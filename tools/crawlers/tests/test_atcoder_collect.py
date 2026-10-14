"""Offline checks for statement parsing and durable, resumable SQLite imports."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


CRAWLERS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLERS))
from problem_content import parse_atcoder
from problem_store import ProblemStore


SOURCE_URL = "https://atcoder.jp/contests/abc001/tasks/abc001_1?lang=en"


def statement(body="Solve <var>x &lt; y</var>.", sample_input="1 2\n", sample_output="3\n"):
    return (
        '<div id="task-statement"><span class="lang-en"><div class="part"><section>'
        f"<h3>Problem Statement</h3><p>{body}</p></section></div>"
        f"<section><h3>Sample Input 1</h3><pre>{sample_input}</pre></section>"
        f"<section><h3>Sample Output 1</h3><pre>{sample_output}</pre></section></span></div>"
    ).encode("utf-8")


def metadata(problem_id="abc001_1"):
    return {
        "platform": "atcoder", "problem_id": problem_id, "contest_id": "abc001",
        "problem_name": "Example", "problem_rating": None, "tags": [],
        "problem_url": SOURCE_URL.split("?")[0],
    }


def content(raw=None):
    result = parse_atcoder(raw or statement(), SOURCE_URL)
    result.update(requested_language="en", source_url=SOURCE_URL, sha256="test-hash")
    return result


class StatementTests(unittest.TestCase):
    def test_bilingual_page_selects_only_requested_language_and_preserves_samples(self):
        english = statement(
            body='English <var>x &lt; y</var><img src="/images/example.png">',
            sample_input="  1 &lt; 2\r\n\n3<br>4\n", sample_output="  9\n",
        ).decode("utf-8")
        japanese = '<span class="lang-ja"><h3>入力例 1</h3><pre>日\n</pre><h3>出力例 1</h3><pre>本\n</pre></span>'
        raw = english.replace('<span class="lang-en">', japanese + '<span class="lang-en">').encode("utf-8")
        parsed = parse_atcoder(raw, SOURCE_URL)
        self.assertEqual(parsed["statement_language"], "en")
        self.assertEqual(parsed["samples"], [{"index": 1, "input": "  1 < 2\n\n3\n4\n", "output": "  9\n"}])
        self.assertIn('<var>x &lt; y</var>', parsed["statement_html"])
        self.assertIn('src="https://atcoder.jp/images/example.png"', parsed["statement_html"])
        self.assertIn("Sample Input 1", parsed["statement_html"])
        self.assertNotIn("入力例", parsed["statement_html"])
        self.assertEqual(parse_atcoder(raw, SOURCE_URL, "ja")["samples"][0]["input"], "日\n")

    def test_old_japanese_page_falls_back_and_pairs_samples_by_number(self):
        raw = ('<div id="task-statement"><h3>問題文</h3><p>テスト</p>'
               '<h3>出力例2</h3><pre>-15\n</pre><h3>入力例2</h3><pre>5\n20\n</pre>'
               '<h3>入力例1</h3><pre>15\n10\n</pre><h3>出力例1</h3><pre>5\n</pre></div>').encode("utf-8")
        parsed = parse_atcoder(raw, SOURCE_URL)
        self.assertEqual(parsed["statement_language"], "ja")
        self.assertEqual(parsed["samples"], [
            {"index": 1, "input": "15\n10\n", "output": "5\n"},
            {"index": 2, "input": "5\n20\n", "output": "-15\n"},
        ])

    def test_pre_formatting_newline_is_ignored_but_sample_blank_lines_remain(self):
        parsed = parse_atcoder(statement(sample_input="\r\n\n 15\r\n10\r\n", sample_output="\n5\n"), SOURCE_URL)
        self.assertEqual(parsed["samples"], [{"index": 1, "input": "\n 15\n10\n", "output": "5\n"}])

    def test_login_pages_and_broken_samples_are_rejected(self):
        invalid_pages = [
            b"<html><h1>Sign in</h1></html>",
            b'<div id="task-statement"><h3>Sample Input 1</h3><pre>1</pre></div>',
            b'<div id="task-statement"><h3>Sample Input 1</h3><p>missing pre</p></div>',
            b'<div id="task-statement">   </div>',
        ]
        for raw in invalid_pages:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_atcoder(raw, SOURCE_URL)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "problems.db"
        self.store = ProblemStore(self.path)
        self.addCleanup(self.store.close)
        self.store.import_metadata([metadata()])

    def row(self):
        return self.store.connection.execute("SELECT * FROM crawler_problems").fetchone()

    def test_same_record_contains_body_and_samples_and_metadata_refresh_preserves_them(self):
        original = content()
        self.store.save_content("atcoder", "abc001_1", original)
        self.store.import_metadata([{**metadata(), "problem_name": "Updated name"}])
        row = self.row()
        self.assertEqual(row["problem_name"], "Updated name")
        self.assertEqual(row["statement_html"], original["statement_html"])
        self.assertEqual(json.loads(row["samples"]), original["samples"])
        self.assertEqual(self.store.counts("atcoder"), {"metadata_count": 1, "statement_count": 1, "sample_count": 1})
        self.assertEqual(self.store.completed_ids("atcoder", "en"), {"abc001_1"})
        self.assertEqual(self.store.completed_ids("atcoder", "ja"), set())
        with closing(sqlite3.connect(self.path)) as reader:
            self.assertEqual(reader.execute("SELECT samples FROM crawler_problems").fetchone()[0], row["samples"])

    def test_refresh_replaces_samples_and_failed_refresh_preserves_last_good_content(self):
        self.store.save_content("atcoder", "abc001_1", content())
        replacement = content(statement(body="Updated body", sample_input="8\n", sample_output="16\n"))
        self.store.save_content("atcoder", "abc001_1", replacement)
        self.assertEqual(json.loads(self.row()["samples"]), replacement["samples"])
        with self.assertRaises(ValueError):
            self.store.save_content("atcoder", "abc001_1", {**replacement, "samples": []})
        self.store.record_failure("atcoder", "abc001_1", "incomplete page")
        row = self.row()
        self.assertEqual(row["statement_html"], replacement["statement_html"])
        self.assertEqual(json.loads(row["samples"]), replacement["samples"])
        self.assertEqual(row["last_fetch_status"], "failed")
        self.assertEqual(self.store.completed_ids("atcoder", "en"), set())

    def test_database_failure_rolls_back_body_and_samples_together(self):
        self.store.save_content("atcoder", "abc001_1", content())
        old_row = dict(self.row())
        self.store.connection.executescript(
            "CREATE TRIGGER reject_refresh BEFORE UPDATE OF statement_html ON crawler_problems "
            "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END;"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_content("atcoder", "abc001_1", content(statement(body="New body", sample_output="10\n")))
        self.assertEqual(dict(self.row()), old_row)


class CollectorTests(unittest.TestCase):
    def run_collect(self, directory, *options):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(CRAWLERS / "atcoder_collect.py"),
             "--metadata-json", str(directory / "metadata.json"), "--database", str(directory / "problems.db"),
             "--output-dir", str(directory / "output"), "--html-dir", str(directory / "pages"), *options],
            capture_output=True, encoding="utf-8",
        )

    def test_limited_runs_resume_and_failed_refresh_keeps_previous_data(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "pages").mkdir()
            (directory / "metadata.json").write_text(json.dumps([metadata("abc001_1"), metadata("abc001_2")]), encoding="utf-8")
            for problem_id in ("abc001_1", "abc001_2"):
                (directory / "pages" / (problem_id + ".html")).write_bytes(statement())
            for _ in range(2):
                result = self.run_collect(directory, "--limit", "1")
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads((directory / "output" / "atcoder_content_report.json").read_text(encoding="utf-8"))
                self.assertEqual(report["success_count"], 1)
            result = self.run_collect(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((directory / "output" / "atcoder_content_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["skipped_count"], 2)
            self.assertEqual(report["selected_count"], 0)
            with closing(sqlite3.connect(directory / "problems.db")) as connection:
                old_row = connection.execute(
                    "SELECT statement_html,samples FROM crawler_problems WHERE problem_id='abc001_1'"
                ).fetchone()
            (directory / "pages" / "abc001_1.html").write_bytes(b"<h1>Sign in</h1>")
            result = self.run_collect(directory, "--problem-id", "abc001_1", "--refresh")
            self.assertEqual(result.returncode, 1)
            with closing(sqlite3.connect(directory / "problems.db")) as connection:
                new_row = connection.execute(
                    "SELECT statement_html,samples FROM crawler_problems WHERE problem_id='abc001_1'"
                ).fetchone()
                self.assertEqual(new_row, old_row)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM crawler_problems").fetchone()[0], 2)
            report = json.loads((directory / "output" / "atcoder_content_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["failure_count"], 1)
            self.assertEqual(report["database_counts"], {"metadata_count": 2, "statement_count": 2, "sample_count": 2})


if __name__ == "__main__":
    unittest.main()
