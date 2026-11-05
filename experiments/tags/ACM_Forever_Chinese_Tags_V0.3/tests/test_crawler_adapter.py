"""Shareable synthetic crawler records; no network, private splits or real DB."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from api_helpers import sample
import adapt_problems
from annotation_api.adapter import adapt
from annotation_api.prompt import messages
from problem_processing.adapter import normalize, read_problems, source_identity
from problem_processing.crawler_input import expanded
from problem_processing.repository import Repository
from problem_processing.statement import html_statement, parser_module
from problem_processing.translation import language_plan, prepare_request, translation_fingerprint

FIXTURE = Path(__file__).parent / "fixtures/crawler_records.json"


def crawler(**changes):
    return {"platform": "codeforces", "problem_id": "cf_123A", "contest_id": "123", "problem_index": "A",
            "problem_name": "Synthetic Sum", "problem_url": "https://codeforces.com/contest/123/problem/A",
            "statement_text": "You are given two integers. Print their sum.", "tags": '["dsu"]',
            "samples": "[]", "last_fetch_status": "ok", **changes}


class CrawlerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-crawler-adapter-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("No real API"))
        guard.start()
        self.addCleanup(guard.stop)

    def write(self, rows, suffix=".jsonl"):
        path = self.root / ("records" + suffix)
        value = "".join(json.dumps(row) + "\n" for row in rows) if suffix == ".jsonl" else json.dumps({"items": rows})
        path.write_text(value, encoding="utf-8")
        return path

    def test_cf_prefixed_combined_and_canonical_ids_agree(self):
        for pid in ["cf_123A", "123A", "A"]:
            with self.subTest(pid=pid):
                result = normalize(crawler(problem_id=pid))
                self.assertEqual(result["problem_key"], "codeforces:123:A")
                self.assertEqual(result["source_problem_id"], pid)
                self.assertEqual(result["rule_base"]["cf_exact_tag_ids"], ["dsu"])

    def test_cf_alphanumeric_special_indices_and_gym(self):
        for contest, index in [("123", "A1"), ("123", "ZZZ99"), ("921", "1"), ("999999", "B2")]:
            with self.subTest(contest=contest,index=index):
                result = normalize(crawler(contest_id=contest, problem_index=index, problem_id=f"cf_{contest}{index}",
                                  problem_url=f"https://codeforces.com/gym/{contest}/problem/{index}"))
                self.assertEqual(result["problem_key"], f"codeforces:{contest}:{index}")

    def test_numeric_index_equal_to_contest_is_not_stripped(self):
        result = normalize(crawler(contest_id="1", problem_index="1", problem_id="cf_11",
                                   problem_url="https://codeforces.com/contest/1/problem/1"))
        self.assertEqual(result["problem_key"], "codeforces:1:1")
        self.assertEqual(result["rule_base"]["problem_key"], "codeforces:1:1")
        self.assertEqual(adapt(result)["rule_base"]["problem_key"], "codeforces:1:1")

    def test_cf_problemset_url_and_inferred_alphanumeric_contest(self):
        result = normalize(crawler(contest_id=None, problem_id="cf_123A", problem_index=None,
                                   problem_url="https://codeforces.com/problemset/problem/123/A"))
        self.assertEqual(result["problem_key"], "codeforces:123:A")
        self.assertEqual(source_identity({"platform":"codeforces","problem_id":"cf_123A"})[3], "codeforces:123:A")

    def test_numeric_combined_id_without_contest_or_url_rejected(self):
        with self.assertRaises(ValueError):
            normalize(crawler(contest_id=None, problem_id="cf_9211", problem_index=None, problem_url=None))

    def test_cf_invalid_indices_and_conflicts_rejected(self):
        for changes in [{"problem_index":"A123"}, {"problem_index":"ABCD"}, {"problem_id":"cf_124A"},
                        {"problem_key":"codeforces:124:A"}, {"problem_url":"https://codeforces.com/contest/123/problem/B"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(crawler(**changes))

    def test_atcoder_actual_task_id_and_old_numeric_task(self):
        for contest, pid in [("abc475", "abc475_d"), ("abc001", "abc001_1"), ("archive-a", "legacy-task")]:
            row = {"platform":"atcoder", "contest_id":contest, "problem_id":pid, "problem_index":"D",
                   "statement_text":"A synthetic problem.", "problem_url":f"https://atcoder.jp/contests/{contest}/tasks/{pid}"}
            self.assertEqual(normalize(row)["problem_key"], f"atcoder:{contest}:{pid}")

    def test_atcoder_link_supplies_contest_without_guessing_task_prefix(self):
        row = {"platform":"atcoder", "problem_id":"different_task", "statement_text":"A synthetic problem.",
               "problem_url":"https://atcoder.jp/contests/archive/tasks/different_task"}
        self.assertEqual(normalize(row)["problem_key"], "atcoder:archive:different_task")
        row.pop("problem_url")
        with self.assertRaises(ValueError):
            normalize(row)

    def test_atcoder_id_catalog_alias_is_supported(self):
        row = {"platform":"atcoder", "id":"demo_a", "contest_id":"demo", "statement_text":"A synthetic problem."}
        self.assertEqual(normalize(row)["problem_key"], "atcoder:demo:demo_a")

    def test_legacy_identity_and_content_hash_are_retained(self):
        for platform in ["codeforces", "atcoder"]:
            p = sample(platform)
            expected = adapt(p)
            result = normalize(p)
            self.assertEqual(result["problem_key"], expected["rule_base"]["problem_key"])
            self.assertEqual(result["content_hash"], expected["rule_base"]["content_hash"])
            self.assertEqual(result["annotation_input_hash"], expected["annotation_input_hash"])
        p = {**sample(), "content_hash":"legacy-source-version"}
        self.assertEqual(normalize(p)["content_hash"], "legacy-source-version")

    def test_json_columns_and_metadata_fallback(self):
        row = crawler()
        row["metadata_json"] = json.dumps({"platform":"codeforces", "problem_id":"cf_123A", "contest_id":"123",
                                           "difficulty_raw":1234, "difficulty_source":"synthetic"})
        result = normalize(row)
        self.assertEqual(result["raw_tags"], ["dsu"])
        self.assertEqual(result["difficulty_raw"],1234)
        self.assertEqual(result["difficulty_source"],"synthetic")

    def test_metadata_identity_conflict_and_bad_json_rejected(self):
        for changes in [{"metadata_json":'{"contest_id":"124"}'}, {"tags":"not-json"},
                        {"samples":"{}"}, {"metadata_json":"[]"}, {"metadata_json":"{broken"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(crawler(**changes))

    def test_multiple_links_preserved_and_identity_checked(self):
        row = crawler(source_links=["https://codeforces.com/problemset/problem/123/A", "https://example.org/synthetic"],
                      statement_source_url="https://codeforces.com/contest/123/problem/A?locale=en")
        result = normalize(row)
        self.assertEqual(len(result["source_links"]),4)
        row["source_links"].append("https://atcoder.jp/contests/demo/tasks/demo_a")
        with self.assertRaises(ValueError):
            normalize(row)

    def test_missing_identity_not_inferred_from_title(self):
        for row in [{"platform":"codeforces","problem_name":"123A"},
                    {"platform":"atcoder","contest_id":"demo","problem_name":"demo_a"}]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                normalize(row)

    def test_source_links_reject_authentication_and_non_http(self):
        for link in ["javascript:alert(1)", "https://user:pass@codeforces.com/contest/123/problem/A", "file:///local"]:
            with self.subTest(link=link), self.assertRaises(ValueError):
                normalize(crawler(source_links=[link]))

    def test_html_tree_is_reused_and_richer_than_plain_text(self):
        result = normalize(crawler(statement_html="<h3>Statement</h3><p>Compute <var>x^2</var>.</p>", statement_text="lossy fallback"))
        self.assertEqual(parser_module().TreeParser.__module__, "_acm_tag_statement_tree")
        self.assertIn("### Statement", result["original_statement"])
        self.assertIn("$x^2$", result["original_statement"])
        self.assertEqual(result["source_statement_text"],"lossy fallback")
        self.assertEqual(result["processing_status"],"ready")

    def test_latex_and_math_script_are_preserved(self):
        html = r'<p>Use \\(x \\le 10\\) and $$$N^2$$$.</p><script type="math/tex">x_1 + x_2</script>'
        result = normalize(crawler(statement_html=html,statement_text=None))
        self.assertIn(r"\\(x \\le 10\\)",result["original_statement"])
        self.assertIn("$$$N^2$$$",result["original_statement"])
        self.assertIn("$x_1 + x_2$",result["original_statement"])
        self.assertEqual(result["original_statement_html"],html)

    def test_pre_and_sample_blank_lines_not_flattened(self):
        html = '<h3>Sample Input 1</h3><pre>\n  1 &lt; 2\n\n3<br>4\n</pre><p><code>a + b</code></p>'
        result = normalize(crawler(statement_html=html,statement_text=None))
        self.assertIn("```\n  1 < 2\n\n3\n4\n```", result["original_statement"])
        self.assertIn("`a + b`",result["original_statement"])

    def test_cf_test_example_lines_preserve_line_boundaries(self):
        html = '<pre><div class="test-example-line">1 2</div><div class="test-example-line">3 4</div></pre>'
        self.assertIn("1 2\n3 4\n",normalize(crawler(statement_html=html))["original_statement"])

    def test_atcoder_language_container_selection_and_navigation_removed(self):
        html = '<html><nav>Navigation</nav><div id="task-statement"><span class="lang-ja"><p>日本語問題です。</p></span><span class="lang-en"><p>English synthetic problem.</p></span></div></html>'
        row = normalize(crawler(statement_html=html,statement_language="en"))
        self.assertIn("English synthetic",row["original_statement"])
        self.assertNotIn("日本語",row["original_statement"])
        self.assertNotIn("Navigation",row["original_statement"])

    def test_images_links_and_mathml_are_conservative(self):
        html = '<p>Use <a href="/help">help</a><img src="/diagram.png" alt="diagram"></p><math><mi>x</mi></math>'
        row = normalize(crawler(statement_html=html))
        self.assertIn("[help](https://codeforces.com/help)",row["original_statement"])
        self.assertIn("![diagram](https://codeforces.com/diagram.png)",row["original_statement"])
        self.assertEqual(row["processing_status"],"html_pending")
        self.assertNotEqual(row["statement_status"],"ok")
        self.assertEqual(language_plan(row)["action"],"needs_review")

    def test_unbalanced_unknown_or_error_html_never_ready(self):
        for html in ["<p>Unclosed", "<p><div>Mismatch</p>", "<html><body>Error body</body></html>",
                     "<p>Access denied</p>", "<script>alert(1)</script>"]:
            with self.subTest(html=html):
                self.assertNotEqual(normalize(crawler(statement_html=html))["processing_status"],"ready")

    def test_complex_table_kept_for_review(self):
        row = normalize(crawler(statement_html='<table><tr><td colspan="2">Data</td></tr></table>'))
        self.assertIn("Data",row["original_statement"])
        self.assertIn("complex_table",row["processing_issues"])

    def test_pdf_only_binary_or_reference_never_becomes_statement(self):
        for pdf in [b"%PDF-1.7\nsynthetic\n%%EOF", "statement.pdf", {"filename":"statement.pdf"}]:
            with self.subTest(pdf=type(pdf).__name__):
                row = normalize(crawler(statement_text=None,statement_pdf=pdf))
                self.assertEqual(row["processing_status"],"pdf_pending")
                self.assertEqual(row["original_statement"],"")
                self.assertTrue(row["pdf_metadata"]["present"])
                self.assertNotIn("statement_pdf",row)
                self.assertEqual(language_plan(row)["action"],"needs_review")
                json.dumps(row)

    def test_pdf_detail_api_flag_and_filename_in_text_stay_pending(self):
        row = normalize(crawler(statement_text="https://example.org/statement.pdf",has_pdf=True,statement_format="pdf"))
        self.assertEqual(row["processing_status"],"pdf_pending")
        self.assertEqual(row["original_statement"],"")

    def test_pdf_plus_reliable_text_can_be_ready(self):
        row = normalize(crawler(statement_pdf={"available":True}))
        self.assertEqual(row["processing_status"],"ready")
        self.assertEqual(row["statement_format"],"text")

    def test_empty_failed_and_never_fetched_are_pending(self):
        self.assertEqual(normalize(crawler(statement_text=" "))["processing_status"],"missing_statement")
        for status in ["failed","never"]:
            row = normalize(crawler(last_fetch_status=status))
            self.assertEqual(row["processing_status"],"source_pending")
            self.assertFalse(adapt(row)["has_statement"])

    def test_samples_and_count_validation(self):
        for changes in [{"samples":[{"index":1,"input":"x"}]}, {"sample_count":1},
                        {"samples":[{"index":True,"input":"x","output":"y"}]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(crawler(**changes))

    def test_plain_text_samples_appended_without_whitespace_loss(self):
        row = normalize(crawler(samples=[{"index":1,"input":" 1 2\r\n\r\n","output":"3\r\n"}]))
        self.assertIn(" 1 2\n\n",row["original_statement"])
        self.assertEqual(row["samples"][0]["input"]," 1 2\n\n")
        self.assertIn("Sample Output 1",row["original_statement"])

    def test_separate_samples_missing_from_html_are_included(self):
        row = normalize(crawler(statement_html="<p>Synthetic body.</p>",samples=[{"index":1,"input":" 7\n\n","output":"8\n"}]))
        self.assertIn(" 7\n\n",row["original_statement"])
        self.assertIn("Sample Output 1",row["original_statement"])

    def test_sample_array_order_is_normalized_stably(self):
        samples = [{"index":1,"input":"1","output":"2"},{"index":2,"input":"3","output":"4"}]
        first = normalize(crawler(samples=samples))
        second = normalize(crawler(samples=list(reversed(samples))))
        self.assertEqual(first["normalized_content_hash"],second["normalized_content_hash"])

    def test_source_and_normalized_annotation_translation_hashes_separated(self):
        row = normalize(crawler(statement_sha256="a"*64,content_hash="source-specific-version"))
        self.assertEqual(row["source_statement_sha256"],"a"*64)
        self.assertEqual(row["source_content_hash"],"source-specific-version")
        self.assertEqual(row["content_hash"],row["normalized_content_hash"])
        self.assertEqual(len({row[k] for k in ["source_statement_sha256","content_hash","annotation_input_hash","translation_input_hash"]}),4)

    def test_crawl_timestamp_or_source_hash_change_does_not_invalidate_input(self):
        first = normalize(crawler(statement_sha256="a"*64,statement_fetched_at="2026-01-01"))
        second = normalize(crawler(statement_sha256="b"*64,statement_fetched_at="2026-02-01"))
        for k in ["content_hash","annotation_input_hash","translation_input_hash"]:
            self.assertEqual(first[k],second[k])

    def test_input_hash_changes_only_for_relevant_inputs(self):
        first = normalize(crawler())
        changed = normalize(crawler(tags=["dsu","graphs"]))
        self.assertEqual(first["content_hash"],changed["content_hash"])
        self.assertNotEqual(first["annotation_input_hash"],changed["annotation_input_hash"])
        self.assertEqual(first["translation_input_hash"],changed["translation_input_hash"])
        changed = normalize(crawler(statement_text="A different synthetic statement."))
        for k in ["content_hash","annotation_input_hash","translation_input_hash"]:
            self.assertNotEqual(first[k],changed[k])

    def test_newline_hash_stability(self):
        first = normalize(crawler(statement_text="First line.\r\nSecond line."))
        second = normalize(crawler(statement_text="First line.\nSecond line."))
        self.assertEqual(first["normalized_content_hash"],second["normalized_content_hash"])

    def test_original_record_not_modified_and_repeated_normalization_idempotent(self):
        source = crawler(samples=[{"index":1,"input":"1\n","output":"2\n"}])
        before = deepcopy(source)
        first = normalize(source)
        self.assertEqual(source,before)
        self.assertEqual(first,normalize(source))
        self.assertEqual(first,normalize(first))

    def test_normalized_hash_tampering_rejected(self):
        row = normalize(crawler())
        row["original_statement"] = "Tampered"
        with self.assertRaises(ValueError):
            normalize(row)

    def test_reimport_checks_aliases_tags_and_input_hashes(self):
        for changes in [{"title":"Changed alias"}, {"raw_tags":["graphs"]},
                        {"translation_input_hash":"0"*64}, {"normalized_content_hash":"0"*64},
                        {"input_adapter_version":"unknown-version"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize({**normalize(crawler()),**changes})

    def test_math_display_mode_and_rendered_only_math(self):
        row = normalize(crawler(statement_html='<script type="math/tex; mode=display">x^2</script>'))
        self.assertIn("$$x^2$$",row["original_statement"])
        row = normalize(crawler(statement_html='<span class="katex-display">Rendered only</span>'))
        self.assertEqual(row["processing_status"],"html_pending")

    def test_legacy_nested_statement_works_with_new_metadata(self):
        row = crawler()
        row.pop("statement_text")
        row["statement"] = {"markdown":"A synthetic complete statement.","status":"ok"}
        self.assertEqual(normalize(row)["original_statement"],row["statement"]["markdown"])

    def test_jsonl_normalized_output_can_be_reprocessed_identically(self):
        first,errors,_ = adapt_problems.adapt_file(self.write([crawler()]))
        second,errors2,_ = adapt_problems.adapt_file(self.write(first))
        self.assertEqual((errors,errors2),([],[]))
        self.assertEqual(first,second)

    def test_json_jsonl_single_and_envelope_formats(self):
        for suffix in [".json", ".jsonl"]:
            path = self.write([crawler()],suffix)
            self.assertEqual(len(read_problems(path)),1)
            self.assertEqual(adapt_problems.adapt_file(path)[2]["ready"],1)
        path.write_text(json.dumps(crawler()),encoding="utf-8")
        self.assertEqual(len(read_problems(path)),1)

    def test_batch_duplicates_merge_links_without_merging_by_title(self):
        p = crawler()
        alt = crawler(problem_id="123A",source_links=["https://example.org/reference"])
        rows,errors,summary = adapt_problems.adapt_file(self.write([p,alt]))
        self.assertEqual(errors,[])
        self.assertEqual(summary["duplicates"],1)
        self.assertEqual(len(rows[0]["source_problem_ids"]),2)
        self.assertIn("https://example.org/reference",rows[0]["source_links"])
        other = crawler(problem_id="cf_123B",problem_index="B",problem_url="https://codeforces.com/contest/123/problem/B")
        self.assertEqual(len(adapt_problems.adapt_file(self.write([p,other]))[0]),2)

    def test_batch_conflicting_and_invalid_duplicates_block_entire_identity(self):
        for changed in [crawler(statement_text="Different body."),crawler(tags="invalid")]:
            rows,errors,_ = adapt_problems.adapt_file(self.write([crawler(),changed]))
            self.assertEqual(rows,[])
            self.assertTrue(errors)

    def test_invalid_line_isolated_and_no_raw_error_text_leaked(self):
        path = self.write([crawler()])
        path.write_text("{broken-secret-like-input\n" + path.read_text(encoding="utf-8"),encoding="utf-8")
        rows,errors,summary = adapt_problems.adapt_file(path)
        self.assertEqual((len(rows),len(errors),summary["invalid"]),(1,1,1))
        self.assertNotIn("broken-secret",json.dumps(errors))

    def test_fixture_has_two_ready_one_pdf_pending_and_no_api_calls(self):
        rows,errors,summary = adapt_problems.adapt_file(FIXTURE)
        self.assertEqual((len(rows),errors,summary["ready"],summary["pending"]),(3,[],2,1))
        self.assertEqual(summary["real_api_calls"],0)

    def test_cli_default_dry_run_does_not_write_or_read_credentials(self):
        output = self.root/"not-created.jsonl"
        with redirect_stdout(io.StringIO()) as log, patch("annotation_api.config.Config.from_args",side_effect=AssertionError("No key")):
            code = adapt_problems.main(["--input",str(FIXTURE),"--output",str(output)])
        self.assertEqual(code,0)
        self.assertFalse(output.exists())
        self.assertEqual(json.loads(log.getvalue())["mode"],"dry_run")

    def test_cli_write_is_explicit_non_overwriting_and_confined(self):
        generated = self.root/"adapted"
        output = generated/"records.jsonl"
        with patch.object(adapt_problems,"OUTPUT_ROOT",generated),redirect_stdout(io.StringIO()):
            self.assertEqual(adapt_problems.main(["--input",str(FIXTURE),"--write","--output",str(output)]),0)
            before = output.read_bytes()
            self.assertEqual(adapt_problems.main(["--input",str(FIXTURE),"--write","--output",str(output)]),2)
            self.assertEqual(output.read_bytes(),before)
            self.assertEqual(adapt_problems.main(["--input",str(FIXTURE),"--write","--output",str(self.root/"unsafe.jsonl")]),2)

    def test_cli_invalid_batch_does_not_publish_partial_output(self):
        path = self.write([crawler(),{}])
        with patch.object(adapt_problems,"OUTPUT_ROOT",self.root/"adapted"),redirect_stdout(io.StringIO()):
            output = self.root/"adapted/records.jsonl"
            self.assertEqual(adapt_problems.main(["--input",str(path),"--write","--output",str(output)]),1)
        self.assertFalse(output.exists())

    def test_label_and_translation_protocols_and_mock_repository_import(self):
        row = normalize(crawler(statement_text="You are given two integers. Print the sum of these integers.",
                                editorial_status="ok",verified_editorial_markdown="Verified synthetic solution."))
        api_input = adapt(row)
        self.assertEqual(api_input["annotation_input_hash"],row["annotation_input_hash"])
        self.assertEqual(json.loads(messages(api_input)[1]["content"])["statement_markdown"],row["original_statement"])
        self.assertIn("Verified synthetic",api_input["evidence"]["verified_editorial_markdown"])
        plan = language_plan(row)
        self.assertEqual(plan["action"],"translate")
        self.assertTrue(prepare_request(row,plan)["segments"])
        self.assertNotEqual(row["translation_input_hash"],translation_fingerprint(row,plan,{"model":"mock"}))
        repo = Repository(self.root/"labels")
        repo.import_records([row])
        self.assertEqual(repo.metadata_many()[0]["problem_key"],row["problem_key"])


if __name__ == "__main__":
    unittest.main()
