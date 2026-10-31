"""Offline regressions for historical ICPC sample headings and unnumbered pairs."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from problem_content import parse_atcoder


SOURCE = 'https://atcoder.jp/contests/jag2013summer-warmingup/tasks/icpc2013summer_warmingUp_a?lang=en'


def page(body):
    return ('<div id="task-statement"><h3>Problem Statement</h3>'
            '<p>Synthetic ICPC problem.</p>' + body + '</div>').encode('utf-8')


def section(heading, value):
    return f'<h3>{heading}</h3><section><pre>{value}</pre></section>'


class ICPCFormatTests(unittest.TestCase):
    def test_output_for_sample_input_aliases_accept_numbers_case_and_colons(self):
        for heading in ['Output for the Sample Input 1', 'Output for Sample Input 1:',
                        'OUTPUT FOR THE SAMPLE INPUT 1：', 'output for sample input 1 :']:
            with self.subTest(heading=heading):
                raw = page(section('Sample Input 1', '  1\n2\n') + section(heading, '3\n'))
                self.assertEqual(parse_atcoder(raw, SOURCE)['samples'],
                                 [{'index': 1, 'input': '  1\n2\n', 'output': '3\n'}])

    def test_all_unnumbered_adjacent_pairs_are_numbered_in_document_order(self):
        for output_heading in ['Sample Output', 'Output for the Sample Input', 'Output for Sample Input']:
            raw = page(section('Sample Input', '10\n') + section(output_heading, '11\n')
                       + section('Sample Input', '20\n') + section(output_heading, '21\n')
                       + section('Sample Input', '30\n') + section(output_heading, '31\n'))
            with self.subTest(output_heading=output_heading):
                self.assertEqual(parse_atcoder(raw, SOURCE)['samples'], [
                    {'index': 1, 'input': '10\n', 'output': '11\n'},
                    {'index': 2, 'input': '20\n', 'output': '21\n'},
                    {'index': 3, 'input': '30\n', 'output': '31\n'},
                ])

    def test_single_unnumbered_alias_pair_keeps_index_one(self):
        raw = page(section('Sample Input', '1\n') + section('Output for the Sample Input', '2\n'))
        self.assertEqual(parse_atcoder(raw, SOURCE)['samples'],
                         [{'index': 1, 'input': '1\n', 'output': '2\n'}])

    def test_mixed_numbering_does_not_repair_ambiguous_unnumbered_pairs(self):
        for body in [
            section('Sample Input', '1') + section('Sample Output', '2')
            + section('Sample Input', '3') + section('Sample Output 2', '4'),
            section('Sample Input 1', '1') + section('Sample Output', '2')
            + section('Sample Input', '3') + section('Sample Output', '4'),
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_atcoder(page(body), SOURCE)

    def test_unnumbered_pairs_must_be_complete_alternating_and_adjacent(self):
        malformed = [
            section('Sample Input', '1') + section('Sample Input', '2')
            + section('Sample Output', '3') + section('Sample Output', '4'),
            section('Sample Output', '2') + section('Sample Input', '1')
            + section('Sample Output', '4') + section('Sample Input', '3'),
            section('Sample Input', '1') + section('Sample Output', '2') + section('Sample Input', '3'),
            '<h3>Sample Input</h3><p>missing pre</p>' + section('Sample Output', '2')
            + section('Sample Input', '3') + section('Sample Output', '4'),
            section('Sample Input', '1') + '<h3>Explanation</h3><p>Another section.</p>'
            + section('Sample Output', '2') + section('Sample Input', '3') + section('Sample Output', '4'),
        ]
        for body in malformed:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_atcoder(page(body), SOURCE)

    def test_numbered_pairs_may_still_put_outputs_before_inputs(self):
        raw = page(section('Output for Sample Input 2', '20') + section('Sample Input 2', '10')
                   + section('Sample Output 1', '2') + section('Sample Input 1', '1'))
        self.assertEqual(parse_atcoder(raw, SOURCE)['samples'], [
            {'index': 1, 'input': '1', 'output': '2'},
            {'index': 2, 'input': '10', 'output': '20'},
        ])

    def test_sample_data_and_quoted_text_are_not_supplemental_input_declarations(self):
        marker = 'この入力は採点用テストケースに含まれません'
        for body in [section('Sample Input 1', marker + '\n'),
                     section('Sample Input 1', f'<p>{marker}</p>'),
                     section('Sample Input 1', f'<code><p>{marker}</p></code>'),
                     section('Sample Input 1', '1\n')
                     + f'<p>「{marker}」という説明は誤りです。</p>']:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_atcoder(page(body), SOURCE)

    def test_unrelated_zip_does_not_replace_a_missing_text_sample_output(self):
        body = (section('Sample Input 1', '1\n')
                + '<p>Visualizer: <a href="https://img.atcoder.jp/example/visualizer.zip">'
                'visualizer</a></p>')
        with self.assertRaises(ValueError):
            parse_atcoder(page(body), SOURCE)


if __name__ == '__main__':
    unittest.main()
