"""Offline checks for metadata export and error handling."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "codeforces_sample.py"


class CodeforcesSampleTests(unittest.TestCase):
    def run_export(self, directory, payload, *options):
        source = directory / "input.json"
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        source.write_bytes(raw)
        output = directory / "output"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--input-json", str(source),
             "--output-dir", str(output), *options],
            capture_output=True, encoding="utf-8", errors="replace",
        )
        return result, output, raw

    def test_export_preserves_raw_and_handles_optional_fields(self):
        payload = {"status": "OK", "result": {"problems": [
            {"contestId": 2000, "index": "A", "name": "测试题", "type": "PROGRAMMING",
             "rating": 800, "tags": ["math"]},
            {"contestId": 2000, "index": "A", "name": "重复记录", "type": "PROGRAMMING",
             "tags": []},
            {"contestId": 2000, "index": "B", "name": "Unrated", "type": "PROGRAMMING",
             "points": 500, "tags": []},
            {"problemsetName": "other", "index": "1", "name": "No contest",
             "type": "PROGRAMMING", "tags": []},
        ], "problemStatistics": []}}
        with tempfile.TemporaryDirectory() as temp:
            result, output, raw = self.run_export(Path(temp), payload, "--limit", "2")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "cf_raw.json").read_bytes(), raw)
            sample = json.loads((output / "cf_sample.json").read_text(encoding="utf-8"))
            self.assertEqual([p["problem_id"] for p in sample], ["2000A", "2000B"])
            self.assertEqual(sample[0]["problem_name"], "测试题")
            self.assertIsNone(sample[1]["problem_rating"])
            self.assertIsNone(sample[0]["statement_html"])
            report = json.loads((output / "cf_fields.json").read_text(encoding="utf-8"))
            self.assertEqual(report["problem_count"], 4)
            self.assertEqual(report["fields"]["rating"]["missing"], 3)
            self.assertEqual(report["fields"]["problemsetName"]["present"], 1)
            self.assertEqual(report["fields"]["tags"]["types"], ["array"])

    def test_failed_api_response_does_not_export(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output, _ = self.run_export(
                Path(temp), {"status": "FAILED", "comment": "Call limit exceeded"}
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Call limit exceeded", result.stderr)
            self.assertFalse(output.exists())

    def test_invalid_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output, _ = self.run_export(Path(temp), {}, "--limit", "0")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
