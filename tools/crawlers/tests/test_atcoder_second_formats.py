"""Offline regressions for legacy no-input, translation, and supplemental examples."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from problem_content import parse_atcoder


SOURCE = 'https://atcoder.jp/contests/example/tasks/example_a?lang=en'
SUPPLEMENT_NOTE = 'この入力は採点用テストケースに含まれません。'


def page(body):
    return ('<div id="task-statement">' + body + '</div>').encode('utf-8')


def language_body(language, body):
    return f'<span class="lang-{language}"><h3>Problem Statement</h3><p>{language} statement.</p>{body}</span>'


class LegacyAtCoderFormatTests(unittest.TestCase):
    def test_more_explicit_no_input_sentences_and_fullwidth_period(self):
        for heading, declaration in [
            ('Input', 'There is no input in this problem.'),
            ('入力', 'この問題には入力はありません。'),
            ('入力', 'この問題には入力はない．'),
            ('入力', 'この問題では入力は与えられない。'),
        ]:
            raw = page(f'<h3>{heading}</h3><p>{declaration}</p>'
                       '<h3>Sample Output 1</h3><pre>example\n</pre>')
            with self.subTest(declaration=declaration):
                self.assertEqual(parse_atcoder(raw, SOURCE)['samples'],
                                 [{'index': 1, 'input': '', 'output': 'example\n'}])

    def test_conditional_or_negated_input_descriptions_are_not_empty_input(self):
        for declaration in [
            'There is no input in this problem if N is zero.',
            'この問題には入力はない場合もあります。',
            'この問題には入力はありませんという説明は誤りです。',
        ]:
            raw = page(f'<h3>Input</h3><p>{declaration}</p>'
                       '<h3>Sample Output 1</h3><pre>example</pre>')
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                parse_atcoder(raw, SOURCE)

    def test_broken_preferred_translation_falls_back_as_a_whole(self):
        japanese = ('<h3>入力例1</h3><pre>1\n</pre><h3>出力例1</h3><pre>2\n</pre>'
                    '<h3>入力例2</h3><pre>3\n</pre><h3>出力例2</h3><pre>4\n</pre>')
        broken_english = ('<h3>Sample Input 1</h3><pre>1\n</pre>'
                          '<h3>Sample Output 1</h3><pre>2\n</pre>'
                          '<h3>Sample Output 2</h3><pre>3\n</pre>'
                          '<h3>Sample Output 2</h3><pre>4\n</pre>')
        raw = page(language_body('ja', japanese) + language_body('en', broken_english))
        parsed = parse_atcoder(raw, SOURCE, 'en')
        self.assertEqual(parsed['statement_language'], 'ja')
        self.assertIn('ja statement.', parsed['statement_text'])
        self.assertNotIn('en statement.', parsed['statement_text'])
        self.assertIn('入力例2', parsed['statement_html'])
        self.assertNotIn('Sample Output 2', parsed['statement_html'])
        self.assertEqual(parsed['samples'], [
            {'index': 1, 'input': '1\n', 'output': '2\n'},
            {'index': 2, 'input': '3\n', 'output': '4\n'},
        ])

    def test_valid_preferred_translation_does_not_switch_languages(self):
        good_english = '<h3>Sample Input 1</h3><pre>1</pre><h3>Sample Output 1</h3><pre>2</pre>'
        broken_japanese = '<h3>入力例1</h3><pre>3</pre>'
        parsed = parse_atcoder(page(language_body('ja', broken_japanese)
                                    + language_body('en', good_english)), SOURCE, 'en')
        self.assertEqual(parsed['statement_language'], 'en')
        self.assertEqual(parsed['samples'], [{'index': 1, 'input': '1', 'output': '2'}])

    def test_both_translations_broken_still_fail(self):
        raw = page(language_body('ja', '<h3>入力例1</h3><pre>1</pre>')
                   + language_body('en', '<h3>Sample Output 1</h3><pre>2</pre>'))
        with self.assertRaises(ValueError):
            parse_atcoder(raw, SOURCE)

    def test_explicit_supplemental_input_keeps_its_note_without_fabricating_output(self):
        body = ('<h3>入力例1</h3><pre>1\n</pre><h3>出力例1</h3><pre>2\n</pre>'
                f'<h3>入力例2</h3><pre>3\n</pre><p>{SUPPLEMENT_NOTE}</p>')
        parsed = parse_atcoder(page(body), SOURCE)
        self.assertEqual(parsed['samples'], [
            {'index': 1, 'input': '1\n', 'output': '2\n'},
            {'index': 2, 'input': '3\n', 'output': None, 'output_note': SUPPLEMENT_NOTE},
        ])
        self.assertIn(SUPPLEMENT_NOTE, parsed['statement_text'])
        self.assertIn('<pre>3\n</pre>', parsed['statement_html'])

    def test_missing_output_is_not_excused_by_an_unrelated_supplement_note(self):
        for body in [
            '<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
            '<h3>入力例2</h3><pre>3</pre>',
            '<h3>入力例1</h3><pre>1</pre><h3>出力例1</h3><pre>2</pre>'
            f'<p>{SUPPLEMENT_NOTE}</p><h3>入力例2</h3><pre>3</pre>',
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_atcoder(page(body), SOURCE)


if __name__ == '__main__':
    unittest.main()
