"""Repeatable integration audit with synthetic inputs and isolated repositories."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import check_crawler_integration as integration
from problem_processing.adapter import normalize
from problem_processing.planning import task_policies
from problem_processing.repository import Repository


def record(number=1, **changes):
    return {"platform": "atcoder", "contest_id": "offline", "problem_id": f"offline_{number}",
            "problem_name": "Synthetic Addition",
            "problem_url": f"https://atcoder.jp/contests/offline/tasks/offline_{number}",
            "statement_text": "You are given two integers. Print their sum.",
            "tags": [], "samples": [{"index": 1, "input": "1 2\n", "output": "3\n"}],
            "last_fetch_status": "ok", **changes}


class CrawlerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-input-integration-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "labels"
        self.options = {"root": self.root, "cache_roots": [], "manifest_roots": []}
        for name in ("socket.create_connection", "annotation_api.client.APIClient", "dotenv.load_dotenv"):
            guard = patch(name, side_effect=AssertionError("No network or credentials in integration audit"))
            guard.start()
            self.addCleanup(guard.stop)

    def write(self, rows, name="input.json"):
        path = self.base / name
        content = ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
                   if name.endswith(".jsonl") else json.dumps({"problems": rows}, ensure_ascii=False))
        path.write_text(content, encoding="utf-8")
        return path

    def audit(self, rows, **options):
        return integration.audit_files([self.write(rows)], **self.options, **options)

    def test_json_input_adapter_and_planner_are_connected(self):
        report = self.audit([record()])
        self.assertTrue(report["success"])
        self.assertEqual(report["sample_plan"]["entries"][0]["status"], "needs_both")
        self.assertEqual(report["real_api_calls"], 0)
        self.assertFalse(report["execution_supported"])
        self.assertFalse(self.root.exists())

    def test_jsonl_and_per_file_limit(self):
        paths = [self.write([record(1), record(2)], "first.jsonl"), self.write([record(3)], "second.json")]
        report = integration.audit_files(paths, limit_per_file=1, **self.options)
        self.assertEqual(len(report["records"]), 2)
        self.assertEqual(report["sample_plan"]["summary"]["total"], 2)

    def test_cf_and_atcoder_identities_remain_distinct(self):
        cf = record(platform="codeforces", contest_id="123", problem_id="cf_123A",
                    problem_index="A", problem_url="https://codeforces.com/contest/123/problem/A")
        report = self.audit([cf, record()])
        self.assertEqual({r["problem_key"] for r in report["records"]},
                         {"codeforces:123:A", "atcoder:offline:offline_1"})

    def test_handoff_markdown_formula_and_samples_preserved(self):
        row = {"platform": "atcoder", "contest_id": "offline", "problem_id": "offline_1",
               "title": "Synthetic handoff", "tags": {"values": []},
               "statement": {"status": "ok", "markdown": "Compute $x^2$.\n\n```\n 1\n\n```"}}
        report = self.audit([row])
        self.assertTrue(report["records"][0]["checks"]["source_markdown_preserved"])
        self.assertTrue(report["records"][0]["samples_embedded_in_markdown"])

    def test_omitted_output_reaches_plan_without_fake_answer(self):
        row = record(samples=[{"index": 1, "input": "1", "output": None,
                               "output_note": "Output omitted because it is very long."}])
        report = self.audit([row])
        self.assertTrue(report["success"])
        self.assertEqual(report["records"][0]["omitted_outputs"], 1)

    def test_pdf_and_missing_body_remain_pending(self):
        report = self.audit([record(statement_text="", samples=[], statement_pdf={"available": True})])
        self.assertEqual(report["sample_plan"]["summary"]["pending"], 1)
        self.assertEqual(report["sample_plan"]["summary"]["estimated_api_tasks"], 0)

    def test_conflicting_identity_is_invalid_without_leaking_source(self):
        report = self.audit([record(problem_key="atcoder:other:other_a")])
        self.assertFalse(report["success"])
        self.assertEqual(report["records"][0]["processing_status"], "invalid")

    def test_sensitive_input_is_rejected_without_export(self):
        report = self.audit([record(api_key="synthetic-credential-not-real")])
        self.assertFalse(report["success"])
        self.assertNotIn("synthetic-credential-not-real", json.dumps(report))

    def test_input_files_and_persistent_results_are_unchanged(self):
        row = record()
        normalized = normalize(row)
        annotation = {**normalized["rule_base"], "specific_tag_ids": ["enumeration"],
                      "provisional_tag_ids": [], "api_call_status": "success", "model": "offline-model",
                      "annotation_input_hash": normalized["annotation_input_hash"],
                      "processing_policy": task_policies()["annotation"]}
        repo = Repository(self.root)
        repo.import_records([row], [annotation])
        repo.manager().change(normalized["problem_key"], "remove", ["enumeration"])
        before = integration.persistent_hashes(self.root)
        report = self.audit([row])
        self.assertTrue(report["success"])
        self.assertEqual(before, integration.persistent_hashes(self.root))
        self.assertEqual(report["existing_results_plan"]["summary"]["annotation_reused"], 1)
        self.assertEqual(report["sample_plan"]["summary"]["needs_annotation"], 0)

    def test_complete_audit_is_deterministic(self):
        path = self.write([record()])
        first = integration.audit_files([path], **self.options)
        self.assertEqual(first, integration.audit_files([path], **self.options))

    def test_report_contains_no_problem_body(self):
        report = self.audit([record(statement_text="PRIVATE_SYNTHETIC_BODY_MARKER")])
        text = json.dumps(report)
        self.assertNotIn("PRIVATE_SYNTHETIC_BODY_MARKER", text)
        self.assertNotIn('"statement_html"', text)
        self.assertEqual(report["input_provenance"], "caller_supplied_not_independently_verified")

    def test_invalid_limits_and_database_input_rejected(self):
        for limit in (0, -1, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.audit([record()], limit_per_file=limit)
        path = self.base / "test.db"
        path.write_bytes(b"not a database")
        with self.assertRaises(ValueError):
            integration.audit_files([path], **self.options)

    def test_holdout_keys_are_skipped_before_body_normalization(self):
        manifest = self.base / "selection.json"
        manifest.write_text(json.dumps({"holdout_keys": ["atcoder:offline:offline_1"]}), encoding="utf-8")
        path = self.write([record(1), record(2)])
        from problem_processing.adapter import normalize as real_normalize
        def checked(row):
            self.assertNotEqual(row["problem_id"], "offline_1")
            return real_normalize(row)
        with patch("check_crawler_integration.normalize", side_effect=checked):
            report = integration.audit_files([path], limit_per_file=1, selection_manifest=manifest, **self.options)
        self.assertEqual(report["records"][0]["problem_key"], "atcoder:offline:offline_2")
        self.assertEqual(report["sources"][0]["holdout_rows_skipped_before_normalization"], 1)

    def test_holdout_file_rejected_before_reading(self):
        path = self.write([record()], "holdout_inputs.json")
        with patch("check_crawler_integration.read_problems", side_effect=AssertionError("Must not read holdout")):
            with self.assertRaises(ValueError):
                integration.audit_files([path], **self.options)

    def test_malformed_split_manifest_blocks_audit(self):
        path = self.write([record()])
        manifest = self.base / "selection.json"
        manifest.write_text('{"holdout_keys":"invalid"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            integration.audit_files([path], selection_manifest=manifest, **self.options)

    def test_cli_is_read_only_by_default(self):
        path = self.write([record()])
        output = io.StringIO()
        with redirect_stdout(output):
            code = integration.main(["--input", str(path), "--data-root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(output.getvalue())["report"])
        self.assertFalse(self.root.exists())

    def test_cli_report_uses_existing_safe_writer_and_refuses_overwrite(self):
        path = self.write([record()])
        reports = self.base / "reports"
        target = reports / "audit.json"
        args = ["--input", str(path), "--data-root", str(self.root), "--report", str(target)]
        with patch("problem_processing.planning.OUTPUT_ROOT", reports), redirect_stdout(io.StringIO()):
            self.assertEqual(integration.main(args), 0)
            before = target.read_bytes()
            self.assertEqual(integration.main(args), 2)
            self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
