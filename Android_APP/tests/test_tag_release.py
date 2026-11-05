"""Offline tests of the tag publication transaction; no GitHub writes or real APKs."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools/tag_release.py"
spec = importlib.util.spec_from_file_location("tag_release", SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class FakeGitHub:
    repository = "GiraffesLoveBeauty/ACM-Forever"

    def __init__(self):
        self.private = False
        self.releases = {}
        self.files = {}
        self.latest_tag = None
        self.operations = []
        self.corrupt = None
        self.fail_upload = False
        self.fail_publish = False

    def repository_info(self):
        return {"private": self.private}

    def latest(self):
        return self.releases.get(self.latest_tag)

    def release(self, tag):
        return self.releases.get(tag)

    def create(self, tag, title, notes):
        self.operations.append("create")
        self.assert_notes = notes.read_text(encoding="utf-8")
        self.releases[tag] = {"tag_name": tag, "draft": True, "assets": []}

    def upload(self, tag, paths):
        self.operations.append("upload")
        if self.fail_upload:
            raise RuntimeError("simulated upload failure")
        self.releases[tag]["assets"] = [{"name": path.name} for path in paths]
        for path in paths:
            self.files[(tag, path.name)] = path.read_bytes()

    def download(self, tag, filename, directory):
        self.operations.append("download:" + filename)
        path = directory / filename
        path.write_bytes(b"corrupt" if filename == self.corrupt else self.files[(tag, filename)])
        return path

    def publish(self, tag):
        self.operations.append("publish")
        if self.fail_publish:
            raise RuntimeError("simulated publish failure")
        self.releases[tag]["draft"] = False
        self.latest_tag = tag


class TagReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.github = FakeGitHub()
        self.tag = "v0.2.14"
        self.filename = "acmforever-0.2.14-debug.apk"
        self.commit = "a" * 40
        self.manifest = {
            "packageName": release.PACKAGE, "versionCode": 28, "versionName": "0.2.14", "minSdk": 26,
            "apkUrl": "https://github.com/" + self.github.repository + "/releases/download/" + self.tag + "/" + self.filename,
            "sha256": hashlib.sha256(b"fixture bytes").hexdigest(), "sizeBytes": len(b"fixture bytes"),
            "channel": "debug", "signingCertificateSha256": "1" * 64, "notes": "真实更新说明",
        }
        (self.directory / self.filename).write_bytes(b"fixture bytes")
        (self.directory / (self.filename + ".sha256")).write_text(self.manifest["sha256"] + "  " + self.filename + "\n", encoding="ascii")
        self.save()

    def save(self):
        (self.directory / "update.json").write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def publish(self):
        return release.publish(self.github, self.tag, self.directory, self.commit)

    def previous(self, code=27, certificate="1" * 64, channel="debug"):
        tag = "v0.2.13"
        value = {**self.manifest, "versionCode": code, "versionName": "0.2.13", "channel": channel,
                 "signingCertificateSha256": certificate}
        self.github.releases[tag] = {"tag_name": tag, "draft": False, "assets": [{"name": "update.json"}]}
        self.github.files[(tag, "update.json")] = json.dumps(value).encode()
        self.github.latest_tag = tag

    def test_tag_version_code_and_bundled_notes_must_agree(self):
        gradle = "versionName '0.2.14'\nversionCode 28"
        history = {"schemaVersion": 1, "currentVersionCode": 28, "entries": [{"versionName": "0.2.14"}]}
        self.assertEqual(release.validate_source(self.tag, gradle, history), ("0.2.14", 28))
        for tag in ("v0.2.13", "0.2.14", "v0.2.14-rc1", "v0.2.14\n"):
            with self.subTest(tag=tag), self.assertRaises(ValueError): release.validate_source(tag, gradle, history)
        for bad in ({**history, "currentVersionCode": 27}, {**history, "entries": []}, {**history, "schemaVersion": 2}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): release.validate_source(self.tag, gradle, bad)
        with self.assertRaises(ValueError): release.validate_source(self.tag, gradle.replace("28", "0"), history)

    def test_draft_upload_then_all_assets_read_back_before_publish(self):
        self.assertIn("Published", self.publish())
        self.assertEqual(self.github.operations, ["create", "upload", "download:" + self.filename,
            "download:" + self.filename + ".sha256", "download:update.json", "publish"])
        self.assertFalse(self.github.releases[self.tag]["draft"])
        self.assertIn(self.commit, self.github.assert_notes)
        self.assertIn(self.manifest["notes"], self.github.assert_notes)

    def test_upload_failure_leaves_draft_and_previous_latest(self):
        self.previous()
        self.github.fail_upload = True
        with self.assertRaises(RuntimeError): self.publish()
        self.assertTrue(self.github.releases[self.tag]["draft"])
        self.assertEqual(self.github.latest_tag, "v0.2.13")
        self.assertNotIn("publish", self.github.operations)

    def test_each_asset_readback_failure_prevents_publication(self):
        for filename in (self.filename, self.filename + ".sha256", "update.json"):
            self.github = FakeGitHub()
            self.github.corrupt = filename
            with self.subTest(filename=filename), self.assertRaises(ValueError): self.publish()
            self.assertTrue(self.github.releases[self.tag]["draft"])
            self.assertNotIn("publish", self.github.operations)

    def test_retry_reuses_draft_after_transient_failure(self):
        self.github.fail_publish = True
        with self.assertRaises(RuntimeError): self.publish()
        self.github.fail_publish = False
        self.publish()
        self.assertEqual(self.github.operations.count("create"), 1)
        self.assertFalse(self.github.releases[self.tag]["draft"])

    def test_private_repository_is_rejected_before_any_mutation(self):
        self.github.private = True
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(self.github.operations, [])

    def test_version_code_must_be_higher_than_published_version(self):
        for code in (28, 29):
            self.github = FakeGitHub()
            self.previous(code=code)
            with self.subTest(code=code), self.assertRaises(ValueError): self.publish()
            self.assertNotIn("create", self.github.operations)
        self.github = FakeGitHub()
        self.previous(code=27)
        self.publish()
        self.assertFalse(self.github.releases[self.tag]["draft"])

    def test_same_channel_cannot_change_certificate(self):
        self.previous(certificate="2" * 64)
        with self.assertRaises(ValueError): self.publish()
        self.assertNotIn("upload", self.github.operations)

    def test_explicit_channel_migration_uses_separate_signing_identity(self):
        self.previous(channel="release", certificate="2" * 64)
        self.publish()
        self.assertFalse(self.github.releases[self.tag]["draft"])

    def test_published_assets_are_immutable_and_identical_rerun_does_not_write(self):
        self.publish()
        self.github.operations.clear()
        self.assertIn("Already published", self.publish())
        self.assertFalse(set(self.github.operations) & {"create", "upload", "publish"})
        self.manifest["notes"] = "different"
        self.save()
        with self.assertRaises(ValueError): self.publish()
        self.assertFalse(set(self.github.operations) & {"create", "upload", "publish"})

    def test_published_rerun_rechecks_apk_and_checksum(self):
        self.publish()
        for name in (self.filename, self.filename + ".sha256"):
            self.github.corrupt = name
            with self.subTest(name=name), self.assertRaises(ValueError): self.publish()

    def test_missing_or_invalid_latest_metadata_blocks_publication(self):
        self.previous()
        self.github.releases["v0.2.13"]["assets"] = []
        with self.assertRaises(ValueError): self.publish()
        self.github.releases["v0.2.13"]["assets"] = [{"name": "update.json"}]
        self.github.files[("v0.2.13", "update.json")] = b"{}"
        with self.assertRaises(ValueError): self.publish()
        self.assertNotIn("upload", self.github.operations)

    def test_latest_is_checked_again_before_publish(self):
        self.previous()
        original = self.github.latest
        calls = []
        def changed_latest():
            calls.append(1)
            if len(calls) == 2:
                self.previous(code=29)
            return original()
        self.github.latest = changed_latest
        with self.assertRaises(ValueError): self.publish()
        self.assertTrue(self.github.releases[self.tag]["draft"])
        self.assertNotIn("publish", self.github.operations)

    def test_local_tampering_is_rejected_before_github_mutation(self):
        for filename in (self.filename, self.filename + ".sha256"):
            path = self.directory / filename
            before = path.read_bytes()
            path.write_bytes(b"tampered")
            with self.subTest(filename=filename), self.assertRaises(ValueError): self.publish()
            path.write_bytes(before)
        self.assertEqual(self.github.operations, [])

    def test_bad_manifest_fields_are_rejected(self):
        for key, value in (("packageName", "other.app"), ("versionCode", True), ("versionCode", 0),
                           ("versionName", "0.2.14-rc1"), ("sha256", "bad"), ("channel", "beta"),
                           ("signingCertificateSha256", ""), ("sizeBytes", 0), ("minSdk", 25),
                           ("notes", ""), ("notes", "😀" * 4001), ("apkUrl", "https://example.com/app.apk")):
            original = copy.deepcopy(self.manifest)
            self.manifest[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.publish()
            self.manifest = original
        self.assertEqual(self.github.operations, [])

    def test_cli_refuses_local_or_non_tag_publication(self):
        environment = dict(os.environ, GITHUB_ACTIONS="false", GITHUB_EVENT_NAME="push")
        result = subprocess.run([sys.executable, str(SCRIPT), "publish", "--tag", self.tag,
            "--directory", str(self.directory), "--repository", self.github.repository,
            "--source-commit", self.commit], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("matching GitHub tag-push Action", result.stderr)

    def test_gh_adapter_only_treats_http404_as_missing(self):
        github = release.GitHub(self.github.repository)
        for message, missing in (("gh: Not Found (HTTP 404)", True), ("HTTP 403", False), ("timeout", False)):
            with self.subTest(message=message), patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", message)):
                if missing: self.assertIsNone(github.latest())
                else:
                    with self.assertRaises(RuntimeError): github.latest()

    def test_gh_adapter_refuses_upload_to_published_release(self):
        github = release.GitHub(self.github.repository)
        with patch.object(github, "release", return_value={"draft": False}), patch.object(github, "run") as run:
            with self.assertRaises(ValueError): github.upload(self.tag, [])
            run.assert_not_called()


class GitHubDraftAdapterTests(unittest.TestCase):
    def test_tag_lookup_404_falls_back_to_authenticated_draft_list(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        draft = {"id": 11, "tag_name": "v0.2.14", "draft": True, "assets": []}
        def api(path, **kwargs):
            if path == "/releases/tags/v0.2.14":
                return None
            if path == "/releases?per_page=100&page=1":
                return [draft]
            raise AssertionError(path)
        with patch.object(github, "api", side_effect=api):
            self.assertEqual(github.release("v0.2.14"), draft)

    def test_draft_list_is_paginated_and_matches_tag_exactly(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        other = {"id": 1, "tag_name": "v0.2.140", "draft": True}
        wanted = {"id": 2, "tag_name": "v0.2.14", "draft": True}
        with patch.object(github, "api", side_effect=[None, [other] * 100, [wanted]]) as api:
            self.assertEqual(github.release("v0.2.14"), wanted)
            self.assertEqual(api.call_args_list[-1].args, ("/releases?per_page=100&page=2",))

    def test_ambiguous_drafts_stop_instead_of_overwriting_one(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        rows = [{"id": n, "tag_name": "v0.2.14", "draft": True} for n in (1, 2)]
        with patch.object(github, "api", side_effect=[None, rows]), self.assertRaises(ValueError):
            github.release("v0.2.14")

    def test_published_tag_lookup_is_preferred_and_missing_tag_returns_none(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        published = {"id": 1, "tag_name": "v0.2.14", "draft": False}
        with patch.object(github, "api", return_value=published) as api:
            self.assertEqual(github.release("v0.2.14"), published)
            self.assertEqual(api.call_count, 1)
        with patch.object(github, "api", side_effect=[None, []]):
            self.assertIsNone(github.release("v0.2.14"))

    def test_upload_addresses_draft_id_and_replaces_only_matching_attachment(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        draft = {"id": 11, "draft": True, "assets": [{"id": 22, "name": "update.json"}]}
        path = Path("update.json")
        with patch.object(github, "release", return_value=draft), patch.object(github, "run") as run:
            github.upload("v0.2.14", [path])
            self.assertEqual(run.call_args_list[0].args, ("api", "--method", "DELETE",
                "repos/" + github.repository + "/releases/assets/22"))
            self.assertEqual(run.call_args_list[1].args, ("api", "--method", "POST",
                "https://uploads.github.com/repos/" + github.repository + "/releases/11/assets?name=update.json",
                "--header", "Content-Type: application/octet-stream", "--input", str(path)))

    def test_binary_download_failure_removes_partial_output(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        draft = {"id": 11, "draft": True, "assets": [{"id": 22, "name": "update.json"}]}
        def failed(args, **kwargs):
            kwargs["stdout"].write(b"partial")
            return subprocess.CompletedProcess(args, 1)
        with tempfile.TemporaryDirectory() as temp, patch.object(github, "release", return_value=draft), \
                patch.object(release.subprocess, "run", side_effect=failed):
            target = Path(temp) / "update.json"
            with self.assertRaises(RuntimeError):
                github.download("v0.2.14", target.name, target.parent)
            self.assertFalse(target.exists())

    def test_publish_addresses_id_and_refuses_a_published_release(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        published = {"tag_name": "v0.2.14", "draft": False}
        with patch.object(github, "release", return_value={"id": 11, "draft": True}), \
                patch.object(github, "api", return_value=published) as api:
            github.publish("v0.2.14")
            self.assertEqual(api.call_args.args, ("/releases/11", "--method", "PATCH",
                "--field", "draft=false", "--field", "prerelease=false", "--raw-field", "make_latest=true"))
        with patch.object(github, "release", return_value=published), patch.object(github, "api") as api:
            with self.assertRaises(ValueError):
                github.publish("v0.2.14")
            api.assert_not_called()

    def test_complete_real_adapter_handles_hidden_draft_and_immutable_rerun(self):
        github = release.GitHub("GiraffesLoveBeauty/ACM-Forever")
        tag, filename, data = "v0.2.15", "acmforever-0.2.15-debug.apk", b"synthetic fixture"
        manifest = {"packageName": release.PACKAGE, "versionName": "0.2.15", "versionCode": 29,
            "minSdk": 26, "channel": "debug", "signingCertificateSha256": "1" * 64,
            "notes": "Synthetic test notes", "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data),
            "apkUrl": "https://github.com/" + github.repository + "/releases/download/" + tag + "/" + filename}
        state = {"release": None, "assets": {}, "writes": [], "downloads": []}
        prefix = "repos/" + github.repository
        def process(args, **kwargs):
            if args[1:3] == ["release", "create"]:
                state["release"] = {"id": 11, "tag_name": tag, "draft": True, "assets": []}
                state["writes"].append("create")
                return subprocess.CompletedProcess(args, 0, "", "")
            self.assertEqual(args[1], "api")
            endpoint = next(a for a in args if a.startswith(("repos/", "https://uploads.github.com/")))
            method = args[args.index("--method") + 1] if "--method" in args else "GET"
            current = state["release"]
            if endpoint == prefix:
                value = {"private": False}
            elif endpoint == prefix + "/releases/latest":
                value = current if current is not None and not current["draft"] else None
            elif endpoint == prefix + "/releases/tags/" + tag:
                value = current if current is not None and not current["draft"] else None
            elif endpoint == prefix + "/releases?per_page=100&page=1":
                value = [current] if current is not None else []
            elif endpoint.startswith("https://uploads.github.com/" + prefix + "/releases/11/assets?name="):
                self.assertEqual(method, "POST")
                path = Path(args[args.index("--input") + 1])
                asset_id = len(state["assets"]) + 1
                state["assets"][asset_id] = path.read_bytes()
                value = {"id": asset_id, "name": path.name}
                current["assets"].append(value)
                state["writes"].append("upload:" + path.name)
            elif endpoint.startswith(prefix + "/releases/assets/"):
                asset_id = int(endpoint.rsplit("/", 1)[1])
                self.assertEqual(args[-2:], ["--header", "Accept: application/octet-stream"])
                kwargs["stdout"].write(state["assets"][asset_id])
                state["downloads"].append(asset_id)
                return subprocess.CompletedProcess(args, 0)
            elif endpoint == prefix + "/releases/11":
                self.assertEqual(method, "PATCH")
                self.assertEqual(len(state["downloads"]), 3)
                current["draft"] = False
                state["writes"].append("publish")
                value = current
            else:
                raise AssertionError(args)
            return subprocess.CompletedProcess(args, 0 if value is not None else 1,
                json.dumps(value) if value is not None else "", "" if value is not None else "gh: Not Found (HTTP 404)")
        with tempfile.TemporaryDirectory() as temp, patch.object(release.subprocess, "run", side_effect=process):
            directory = Path(temp)
            (directory / filename).write_bytes(data)
            (directory / (filename + ".sha256")).write_text(manifest["sha256"] + "  " + filename, encoding="ascii")
            (directory / "update.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertIn("Published", release.publish(github, tag, directory, "a" * 40))
            self.assertEqual(state["writes"], ["create", "upload:" + filename,
                "upload:" + filename + ".sha256", "upload:update.json", "publish"])
            before = list(state["writes"])
            self.assertIn("Already published", release.publish(github, tag, directory, "a" * 40))
            self.assertEqual(state["writes"], before)


if __name__ == "__main__":
    unittest.main()
