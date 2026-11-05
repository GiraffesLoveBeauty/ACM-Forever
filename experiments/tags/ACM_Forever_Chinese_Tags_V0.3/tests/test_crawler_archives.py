"""New crawler ZIP/nullable sample contracts, entirely offline and synthetic."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import adapt_problems
import check_crawler_integration
from annotation_api.adapter import adapt
from problem_processing.adapter import normalize, normalized_samples
from problem_processing.executor import execute_batch, mock_config
from problem_processing.planning import Planner
from problem_processing.statement import parser_module
from problem_processing.translation import language_plan

FIXTURE = Path(__file__).parent / "fixtures/crawler_archive_records.json"
ZIP = "https://img.atcoder.jp/offline/samples.zip"


def attached(**changes):
    return {"index": 1, "input": None, "output": None,
            "input_note": "Sample input is provided in the official ZIP; not expanded.",
            "output_note": "Refer to the source and the attached sample files.",
            "attachments": [{"url": ZIP, "name": "Official sample ZIP"}], **changes}


def record(**changes):
    return {"platform": "atcoder", "contest_id": "offline", "problem_id": "offline_a",
            "problem_name": "Synthetic archive sample", "statement_text": "Read integers. Print their sum.",
            "problem_url": "https://atcoder.jp/contests/offline/tasks/offline_a",
            "statement_language": "en", "samples": [attached()], "sample_count": 1,
            "last_fetch_status": "ok", **changes}


def backend_record():
    raw = ('<div id="task-statement"><span class="lang-en">'
           '<h3>Problem Statement</h3><p>Read <var>N</var> integers.</p>'
           '<h3>Sample Input 0</h3><pre> 1\n\n</pre>'
           '<h3>Sample Output 0</h3><pre>2\n</pre>'
           '<h3>Sample Input 1</h3><p><a href="' + ZIP + '">Official sample ZIP</a></p>'
           '</span></div>').encode()
    parsed = parser_module().parse_atcoder(raw, record()["problem_url"])
    return record(**parsed, sample_count=len(parsed["samples"]))


class CrawlerArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-crawler-archive-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target in ("socket.create_connection", "urllib.request.urlopen",
                       "httpx.HTTPTransport.handle_request", "dotenv.load_dotenv"):
            guard = patch(target, side_effect=AssertionError("Offline adapter: network/credentials forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_backend_output_is_accepted_without_rewriting(self):
        row = backend_record()
        before = deepcopy(row)
        result = normalize(row)
        self.assertEqual(result["samples"], row["samples"])
        self.assertEqual(row, before)
        self.assertEqual(result["processing_status"], "sample_pending")

    def test_zero_source_number_is_preserved_behind_positive_indices(self):
        samples = normalize(backend_record())["samples"]
        self.assertEqual([s["index"] for s in samples], [1, 2])
        self.assertEqual([s["source_index"] for s in samples], [0, 1])
        self.assertEqual(samples[0]["input"], " 1\n\n")

    def test_input_and_output_nulls_are_not_fabricated_code(self):
        result = normalize(record())
        self.assertIsNone(result["samples"][0]["input"])
        self.assertIsNone(result["samples"][0]["output"])
        self.assertNotIn("```", result["original_statement"])
        self.assertIn("not actual input", result["original_statement"])
        self.assertIn("not expected output", result["original_statement"])

    def test_zip_is_only_a_reference_not_downloaded_or_unpacked(self):
        result = normalize(record())
        self.assertIn(ZIP, result["original_statement"])
        self.assertIn("files have not been downloaded or expanded", result["original_statement"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_null_input_note_without_attachment_is_pending(self):
        result = normalize(record(samples=[attached(attachments=[])]))
        self.assertEqual(result["processing_status"], "sample_pending")
        self.assertIn("sample_input_unavailable", result["processing_issues"])

    def test_null_either_side_requires_its_own_note(self):
        for kind in ("input", "output"):
            sample = attached()
            del sample[kind + "_note"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                normalize(record(samples=[sample]))

    def test_empty_or_invalid_notes_rejected(self):
        for kind in ("input", "output"):
            for note in (None, "", " \r\n", 5, False, []):
                with self.subTest(kind=kind, note=note), self.assertRaises(ValueError):
                    normalize(record(samples=[attached(**{kind + "_note": note})]))

    def test_missing_side_is_not_implicitly_null(self):
        for kind in ("input", "output"):
            sample = attached()
            del sample[kind]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                normalize(record(samples=[sample]))

    def test_input_note_does_not_excuse_nonstring_input(self):
        for value in (1, False, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(record(samples=[attached(input=value)]))

    def test_explicit_empty_input_and_output_stay_ready(self):
        result = normalize(record(samples=[{"index": 1, "input": "", "output": ""}]))
        self.assertEqual(result["processing_status"], "ready")
        self.assertEqual(result["samples"][0]["input"], "")
        self.assertEqual(result["samples"][0]["output"], "")

    def test_plain_source_omitted_output_still_ready(self):
        sample = {"index": 1, "input": "1\n", "output": None, "output_note": "Output omitted by the source."}
        self.assertEqual(normalize(record(samples=[sample]))["processing_status"], "ready")

    def test_archive_for_missing_output_blocks_processing(self):
        result = normalize(record(samples=[attached(input="1\n")]))
        self.assertEqual(result["processing_status"], "sample_pending")
        self.assertIn("sample_attachment_unexpanded", result["processing_issues"])

    def test_supplementary_zip_with_complete_text_stays_ready(self):
        result = normalize(record(samples=[attached(input="1\n", output="2\n")]))
        self.assertEqual(result["processing_status"], "ready")
        self.assertIn("```\n1\n```", result["original_statement"])
        self.assertIn(ZIP, result["original_statement"])

    def test_attachment_order_and_duplicates_are_stable(self):
        a, b = {"url": ZIP, "name": "ZIP A"}, {"url": ZIP.replace("samples", "other"), "name": "ZIP B"}
        first = normalize(record(samples=[attached(attachments=[a, b, a])]))
        second = normalize(record(samples=[attached(attachments=[b, a])]))
        self.assertEqual(first, second)
        self.assertEqual(len(first["samples"][0]["attachments"]), 2)

    def test_same_url_with_conflicting_names_rejected(self):
        with self.assertRaises(ValueError):
            normalize(record(samples=[attached(attachments=[{"url":ZIP,"name":"A"}, {"url":ZIP,"name":"B"}])]))

    def test_attachment_objects_use_explicit_field_allowlist(self):
        for value in (None, {}, "zip", False, [None], [ZIP], [{"url":ZIP,"headers":{}}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(record(samples=[attached(attachments=value)]))

    def test_optional_attachment_name_has_a_stable_default(self):
        sample = normalize(record(samples=[attached(attachments=[{"url":ZIP}])]))["samples"][0]
        self.assertEqual(sample["attachments"][0]["name"], "官方样例 ZIP")

    def test_attachment_names_require_text(self):
        for name in (None, "", " \n", False, 5):
            with self.subTest(name=name), self.assertRaises(ValueError):
                normalize(record(samples=[attached(attachments=[{"url":ZIP,"name":name}])]))

    def test_untrusted_malformed_or_nonzip_urls_rejected(self):
        for url in (None, "", "samples.zip", "javascript:alert(1)", "file:///samples.zip",
                    "http://img.atcoder.jp/a.zip", "https://evil.test/a.zip",
                    "https://img.atcoder.jp.evil.test/a.zip", "https://user:pass@img.atcoder.jp/a.zip",
                    "https://img.atcoder.jp:444/a.zip", "https://img.atcoder.jp:bad/a.zip",
                    "https://img.atcoder.jp/a.zip/x", "https://img.atcoder.jp/a.txt",
                    "https://[broken/a.zip", "https://img.atcoder.jp/a\n.zip",
                    "https://img.atcoder.jp/a).zip", "https://img.atcoder.jp/a\\b.zip"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize(record(samples=[attached(attachments=[{"url":url}])]))

    def test_public_https_443_and_download_query_are_supported(self):
        url = "https://img.atcoder.jp:443/offline/samples.ZIP?download=1#sample"
        sample = normalize(record(samples=[attached(attachments=[{"url":url}])]))["samples"][0]
        self.assertEqual(sample["attachments"][0]["url"], url)

    def test_credential_query_links_rejected(self):
        for key in ("token", "api_key", "access_token", "%61pi_key", "signature"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalize(record(samples=[attached(attachments=[{"url":ZIP + "?" + key + "=synthetic"}])]))

    def test_original_source_index_requires_nonnegative_integer(self):
        for index in (-1, False, "0", None):
            with self.subTest(index=index), self.assertRaises(ValueError):
                normalize(record(samples=[attached(source_index=index)]))

    def test_duplicate_original_source_indices_rejected(self):
        with self.assertRaises(ValueError):
            normalized_samples([attached(source_index=0), attached(index=2, source_index=0)])

    def test_html_math_code_and_samples_are_preserved(self):
        result = normalize(backend_record())
        self.assertIn("$N$", result["original_statement"])
        self.assertIn(" 1\n\n", result["original_statement"])
        self.assertIn(ZIP, result["original_statement_html"])

    def test_sql_encoded_and_http_decoded_shapes_agree(self):
        plain = record()
        sql = deepcopy(plain)
        sql["samples"] = json.dumps(sql["samples"], ensure_ascii=False)
        sql["tags"] = "[]"
        self.assertEqual(normalize(plain), normalize(sql))

    def test_json_jsonl_cli_and_status_counts(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        path = self.root / "mock.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in fixture["items"]), encoding="utf-8")
        rows, errors, summary = adapt_problems.adapt_file(path)
        other, _, _ = adapt_problems.adapt_file(FIXTURE)
        self.assertEqual(rows, other)
        self.assertEqual(errors, [])
        self.assertEqual(summary["ready"], 2)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["status_counts"]["sample_pending"], 1)
        output = io.StringIO()
        with redirect_stdout(output):
            code = adapt_problems.main(["--input",str(FIXTURE),"--dry-run"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["output_written"])

    def test_repeated_adaptation_and_json_roundtrip_are_identical(self):
        row = backend_record()
        first = normalize(row)
        self.assertEqual(first, normalize(row))
        self.assertEqual(first, normalize(json.loads(json.dumps(first))))
        self.assertEqual(first["original_statement"].count("external ZIP references"), 1)

    def test_metadata_only_changes_do_not_change_task_hashes(self):
        first = normalize(record())
        second = normalize(record(updated_at="later", statement_fetched_at="later"))
        for name in ("normalized_content_hash", "annotation_input_hash", "translation_input_hash"):
            self.assertEqual(first[name], second[name])

    def test_note_and_attachment_changes_are_not_reused_silently(self):
        first = normalize(record())
        for sample in (attached(input_note="Different source explanation."),
                       attached(attachments=[{"url":ZIP.replace('samples','replacement'),"name":"Official sample ZIP"}])):
            other = normalize(record(samples=[sample]))
            for name in ("normalized_content_hash", "annotation_input_hash", "translation_input_hash"):
                self.assertNotEqual(first[name], other[name])

    def test_line_ending_normalization_is_stable_without_mutation(self):
        row = record(samples=[attached(input_note="First\r\nSecond")])
        before = deepcopy(row)
        result = normalize(row)
        self.assertEqual(row, before)
        self.assertEqual(result, normalize(record(samples=[attached(input_note="First\nSecond")])))

    def test_changed_input_note_on_normalized_record_is_rejected(self):
        row = normalize(record())
        row["samples"][0]["input_note"] = "Changed explanation."
        with self.assertRaises(ValueError): normalize(row)

    def test_changed_attachment_on_normalized_record_is_rejected(self):
        row = normalize(record())
        row["samples"][0]["attachments"][0]["url"] = ZIP.replace('samples','changed')
        with self.assertRaises(ValueError): normalize(row)

    def test_pending_record_cannot_be_relabeled_ready_without_expansion(self):
        row = normalize(record())
        row.update(processing_status="ready", statement_status="ok")
        with self.assertRaises(ValueError): normalize(row)

    def test_bodyless_archive_does_not_become_a_fake_statement(self):
        result = normalize(record(statement_text=""))
        self.assertEqual(result["original_statement"], "")
        self.assertEqual(result["processing_status"], "missing_statement")
        self.assertEqual(result, normalize(result))

    def test_annotation_and_translation_protocols_block_incomplete_samples(self):
        row = normalize(record())
        self.assertFalse(adapt(row)["has_statement"])
        self.assertEqual(language_plan(row)["action"], "needs_review")

    def test_incremental_planner_proposes_zero_paid_tasks_for_unexpanded_samples(self):
        plan = Planner(self.root/'labels', cache_roots=[], manifest_roots=[]).plan([record()])
        self.assertEqual(plan["summary"]["pending"], 1)
        self.assertEqual(plan["summary"]["estimated_api_tasks"], 0)
        for task in ("annotation", "translation"):
            self.assertEqual(plan["entries"][0][task]["status"], "pending")
            self.assertFalse(plan["entries"][0][task]["needs_ai"])

    def test_executor_never_dispatches_incomplete_sample_tasks(self):
        for task in ("annotation", "translation"):
            client = unittest.mock.Mock()
            client.offline_transport = True
            result = execute_batch([record()],task,root=self.root/task,config=mock_config(),
                                   mock=True,client=client,cache_roots=[],manifest_roots=[])
            self.assertEqual(result["api_calls"], 0)
            client.call.assert_not_called()

    def test_integration_audit_counts_unavailable_samples(self):
        path = self.root/'input.json'
        path.write_text(json.dumps([record()]),encoding='utf-8')
        report = check_crawler_integration.audit_files([path], root=self.root/'labels',
                      cache_roots=[],manifest_roots=[],selection_manifest=self.root/'split.json')
        self.assertTrue(report["success"])
        self.assertEqual(report["records"][0]["unavailable_inputs"],1)
        self.assertEqual(report["records"][0]["omitted_outputs"],1)
        self.assertEqual(report["records"][0]["sample_attachment_count"],1)
        self.assertEqual(report["sample_plan"]["summary"]["estimated_api_tasks"],0)


if __name__ == '__main__':
    unittest.main()
