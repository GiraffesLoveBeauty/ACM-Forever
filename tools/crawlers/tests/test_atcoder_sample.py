"""Offline checks for joining AtCoder metadata and difficulty models."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "atcoder_sample.py"


class AtCoderSampleTests(unittest.TestCase):
    def run_export(self, directory, problems, models, *options):
        problem_file, model_file = directory / "problems.json", directory / "models.json"
        problem_raw = json.dumps(problems, ensure_ascii=False).encode("utf-8")
        model_raw = json.dumps(models, ensure_ascii=False).encode("utf-8")
        problem_file.write_bytes(problem_raw)
        model_file.write_bytes(model_raw)
        output = directory / "output"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--input-json", str(problem_file),
             "--input-models", str(model_file), "--output-dir", str(output), *options],
            capture_output=True, encoding="utf-8",
        )
        return result, output, problem_raw, model_raw

    def test_join_by_id_preserves_all_problems_and_missing_difficulty(self):
        problems = [
            {"id": "abc001_1", "contest_id": "abc001", "problem_index": "A", "name": "未建模"},
            {"id": "abc002_a", "contest_id": "abc002", "problem_index": "A", "name": "测试题"},
            {"id": "abc002_b", "contest_id": "abc002", "title": "B. Fallback title"},
            {"id": "abc002_a", "contest_id": "abc002", "name": "Duplicate"},
        ]
        models = {
            "abc002_a": {"difficulty": 800, "is_experimental": False},
            "abc002_b": {"difficulty": None, "is_experimental": True},
        }
        with tempfile.TemporaryDirectory() as temp:
            result, output, problem_raw, model_raw = self.run_export(Path(temp), problems, models, "--limit", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "atcoder_raw.json").read_bytes(), problem_raw)
            self.assertEqual((output / "atcoder_models_raw.json").read_bytes(), model_raw)
            items = json.loads((output / "atcoder_problems.json").read_text(encoding="utf-8"))
            self.assertEqual([p["problem_id"] for p in items], ["abc001_1", "abc002_a", "abc002_b"])
            self.assertIsNone(items[0]["problem_rating"])
            self.assertIsNone(items[0]["difficulty_source"])
            self.assertEqual(items[1]["problem_rating"], 800)
            self.assertEqual(items[1]["difficulty_source"], "atcoder_problems")
            self.assertEqual(items[1]["problem_url"], "https://atcoder.jp/contests/abc002/tasks/abc002_a")
            self.assertEqual(items[2]["problem_name"], "B. Fallback title")
            self.assertTrue(items[2]["difficulty_is_experimental"])
            self.assertIsNone(items[1]["statement_html"])
            sample = json.loads((output / "atcoder_sample.json").read_text(encoding="utf-8"))
            self.assertEqual([p["problem_id"] for p in sample], ["abc002_a"])
            report = json.loads((output / "atcoder_fields.json").read_text(encoding="utf-8"))
            self.assertEqual(report["problem_count"], 4)
            self.assertEqual(report["exported_count"], 3)
            self.assertEqual(report["matched_model_count"], 2)
            self.assertEqual(report["difficulty_missing_count"], 2)
            self.assertEqual(report["problem_fields"]["title"]["present"], 1)

    def test_display_difficulty_and_invalid_model_values(self):
        values = [-1000000, 0, 399, 400, 1200, True, "unknown"]
        problems = [{"id": f"abc001_{i}", "contest_id": "abc001", "name": f"Task {i}"}
                    for i in range(len(values))]
        models = {p["id"]: {"difficulty": value} for p, value in zip(problems, values)}
        with tempfile.TemporaryDirectory() as temp:
            result, output, _, _ = self.run_export(Path(temp), problems, models)
            self.assertEqual(result.returncode, 0, result.stderr)
            items = json.loads((output / "atcoder_problems.json").read_text(encoding="utf-8"))
            self.assertEqual([p["problem_rating"] for p in items], [0, 147, 399, 400, 1200, None, None])
            self.assertEqual(items[1]["difficulty_raw"], 0)

    def test_malformed_models_do_not_export(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output, _, _ = self.run_export(
                Path(temp), [{"id": "abc001_1", "contest_id": "abc001", "name": "Task"}], []
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(output.exists())

    def test_offline_inputs_must_be_paired(self):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--input-json", "unused.json"],
            capture_output=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--input-models", result.stderr)


if __name__ == "__main__":
    unittest.main()
