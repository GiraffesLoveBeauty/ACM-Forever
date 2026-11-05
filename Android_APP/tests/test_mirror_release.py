"""Exercise mirror filesystem transactions and publication recovery without production access."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import test_tag_release as fixtures

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("mirror_release", TOOLS / "mirror_release.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)
ORIGIN = "https://downloads.example.org"


class MirrorReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TagReleaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "releases"
        self.f = self.fixture
        self.f.manifest["apkFallbackUrls"] = [self.f.manifest["apkUrl"]]
        self.f.manifest["apkUrl"] = self.f.manifest["apkUrl"].replace("https://github.com", ORIGIN)
        self.f.save()

    def archive(self, extra=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as output:
            for item in self.f.directory.iterdir():
                output.add(item, arcname=item.name, recursive=False)
            if extra:
                output.addfile(extra, io.BytesIO(b"x" * extra.size) if extra.isfile() else None)
        stream.seek(0)
        return stream

    def stage(self):
        return mirror.receive(self.root, self.f.tag, self.archive())

    def latest(self):
        return json.loads((self.root / "latest/update.json").read_text(encoding="utf-8"))

    def test_stage_is_immutable_and_does_not_change_latest(self):
        self.stage()
        self.assertFalse((self.root / "latest").exists())
        self.stage()
        self.assertFalse(list(self.root.glob(".stage-*")))
        self.f.manifest["notes"] = "different content"
        self.f.save()
        with self.assertRaises(ValueError):
            self.stage()

    def test_promote_is_idempotent_and_exact(self):
        self.stage()
        mirror.promote(self.root, self.f.tag)
        self.assertEqual(self.latest(), self.f.manifest)
        mirror.promote(self.root, self.f.tag)
        self.assertFalse(list((self.root / "latest").glob(".update-*")))

    def test_latest_cannot_downgrade_change_channel_or_certificate(self):
        self.stage()
        (self.root / "latest").mkdir()
        target = self.root / "latest/update.json"
        for change in ({"versionCode": 100}, {"versionCode": 27, "channel": "release"},
                       {"versionCode": 27, "signingCertificateSha256": "0" * 64},
                       {"notes": "same code changed"}):
            value = {**self.f.manifest, **change}
            target.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                mirror.promote(self.root, self.f.tag)
            self.assertEqual(self.latest(), value)

    def test_failed_atomic_replace_preserves_previous_latest(self):
        self.stage()
        (self.root / "latest").mkdir()
        old = {**self.f.manifest, "versionCode": 27}
        (self.root / "latest/update.json").write_text(json.dumps(old))
        with patch.object(mirror.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                mirror.promote(self.root, self.f.tag)
        self.assertEqual(self.latest(), old)
        self.assertFalse(list((self.root / "latest").glob(".update-*")))

    def test_rejects_archive_paths_links_duplicates_and_extra_files(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("unexpected.txt", tarfile.REGTYPE), ("update.json", tarfile.REGTYPE),
                           ("update.json", tarfile.SYMTYPE), ("update.json", tarfile.LNKTYPE)):
            entry = tarfile.TarInfo(name)
            entry.type, entry.size, entry.linkname = kind, 1 if kind == tarfile.REGTYPE else 0, "../outside"
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                mirror.receive(self.root, self.f.tag, self.archive(entry))
        self.assertFalse((Path(self.temp.name) / "escape").exists())
        self.assertFalse(list(self.root.glob(".stage-*")))

    def test_rejects_tampered_hash_and_missing_assets(self):
        (self.f.directory / self.f.filename).write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            self.stage()
        (self.f.directory / self.f.filename).unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.stage()
        self.assertFalse((self.root / "download" / self.f.tag).exists())

    def test_rejects_invalid_tag_and_escape_child(self):
        for tag in ("../main", "v0.2.14/../escape", "v0.2.14\n"):
            with self.assertRaises(ValueError):
                mirror.receive(self.root, tag, self.archive())
        root = mirror.checked_root(self.root)
        with self.assertRaises(ValueError):
            mirror.child(root, "..", "outside")

    def transport(self):
        testcase = self

        class Transport:
            fail_stage = False
            fail_promote = False

            def stage(self, tag, directory, manifest):
                testcase.f.github.operations.append("mirror:stage")
                if self.fail_stage:
                    raise RuntimeError("simulated mirror outage")
                testcase.stage()

            def promote(self, tag, directory, manifest):
                testcase.f.github.operations.append("mirror:promote")
                if self.fail_promote:
                    raise RuntimeError("simulated promotion outage")
                mirror.promote(testcase.root, tag)

        return Transport()

    def publish(self, transport):
        return fixtures.release.publish(self.f.github, self.f.tag, self.f.directory, self.f.commit, ORIGIN, transport)

    def test_requires_mirror_and_exact_github_backup(self):
        with self.assertRaises(ValueError):
            self.publish(None)
        self.f.manifest["apkFallbackUrls"] = ["https://wrong.example.org/app.apk"]
        self.f.save()
        with self.assertRaises(ValueError):
            self.publish(self.transport())
        self.assertEqual(self.f.github.operations, [])

    def test_order_and_mirror_stage_failure_leave_draft(self):
        transport = self.transport()
        transport.fail_stage = True
        with self.assertRaises(RuntimeError):
            self.publish(transport)
        self.assertTrue(self.f.github.releases[self.f.tag]["draft"])
        self.assertNotIn("publish", self.f.github.operations)
        transport.fail_stage = False
        self.publish(transport)
        operations = self.f.github.operations
        self.assertLess(operations.index("mirror:stage"), operations.index("publish"))
        self.assertLess(operations.index("publish"), operations.index("mirror:promote"))
        self.assertEqual(self.latest(), self.f.manifest)

    def test_promotion_failure_recovers_after_github_publication(self):
        transport = self.transport()
        transport.fail_promote = True
        with self.assertRaises(RuntimeError):
            self.publish(transport)
        self.assertFalse(self.f.github.releases[self.f.tag]["draft"])
        self.assertFalse((self.root / "latest").exists())
        transport.fail_promote = False
        self.publish(transport)
        self.assertEqual(self.latest(), self.f.manifest)
        self.assertEqual(self.f.github.operations.count("publish"), 1)

    def test_historical_rerun_cannot_rewind_mirror(self):
        transport = self.transport()
        self.publish(transport)
        self.f.github.latest_tag = "v0.3.0"
        self.f.github.releases["v0.3.0"] = {"tag_name": "v0.3.0"}
        count = self.f.github.operations.count("mirror:promote")
        with self.assertRaises(ValueError):
            self.publish(transport)
        self.assertEqual(self.f.github.operations.count("mirror:promote"), count)

    def test_newer_release_appearing_during_stage_prevents_publish(self):
        transport = self.transport()
        stage = transport.stage

        def race(*args):
            stage(*args)
            self.f.previous(code=100)

        transport.stage = race
        with self.assertRaises(ValueError):
            self.publish(transport)
        self.assertNotIn("publish", self.f.github.operations)

    def test_ssh_configuration_rejects_unsafe_roots_hosts_and_users(self):
        key, hosts = Path(self.temp.name) / "key", Path(self.temp.name) / "hosts"
        key.write_text("fixture key")
        hosts.write_text("fixture known hosts")
        env = {"ANDROID_MIRROR_HOST": "downloads.example.org", "ANDROID_MIRROR_USER": "publisher",
               "ANDROID_MIRROR_ROOT": "/srv/acmforever-releases", "ANDROID_MIRROR_PORT": "22",
               "ANDROID_MIRROR_KEY_FILE": str(key), "ANDROID_MIRROR_HOSTS_FILE": str(hosts)}
        with patch.dict(os.environ, env):
            mirror.SSHMirror(self.f.github.repository, ORIGIN)
            for field, value in (("ROOT", "/"), ("ROOT", "/root/acm-forever-feat/releases"),
                                 ("ROOT", "/srv"), ("HOST", "-oProxyCommand=bad"),
                                 ("USER", "user;bad"), ("PORT", "99999")):
                with patch.dict(os.environ, {"ANDROID_MIRROR_" + field: value}), self.assertRaises(ValueError):
                    mirror.SSHMirror(self.f.github.repository, ORIGIN)


if __name__ == "__main__":
    unittest.main()
