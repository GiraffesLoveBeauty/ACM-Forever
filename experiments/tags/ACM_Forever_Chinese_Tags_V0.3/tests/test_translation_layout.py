"""ID-bound local layout: synthetic statements, no sockets and no paid requests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from problem_processing.adapter import normalize
from problem_processing.executor import execute_batch
from problem_processing.execution_state import Ledger
from problem_processing.planning import Planner, task_policies
from problem_processing.translation import (MockTranslationClient, language_plan,
    prepare_layout_request, parse_translation, translate)
from problem_processing.translation_layout import build_layout, fill_layout


def problem(text, **extra):
    return normalize({'platform': 'atcoder', 'problem_key': 'atcoder:offline:offline_layout',
        'title': 'Synthetic local layout', 'statement_markdown': text, 'statement_status': 'ok',
        'language_hint': 'en', **extra})


class LayoutTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket.connect', side_effect=AssertionError('NO NETWORK'))
        guard.start(); self.addCleanup(guard.stop)
        self.source = ('# Problem Statement\n\nRead the following figure.\n\n'
            '![diagram](https://img.atcoder.jp/offline/figure(1).png)\n\n'
            'Calculate $N+1$ from the input.\n\n- Print the answer.\n\n'
            '```\n1  2\n\n```\n\nSee [the source](https://atcoder.jp/contests/offline/tasks/offline_layout).')
        self.p = problem(self.source)
        self.prepared = prepare_layout_request(self.p, language_plan(self.p))

    def response(self, prepared=None):
        return json.loads(MockTranslationClient().call((prepared or self.prepared)['messages']).content)

    def fill(self, value=None):
        return parse_translation(json.dumps(self.response() if value is None else value), self.prepared)[1]

    def test_only_text_slots_are_sent(self):
        payload = json.loads(self.prepared['messages'][1]['content'])
        sent = json.dumps(payload)
        for content in ('img.atcoder.jp', '$N+1$', '1  2', '```', '![diagram]', 'parts', '__ACM_KEEP_'):
            self.assertNotIn(content, sent)
        self.assertEqual(set(payload['segments'][0]), {'id', 'text'})
        self.assertEqual(self.prepared['layout']['image_count'], 1)

    def test_images_math_samples_and_links_keep_local_order(self):
        statement = self.fill()
        image = '![diagram](https://img.atcoder.jp/offline/figure(1).png)'
        self.assertIn(image, statement)
        self.assertIn('```\n1  2\n\n```', statement)
        self.assertIn('](https://atcoder.jp/contests/offline/tasks/offline_layout)', statement)
        self.assertLess(statement.index(image), statement.index('$N+1$'))
        self.assertLess(statement.index('$N+1$'), statement.index('```'))
        self.assertTrue(statement.startswith('# '))
        self.assertIn('\n\n- ', statement)

    def test_reordered_response_is_joined_by_id_not_response_order(self):
        value = self.response()
        expected = self.fill(value)
        value['segments'].reverse()
        self.assertEqual(self.fill(value), expected)

    def test_missing_segment_is_not_silently_filled_with_source(self):
        value = self.response(); value['segments'].pop()
        with self.assertRaisesRegex(ValueError, '缺少'): self.fill(value)

    def test_duplicate_id_rejected(self):
        value = self.response(); value['segments'].append(deepcopy(value['segments'][0]))
        with self.assertRaises(ValueError): self.fill(value)

    def test_unknown_id_rejected(self):
        value = self.response(); value['segments'][0]['id'] = 999999
        with self.assertRaises(ValueError): self.fill(value)

    def test_boolean_id_is_not_an_integer_identity(self):
        value = self.response(); value['segments'][0]['id'] = False
        with self.assertRaises(ValueError): self.fill(value)

    def test_empty_slot_and_title_rejected(self):
        for title, text in [(' ', '中文'), ('题名', ' ')]:
            value = self.response(); value['title_zh'] = title; value['segments'][0]['text'] = text
            with self.assertRaises(ValueError): self.fill(value)

    def test_model_markup_cannot_add_an_image_heading_or_html(self):
        value = self.response()
        value['segments'][0]['text'] = '# 新标题\n\n![fake](https://evil.invalid/x)<script>bad()</script>'
        result = self.fill(value)
        self.assertIn('\\!&#91;fake&#93;', result)
        self.assertIn('&lt;script&gt;', result)
        self.assertEqual(result.count('\n'), self.source.count('\n'))

    def test_numbers_and_chinese_quality_are_not_strict_content_gates(self):
        value = self.response(); value['segments'][0]['text'] = 'Returned English 999'
        self.assertIn('Returned English 999', self.fill(value))

    def test_prepared_layout_and_payload_not_mutated(self):
        before = deepcopy(self.prepared); value = self.response(); original = deepcopy(value)
        self.fill(value)
        self.assertEqual(self.prepared, before); self.assertEqual(value, original)

    def test_source_and_layout_hashes_are_stable_and_sensitive_to_content(self):
        a, b = build_layout(self.source), build_layout(self.source)
        self.assertEqual(a, b)
        changed = build_layout(self.source.replace('figure(1)', 'figure(2)'))
        self.assertNotEqual(a['layout_sha256'], changed['layout_sha256'])
        self.assertNotEqual(a['source_sha256'], changed['source_sha256'])

    def test_tables_emphasis_blockquotes_and_lists_stay_local(self):
        source = '> ## Heading\n> **Important words**\n\n1. Read the table.\n\n| Name | Value |\n| --- | --- |\n| Test | $N$ |'
        layout = build_layout(source)
        value = {'title_zh': '模拟', 'segments': [{'id':s['id'], 'text':'中文'} for s in layout['segments']]}
        result = fill_layout(value, layout)[1]
        for marker in ('> ## ', '> **', '**\n', '1. ', '| --- | --- |', '| $N$ |'):
            self.assertIn(marker, result)

    def test_linked_and_reference_images_stay_local(self):
        source = '[![diagram](https://img.atcoder.jp/offline/a.png)](https://atcoder.jp/)\n\n![map][img]\n\n[img]: https://img.atcoder.jp/offline/map.png'
        layout = build_layout(source)
        self.assertEqual(layout['image_count'], 2)
        self.assertEqual(layout['segments'], [])
        self.assertEqual(fill_layout({'title_zh':'模拟', 'segments':[]}, layout)[1], source)

    def test_raw_html_images_and_code_remain_at_source_positions(self):
        source = 'Read this figure.\n\n<img src="https://img.atcoder.jp/x.png" alt="原图">\n\n<pre>do_not_translate()</pre>\n\nPrint the answer.'
        layout = build_layout(source)
        value = {'title_zh':'模拟', 'segments':[{'id':s['id'],'text':'中文'} for s in layout['segments']]}
        result = fill_layout(value, layout)[1]
        self.assertIn('<pre>do_not_translate()</pre>', result)
        self.assertLess(result.index('<img'), result.index('<pre>'))
        self.assertNotIn('src=', json.dumps(layout['segments']))

    def test_crlf_code_bytes_are_preserved(self):
        source = 'Read the input.\r\n\r\n```\r\n 1 2 \r\nprint(answer)\r\n\r\n```\r\n'
        layout = build_layout(source)
        result = fill_layout({'title_zh':'模拟', 'segments':[{'id':s['id'],'text':'中文'} for s in layout['segments']]},layout)[1]
        self.assertIn('```\r\n 1 2 \r\nprint(answer)\r\n\r\n```\r\n', result)

    def test_direct_mock_stores_layout_metadata_and_reuses_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            client = MockTranslationClient()
            first = translate(self.p, root=Path(temp)/'labels', mock=True, client=client)
            second = translate(self.p, root=Path(temp)/'labels', mock=True, client=client)
        self.assertEqual(first['translation_validation_mode'], 'layout_by_id')
        self.assertEqual(first['translation_layout']['image_count'], 1)
        self.assertEqual(first['real_api_calls'], 0)
        self.assertTrue(second['cache_hit']); self.assertEqual(client.calls, 1)

    def crawler(self, **extra):
        return normalize({'platform':'atcoder', 'contest_id':'offline', 'problem_id':'offline_image',
            'problem_name':'Synthetic image problem', 'last_fetch_status':'ok', 'problem_url':'https://atcoder.jp/contests/offline/tasks/offline_image',
            'statement_html':'<div id="task-statement"><p>Read the given figure and print the answer.</p><img src="https://img.atcoder.jp/offline/a.png"><p>Print the integer.</p></div>', **extra})

    def test_image_input_can_translate_text_but_not_annotate(self):
        p = self.crawler()
        with tempfile.TemporaryDirectory() as temp:
            plan = Planner(Path(temp)/'labels').one(p)
        self.assertEqual(plan['annotation']['status'], 'pending')
        self.assertEqual(plan['translation']['status'], 'needs_translation')
        self.assertTrue(plan['translation']['needs_ai'])

    def test_image_execution_through_mock_executor_preserves_image(self):
        p = self.crawler()
        with tempfile.TemporaryDirectory() as temp:
            outcome = execute_batch([p], 'translation', root=Path(temp)/'labels', mock=True)
        self.assertEqual(outcome['completed'], 1, outcome)
        self.assertEqual(outcome['real_api_calls'], 0)
        self.assertIn('![图片](https://img.atcoder.jp/offline/a.png)', outcome['results'][0]['result']['statement_zh'])

    def test_failed_source_with_image_is_still_blocked(self):
        p = self.crawler(last_fetch_status='failed')
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(Planner(Path(temp)/'labels').one(p)['translation']['needs_ai'])

    def test_pdf_only_remains_pending(self):
        p = self.crawler(statement_html='', has_pdf=True)
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(Planner(Path(temp)/'labels').one(p)['translation']['status'], 'pending')

    def test_bare_tex_nested_groups_and_environments_stay_local(self):
        source = r'Read \frac{a_{i}}{b_i}, \mathrm{case}_1 and \dots.' + '\n' + r'\begin{cases}x & x>0\\0 & x\le 0\end{cases}'
        layout = build_layout(source)
        sent = json.dumps(layout['segments'])
        for literal in (r'\frac{a_{i}}{b_i}',r'\mathrm{case}_1',r'\dots',r'\begin{cases}x & x>0\\0 & x\le 0\end{cases}'):
            self.assertNotIn(literal, sent)
            result = fill_layout({'title_zh':'模拟','segments':[{'id':s['id'],'text':'文字'} for s in layout['segments']]},layout)[1]
            self.assertIn(literal, result)

    def test_apostrophe_and_parentheses_in_image_url_do_not_become_prose(self):
        source = "Read this figure.\n\n![map](https://img.atcoder.jp/figure's(1).png)\n\nPrint the answer."
        layout = build_layout(source)
        self.assertNotIn('atcoder.jp',json.dumps(layout['segments']))
        result = fill_layout({'title_zh':'模拟','segments':[{'id':s['id'],'text':'文字'} for s in layout['segments']]},layout)[1]
        self.assertIn("![map](https://img.atcoder.jp/figure's(1).png)",result)

    def test_invalid_ids_save_response_and_block_second_call(self):
        class MissingID(MockTranslationClient):
            def call(self, *args, **kwargs):
                response = super().call(*args, **kwargs)
                value = json.loads(response.content); value['segments'].pop()
                response.content = json.dumps(value)
                return response
        client = MissingID()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'labels'
            first = execute_batch([self.p], 'translation', root=root, mock=True, client=client)
            second = execute_batch([self.p], 'translation', root=root, mock=True, client=client)
            tasks = Ledger(root).records()
            self.assertTrue(tasks[0].get('response_sha256'))
            self.assertEqual(tasks[0]['state'], 'blocked')
        self.assertEqual(first['completed'], 0); self.assertEqual(second['api_calls'], 0)
        self.assertEqual(client.calls, 1)

    def test_translation_policy_changes_do_not_change_annotation_policy(self):
        original = task_policies()
        with patch('problem_processing.translation.SYSTEM', 'different layout prompt'):
            modified = task_policies()
        self.assertEqual(original['annotation'], modified['annotation'])
        self.assertNotEqual(original['translation'], modified['translation'])
