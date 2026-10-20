import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api_helpers import sample, config, save_rows, FakeClient
from annotation_api.runner import run
from annotation_api.storage import read_jsonl
from annotation_api.evaluation import report
from evaluate_api import main
from label_pipeline import TAXONOMY


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "input.jsonl"
        self.output = self.root / "output"
        save_rows(self.input, [sample(number=1), sample(number=2)])
        run(self.input, config(), output=self.output, cache_root=self.root / "cache", client=FakeClient(), sleep=lambda _: None)
        self.predictions = read_jsonl(self.output / "predictions.jsonl")
        self.manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.golds = [{"problem_key": p["problem_key"], "taxonomy_version": TAXONOMY["version"],
                       "reviewed": True, "accepted_specific_tag_ids": ["prefix_sum"],
                       "accepted_provisional_tag_ids": [], "content_hash": p["content_hash"]} for p in self.predictions]

    def evaluate(self, predictions=None, golds=None, **kwargs):
        return report(self.predictions if predictions is None else predictions,
                      self.golds if golds is None else golds, manifest=self.manifest, **kwargs)

    def test_reviewed_metrics(self):
        result = self.evaluate()
        metrics = result["quality_on_reviewed"]
        self.assertEqual(metrics["reviewed_count"], 2)
        for name in ("micro_precision", "micro_recall", "micro_f1", "exact_match_rate"):
            self.assertEqual(metrics[name], 1)

    def test_unreviewed_no_accuracy(self):
        gold = [{**g, "reviewed": False} for g in self.golds]
        quality = self.evaluate(golds=gold)["quality_on_reviewed"]
        self.assertEqual(quality["reviewed_count"], 0)
        self.assertIsNone(quality["micro_f1"])
        self.assertIn("无法计算", quality["message"])

    def test_truthy_review_status_not_accepted(self):
        for value in ("true", "false", 1, [], None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.evaluate(golds=[{**self.golds[0], "reviewed": value}])

    def test_duplicate_and_unknown_id(self):
        for pred in ([*self.predictions, self.predictions[0]],
                     [{**self.predictions[0], "specific_tag_ids": ["invented"]}]):
            with self.assertRaises(ValueError):
                self.evaluate(predictions=pred)
        with self.assertRaises(ValueError):
            self.evaluate(golds=[*self.golds, self.golds[0]])

    def test_version_and_identity_mismatches(self):
        for change in ({"taxonomy_version": "wrong"}, {"content_hash": "wrong"},
                       {"problem_key": "atcoder:other:other_a"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.evaluate(golds=[{**self.golds[0], **change}])
        with self.assertRaises(ValueError):
            self.evaluate(predictions=[{**self.predictions[0], "taxonomy_version": "wrong"}])
        with self.assertRaises(ValueError):
            self.evaluate(predictions=[{**self.predictions[0], "annotation_input_hash": "wrong"}])

    def test_gold_without_hash_requires_manifest(self):
        gold = [{k: v for k, v in g.items() if k != "content_hash"} for g in self.golds]
        self.assertEqual(self.evaluate(golds=gold)["legacy_gold_associated_via_manifest"], 2)
        with self.assertRaises(ValueError):
            report(self.predictions, gold)

    def test_manual_corrections_not_evaluated_as_model_predictions(self):
        for changes in ({"review_status": "human_confirmed"}, {"human_review_status": "approved"},
                        {"prediction_origin": "human"}, {"evaluation_specific_tag_ids": ["dsu"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.evaluate(predictions=[{**self.predictions[0], **changes}])

    def test_missing_predictions_count_as_failure_not_exact_match(self):
        error = {"problem_key": self.golds[1]["problem_key"], "error_code": "refusal"}
        result = self.evaluate(predictions=[self.predictions[0]], errors=[error])
        quality, stats = result["quality_on_reviewed"], result["descriptive_all_selected"]
        self.assertEqual(quality["micro_recall"], .5)
        self.assertEqual(quality["exact_match_rate"], .5)
        self.assertEqual(stats["failure_rate"], .5)
        self.assertEqual(stats["prediction_coverage"], .5)
        self.assertEqual(stats["missing_reviewed_prediction_count"], 1)

    def test_historical_error_does_not_count_as_current_failure(self):
        result = self.evaluate(errors=[{"problem_key": self.golds[0]["problem_key"], "error_code": "invalid_annotation"}])
        self.assertEqual(result["descriptive_all_selected"]["failure_rate"], 0)

    def test_missing_empty_gold_is_not_exact_match(self):
        gold = [{**self.golds[0], "accepted_specific_tag_ids": []}]
        result = self.evaluate(predictions=[], golds=gold)
        self.assertEqual(result["quality_on_reviewed"]["exact_match_rate"], 0)

    def test_provisional_statistics_not_treated_as_specific(self):
        dest = self.root / "provisional"
        run(self.input, config(), output=dest, cache_root=self.root / "cache", client=FakeClient([
            {"specific_tag_ids": [], "provisional_tag_ids": ["pending_dp"]}]), sleep=lambda _: None)
        pred = read_jsonl(dest / "predictions.jsonl")
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        result = report(pred, self.golds, manifest=manifest)
        self.assertEqual(result["descriptive_all_selected"]["provisional_rate_all_selected"], .5)
        self.assertEqual(result["descriptive_all_selected"]["specific_coverage_all_selected"], .5)
        self.assertEqual(result["quality_on_reviewed"]["micro_recall"], .5)

    def test_cf_evaluation_preserves_rule_tags(self):
        path = self.root / "cf.jsonl"
        save_rows(path, [sample("codeforces", tags=["dsu", "data structures"])])
        dest = self.root / "cf"
        run(path, config(), output=dest, cache_root=self.root / "cache", client=FakeClient(), sleep=lambda _: None)
        pred = read_jsonl(dest / "predictions.jsonl")
        gold = [{"problem_key": pred[0]["problem_key"], "reviewed": True,
                 "taxonomy_version": TAXONOMY["version"], "content_hash": pred[0]["content_hash"],
                 "accepted_specific_tag_ids": ["dsu", "prefix_sum"]}]
        result = report(pred, gold)
        self.assertEqual(result["quality_on_reviewed"]["micro_f1"], 1)
        self.assertEqual(result["quality_on_reviewed"]["provisional_rate"], 1)

    def test_mixed_model_profile_rejected(self):
        altered = [self.predictions[0], {**self.predictions[1], "profile_id": "different"}]
        with self.assertRaises(ValueError):
            self.evaluate(predictions=altered)

    def test_cli_and_overwrite_protection(self):
        path = self.root / "gold.jsonl"
        save_rows(path, self.golds)
        output = self.root / "report.json"
        args = ["--predictions", str(self.output / "predictions.jsonl"), "--gold", str(path), "--output", str(output)]
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(args), 0)
            self.assertEqual(main([*args[:-1], str(path)]), 2)
        self.assertTrue(output.exists())
        self.assertEqual(read_jsonl(path), self.golds)

    def test_missing_gold_is_a_file_error_not_an_empty_answer_set(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            code = main(["--predictions", str(self.output / "predictions.jsonl"), "--gold", str(self.root / "missing.jsonl")])
        self.assertEqual(code, 2)
