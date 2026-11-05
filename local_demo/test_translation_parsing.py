"""Parse-only translation acceptance. Synthetic content, no network or credentials."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server  # Configure imports for the isolated processing module.
from problem_processing.adapter import normalize
from problem_processing.translation import (
    MockTranslationClient, TOKEN, language_plan, parse_translation, prepare_request, prepare_layout_request, translate,
)


class TranslationParsingTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK'))
        guard.start();self.addCleanup(guard.stop)
        self.problem=normalize({'problem_key':'atcoder:abc997:abc997_a','platform':'atcoder',
            'contest_id':'abc997','problem_id':'abc997_a','original_title':'Synthetic parse-only task',
            'original_statement':'# Problem Statement\n\nRead $N$ and $M$ in that order.\n\n'
                '- There are 100 items.\n\nInput\n\n```\n1 2\n```\n\nOutput\n\nPrint the result.'})
        self.prepared=prepare_request(self.problem,language_plan(self.problem))
        self.value=json.loads(MockTranslationClient().call(self.prepared['messages']).content)

    def parse(self,value=None):
        return parse_translation(json.dumps(value if value is not None else self.value,ensure_ascii=False),self.prepared)

    def formula_segment(self):
        return next(s for s in self.value['segments'] if len(TOKEN.findall(s['text']))==2)

    def test_formula_reordering_is_accepted_and_restored(self):
        segment=self.formula_segment();a,b=TOKEN.findall(segment['text'])
        segment['text']=f'先考虑 {b}，再考虑 {a}。'
        self.assertIn('先考虑 $M$，再考虑 $N$。',self.parse()[1])

    def test_line_and_anchor_movement_is_accepted(self):
        segment=self.formula_segment();a,b=TOKEN.findall(segment['text'])
        segment['text']=f'{b}\n\n{a}'
        self.assertIn('$M$\n\n$N$',self.parse()[1])

    def test_missing_or_repeated_known_tokens_do_not_block(self):
        segment=self.formula_segment();a,b=TOKEN.findall(segment['text'])
        segment['text']=f'模型返回 {b} 和 {b}。'
        statement=self.parse()[1]
        self.assertIn('$M$ 和 $M$',statement)
        self.assertNotIn('$N$',statement)

    def test_numeric_changes_are_not_a_content_gate(self):
        segment=next(s for s in self.value['segments'] if '100' in s['text'])
        segment['text']=segment['text'].replace('100','99')
        self.assertIn('99',self.parse()[1])

    def test_markdown_changes_do_not_block(self):
        self.value['segments'][0]['text']='## 模型返回的新标题'
        self.assertTrue(self.parse()[1].startswith('## 模型返回的新标题'))

    def test_no_chinese_language_gate(self):
        self.value['segments'][0]['text']='# Returned English heading'
        self.assertIn('Returned English heading',self.parse()[1])

    def test_omitted_segments_are_not_filled_with_untranslated_source(self):
        self.value['segments']=[{'id':2,'text':'仅展示模型返回的这一段。'}]
        self.assertEqual(self.parse()[1],'仅展示模型返回的这一段。')

    def test_reordered_or_unrecognized_ids_preserve_returned_text(self):
        self.value['segments']=[{'id':999,'text':'模型第一段。'},{'id':2,'text':'模型第二段。'}]
        self.assertEqual(self.parse()[1],'模型第一段。\n\n模型第二段。')

    def test_unknown_token_is_literal_instead_of_triggering_paid_retry(self):
        self.value['segments']=[{'id':0,'text':'模型返回 __ACM_KEEP_999999__。'}]
        self.assertIn('__ACM_KEEP_999999__',self.parse()[1])

    def test_original_code_and_sample_restoration_still_work(self):
        self.assertIn('```\n1 2\n```',self.parse()[1])

    def test_extra_json_metadata_does_not_trigger_strict_schema_gate(self):
        self.value['comment']='model supplied extra metadata'
        self.assertTrue(self.parse()[1])

    def test_unparseable_or_empty_outputs_still_fail(self):
        for value in ([],{}, {'title_zh':'中文','segments':[]},
                      {'title_zh':'中文','segments':[{'text':None}]},
                      {'title_zh':'','segments':[{'text':'正文'}]}):
            with self.subTest(value=value),self.assertRaises(ValueError):self.parse(value)
        with self.assertRaises(ValueError):parse_translation('not JSON',self.prepared)

    def test_parsing_does_not_mutate_prepared_source_or_payload(self):
        original=deepcopy(self.prepared);payload=deepcopy(self.value)
        self.parse()
        self.assertEqual(original,self.prepared);self.assertEqual(payload,self.value)

    def test_direct_mock_entry_uses_local_layout_and_reuses_cached_result(self):
        prepared=prepare_layout_request(self.problem,language_plan(self.problem))
        response=MockTranslationClient().call(prepared['messages'])
        class SavedResponse:
            calls=0
            def call(self,*args,**kwargs):
                self.calls+=1
                return response
        client=SavedResponse()
        with tempfile.TemporaryDirectory(prefix='parse-only-mock-') as temp:
            with patch('problem_processing.translation.validate_translation',side_effect=AssertionError('STRICT GATE DISABLED')):
                first=translate(self.problem,root=Path(temp)/'labels',client=client,mock=True)
                second=translate(self.problem,root=Path(temp)/'labels',client=client,mock=True)
        self.assertEqual(first['translation_status'],'mock')
        self.assertEqual(first['translation_validation_mode'],'layout_by_id')
        self.assertEqual(first['real_api_calls'],0)
        self.assertLess(first['statement_zh'].index('$N$'),first['statement_zh'].index('$M$'))
        self.assertEqual(client.calls,1);self.assertTrue(second['cache_hit'])


if __name__=='__main__':unittest.main()
