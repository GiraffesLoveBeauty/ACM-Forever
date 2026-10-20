"""Offline repository and translation tests: synthetic data, MockTransport, no API."""
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import import_tags
import translate_api
from annotation_api.client import APIClient, CallError, Response
from annotation_api.runner import profile_for
from api_helpers import config
from label_pipeline import TAXONOMY
from problem_processing.adapter import normalize, read_problems
from problem_processing.repository import Repository, data_root
from problem_processing.translation import (MockTranslationClient, SCHEMA, SYSTEM, current_translation,
                                          language_plan, plan_tasks, prepare_request, translate,
                                          translation_fingerprint, validate_translation)
from tag_management import TagManager, get_effective_tags_many, iter_effective_tags

FIXTURES = Path(__file__).parent / "fixtures" / "translation_samples.jsonl"
SAMPLES = read_problems(FIXTURES)


def raw(number=0, **values):
    return {"problem_key": f"atcoder:offline:offline_{number}", "platform": "atcoder",
            "title": "Mock Addition", "statement_markdown": "You are given two integers. Print their sum.",
            "statement_status": "ok", **values}


def annotation(problem, tags=None):
    p = normalize(problem)
    return {"problem_key": p["problem_key"], "platform": p["platform"], "title": p["original_title"],
            "source_url": p["source_links"][0] if p["source_links"] else None, "content_hash": p["content_hash"],
            "taxonomy_version": TAXONOMY["version"], "raw_tags": p["raw_tags"],
            "specific_tag_ids": ["enumeration"] if tags is None else tags, "provisional_tag_ids": [],
            "api_call_status": "success", "human_review_status": "pending_review", "model": "mock"}


class SecondaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "labels"
        self.repo = Repository(self.root)
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Real network forbidden"))
        guard.start(); self.addCleanup(guard.stop)

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, p=None, tags=None):
        p = p or raw()
        return self.repo.import_records([p], [annotation(p, tags)])

    def test_automatic_persistence_and_restart_without_outputs(self):
        self.seed()
        manager = Repository(self.root).manager()
        self.assertEqual(manager.get_effective_tags(raw()["problem_key"])["specific_tag_ids"], ["enumeration"])
        self.assertEqual(len(list((self.root / "annotations").glob("*.jsonl"))), 1)
        self.assertEqual(manager.get_effective_tags(raw()["problem_key"])["review_status"], "auto")

    def test_duplicate_import_is_idempotent_and_history_immutable(self):
        first = self.seed()
        pointer = self.repo.pointer.read_bytes()
        second = self.seed()
        self.assertEqual(first["generation_id"], second["generation_id"])
        self.assertTrue(second["unchanged"])
        self.assertEqual(pointer, self.repo.pointer.read_bytes())
        self.assertEqual(len(list((self.root / "annotations").glob("*.jsonl"))), 1)

    def test_manual_tombstones_survive_new_auto_results(self):
        self.seed()
        key = raw()["problem_key"]
        self.repo.manager().change(key, "remove", ["enumeration"])
        self.repo.manager().change(key, "add", ["prefix_sum"])
        self.seed(tags=["enumeration", "simulation"])
        result = self.repo.manager().get_effective_tags(key)
        self.assertEqual(set(result["specific_tag_ids"]), {"prefix_sum", "simulation"})
        self.assertEqual(result["review_status"], "corrected")

    def test_content_versions_preserve_manual_edits_and_history(self):
        first = self.seed()
        key = raw()["problem_key"]
        self.repo.manager().change(key, "remove", ["enumeration"])
        second = self.seed(raw(statement_markdown="You are given three integers. Print their sum."))
        self.assertNotEqual(first["generation_id"], second["generation_id"])
        self.assertTrue((self.root / "catalog" / "generations" / first["generation_id"]).exists())
        result = self.repo.manager().get_effective_tags(key)
        self.assertEqual(result["specific_tag_ids"], [])
        self.assertEqual(result["review_status"], "needs_review")

    def test_interrupted_pointer_switch_keeps_old_complete_generation(self):
        self.seed()
        old = self.repo.pointer.read_bytes()
        original_atomic = __import__("problem_processing.repository", fromlist=["atomic_json"]).atomic_json
        def fail_pointer(path, value):
            if Path(path) == self.repo.pointer:
                raise OSError("mock interruption")
            original_atomic(path, value)
        with patch("problem_processing.repository.atomic_json", side_effect=fail_pointer):
            with self.assertRaises(OSError):
                self.seed(raw(1))
        self.assertEqual(self.repo.pointer.read_bytes(), old)
        self.assertEqual(len(self.repo.snapshot()[0]), 1)
        self.seed(raw(1))
        self.assertEqual(len(self.repo.snapshot()[0]), 2)

    def test_hash_conflict_mismatched_annotation_and_duplicates_rejected(self):
        p = raw(content_hash="provided-hash")
        self.seed(p)
        with self.assertRaises(ValueError):
            self.seed(raw(content_hash="provided-hash", statement_markdown="Different actual content."))
        bad = annotation(raw()); bad["content_hash"] = "wrong"
        with self.assertRaises(ValueError):
            self.repo.import_records([raw()], [bad])
        with self.assertRaises(ValueError):
            self.repo.import_records([raw(), raw()])

    def test_invalid_automatic_label_rejected(self):
        bad = annotation(raw()); bad["specific_tag_ids"] = ["invalid"]
        with self.assertRaises(ValueError):
            self.repo.import_records([raw()], [bad])

    def test_batch_queries_load_catalog_and_history_once(self):
        self.repo.import_records([raw(i) for i in range(30)], [annotation(raw(i)) for i in range(30)])
        manager = self.repo.manager()
        with patch.object(manager, "catalog", wraps=manager.catalog) as c, patch.object(manager.journal, "read", wraps=manager.journal.read) as h:
            results = manager.get_effective_tags_many([raw(i)["problem_key"] for i in range(30)])
            self.assertEqual(len(results), 30)
            self.assertEqual(c.call_count, 1); self.assertEqual(h.call_count, 1)
        kwargs = {"auto_file": manager.auto_file, "override_file": manager.journal.path}
        self.assertEqual(len(get_effective_tags_many([raw()["problem_key"]], **kwargs)), 1)
        self.assertEqual(len(list(iter_effective_tags(platform="atcoder", tag_ids=["枚举"], status="auto", **kwargs))), 30)

    def test_batch_missing_key_and_filter_validation(self):
        self.seed()
        with self.assertRaises(ValueError):
            self.repo.manager().get_effective_tags_many(["atcoder:offline:missing"])
        with self.assertRaises(ValueError):
            list(self.repo.manager().iter_effective_tags(tag_ids=["unknown"]))

    def test_nowcoder_global_identity_and_original_tags_preserved(self):
        p = {"platform": "nowcoder", "problem_id": "12345", "problem_name": "模拟牛客题", "tags": ["原站未知标签"],
             "problem_url": "https://ac.nowcoder.com/acm/problem/12345", "statement_markdown": "给定两个整数，求它们的和并输出结果。"}
        metadata = normalize(p)
        self.assertEqual(metadata["problem_key"], "nowcoder:problem:12345")
        self.repo.import_records([p], [annotation(p, ["simulation"])])
        self.assertEqual(metadata["raw_tags"], ["原站未知标签"])
        self.assertEqual(self.repo.manager().get_effective_tags(metadata["problem_key"])["specific_tag_ids"], ["simulation"])

    def test_crawler_envelope_html_only_and_url_contest_adapter(self):
        p = {"platform": "codeforces", "contest_id": 999999, "problem_id": "999999A", "problem_name": "HTML",
             "problem_url": "https://codeforces.com/contest/999999/problem/A", "statement_html": "<p>Only HTML</p>", "tags": ["dsu"]}
        m = normalize(p)
        self.assertEqual(m["problem_key"], "codeforces:999999:A")
        self.assertEqual(m["statement_status"], "html_only")
        self.assertEqual(language_plan(m)["action"], "needs_review")
        path = Path(self.temp.name) / "crawler.json"
        path.write_text(json.dumps({"schema": "crawler", "problems": [p]}), encoding="utf-8")
        self.assertEqual(len(read_problems(path)), 1)
        atc = normalize({"platform": "atcoder", "problem_id": "offline_a", "problem_url": "https://atcoder.jp/contests/offline/tasks/offline_a"})
        self.assertEqual(atc["problem_key"], "atcoder:offline:offline_a")

    def test_multiple_links_preserved_and_same_titles_not_merged(self):
        self.repo.import_records([raw(0, source_links=["https://example.org/p/1", "https://example.org/p/2"]), raw(1)])
        metadata, _ = self.repo.snapshot()
        self.assertEqual(len(metadata), 2)
        self.assertEqual(len(metadata[raw()["problem_key"]]["source_links"]), 2)

    def test_same_identity_link_updates_do_not_discard_previous_links(self):
        self.seed(raw(source_links=["https://example.org/p/1"]))
        self.seed(raw(source_links=["https://example.org/p/2"]))
        p = self.repo.snapshot()[0][raw()["problem_key"]]
        self.assertEqual(p["source_links"], ["https://example.org/p/1", "https://example.org/p/2"])

    def test_default_persistent_query_does_not_need_experimental_outputs(self):
        self.seed()
        settings = Path(self.temp.name) / "settings.json"
        settings.write_text(json.dumps({"schema_version": 1, "storage": "persistent"}), encoding="utf-8")
        with patch("tag_management.service.DEFAULT_SETTINGS", settings), patch.dict(os.environ, {"TAG_DATA_ROOT": str(self.root)}):
            manager = TagManager()
            self.assertTrue(manager.auto_file.is_relative_to(self.root))
            self.assertEqual(manager.journal.path, self.root / "manual" / "overrides.jsonl")
            self.assertEqual(manager.get_effective_tags(raw()["problem_key"])["review_status"], "auto")

    def test_export_contains_effective_labels_rights_and_no_original_overwrite(self):
        self.seed()
        self.repo.manager().change(raw()["problem_key"], "remove", ["enumeration"])
        result = self.repo.export()
        record = json.loads(Path(result["path"]).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["effective_tag_ids"], [])
        self.assertTrue(record["display_requires_rights_check"])
        self.assertEqual(record["rights_status"], "unknown")
        with self.assertRaises(ValueError):
            self.repo.export(Path(self.temp.name) / "original.jsonl")

    def test_data_root_override_and_no_disposable_root(self):
        with patch.dict(os.environ, {"TAG_DATA_ROOT": str(self.root)}):
            self.assertEqual(data_root(), self.root.resolve())
        with self.assertRaises(ValueError):
            Repository(Path(self.temp.name) / "outputs" / "labels")

    def test_original_inputs_and_predictions_never_modified_by_cli(self):
        path = Path(self.temp.name) / "input.jsonl"
        labels = Path(self.temp.name) / "labels.jsonl"
        path.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
        labels.write_text(json.dumps(annotation(raw())) + "\n", encoding="utf-8")
        before = (path.read_bytes(), labels.read_bytes())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(import_tags.main(["--input", str(path), "--annotations", str(labels), "--data-root", str(self.root)]), 0)
        self.assertEqual(before, (path.read_bytes(), labels.read_bytes()))

    def test_language_english_japanese_chinese(self):
        plans = [language_plan(normalize(p)) for p in SAMPLES]
        self.assertEqual([p["source_language"] for p in plans], ["en", "ja", "zh-CN"])
        self.assertEqual([p["action"] for p in plans], ["translate", "translate", "skip"])

    def test_complete_bilingual_prefers_english_incomplete_requires_review(self):
        text = "問題文\n整数が与えられます。\n\nProblem Statement\nYou are given two integers.\n\nConstraints\nN <= 100\n\nInput\nN\n\nOutput\nPrint the result."
        plan = language_plan(normalize(raw(statement_markdown=text)))
        self.assertEqual(plan["source_language"], "en")
        self.assertNotIn("問題文", plan["source_text"])
        self.assertEqual(language_plan(normalize(raw(statement_markdown=text.replace("Constraints", "No section"))))["action"], "needs_review")

    def test_mixed_language_not_skipped_due_to_hanzi(self):
        text = "中文说明：下面的题面需要完整翻译。\nYou are given a sequence of integers and must compute the sum of all elements and print the answer."
        plan = language_plan(normalize(raw(statement_markdown=text)))
        self.assertEqual(plan["action"], "translate")
        self.assertEqual(plan["source_language"], "mixed")

    def test_missing_statement_unknown_language_and_invalid_inputs(self):
        for p in [raw(statement_markdown=""), raw(statement_markdown="123")]:
            result = translate(normalize(p), root=self.root, mock=True)
            self.assertEqual(result["translation_status"], "needs_review")
            self.assertEqual(result["api_calls"], 0)
        for p in [[], raw(tags="greedy"), raw(statement_markdown=123)]:
            with self.assertRaises(ValueError):
                normalize(p)

    def test_mock_english_and_japanese_preserve_samples_and_formulas(self):
        for p in SAMPLES[:2]:
            result = translate(normalize(p), root=self.root, mock=True)
            self.assertEqual(result["translation_status"], "mock")
            self.assertIn("```\n1 2\n```", result["statement_zh"])
            self.assertIn("$A$", result["statement_zh"])
            self.assertIn("$B$", result["statement_zh"])
            self.assertEqual(result["real_api_calls"], 0)
        self.assertFalse((self.root / "translations" / "current.json").exists())

    def test_chinese_skipped_without_client_or_store(self):
        result = translate(normalize(SAMPLES[2]), root=self.root, mock=True)
        self.assertEqual(result["translation_status"], "skipped")
        self.assertFalse(self.root.exists())

    def translated_payload(self, p=None):
        p = normalize(p or SAMPLES[0]); plan = language_plan(p); request = prepare_request(p, plan)
        response = MockTranslationClient().call(request["messages"])
        return request, json.loads(response.content)

    def test_damaged_formula_or_sample_placeholder_rejected(self):
        prepared, value = self.translated_payload()
        target = next(s for s in value["segments"] if "__ACM_KEEP_" in s["text"])
        target["text"] = re.sub(r"__ACM_KEEP_\d+__", "错误改写", target["text"], count=1)
        with self.assertRaises(ValueError):
            validate_translation(json.dumps(value), prepared)

    def test_lost_segment_changed_numeric_constraint_and_markdown_rejected(self):
        p = raw(statement_markdown="# Statement\n\nYou must print the sum of these integers.\n\n- There are 100 numbers.")
        prepared, value = self.translated_payload(p)
        for kind in ["drop", "number", "heading"]:
            bad = json.loads(json.dumps(value))
            if kind == "drop": bad["segments"].pop()
            if kind == "number": bad["segments"][-1]["text"] = bad["segments"][-1]["text"].replace("100", "99")
            if kind == "heading": bad["segments"][0]["text"] = bad["segments"][0]["text"].replace("#", "##")
            with self.assertRaises(ValueError):
                validate_translation(json.dumps(bad), prepared)

    def test_images_links_inline_code_and_display_math_preserved(self):
        p = raw(statement_markdown="You are given an array of integers. Compute its sum.\n\n![diagram](https://example.org/image.png)\n\nUse `N = 10` and \\[N \\le 100\\].")
        result = translate(normalize(p), root=self.root, mock=True)
        self.assertEqual(result["translation_status"], "mock")
        for token in ["![diagram](https://example.org/image.png)", "`N = 10`", "\\[N \\le 100\\]"]:
            self.assertIn(token, result["statement_zh"])

    def test_unwrapped_math_expressions_and_variable_order_preserved(self):
        p = raw(statement_markdown="You are given an integer N with 1 <= N <= 100. Print N^2.")
        result = translate(normalize(p), root=self.root, mock=True)
        self.assertIn("1 <= N <= 100", result["statement_zh"])
        self.assertIn("N^2", result["statement_zh"])
        prepared, value = self.translated_payload(p)
        text = value["segments"][0]["text"]
        tokens = re.findall(r"__ACM_KEEP_\d+__", text)
        self.assertGreaterEqual(len(tokens), 2)
        value["segments"][0]["text"] = text.replace(tokens[0], "__TEMP__").replace(tokens[1], tokens[0]).replace("__TEMP__", tokens[1])
        with self.assertRaises(ValueError):
            validate_translation(json.dumps(value), prepared)

    def test_retry_cache_and_unknown_delivery_never_resent(self):
        p = normalize(SAMPLES[0]); client = MockTranslationClient()
        first = translate(p, root=self.root, client=client, mock=True)
        second = translate(p, root=self.root, client=client, mock=True)
        self.assertEqual(client.calls, 1); self.assertTrue(second["cache_hit"])
        other = Path(self.temp.name) / "uncertain"
        class Timeout:
            calls = 0
            def call(self, *a, **kw):
                self.calls += 1
                raise CallError("unknown_delivery", unknown=True)
        timeout = Timeout()
        translate(p, root=other, client=timeout, mock=True)
        result = translate(p, root=other, client=timeout, mock=True)
        self.assertEqual(timeout.calls, 1); self.assertEqual(result["error"], "unknown_delivery")

    def test_invalid_translation_preserves_usage_and_does_not_retry(self):
        class Invalid:
            calls = 0
            def call(self, *a, **kw):
                self.calls += 1
                return Response('{"title_zh":"中文","segments":[]}', "offline", {"total_tokens": 10}, "stop")
        client = Invalid()
        problem = normalize(SAMPLES[0])
        first = translate(problem, root=self.root, mock=True, client=client)
        second = translate(problem, root=self.root, mock=True, client=client)
        self.assertEqual(first["translation_status"], "needs_review")
        self.assertEqual(first["usage"]["total_tokens"], 10)
        self.assertEqual(second["api_calls"], 0)
        self.assertEqual(client.calls, 1)

    def test_translation_prompt_change_does_not_change_label_profile(self):
        p = normalize(SAMPLES[0]); plan = language_plan(p)
        label_before = profile_for(config(), FIXTURES, "atcoder")
        before = translation_fingerprint(p, plan, {"model": "mock"})
        with patch("problem_processing.translation.SYSTEM", SYSTEM + "\n新版翻译提示词"):
            after = translation_fingerprint(p, plan, {"model": "mock"})
            self.assertEqual(label_before, profile_for(config(), FIXTURES, "atcoder"))
        self.assertNotEqual(before, after)

    def test_translation_does_not_touch_manual_labels(self):
        self.seed(SAMPLES[0])
        key = SAMPLES[0]["problem_key"]
        manager = self.repo.manager(); manager.change(key, "add", ["prefix_sum"])
        before = manager.journal.path.read_bytes()
        translate(normalize(SAMPLES[0]), root=self.root, mock=True)
        self.assertEqual(manager.journal.path.read_bytes(), before)

    def test_sdk_mock_uses_translation_schema_not_label_schema(self):
        observed = []
        p = normalize(SAMPLES[0]); prepared = prepare_request(p, language_plan(p))
        response = MockTranslationClient().call(prepared["messages"])
        def handler(request):
            observed.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 0,
                "model": "mock-sdk", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": response.content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}})
        client = APIClient(config(), http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            result = translate(p, root=self.root, config=config(), client=client)
        finally:
            client.close()
        self.assertEqual(result["translation_status"], "auto")
        self.assertEqual(observed[0]["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertEqual(result["usage"]["total_tokens"], 30)
        self.assertIsNotNone(current_translation(self.root, p))
        self.assertIsNone(current_translation(self.root, normalize(raw(statement_markdown="Changed source."))))

    def test_task_planning_translation_only_labels_only_and_joint_design(self):
        en = normalize(SAMPLES[0]); zh = normalize(SAMPLES[2])
        self.assertEqual(plan_tasks(en, labels_available=True)["tasks"], ["translation"])
        self.assertEqual(plan_tasks(zh)["tasks"], ["labels"])
        self.assertTrue(plan_tasks(en)["combined_request_candidate"])
        self.assertFalse(plan_tasks(en)["combined_execution_implemented"])
        self.assertEqual(plan_tasks(en, labels_available=True, translation_available=True)["tasks"], [])

    def test_dry_run_does_not_load_key_or_create_data(self):
        with patch("translate_api.Config.from_args", side_effect=AssertionError("No credentials")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(translate_api.main(["--input", str(FIXTURES), "--limit", "3", "--data-root", str(self.root), "--dry-run"]), 0)
        self.assertIn('"real_api_calls": 0', output.getvalue())
        self.assertFalse(self.root.exists())

    def test_mock_1000_and_5000_cold_loading_and_batch_query(self):
        for n in [1000, 5000]:
            repo = Repository(Path(self.temp.name) / str(n))
            problems = [raw(i) for i in range(n)]
            repo.import_records(problems, [annotation(p) for p in problems])
            manager = repo.manager()
            keys = [p["problem_key"] for p in problems]
            start = time.perf_counter()
            catalog = manager.catalog()
            cold = time.perf_counter() - start
            start = time.perf_counter()
            with patch.object(manager, "catalog", return_value=catalog) as reader:
                results = manager.get_effective_tags_many(keys)
            bulk = time.perf_counter() - start
            self.assertEqual(len(results), n); self.assertEqual(reader.call_count, 1)
            print(json.dumps({"mock_performance": n, "cold_load_seconds": round(cold, 4), "indexed_batch_seconds": round(bulk, 4)}))


if __name__ == "__main__":
    unittest.main()
