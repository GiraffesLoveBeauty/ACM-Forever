"""Offline checks for HTTP failures in the local AtCoder collector."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError


CRAWLERS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLERS))
from atcoder_collect import collect


SOURCE = "https://atcoder.jp/contests/asprocon6/tasks/asprocon6_a"


class AtCoderDownloadTests(unittest.TestCase):
    def request(self, status):
        item = {"problem_id": "asprocon6_a", "problem_url": SOURCE}
        store = Mock()
        stderr = io.StringIO()
        error = HTTPError(SOURCE + "?lang=en", status, "HTTP error", {}, None)
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(stderr), \
             patch("atcoder_collect.urlopen", side_effect=error), \
             patch("atcoder_collect.time.sleep"), patch("atcoder_collect.parse_atcoder") as parse:
            result = collect([item], store, "en", Path(directory))
            parse.assert_not_called()
        store.save_content.assert_not_called()
        store.record_failure.assert_called_once()
        self.assertEqual(store.record_failure.call_args.args[:2], ("atcoder", "asprocon6_a"))
        self.assertEqual(result[0], [])
        self.assertFalse(result[2])
        self.assertEqual(len(result[1]), 1)
        return result[1][0]["error"], store.record_failure.call_args.args[2]

    def test_404_stays_a_failure_with_clear_original_site_status_and_url(self):
        message, recorded = self.request(404)
        self.assertIn("HTTP 404", message)
        self.assertIn("题目可能未公开或已移除", message)
        self.assertIn(SOURCE + "?lang=en", message)
        self.assertIsInstance(recorded, ValueError)

    def test_other_http_errors_remain_http_errors(self):
        for status in (403, 503):
            with self.subTest(status=status):
                message, recorded = self.request(status)
                self.assertIn(str(status), message)
                self.assertNotIn("题目可能未公开或已移除", message)
                self.assertIsInstance(recorded, HTTPError)


if __name__ == "__main__":
    unittest.main()
