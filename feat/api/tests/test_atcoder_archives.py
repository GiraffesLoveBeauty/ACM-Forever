"""Offline contracts for numbered-zero examples and official sample ZIP references."""

import html
import json
import unittest
from unittest.mock import patch

import test_problem_sync as contract
from feat.api.acm_api.problem_content import parse_atcoder
from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL


SOURCE = 'https://atcoder.jp/contests/example/tasks/example_a?lang=en'
ARCHIVE = 'https://img.atcoder.jp/example/sample-files.zip'
ARCHIVE_NAME = 'Official input files ZIP'


def page(body):
    return ('<div id="task-statement"><span class="lang-en">'
            '<h3>Problem Statement</h3><p>Synthetic attached-sample problem.</p>'
            + body + '</span></div>').encode('utf-8')


def link(url=ARCHIVE, name=ARCHIVE_NAME):
    return f'<p><a href="{html.escape(url, quote=True)}">{html.escape(name)}</a></p>'


INLINE_ZERO = ('<h3>入力例0</h3><pre>zero input\n</pre>'
               '<h3>出力例0</h3><pre>zero output\n</pre>')
ATTACHED = page(INLINE_ZERO + '<h3>入力例1</h3>' + link())


class ArchiveSampleTests(unittest.TestCase):
    def test_zero_numbered_samples_keep_source_numbering_and_archive_samples_remain_references(self):
        parsed = parse_atcoder(ATTACHED, SOURCE)
        first, attached = parsed['samples']
        self.assertEqual([sample['index'] for sample in parsed['samples']], [1, 2])
        self.assertEqual([sample['source_index'] for sample in parsed['samples']], [0, 1])
        self.assertEqual(first['input'], 'zero input\n')
        self.assertEqual(first['output'], 'zero output\n')
        for kind in ['input', 'output']:
            self.assertIsNone(attached[kind])
            self.assertTrue(attached[kind + '_note'])
        self.assertEqual(attached['attachments'], [{'url': ARCHIVE, 'name': ARCHIVE_NAME}])
        self.assertIn(ARCHIVE, parsed['statement_html'])
        self.assertIn(ARCHIVE_NAME, parsed['statement_text'])

    def test_untrusted_or_nonarchive_links_do_not_replace_missing_sample_text(self):
        for url in ['https://evil.test/samples.zip', 'https://img.atcoder.jp.evil.test/samples.zip',
                    'http://img.atcoder.jp/samples.zip', 'javascript:alert(1)',
                    'https://user:password@img.atcoder.jp/samples.zip',
                    'https://img.atcoder.jp:444/samples.zip', 'https://img.atcoder.jp:bad/samples.zip',
                    'https://img.atcoder.jp/samples.txt', 'https://img.atcoder.jp/samples.zip/other',
                    'https://[invalid/samples.zip', 'not a URL']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_atcoder(page('<h3>Sample Input 1</h3>' + link(url)), SOURCE)
        for tag in ['pre', 'code']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                parse_atcoder(page(f'<h3>Sample Input 1</h3><{tag}>' + link() + f'</{tag}>'), SOURCE)

    def test_the_same_archive_in_input_and_output_is_deduplicated_by_url(self):
        raw = page('<h3>Sample Input 1</h3>' + link(name='Input files')
                   + link(name='Download input again')
                   + '<h3>Sample Output 1</h3>' + link(name='Output files'))
        attached = parse_atcoder(raw, SOURCE)['samples'][0]
        self.assertEqual(attached['attachments'], [{'url': ARCHIVE, 'name': 'Input files'}])
        self.assertIsNone(attached['input'])
        self.assertIsNone(attached['output'])
        self.assertIn('input_note', attached)
        self.assertIn('output_note', attached)


class ArchiveSyncTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ProblemSyncTests.asyncSetUp
    asyncTearDown = contract.ProblemSyncTests.asyncTearDown
    login = contract.ProblemSyncTests.login
    query = contract.ProblemSyncTests.query
    submit_platform = contract.ProblemSyncTests.submit_platform

    async def test_archive_metadata_survives_store_detail_resume_and_failed_refresh(self):
        catalog = [{'id': 'example_a', 'contest_id': 'example', 'name': 'Attached samples'}]
        broken = False

        async def download(http, url):
            if url == ATCODER_CATALOG_URL:
                return json.dumps(catalog).encode()
            return page('<h3>Sample Input 1</h3><pre>broken replacement</pre>') if broken else ATTACHED

        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, 'download', side_effect=download) as fetch:
                first = await self.submit_platform(client, headers)
                self.assertEqual(first['status'], 'completed')
                self.assertEqual(first['result']['success_count'], 1)
                self.assertEqual(first['result']['sample_count'], 2)
                before = await self.query('SELECT statement_html,samples,statement_sha256 FROM crawler_problems')
                stored = json.loads(before[0]['samples'])
                self.assertEqual([sample['source_index'] for sample in stored], [0, 1])
                self.assertEqual([sample['index'] for sample in stored], [1, 2])
                attached = stored[1]
                self.assertEqual(attached['attachments'], [{'url': ARCHIVE, 'name': ARCHIVE_NAME}])
                self.assertIsNone(attached['input'])
                self.assertIsNone(attached['output'])
                self.assertIn('input_note', attached)
                self.assertIn('output_note', attached)
                detail = await (await client.get('/api/problems/atcoder/example_a')).get_json()
                self.assertTrue(detail['content_available'])
                self.assertEqual(detail['samples'], stored)
                fetch.reset_mock()
                resumed = await self.submit_platform(client, headers)
                self.assertEqual(resumed['result']['skipped_count'], 1)
                self.assertEqual(resumed['result']['selected_count'], 0)
                self.assertEqual(fetch.await_count, 1, 'only the catalog is fetched on resume')
                broken = True
                refreshed = await self.submit_platform(client, headers, refresh=True)
                self.assertEqual(refreshed['status'], 'failed')
                self.assertEqual(refreshed['result']['failure_count'], 1)
            self.assertEqual(await self.query('SELECT statement_html,samples,statement_sha256 FROM crawler_problems'), before)
            detail = await (await client.get('/api/problems/atcoder/example_a')).get_json()
            self.assertTrue(detail['content_available'])
            self.assertEqual(detail['last_fetch_status'], 'failed')
            self.assertEqual(detail['samples'], stored)


if __name__ == '__main__':
    unittest.main()
