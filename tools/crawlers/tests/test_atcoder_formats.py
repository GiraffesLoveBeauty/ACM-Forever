"""Offline regressions for AtCoder tutorials and historical sample markup."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from problem_content import parse_atcoder


def page(body, title="A - Example"):
    return (f'<span class="h2">{title}</span><div id="task-statement">'
            f'<h3>問題文</h3><p>Synthetic problem.</p>{body}</div>').encode("utf-8")


def source(contest="abc001", task="abc001_1"):
    return f"https://atcoder.jp/contests/{contest}/tasks/{task}?lang=en"


class AtCoderFormatTests(unittest.TestCase):
    def test_formal_numbered_samples_take_priority_over_narrative_examples(self):
        for tag in ("h4", "h5"):
            raw = page(
                f'<{tag}>入力例</{tag}><pre>narrative input\n</pre>'
                f'<{tag}>出力例</{tag}><pre>narrative output\n</pre>'
                '<h3>入力例1</h3><pre>1\n</pre>'
                '<h3>出力例1</h3><pre>2\n</pre>'
                '<h3>入力例2</h3><pre>3\n</pre>'
                '<h3>出力例2</h3><pre>4\n</pre>',
                title="EX9 - Synthetic exercise",
            )
            with self.subTest(tag=tag):
                parsed = parse_atcoder(raw, source("APG4b", "APG4b_cl"))
                self.assertEqual(parsed["samples"], [
                    {"index": 1, "input": "1\n", "output": "2\n"},
                    {"index": 2, "input": "3\n", "output": "4\n"},
                ])
                self.assertIn("narrative input", parsed["statement_html"])
                self.assertIn("narrative output", parsed["statement_text"])

    def test_tutorial_exercise_wrong_answer_output_is_not_a_formal_sample(self):
        for contest in ("APG4b", "APG4bPython"):
            for heading in ("回答例", "解答例"):
                raw = page(
                    '<h3>入力</h3><p>この問題に入力はありません</p>'
                    '<h3>出力</h3><p>AtCoder と出力してください。</p>'
                    f'<section><h3>{heading}</h3><p>不正解となります。</p>'
                    '<pre>print("YoCoder")</pre>'
                    '<h3>出力例</h3><pre>YoCoder\n</pre></section>',
                    title="EX7 - Synthetic exercise",
                )
                with self.subTest(contest=contest, heading=heading):
                    parsed = parse_atcoder(raw, source(contest, contest + "_cp"))
                    self.assertEqual(parsed["samples"], [])
                    self.assertIn("YoCoder", parsed["statement_html"])
                    self.assertIn("不正解となります", parsed["statement_text"])

    def test_numbered_samples_at_lower_heading_levels_are_not_discarded(self):
        body = ('<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
                '<h4>入力例2</h4><pre>3</pre><h4>出力例2</h4><pre>4</pre>')
        parsed = parse_atcoder(page(body, title='EX1 - Example'), source('APG4b', 'APG4b_ca'))
        self.assertEqual([sample['input'] for sample in parsed['samples']], ['1', '3'])
        with self.assertRaises(ValueError):
            parse_atcoder(page(body.replace('<pre>3</pre>', '<p>missing pre</p>'),
                               title='EX1 - Example'), source('APG4b', 'APG4b_ca'))

    def test_tutorial_exercise_keeps_formal_samples_outside_answer_explanations(self):
        raw = page(
            '<section><h3>回答例</h3><p>This answer is incorrect.</p>'
            '<h4>出力例</h4><pre>incorrect\n</pre></section>'
            '<section><h3>入力例1</h3><pre>5\n</pre></section>'
            '<section><h3>出力例1</h3><pre>10\n</pre></section>',
            title="EX1 - Synthetic exercise",
        )
        parsed = parse_atcoder(raw, source("APG4b", "APG4b_ca"))
        self.assertEqual(parsed["samples"], [{"index": 1, "input": "5\n", "output": "10\n"}])

    def test_tutorial_lesson_preserves_independent_examples_in_the_statement(self):
        raw = page(
            '<h1>例題 First example</h1>'
            '<h5>入力例1</h5><pre>6\n</pre><h5>実行結果</h5><pre>3\n</pre>'
            '<h3>解答例</h3><h5>入力例1</h5><pre>6\n</pre>'
            '<h5>実行結果</h5><pre>3\n</pre>'
            '<h1>例題 Second example</h1>'
            '<h5>入力例1</h5><pre>grid\n</pre><h5>出力例1</h5><pre>Yes\n</pre>',
            title="V - 2.05.再帰関数",
        )
        parsed = parse_atcoder(raw, source("APG4b", "APG4b_v"))
        self.assertEqual(parsed["samples"], [])
        self.assertIn("First example", parsed["statement_text"])
        self.assertIn("Second example", parsed["statement_text"])
        self.assertIn("<pre>grid\n</pre>", parsed["statement_html"])
        self.assertIn("実行結果", parsed["statement_text"])

    def test_adjacent_historical_pairs_recover_repeated_output_numbers_without_overwriting(self):
        for wrong_number in (1, 2):
            raw = page(
                '<section><h3>入力例1</h3><pre>10\n</pre></section>'
                '<section><h3>出力例1</h3><pre>11\n</pre></section>'
                '<section><h3>入力例2</h3><pre>20\n</pre></section>'
                '<section><h3>出力例2</h3><pre>21\n</pre></section>'
                '<section><h3>入力例3</h3><pre>30\n</pre></section>'
                f'<section><h3>出力例{wrong_number}</h3><pre>31\n</pre></section>'
            )
            with self.subTest(wrong_number=wrong_number):
                self.assertEqual(parse_atcoder(raw, source())["samples"], [
                    {"index": 1, "input": "10\n", "output": "11\n"},
                    {"index": 2, "input": "20\n", "output": "21\n"},
                    {"index": 3, "input": "30\n", "output": "31\n"},
                ])
        two_pairs = page('<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
                         '<h3>入力例2</h3><pre>3</pre><h3>出力例1</h3><pre>4</pre>')
        self.assertEqual(parse_atcoder(two_pairs, source())["samples"], [
            {"index": 1, "input": "1", "output": "2"},
            {"index": 2, "input": "3", "output": "4"},
        ])

    def test_unique_sample_numbers_still_pair_correctly_when_output_comes_first(self):
        raw = page('<h3>出力例2</h3><pre>20</pre><h3>入力例2</h3><pre>10</pre>'
                   '<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>')
        self.assertEqual(parse_atcoder(raw, source())["samples"], [
            {"index": 1, "input": "1", "output": "2"},
            {"index": 2, "input": "10", "output": "20"},
        ])

    def test_ambiguous_or_incomplete_samples_are_not_repaired(self):
        malformed = [
            '<h3>入力例1</h3><pre>1</pre><h3>入力例2</h3><pre>2</pre>',
            '<h3>入力例1</h3><p>missing pre</p><h3>出力例1</h3><pre>2</pre>',
            '<h3>入力例1</h3><pre>1</pre><h3>入力例2</h3><pre>2</pre>'
            '<h3>出力例1</h3><pre>3</pre><h3>出力例1</h3><pre>4</pre>',
            '<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
            '<h3>出力例1</h3><pre>4</pre><h3>入力例2</h3><pre>3</pre>',
            '<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
            '<h3>入力例3</h3><pre>3</pre><h3>出力例1</h3><pre>4</pre>',
        ]
        for body in malformed:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_atcoder(page(body), source())


if __name__ == "__main__":
    unittest.main()
