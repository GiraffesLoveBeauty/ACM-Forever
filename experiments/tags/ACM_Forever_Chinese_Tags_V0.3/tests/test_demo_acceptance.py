"""Offline acceptance page checks: synthetic repositories, no production data or API."""
import io
import json
import hashlib
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from api_helpers import sample
import demo_acceptance as demo
from label_pipeline import TAXONOMY
from problem_processing.adapter import normalize
from problem_processing.backup import create_backup, restore_backup
from problem_processing.repository import Repository


class AcceptanceDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-demo-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "labels"
        self.repo = Repository(self.root)
        self.source = {**sample(), "title": "模拟题目", "statement_markdown": "PRIVATE_BODY_NEVER_EXPORT"}
        self.annotation = {**normalize(self.source)["rule_base"], "specific_tag_ids": ["prefix_sum"],
                           "provisional_tag_ids": [], "api_call_status": "success", "model": "offline-model",
                           "ai_annotation": {"reason": "模拟静态区间求和依据"}}
        self.repo.import_records([self.source], [self.annotation])
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Real HTTP forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def page_data(self):
        return {"live": demo.load_live(self.root), "tests": None,
                "git": {"branch": "offline", "commit": "demo-commit", "dirty": True},
                "generated_at": "2026-10-20T00:00:00+00:00", "manual": demo.manual_demo(),
                "translations": demo.translation_demo(), "backups": {"reports": [], "missing": True}}

    def backup_with_audit(self):
        folder = Path(create_backup(self.root, self.base / "backups")["backup"])
        restored = restore_backup(folder, self.base / "isolated", active_root=self.root)
        audit = {"backup": str(folder), "restored_data_root": restored["restored_data_root"],
                 "manifest_sha256": hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest(),
                 "created_at": "2026-01-01T00:00:00+00:00", "all_ten_equal": True}
        audits = self.base / "audits"
        audits.mkdir()
        path = audits / "demo-final.json"
        path.write_text(json.dumps(audit), encoding="utf-8")
        return folder, path, audit

    def test_live_counts_come_from_repository(self):
        live = demo.load_live(self.root)
        self.assertEqual((live["problems"], live["auto_success"], live["corrected"], live["real_translations"]), (1, 1, 0, 0))
        self.assertFalse(live["rows"][0]["fully_human_verified"])
        self.assertEqual(live["rows"][0]["status"], "auto")

    def test_live_effective_tags_and_manual_history(self):
        self.repo.manager().change(self.source["problem_key"], "remove", ["prefix_sum"])
        self.repo.manager().change(self.source["problem_key"], "add", ["enumeration"])
        live = demo.load_live(self.root)
        self.assertEqual((live["corrected"], live["manual_events"]), (1, 2))
        self.assertEqual([t["id"] for t in live["rows"][0]["auto_tags"]], ["prefix_sum"])
        self.assertEqual([t["id"] for t in live["rows"][0]["effective_tags"]], ["enumeration"])
        self.assertEqual(live["rows"][0]["effective_tags"][0]["sources"], ["manual_add"])

    def test_display_allowlist_excludes_private_body_and_extra_fields(self):
        self.assertNotIn("PRIVATE_BODY_NEVER_EXPORT", json.dumps(demo.load_live(self.root)))
        self.assertNotIn("original_statement", demo.load_live(self.root)["rows"][0])

    def test_reading_creates_no_files_or_changed_bytes(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        demo.load_live(self.root)
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_repository_has_zero_counts(self):
        root = self.base / "missing"
        live = demo.load_live(root)
        self.assertTrue(live["missing"])
        self.assertEqual(live["problems"], 0)
        self.assertFalse(root.exists())

    def test_original_urls_validate_domain_and_strip_queries(self):
        self.assertEqual(demo.original_url("https://atcoder.jp/contests/demo/tasks/demo_a?secret=anything", "atcoder"),
                         "https://atcoder.jp/contests/demo/tasks/demo_a")
        for link in ["javascript:alert(1)", "https://atcoder.jp.evil.test/a", "https://user:pass@atcoder.jp/a",
                     "https://atcoder.jp:8443/a", "https://codeforces.com/a", "https://atcoder.jp/a\n"]:
            with self.subTest(link=link):
                self.assertIsNone(demo.original_url(link, "atcoder"))

    def test_manual_demo_uses_real_operations_and_reset(self):
        result = demo.manual_demo()
        self.assertTrue(result["isolated"])
        self.assertEqual(result["history_count"], 3)
        steps = result["steps"]
        self.assertEqual([t["id"] for t in steps[2]["effective"]], ["prefix_sum"])
        self.assertEqual(steps[2]["removed"], ["enumeration"])
        self.assertEqual(steps[0]["effective"], steps[3]["effective"])
        self.assertEqual(steps[3]["status"], "auto")

    def test_translation_returns_actual_mock_and_chinese_skip(self):
        rows = demo.translation_demo()
        self.assertEqual([r["language"] for r in rows], ["en", "ja", "zh-CN"])
        self.assertEqual([r["status"] for r in rows], ["mock", "mock", "skipped"])
        self.assertTrue(all(r["protection_ok"] for r in rows[:2]))
        self.assertIn("```", rows[0]["translated"])
        self.assertIn("$A$", rows[0]["translated"])
        self.assertIsNone(rows[2]["translated"])
        self.assertEqual(sum(r["real_api_calls"] for r in rows), 0)

    def test_missing_backup_is_not_success(self):
        result = demo.backup_evidence(self.base / "missing", self.root)
        self.assertTrue(result["missing"])
        self.assertEqual(result["reports"], [])

    def test_backup_hashes_and_existing_isolated_restore_rechecked(self):
        folder, _, _ = self.backup_with_audit()
        record = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertTrue(record["verified"])
        self.assertTrue(record["restored_equal"])
        self.assertEqual(record["restored_count"], 1)
        self.assertTrue(record["manual_history_equal"])
        self.assertEqual(record["audit_date"], "2026-01-01T00:00:00+00:00")

    def test_backup_without_audit_does_not_fabricate_restoration(self):
        folder = Path(create_backup(self.root, self.base / "backups")["backup"])
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertTrue(row["verified"])
        self.assertNotIn("restored_equal", row)

    def test_corrupt_backup_reports_failure(self):
        folder = Path(create_backup(self.root, self.base / "backups")["backup"])
        (folder / "versions/tag_taxonomy_v0.3.json").write_text("{}", encoding="utf-8")
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertFalse(row["verified"])
        self.assertIn("校验失败", row["error"])

    def test_unbound_audit_not_used_as_proof(self):
        folder, path, audit = self.backup_with_audit()
        audit["manifest_sha256"] = "0" * 64
        path.write_text(json.dumps(audit), encoding="utf-8")
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertNotIn("restored_equal", row)

    def test_unrelated_invalid_audits_do_not_hide_valid_evidence(self):
        folder, path, _ = self.backup_with_audit()
        (path.parent / "z-malformed.json").write_text("{broken", encoding="utf-8")
        (path.parent / "z-list.json").write_text("[]", encoding="utf-8")
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertTrue(row["verified"])
        self.assertTrue(row["restored_equal"])

    def test_missing_isolated_restore_does_not_claim_current_match(self):
        folder, path, audit = self.backup_with_audit()
        audit["restored_data_root"] = str(self.base / "absent")
        path.write_text(json.dumps(audit), encoding="utf-8")
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertTrue(row["verified"])
        self.assertNotIn("restored_equal", row)
        self.assertIn("已不可用", row["restoration"])

    def test_current_changes_not_claimed_identical_to_restore(self):
        folder, _, _ = self.backup_with_audit()
        self.repo.manager().change(self.source["problem_key"], "add", ["enumeration"])
        row = demo.backup_evidence(folder.parent, self.root)["reports"][0]
        self.assertTrue(row["verified"])
        self.assertFalse(row["restored_equal"])

    def test_html_escapes_external_values(self):
        data = self.page_data()
        row = data["live"]["rows"][0]
        attack = '<script>alert("XSS")</script><img src=x onerror=alert(1)>'
        row.update(title=attack, reason=attack, model=attack)
        page = demo.render_page(data)
        self.assertNotIn(attack, page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("PRIVATE_BODY_NEVER_EXPORT", page)

    def test_html_has_no_network_assets_and_has_local_filter(self):
        page = demo.render_page(self.page_data())
        self.assertNotIn('<script src=', page)
        self.assertNotIn('rel="stylesheet"', page)
        self.assertIn("connect-src 'none'", page)
        self.assertIn('id="tag-filter"', page)
        self.assertIn('aria-expanded="false"', page)
        self.assertNotIn("@@", page)

    def test_no_test_report_never_displays_invented_pass_count(self):
        page = demo.render_page(self.page_data())
        self.assertIn("未运行", page)
        self.assertIn("未找到本工具生成的测试摘要", page)
        self.assertNotIn("209/209", page)

    def test_secret_like_metadata_is_refused_without_content(self):
        data = self.page_data()
        data["live"]["rows"][0]["reason"] = "Bearer never-publish-this"
        with self.assertRaises(ValueError):
            demo.render_page(data)

    def test_output_is_confined_to_generated_folder(self):
        with patch.object(demo, "GENERATED", self.base / "generated"):
            with self.assertRaises(ValueError):
                demo.write_generated(self.base / "source.json", "overwrite")
            target = self.base / "generated/index.html"
            demo.write_generated(target, "中文")
            self.assertEqual(target.read_text(encoding="utf-8"), "中文")

    def test_cli_rejects_output_outside_artifacts_without_reading_real_data(self):
        with redirect_stderr(io.StringIO()), patch.object(demo, "load_live", side_effect=AssertionError("Must not read")):
            self.assertEqual(demo.main(["--output", str(self.base / "forbidden.html")]), 2)
        self.assertFalse((self.base / "forbidden.html").exists())

    def test_missing_or_malformed_test_record_not_claimed(self):
        self.assertIsNone(demo.load_test_report(self.base / "missing.json"))
        target = self.base / "tests.json"
        target.write_text('{"passed":209}', encoding="utf-8")
        with self.assertRaises(ValueError):
            demo.load_test_report(target)

    def test_test_evidence_is_bound_to_source_hash_and_date(self):
        target = self.base / "tests.json"
        record = {"schema_version": 1, "executed_at": "2026-01-01T00:00:00+00:00", "total": 3,
                  "passed": 3, "failures": 0, "errors": 0, "skipped": 0, "seconds": 0.1,
                  "success": True, "real_api_calls": 0, "network_attempts": 0, "process_exit": 0,
                  "source_digest": demo.source_digest()}
        target.write_text(json.dumps(record), encoding="utf-8")
        self.assertTrue(demo.load_test_report(target)["matches_source"])
        record["source_digest"] = "old-source"
        target.write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(demo.load_test_report(target)["matches_source"])
