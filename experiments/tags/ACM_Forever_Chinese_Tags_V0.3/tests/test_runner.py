import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api_helpers import sample, config, wire, save_rows, FakeClient
from annotation_api.adapter import adapt, digest
from annotation_api.runner import run, preview, profile_for, request_fingerprint
from annotation_api.client import CallError, Response
from annotation_api.storage import Store, read_jsonl, atomic_json
from label_pipeline import TAXONOMY
from annotate_api import main


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "input.jsonl"
        self.output = self.root / "outputs"
        self.cache = self.root / "cache"
        save_rows(self.input, [sample(number=1), sample(number=2)])
        self.guard = patch("annotation_api.runner.APIClient", side_effect=AssertionError("Real client forbidden in runner tests"))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def execute(self, client=None, **kwargs):
        return run(self.input, config(), output=self.output, cache_root=self.cache,
                   client=client or FakeClient(), sleep=lambda _: None, **kwargs)

    def test_success_utf8_files_and_usage(self):
        c = FakeClient()
        summary = self.execute(c)
        self.assertEqual((c.calls, summary["success_count"]), (2, 2))
        self.assertEqual(summary["token_usage_known"]["total_tokens"], 240)
        for file in ("predictions.jsonl", "merged_results.jsonl", "errors.jsonl", "summary.json"):
            self.assertTrue((self.output / file).exists())
        predictions = read_jsonl(self.output / "predictions.jsonl")
        self.assertEqual(predictions[0]["specific_tag_names_zh"], ["前缀和"])
        self.assertEqual(predictions[0]["human_review_status"], "pending_review")
        for path in self.output.iterdir():
            if path.suffix in {".json", ".jsonl"}:
                self.assertNotIn("offline-test-key", path.read_text(encoding="utf-8"))

    def test_one_then_ten_resume_charges_only_remaining(self):
        save_rows(self.input, [sample(number=i) for i in range(1, 11)])
        first, second = FakeClient(), FakeClient()
        self.execute(first, limit=1)
        summary = self.execute(second, limit=10, resume=True)
        self.assertEqual((first.calls, second.calls), (1, 9))
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(len(read_jsonl(self.output / "predictions.jsonl")), 10)
        self.assertEqual(summary["token_usage_known"]["total_tokens"], 1200)

    def test_existing_output_without_resume_rejected(self):
        self.execute()
        with self.assertRaises(ValueError):
            self.execute()

    def test_switch_model_requires_separate_output(self):
        self.execute()
        changed = config(model="other-offline-model")
        with self.assertRaises(ValueError):
            run(self.input, changed, output=self.output, cache_root=self.cache, resume=True, client=FakeClient())
        c = FakeClient()
        result = run(self.input, changed, output=self.root / "other", cache_root=self.cache, client=c, sleep=lambda _: None)
        self.assertEqual(result["api_calls"], 2)

    def test_changed_content_prompt_and_parameters_change_fingerprint(self):
        item = adapt(sample())
        original = digest(profile_for(config(), self.input))
        self.assertNotEqual(original, digest(profile_for(config(max_output_tokens=200), self.input)))
        changed_item = adapt({**sample(), "statement_markdown": "另一题面"})
        self.assertNotEqual(request_fingerprint(original, item), request_fingerprint(original, changed_item))
        with patch("annotation_api.runner.SYSTEM", "changed prompt"):
            self.assertNotEqual(original, digest(profile_for(config(), self.input)))

    def test_interruption_after_send_never_resends_uncertain_question(self):
        first = FakeClient([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            self.execute(first)
        second = FakeClient()
        summary = self.execute(second, resume=True)
        self.assertEqual(second.calls, 1)
        self.assertEqual(summary["unknown_delivery_count"], 1)
        self.assertEqual(read_jsonl(self.output / "errors.jsonl")[0]["error_code"], "unknown_delivery")

    def test_received_response_replayed_without_request(self):
        item = adapt(sample())
        profile = profile_for(config(), self.input)
        pid = digest(profile)
        fp = request_fingerprint(pid, item)
        response = FakeClient().call(__import__("annotation_api.prompt", fromlist=["messages"]).messages(item)).as_dict()
        with Store(self.output, self.cache, profile, pid) as store:
            store.save(fp, {"state": "received", "response": response, "attempts": [{"status": "received", "usage": response["usage"]}]})
        c = FakeClient()
        self.execute(c, resume=True)
        self.assertEqual(c.calls, 1)
        self.assertEqual(len(read_jsonl(self.output / "predictions.jsonl")), 2)

    def test_cache_commit_before_output_failure(self):
        c = FakeClient()
        with patch.object(Store, "save_merged", side_effect=OSError("simulated disk failure")), self.assertRaises(OSError):
            self.execute(c)
        resumed = FakeClient()
        self.execute(resumed, resume=True)
        self.assertEqual(resumed.calls, 1)
        self.assertEqual(len(read_jsonl(self.output / "predictions.jsonl")), 2)

    def test_rate_limit_retries_are_bounded(self):
        c = FakeClient([CallError("rate_limit", retryable=True), CallError("rate_limit", retryable=True)])
        summary = self.execute(c)
        self.assertEqual(c.calls, 4)  # 3 attempts first question + 1 second question
        self.assertEqual(summary["success_count"], 2)

    def test_quota_stops_batch_and_remains_stopped_on_resume(self):
        first = FakeClient([CallError("quota_exhausted", fatal=True)])
        summary = self.execute(first)
        self.assertEqual((first.calls, summary["not_processed_count"]), (1, 1))
        second = FakeClient()
        self.execute(second, resume=True)
        self.assertEqual(second.calls, 0)

    def test_invalid_output_refusal_and_truncation_not_paid_repaired(self):
        outcomes = [Response("not JSON", "offline", {"total_tokens": 50}, "stop"),
                    Response(None, "offline", {"total_tokens": 50}, "stop", refused=True),
                    Response("{", "offline", {"total_tokens": 50}, "length")]
        for i, outcome in enumerate(outcomes):
            with self.subTest(i=i):
                c = FakeClient([outcome])
                dest = self.root / str(i)
                result = run(self.input, config(), output=dest, cache_root=self.cache, client=c, sleep=lambda _: None)
                self.assertEqual((c.calls, result["failed_count"]), (2, 1))
                self.assertEqual(result["token_usage_known"]["total_tokens"], 170)
                resumed = FakeClient()
                run(self.input, config(), output=dest, cache_root=self.cache, resume=True, client=resumed, sleep=lambda _: None)
                self.assertEqual(resumed.calls, 0)

    def test_unknown_timeout_isolated_without_retry(self):
        c = FakeClient([CallError("unknown_delivery", unknown=True)])
        result = self.execute(c)
        self.assertEqual((c.calls, result["failed_count"], result["success_count"]), (2, 1, 1))

    def test_explicit_retry_known_failure_preserves_previous_usage(self):
        c = FakeClient([Response("not JSON", "offline", {"total_tokens": 50}, "stop")])
        self.execute(c)
        resumed = FakeClient()
        summary = self.execute(resumed, resume=True, retry_failed=True)
        self.assertEqual(resumed.calls, 1)
        self.assertEqual(summary["token_usage_known"]["total_tokens"], 290)
        self.assertEqual(len(read_jsonl(self.output / "predictions.jsonl")), 2)
        self.assertTrue(all(x["api_call_status"] == "success" for x in read_jsonl(self.output / "merged_results.jsonl")))

    def test_retry_failed_does_not_resend_unknown_delivery(self):
        self.execute(FakeClient([CallError("unknown_delivery", unknown=True)]))
        resumed = FakeClient()
        self.execute(resumed, resume=True, retry_failed=True)
        self.assertEqual(resumed.calls, 0)

    def test_retry_failure_history_is_logged_once_per_attempt(self):
        self.execute(FakeClient([Response("bad JSON", "offline", None, "stop")]))
        self.execute(FakeClient([Response(None, "offline", None, "stop", refused=True)]), resume=True, retry_failed=True)
        self.execute(resume=True)
        errors = read_jsonl(self.output / "errors.jsonl")
        self.assertEqual([x["error_code"] for x in errors], ["invalid_annotation", "refusal"])

    def test_missing_statement_does_not_call_api(self):
        save_rows(self.input, [{**sample(), "statement_markdown": ""}])
        c = FakeClient()
        result = self.execute(c)
        self.assertEqual((c.calls, result["failed_count"]), (0, 1))

    def test_rule_only_cf_does_not_call_api(self):
        save_rows(self.input, [sample("codeforces", tags=["dsu", "greedy"])])
        c = FakeClient()
        result = self.execute(c)
        self.assertEqual((c.calls, result["rule_only_count"]), (0, 1))
        self.assertEqual(read_jsonl(self.output / "merged_results.jsonl")[0]["specific_tag_ids"], ["dsu", "greedy"])

    def test_human_review_input_preserved_even_when_stale(self):
        save_rows(self.input, [{**sample(), "review_status": "human_confirmed", "specific_tag_ids": ["dsu"],
                               "provisional_tag_ids": [], "taxonomy_version": TAXONOMY["version"]}])
        c = FakeClient()
        result = self.execute(c)
        self.assertEqual((c.calls, result["human_protected_count"]), (0, 1))
        self.assertEqual(read_jsonl(self.output / "merged_results.jsonl")[0]["specific_tag_ids"], ["dsu"])

    def test_external_human_review_overrides_candidates_not_predictions(self):
        self.execute()
        reviews = self.root / "reviews.jsonl"
        save_rows(reviews, [{"problem_key": sample()["problem_key"], "reviewed": True,
                            "taxonomy_version": TAXONOMY["version"], "content_hash": "old-version",
                            "accepted_specific_tag_ids": ["dsu"], "accepted_provisional_tag_ids": []}])
        c = FakeClient()
        result = self.execute(c, resume=True, reviews_path=reviews)
        self.assertEqual(c.calls, 0)
        merged = read_jsonl(self.output / "merged_results.jsonl")
        protected = next(x for x in merged if x["problem_key"] == sample()["problem_key"])
        self.assertEqual(protected["specific_tag_ids"], ["dsu"])
        self.assertTrue(protected["human_review_stale"])
        self.assertEqual(read_jsonl(self.output / "predictions.jsonl")[0]["specific_tag_ids"], ["prefix_sum"])
        # Even without the review file, persisted human results remain protected.
        self.execute(FakeClient(), resume=True)
        self.assertEqual(read_jsonl(self.output / "merged_results.jsonl"), merged)

    def test_dry_run_needs_no_key_writes_nothing(self):
        with patch("annotation_api.config.Config.from_args", side_effect=AssertionError("Must not load key")), patch("sys.stdout", new_callable=io.StringIO):
            code = main(["--input", str(self.input), "--platform", "atcoder", "--limit", "2", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.cache.exists())

    def test_default_cli_is_dry_run_and_conflicting_flags_fail(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["--input", str(self.input)]), 0)
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            main(["--input", str(self.input), "--execute", "--dry-run"])

    def test_execute_without_key_fails_before_any_output_or_request(self):
        with patch.dict("os.environ", {}, clear=True), patch("dotenv.dotenv_values", return_value={}), patch("sys.stderr", new_callable=io.StringIO):
            code = main(["--input", str(self.input), "--execute", "--model", "offline-model", "--output", str(self.output)])
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())

    def test_package_source_directory_cannot_be_output(self):
        from label_pipeline import BASE
        with self.assertRaises(ValueError):
            run(self.input, config(), output=BASE / "data" / "new-output", client=FakeClient())

    def test_storage_tail_repair_and_corrupt_middle_rejected(self):
        self.execute()
        path = self.output / "predictions.jsonl"
        with path.open("ab") as f:
            f.write(b'{"partial":')
        c = FakeClient()
        self.execute(c, resume=True)
        self.assertEqual(c.calls, 0)
        self.assertEqual(len(read_jsonl(path)), 2)
        path.write_bytes(b"{bad}\n" + path.read_bytes())
        with self.assertRaises(ValueError):
            self.execute(resume=True)

    def test_single_writer_lock(self):
        profile = profile_for(config(), self.input)
        pid = digest(profile)
        with Store(self.output, self.cache, profile, pid):
            with self.assertRaises(ValueError):
                with Store(self.output, self.cache, profile, pid, resume=True):
                    pass

    def test_duplicate_inputs_skipped_and_conflicts_not_requested(self):
        save_rows(self.input, [sample(), sample()])
        c = FakeClient()
        result = self.execute(c)
        self.assertEqual((c.calls, result["duplicate_count"]), (1, 1))
        conflicting = self.root / "conflicting.jsonl"
        save_rows(conflicting, [sample(), {**sample(), "statement_markdown": "different"}])
        c = FakeClient()
        result = run(conflicting, config(), output=self.root / "conflicting", cache_root=self.cache, client=c, sleep=lambda _: None)
        self.assertEqual((c.calls, result["input_error_count"]), (0, 1))

    def test_small_limit_resume_keeps_existing_dataset_manifest(self):
        self.execute()
        self.execute(resume=True, limit=1)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["selected"]), 2)
