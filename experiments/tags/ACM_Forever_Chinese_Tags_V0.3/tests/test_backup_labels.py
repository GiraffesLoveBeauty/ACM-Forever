"""Offline backup security/recovery tests; all writes target disposable mock data."""
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup_labels
from annotation_api.adapter import digest
from annotation_api.storage import atomic_json
from label_pipeline import TAXONOMY
from problem_processing import backup as b
from problem_processing.adapter import normalize
from problem_processing.repository import Repository
from problem_processing.translation import (MockTranslationClient, language_plan, translate,
                                          translation_fingerprint)


def raw(number=0, text="You are given two integers. Print their sum."):
    return {"platform": "atcoder", "problem_key": f"atcoder:offline:offline_{number}",
            "title": "Mock Addition", "statement_markdown": text, "statement_status": "ok"}


def annotation(p, tags=None):
    value = normalize(p)
    return {"problem_key": value["problem_key"], "platform": "atcoder", "title": p["title"],
            "content_hash": value["content_hash"], "taxonomy_version": TAXONOMY["version"],
            "specific_tag_ids": ["enumeration"] if tags is None else tags, "provisional_tag_ids": [],
            "api_call_status": "success", "human_review_status": "pending_review", "model": "offline-mock"}


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "labels"
        self.repo = Repository(self.root)
        self.seed()
        self.backups = self.base / "backups"
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("禁止真实网络"))
        guard.start(); self.addCleanup(guard.stop)
        api = patch("annotation_api.client.APIClient.call", side_effect=AssertionError("禁止真实 API"))
        api.start(); self.addCleanup(api.stop)

    def seed(self, p=None, tags=None):
        p = p or raw()
        return self.repo.import_records([p], [annotation(p, tags)])

    def backup(self, **kwargs):
        return Path(b.create_backup(self.root, self.backups, **kwargs)["backup"])

    def restore(self, backup, name="restore", **kwargs):
        result = b.restore_backup(backup, self.base / name, active_root=self.root, **kwargs)
        return Repository(result["restored_data_root"])

    def rewrite_manifest_hash(self, folder, rel):
        path = folder / "manifest.json"
        manifest = b.parse(path.read_bytes())
        data = (folder / rel).read_bytes()
        for entry in manifest["files"]:
            if entry["path"] == rel:
                manifest["total_bytes"] += len(data) - entry["bytes"]
                entry.update(sha256=b.sha256(data), bytes=len(data))
        path.write_bytes(b.json_bytes(manifest))

    def test_complete_backup_includes_versions_and_empty_directories(self):
        folder = self.backup()
        report = b.verify_backup(folder)
        self.assertTrue(report["verified"])
        self.assertEqual(report["manifest"]["counts"]["problems"], 1)
        self.assertTrue((folder / "payload/manual").is_dir())
        self.assertTrue((folder / "payload/translations").is_dir())
        for name in b.VERSION_FILES:
            self.assertTrue((folder / "versions" / name).is_file())

    def test_repeated_backups_are_distinct_without_overwrite(self):
        first = self.backup(); initial = b.inventory(first)
        second = self.backup()
        self.assertNotEqual(first, second)
        self.assertEqual(initial, b.inventory(first))
        self.assertEqual(len(b.list_backups(self.backups)), 2)

    def test_source_all_bytes_and_directories_remain_unchanged(self):
        before = b.inventory(self.root)
        folder = self.backup(); self.restore(folder)
        self.assertEqual(before, b.inventory(self.root))

    def test_restore_reloads_effective_tags_and_all_identities(self):
        self.seed(raw(1), [])
        before = self.repo.metadata_many()
        restored = self.restore(self.backup())
        self.assertEqual(before, restored.metadata_many())
        keys = list(self.repo.snapshot()[0])
        self.assertEqual(self.repo.manager().get_effective_tags_many(keys), restored.manager().get_effective_tags_many(keys))

    def test_corrupt_file_rejected_before_target_creation(self):
        folder = self.backup()
        (folder / "payload/catalog/current.json").write_bytes(b"{}"); target = self.base / "bad"
        with self.assertRaises(ValueError): b.restore_backup(folder, target, active_root=self.root)
        self.assertFalse(target.exists())

    def test_missing_file_detected(self):
        folder = self.backup()
        (folder / "payload/catalog/current.json").unlink()
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_extra_file_detected(self):
        folder = self.backup(); (folder / "unexpected.txt").write_text("mock")
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_missing_manifest_detected(self):
        folder = self.backup(); (folder / "manifest.json").unlink()
        with self.assertRaises(ValueError): b.verify_backup(folder)
        self.assertFalse(b.list_backups(self.backups)[0]["verified"])

    def test_file_size_or_count_mismatch_detected(self):
        folder = self.backup(); path = folder / "manifest.json"; original = b.parse(path.read_bytes())
        for field in ("file_count", "total_bytes"):
            bad = dict(original); bad[field] += 1; path.write_bytes(b.json_bytes(bad))
            with self.assertRaises(ValueError): b.verify_backup(folder)
        bad = b.parse(b.json_bytes(original)); bad["files"][0]["bytes"] += 1
        path.write_bytes(b.json_bytes(bad))
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_missing_source_current_pointer_rejected(self):
        self.repo.pointer.unlink()
        with self.assertRaises(ValueError): self.backup()
        self.assertFalse(self.backups.exists())

    def test_missing_source_directory_rejected(self):
        (self.root / "manual").rmdir()
        with self.assertRaises(ValueError): self.backup()

    def test_incomplete_historical_generation_rejected(self):
        (self.repo.current() / "auto_tags.jsonl").unlink()
        with self.assertRaises((ValueError, FileNotFoundError)): self.backup()

    def test_manual_event_history_and_tombstones_restored(self):
        key = raw()["problem_key"]; manager = self.repo.manager()
        manager.change(key, "remove", ["enumeration"], actor="mock-admin", reason="模拟纠错")
        manager.change(key, "add", ["prefix_sum"])
        before = manager.journal.path.read_bytes()
        self.seed(tags=["enumeration", "simulation"])
        restored = self.restore(self.backup())
        self.assertEqual(before, restored.manager().journal.path.read_bytes())
        self.assertEqual(restored.manager().get_effective_tags(key)["specific_tag_ids"], ["simulation", "prefix_sum"])

    def test_undo_reset_and_full_history_restored(self):
        key = raw()["problem_key"]; manager = self.repo.manager()
        for operation, tags in (("remove", ["enumeration"]), ("undo", []), ("add", ["simulation"]), ("reset", [])):
            manager.change(key, operation, tags)
        restored = self.restore(self.backup())
        events, states = restored.manager().journal.read()
        self.assertEqual(len(events), 4)
        self.assertEqual(restored.manager().get_effective_tags(key)["review_status"], "auto")

    def test_manual_history_chain_corruption_rejected(self):
        manager = self.repo.manager(); manager.change(raw()["problem_key"], "add", ["simulation"])
        events, _ = manager.journal.read(); events[0]["previous_event_id"] = "wrong"
        manager.journal.write(events)
        with self.assertRaises(ValueError): self.backup()

    def test_all_catalog_versions_restored(self):
        first = self.repo.current().name; self.seed(tags=["simulation"]); second = self.repo.current().name
        restored = self.restore(self.backup())
        self.assertEqual(restored.current().name, second)
        self.assertEqual({p.name for p in (restored.root / "catalog/generations").iterdir()}, {first, second})

    def test_select_historical_generation_preserves_manual_history(self):
        first = self.repo.current().name
        self.repo.manager().change(raw()["problem_key"], "remove", ["enumeration"])
        self.seed(raw(text="You are given three integers. Print their sum."), ["simulation"])
        restored = self.restore(self.backup(), generation=first)
        self.assertEqual(restored.current().name, first)
        self.assertEqual(len(restored.manager().journal.read()[0]), 1)
        self.assertEqual(restored.manager().get_effective_tags(raw()["problem_key"])["specific_tag_ids"], [])

    def test_invalid_selected_generation_rejected_before_writing(self):
        folder = self.backup(); target = self.base / "bad"
        for value in ("../../escape", "0" * 64):
            with self.assertRaises(ValueError): b.restore_backup(folder, target, generation=value, active_root=self.root)
        self.assertFalse(target.exists())

    def test_translation_history_index_and_result_restored(self):
        row = translate(normalize(raw()), root=self.root, mock=True)
        fp = row["request_fingerprint"]
        path = self.root / "translations/history" / (fp + ".json")
        value = b.parse(path.read_bytes()); value["translation_status"] = "auto"
        atomic_json(path, value)  # Synthetic usable translation, never a real API.
        atomic_json(self.root / "translations/current.json", {raw()["problem_key"]: fp})
        restored = self.restore(self.backup())
        self.assertEqual(path.read_bytes(), (restored.root / "translations/history" / (fp + ".json")).read_bytes())
        self.assertEqual(self.repo.metadata_many(), restored.metadata_many())
        self.assertEqual(restored.metadata_many()[0]["translated_title"], "模拟题名")

    def test_translation_unknown_delivery_remains_blocked_after_restore(self):
        problem = normalize(raw()); plan = language_plan(problem)
        fp = translation_fingerprint(problem, plan, {"provider": "mock", "model": "mock-translation"})
        atomic_json(self.root / "translations/requests" / (fp + ".json"), {"state": "unknown_delivery", "error": "unknown_delivery"})
        restored = self.restore(self.backup()); client = MockTranslationClient()
        result = translate(problem, root=restored.root, mock=True, client=client)
        self.assertEqual(result["api_calls"], 0); self.assertEqual(client.calls, 0)
        self.assertEqual(result["error"], "unknown_delivery")

    def test_successful_translation_missing_history_rejected(self):
        atomic_json(self.root / "translations/requests" / ("1" * 64 + ".json"), {"state": "success"})
        with self.assertRaises(ValueError): self.backup()

    def test_translation_wrong_problem_pointer_rejected(self):
        atomic_json(self.root / "translations/current.json", {raw()["problem_key"]: "1" * 64})
        with self.assertRaises(ValueError): self.backup()

    def test_request_field_allowlist_drops_credentials_and_raw_responses(self):
        root = self.base / "requests"
        original = {"state": "success", "authorization": "Bearer MOCK-CREDENTIAL", "api_key": "mock-secret",
                    "response": {"content": "mock-secret", "headers": {"cookie": "mock-secret"},
                                 "usage": {"prompt_tokens": 5, "total_tokens": 8, "secret": "mock-secret"}},
                    "attempts": [{"status": "received", "usage": {"total_tokens": 8}, "headers": "mock-secret"}],
                    "merged": {"api_key": "mock-secret"}}
        request = root / ("1" * 64) / ("2" * 64 + ".json"); atomic_json(request, original)
        before = b.inventory(root); folder = self.backup(request_root=root)
        data = (folder / "request_states" / request.relative_to(root)).read_bytes()
        self.assertNotIn(b"mock-secret", data); self.assertNotIn(b"MOCK-CREDENTIAL", data)
        self.assertNotIn(b"content", data); self.assertNotIn(b"headers", data)
        self.assertEqual(b.parse(data)["response_statistics"]["usage"]["total_tokens"], 8)
        self.assertEqual(before, b.inventory(root)); self.restore(folder)

    def test_translation_received_record_sanitized_without_replay(self):
        problem = normalize(raw()); fp = translation_fingerprint(problem, language_plan(problem), {"provider": "mock", "model": "mock-translation"})
        atomic_json(self.root / "translations/requests" / (fp + ".json"),
                    {"state": "received", "response": {"content": "private mocked text", "usage": {"total_tokens": 9}}})
        restored = self.restore(self.backup())
        self.assertNotIn("private mocked text", (restored.root / "translations/requests" / (fp + ".json")).read_text())
        result = translate(problem, root=restored.root, mock=True)
        self.assertEqual(result["api_calls"], 0)

    def test_untrusted_request_error_text_is_not_backed_up(self):
        value = b.request_state({"state": "failed", "error": "Bearer MOCK-SECRET", "usage": {"total_tokens": 1}})
        self.assertEqual(value["error"], "redacted_error")
        self.assertEqual(b.request_state(value), value)

    def test_sensitive_fields_in_persistent_records_fail_closed(self):
        path = next((self.root / "annotations").glob("*.jsonl"))
        record = b.rows(path.read_bytes())[0]; record["api_key"] = "mock-secret"
        path.write_bytes(b.json_bytes(record))
        with self.assertRaises(ValueError) as raised: self.backup()
        self.assertNotIn("mock-secret", str(raised.exception))

    def test_unreviewed_env_or_unknown_files_never_copied(self):
        (self.root / ".env").write_text("OPENAI_API_KEY=mock-not-real")
        with self.assertRaises(ValueError): self.backup()
        self.assertFalse(self.backups.exists())

    def test_runtime_locks_not_restored(self):
        folder = self.backup()
        self.assertIn("catalog/writer.jsonl.lock", b.verify_backup(folder)["manifest"]["excluded_runtime_files"])
        restored = self.restore(folder)
        self.assertFalse((restored.root / "catalog/writer.jsonl.lock").exists())

    def test_existing_destination_refuses_to_overwrite(self):
        folder = self.backup(); target = self.base / "exists"; target.mkdir()
        (target / "sentinel").write_text("keep")
        with self.assertRaises(ValueError): b.restore_backup(folder, target, active_root=self.root)
        self.assertEqual((target / "sentinel").read_text(), "keep")

    def test_active_directory_or_nested_target_rejected(self):
        folder = self.backup()
        for path in (self.root, self.root / "restore", folder / "restore", self.base):
            with self.assertRaises(ValueError): b.restore_backup(folder, path, active_root=self.root)

    def test_backup_destination_inside_source_or_repository_rejected(self):
        for path in (self.root / "backups", b.PROJECT_ROOT / "backups"):
            with self.assertRaises(ValueError): b.create_backup(self.root, path)

    def test_path_traversal_absolute_drive_ads_and_device_names_rejected(self):
        for value in ("../x", "/tmp/x", "C:/x", "payload/../x", "payload\\x", "payload//x", "payload/a:stream", "payload/CON.json", "payload/a. ", "payload/.", "payload/x\x00"):
            with self.subTest(path=value), self.assertRaises(ValueError): b.safe_relative(value)

    def test_malicious_manifest_path_rejected(self):
        folder = self.backup(); path = folder / "manifest.json"; manifest = b.parse(path.read_bytes())
        manifest["files"][0]["path"] = "../../escape.json"
        path.write_bytes(b.json_bytes(manifest))
        with self.assertRaises(ValueError): self.restore(folder)
        self.assertFalse((self.base / "restore").exists())

    def test_case_alias_and_duplicate_manifest_paths_rejected(self):
        folder = self.backup(); path = folder / "manifest.json"; manifest = b.parse(path.read_bytes())
        duplicate = dict(manifest["files"][0]); duplicate["path"] = duplicate["path"].upper()
        manifest["files"].append(duplicate); path.write_bytes(b.json_bytes(manifest))
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_symlink_and_windows_junction_rejected(self):
        path = self.root / "manual"; original = Path.lstat
        for info in (SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0),
                     SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=1024)):
            def mocked(p, *args, **kwargs):
                return info if p == path else original(p, *args, **kwargs)
            with patch.object(Path, "lstat", mocked), self.assertRaises(ValueError): b.inventory(self.root)

    def test_linked_restore_ancestor_rejected(self):
        original = Path.lstat; path = self.base
        def mocked(p, *a, **kw):
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=1024) if p == path else original(p, *a, **kw)
        with patch.object(Path, "lstat", mocked), self.assertRaises(ValueError): b.restore_backup(self.backup(), self.base / "restore", active_root=self.root)

    def test_changed_source_during_capture_rejected(self):
        original = b.inventory; calls = 0
        def changing(root):
            nonlocal calls
            if Path(root) == self.root:
                calls += 1
                if calls == 2:
                    (self.root / "catalog/writer.jsonl.lock").write_bytes(b"changed mock")
            return original(root)
        with patch.object(b, "inventory", changing), self.assertRaises(ValueError): self.backup()
        self.assertFalse(self.backups.exists())

    def test_changed_backup_during_verification_rejected(self):
        folder = self.backup(); original = b.inventory; calls = 0
        def changing(root):
            nonlocal calls
            if Path(root) == folder:
                calls += 1
                if calls == 2: (folder / "payload/catalog/current.json").write_text("{}")
            return original(root)
        with patch.object(b, "inventory", changing), self.assertRaises(ValueError): self.restore(folder)
        self.assertFalse((self.base / "restore").exists())

    def test_tampered_pointer_with_rehashed_file_still_rejected(self):
        folder = self.backup(); rel = "payload/catalog/current.json"
        (folder / rel).write_bytes(b.json_bytes({"generation_id": "0" * 64}))
        self.rewrite_manifest_hash(folder, rel)
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_tampered_version_evidence_rejected_even_if_rehashed(self):
        folder = self.backup(); rel = "versions/tag_taxonomy_v0.3.json"
        (folder / rel).write_text("{}", encoding="utf-8"); self.rewrite_manifest_hash(folder, rel)
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_manifest_unknown_version_and_duplicate_json_keys_rejected(self):
        folder = self.backup(); path = folder / "manifest.json"; manifest = b.parse(path.read_bytes())
        manifest["backup_version"] = 999; path.write_bytes(b.json_bytes(manifest))
        with self.assertRaises(ValueError): b.verify_backup(folder)
        with self.assertRaises(ValueError): b.parse(b'{"backup_version":1,"backup_version":1}')

    def test_invalid_request_state_and_nested_layout_rejected(self):
        root = self.base / "requests"; request = root / ("1" * 64) / ("2" * 64 + ".json")
        atomic_json(request, {"state": "bad"})
        with self.assertRaises(ValueError): self.backup(request_root=root)
        with self.assertRaises(ValueError): b.request_state({"state": "sent", "elapsed_seconds": float("nan")})

    def test_custom_backup_root_environment_and_list_empty(self):
        with patch.dict(os.environ, {"TAG_BACKUP_ROOT": str(self.backups)}):
            self.assertEqual(b.backup_root(), self.backups)
            self.assertEqual(b.list_backups(), [])

    def test_default_environment_source_checked_before_repository_resolution(self):
        checked = b.checked_path
        with patch.dict(os.environ, {"TAG_DATA_ROOT": str(self.root)}), patch.object(b, "checked_path", wraps=checked) as guard:
            folder = Path(b.create_backup(destination=self.backups)["backup"])
            self.assertEqual(guard.call_args_list[0].args[0], self.root)
            self.assertTrue(b.verify_backup(folder)["verified"])

    def test_relative_source_is_project_relative(self):
        # Check path interpretation without writing into the actual project.
        with patch.object(b, "PROJECT_ROOT", self.base), patch.object(b, "checked_path", side_effect=ValueError("mock path guard")) as guard:
            with self.assertRaises(ValueError): b.create_backup("labels", self.backups)
            guard.assert_called_once_with(self.root)

    def test_old_generation_keeps_newer_translation_in_history(self):
        first = self.repo.current().name
        self.seed(raw(1))
        row = translate(normalize(raw(1)), root=self.root, mock=True)
        fp = row["request_fingerprint"]; path = self.root / "translations/history" / (fp + ".json")
        value = b.parse(path.read_bytes()); value["translation_status"] = "auto"; atomic_json(path, value)
        atomic_json(self.root / "translations/current.json", {raw(1)["problem_key"]: fp})
        restored = self.restore(self.backup(), generation=first)
        self.assertEqual(len(restored.snapshot()[0]), 1)
        self.assertTrue((restored.root / "translations/history" / (fp + ".json")).exists())

    def test_stale_manual_content_remains_needs_review(self):
        key = raw()["problem_key"]; self.repo.manager().change(key, "remove", ["enumeration"])
        self.seed(raw(text="You are given ten integers. Print their sum."))
        restored = self.restore(self.backup())
        view = restored.manager().get_effective_tags(key)
        self.assertEqual(view["review_status"], "needs_review")
        self.assertEqual(view["specific_tag_ids"], [])
        self.assertIn("content_changed_since_manual_edit", view["needs_review_reasons"])

    def test_rehashed_translation_raw_response_violates_allowlist(self):
        fp = "1" * 64
        atomic_json(self.root / "translations/requests" / (fp + ".json"), {"state": "received"})
        folder = self.backup(); rel = f"payload/translations/requests/{fp}.json"
        (folder / rel).write_bytes(b.json_bytes({"state": "received", "response": {"content": "unreviewed"}}))
        self.rewrite_manifest_hash(folder, rel)
        with self.assertRaises(ValueError): b.verify_backup(folder)

    def test_interrupted_backup_is_incomplete_and_source_intact(self):
        before = b.inventory(self.root)
        with patch.object(b, "write_new", side_effect=OSError("mock disk failure")), self.assertRaises(OSError):
            self.backup()
        self.assertEqual(before, b.inventory(self.root))
        result = b.list_backups(self.backups)
        self.assertEqual(len(result), 1); self.assertFalse(result[0]["verified"])

    def test_cli_create_summary_verify_list_and_restore(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(backup_labels.main(["create", "--data-root", str(self.root), "--backup-root", str(self.backups), "--no-annotation-requests"]), 0)
        folder = json.loads(out.getvalue())["backup"]
        with redirect_stdout(io.StringIO()):
            for cmd in (["summary", folder], ["verify", folder], ["list", "--backup-root", str(self.backups)],
                        ["restore", folder, "--destination", str(self.base / "cli-restore"), "--active-root", str(self.root)]):
                self.assertEqual(backup_labels.main(cmd), 0)
            self.assertEqual(backup_labels.main(["restore", folder, "--destination", str(self.root)]), 2)


if __name__ == "__main__":
    unittest.main()
