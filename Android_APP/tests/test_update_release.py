"""Offline release contract tests; fixture bytes are not claimed to be an APK."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location("create_update_manifest", Path(__file__).resolve().parents[1] / "tools/create_update_manifest.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.apk = Path(self.temp.name) / "fixture.bin"
        self.apk.write_bytes(b"release-contract-fixture")
        self.badging = "package: name='com.giraffeslovebeauty.acmforever' versionCode='27' versionName='0.2.13'\nsdkVersion:'26'\n"
        self.metadata = release.parse_badging(self.badging)
        self.history = {"schemaVersion": 1, "currentVersionCode": 27, "entries": [{"versionName": "0.2.13"}]}

    def generate(self, **changes):
        args = dict(tag="v0.2.13", repository="GiraffesLoveBeauty/ACM-Forever", server="https://github.com", notes="本次更新说明")
        args.update(changes)
        return release.manifest_for(self.apk, self.metadata, self.history, **args)

    def test_exact_file_digest_size_and_client_fields(self):
        manifest = self.generate()
        self.assertEqual(manifest["sha256"], hashlib.sha256(self.apk.read_bytes()).hexdigest())
        self.assertEqual(manifest["sizeBytes"], self.apk.stat().st_size)
        self.assertEqual((manifest["versionCode"], manifest["minSdk"]), (27, 26))
        self.assertEqual(manifest["apkUrl"], "https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/download/v0.2.13/acmforever-0.2.13.apk")

    def test_rejects_wrong_tag_or_stale_history(self):
        with self.assertRaises(ValueError): self.generate(tag="v0.2.12")
        self.history["currentVersionCode"] = 26
        with self.assertRaises(ValueError): self.generate()

    def test_rejects_unsigned_metadata_identity_or_invalid_system_version(self):
        for badging in (self.badging.replace(release.PACKAGE, "other.app"), self.badging.replace("'26'", "'25'"), self.badging.replace("'27'", "'0'"), ""):
            with self.subTest(badging=badging), self.assertRaises(ValueError): release.parse_badging(badging)

    def test_rejects_empty_or_oversized_files(self):
        self.apk.write_bytes(b"")
        with self.assertRaises(ValueError): self.generate()
        with self.apk.open("wb") as stream: stream.truncate(release.MAX_BYTES + 1)
        with self.assertRaises(ValueError): self.generate()

    def test_rejects_unsafe_origin_and_repository(self):
        for origin in ("http://github.com", "https://user:pass@github.com", "https://github.com/path", "https://github.com#part"):
            with self.subTest(origin=origin), self.assertRaises(ValueError): self.generate(server=origin)
        with self.assertRaises(ValueError): self.generate(repository="owner/repo/../other")

    def test_notes_respect_java_utf16_limit(self):
        self.assertEqual(self.generate(notes="  ")["notes"], "本次更新没有附加说明。")
        self.assertEqual(self.generate(notes="😀" * 4000)["notes"], "😀" * 4000)
        with self.assertRaises(ValueError): self.generate(notes="😀" * 4001)

    def test_empty_release_body_uses_current_bundled_notes(self):
        self.history["entries"][0].update(summary="修复更新", changes=["增加校验"], notes=["需确认安装"])
        self.assertEqual(self.generate(notes=" ")["notes"], "修复更新\n增加校验\n需确认安装")

    def test_bundled_history_matches_source_and_rejects_stale_apk(self):
        with ZipFile(self.apk, "w") as archive:
            archive.writestr("assets/releases/history.json", json.dumps(self.history))
        self.assertEqual(release.bundled_history(self.apk, self.history), self.history)
        self.history["currentVersionCode"] = 26
        with self.assertRaises(ValueError): release.bundled_history(self.apk, self.history)

    def test_rejects_missing_or_oversized_bundled_history(self):
        with ZipFile(self.apk, "w") as archive:
            archive.writestr("assets/releases/history.json", " " * 131073)
        with self.assertRaises(ValueError): release.bundled_history(self.apk, self.history)
        with ZipFile(self.apk, "w") as archive:
            archive.writestr("other.json", "{}")
        with self.assertRaises(KeyError): release.bundled_history(self.apk, self.history)

    def test_debug_filename_channel_and_certificate(self):
        manifest = self.generate(channel="debug", certificate="a" * 64)
        self.assertTrue(manifest["apkUrl"].endswith("/acmforever-0.2.13-debug.apk"))
        self.assertEqual(manifest["channel"], "debug")
        self.assertEqual(manifest["signingCertificateSha256"], "a" * 64)
        with self.assertRaises(ValueError): self.generate(channel="beta")

    def test_build_type_must_match_channel(self):
        release.verify_variant(self.badging, "release")
        release.verify_variant(self.badging + "\napplication-debuggable\n", "debug")
        with self.assertRaises(ValueError): release.verify_variant(self.badging, "debug")
        with self.assertRaises(ValueError): release.verify_variant(self.badging + "\napplication-debuggable\n", "release")

    def test_single_signer_must_match_pinned_certificate(self):
        output = "Signer #1 certificate SHA-256 digest: " + "a" * 64 + "\n"
        self.assertEqual(release.signer_digest(output, ":".join(["AA"] * 32)), "a" * 64)
        for text, pin in (("", "a" * 64), (output, "b" * 64), (output, "not a hash"),
                          (output + output.replace("#1", "#2"), "a" * 64)):
            with self.subTest(text=text, pin=pin), self.assertRaises(ValueError): release.signer_digest(text, pin)


if __name__ == "__main__":
    unittest.main()
