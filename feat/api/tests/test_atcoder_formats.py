"""Public special statement formats, using short synthetic examples offline."""

import json
import unittest
from unittest.mock import patch

import test_problem_sync as contract
from feat.api.acm_api.problem_content import parse_atcoder
from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL


SOURCE = 'https://atcoder.jp/contests/example/tasks/example_a?lang=en'


def page(body):
    return ('<div id="task-statement"><span class="lang-en"><h3>Problem Statement</h3>'
            '<p>Synthetic problem.</p>' + body + '</span></div>').encode('utf-8')


OUTPUT_ONLY = page('<h3>Input</h3><p>No input is given for this problem.</p>'
                   '<h3>Sample Output</h3><pre>example\n</pre>')
OMITTED = page('<h3>入力例1</h3><pre>1\n</pre><h3>出力例1</h3>'
               '<p>出力は膨大な量になるため記載しません。最小のコストは約 12 です。</p>'
               '<h3>入力例2</h3><pre>2\n</pre><h3>出力例2</h3>'
               '<p>このケースに対する最小のコストは約 15 です。</p>')


class SpecialStatementTests(unittest.TestCase):
    def test_only_explicit_empty_input_allows_missing_sample_input(self):
        for text in ['No input is given for this problem.', 'This problem provides no input.',
                     'The input given from Standard Input is empty.', '今回、入力は与えられない。',
                     'この問題に入力はありません']:
            raw = OUTPUT_ONLY.replace(b'No input is given for this problem.', text.encode('utf-8'))
            with self.subTest(text=text):
                self.assertEqual(parse_atcoder(raw, SOURCE)['samples'],
                                 [{'index': 1, 'output': 'example\n', 'input': ''}])
        for raw in [OUTPUT_ONLY.replace(b'No input is given for this problem.', b'An integer is given.'),
                    OUTPUT_ONLY.replace(b'No input is given for this problem.',
                                        b'The input contains a string that is empty if N is zero.'),
                    OUTPUT_ONLY.replace(b'No input is given for this problem.',
                                        '空行が入力に含まれることはありません。'.encode('utf-8')),
                    OUTPUT_ONLY.replace(b'<h3>Input</h3>', b'<h3>Note</h3>')]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_atcoder(raw, SOURCE)

    def test_omitted_outputs_are_notes_not_empty_or_invented_answers(self):
        parsed = parse_atcoder(OMITTED, SOURCE)
        self.assertEqual([sample['input'] for sample in parsed['samples']], ['1\n', '2\n'])
        for sample in parsed['samples']:
            self.assertIsNone(sample['output'])
            self.assertIn('最小のコスト', sample['output_note'])
        self.assertIn('記載しません', parsed['statement_text'])

    def test_missing_pre_remains_invalid_without_explicit_output_omission(self):
        for raw in [OMITTED.replace('出力は膨大な量になるため記載しません。'.encode('utf-8'), b''),
                    OMITTED.replace('このケースに対する最小のコストは約 15 です。'.encode('utf-8'), b'missing pre'),
                    page('<h3>Sample Input 1</h3><p>missing pre</p>'
                         '<h3>Sample Output 1</h3><pre>2</pre>')]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_atcoder(raw, SOURCE)

    def test_placeholder_does_not_become_a_successful_empty_statement(self):
        with self.assertRaisesRegex(ValueError, '原站未提供题面正文'):
            parse_atcoder(b'<div id="task-statement"> \n </div>', SOURCE)


class SpecialFormatSyncTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ProblemSyncTests.asyncSetUp
    asyncTearDown = contract.ProblemSyncTests.asyncTearDown
    login = contract.ProblemSyncTests.login
    query = contract.ProblemSyncTests.query
    submit_platform = contract.ProblemSyncTests.submit_platform

    async def test_special_samples_persist_resume_and_survive_a_broken_refresh(self):
        catalog = [{'id': 'example_a', 'contest_id': 'example', 'name': 'Output only'},
                   {'id': 'example_b', 'contest_id': 'example', 'name': 'Omitted output'}]
        broken = False

        async def download(http, url):
            if url == ATCODER_CATALOG_URL:
                return json.dumps(catalog).encode()
            if broken:
                return page('<h3>Sample Input 1</h3><pre>1</pre>')
            return OUTPUT_ONLY if 'example_a?' in url else OMITTED

        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, 'download', side_effect=download):
                task = await self.submit_platform(client, headers)
                self.assertEqual(task['status'], 'completed')
                self.assertEqual(task['result']['success_count'], 2)
                self.assertEqual(task['result']['sample_count'], 3)
                before = await self.query('SELECT statement_html,samples,statement_sha256 FROM crawler_problems ORDER BY problem_id')
                stored = json.loads(before[1]['samples'])
                self.assertIsNone(stored[0]['output'])
                self.assertIn('output_note', stored[0])
                detail = await (await client.get('/api/problems/atcoder/example_b')).get_json()
                self.assertTrue(detail['content_available'])
                self.assertEqual(detail['samples'], stored)
                resumed = await self.submit_platform(client, headers)
                self.assertEqual(resumed['result']['skipped_count'], 2)
                broken = True
                failed = await self.submit_platform(client, headers, refresh=True)
                self.assertEqual(failed['status'], 'failed')
                self.assertEqual(failed['result']['failure_count'], 2)
            self.assertEqual(await self.query('SELECT statement_html,samples,statement_sha256 FROM crawler_problems ORDER BY problem_id'), before)


if __name__ == '__main__':
    unittest.main()
