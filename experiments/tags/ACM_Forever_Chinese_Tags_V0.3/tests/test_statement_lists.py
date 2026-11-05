"""Synthetic list counters and layout round trips; no network or persisted data."""
from copy import deepcopy
import json
import re
import unittest
from unittest.mock import patch

from problem_processing.adapter import normalize
from problem_processing.statement import html_statement
from problem_processing.translation import (MockTranslationClient, language_plan,
    parse_translation, prepare_layout_request)
from test_crawler_adapter import crawler


class StatementListTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK'))
        guard.start();self.addCleanup(guard.stop)

    def convert(self, html, expected):
        result=html_statement(html)
        self.assertEqual(result['issues'],[])
        self.assertEqual(re.findall(r'^(-?\d+)\\\. ',result['text'],re.M),[str(x) for x in expected])
        return result['text']

    def test_default_ordered_list_preserves_referenced_operation_numbers(self):
        text=self.convert('<ol><li>Insert the item.</li><li>Delete the item.</li></ol><p>Repeat operation 2.</p>',[1,2])
        self.assertIn('1\\. Insert the item.\n\n',text)
        self.assertIn('2\\. Delete the item.',text)
        self.assertIn('Repeat operation 2.',text)

    def test_start_attribute(self):
        self.convert('<ol start="7"><li>First query</li><li>Second query</li></ol>',[7,8])

    def test_item_value_resets_subsequent_counter(self):
        self.convert('<ol start="3"><li>First</li><li value="9">Reset</li><li>Next</li></ol>',[3,9,10])

    def test_decreasing_and_duplicate_values_are_not_renumbered(self):
        self.convert('<ol><li value="8">First</li><li value="2">Second</li><li value="2">Third</li></ol>',[8,2,2])

    def test_zero_and_negative_numbers(self):
        self.convert('<ol start="-1"><li>Negative</li><li>Zero</li><li>Positive</li></ol>',[-1,0,1])

    def test_signed_whitespace_integer_attributes(self):
        self.convert('<ol start=" +03 "><li>First</li><li value=" -2 ">Second</li></ol>',[3,-2])

    def test_separate_lists_have_independent_counters(self):
        self.convert('<ol start="4"><li>First list</li></ol><ol><li>Second list</li></ol>',[4,1])

    def test_reversed_defaults_to_direct_item_count(self):
        self.convert('<ol reversed><li>First</li><li>Second</li><li>Third</li></ol>',[3,2,1])

    def test_reversed_start_and_value(self):
        self.convert('<ol reversed start="8"><li>First</li><li value="4">Reset</li><li>Last</li></ol>',[8,4,3])

    def test_unordered_lists_remain_bullets_and_ignore_value(self):
        result=html_statement('<ul><li value="9">First</li><li>Second</li></ul>')
        self.assertEqual(result['issues'],[])
        self.assertIn('- First',result['text']);self.assertIn('- Second',result['text'])
        self.assertNotIn('9',result['text'])

    def test_mixed_lists_do_not_share_counters(self):
        text=self.convert('<ol start="4"><li>Ordered</li></ol><ul><li>Bullet</li></ul>'
                          '<ol start="9"><li>Another ordered</li></ol>',[4,9])
        self.assertIn('- Bullet',text)

    def test_nested_numbered_hierarchy_is_preserved_as_text_but_requires_review(self):
        html='<ol start="4"><li>Parent<ol start="9"><li>Child</li></ol></li><li>Sibling</li></ol>'
        result=html_statement(html)
        self.assertEqual(re.findall(r'^(-?\d+)\\\. ',result['text'],re.M),['4','9','5'])
        self.assertIn('nested_ordered_list_requires_review',result['issues'])
        for html in (html,'<ul><li>Parent<ol><li>Child</li></ol></li></ul>'):
            self.assertEqual(normalize(crawler(statement_html=html))['processing_status'],'html_pending')

    def test_invalid_integer_attributes_never_claim_reliable_conversion(self):
        for attribute in ('start','value'):
            for value in ('bad','1.5','','1e2','1 2','2147483648','-2147483649','９'):
                html=(f'<ol start="{value}"><li>Body</li></ol>' if attribute=='start' else
                      f'<ol><li value="{value}">Body</li></ol>')
                with self.subTest(attribute=attribute,value=value):
                    result=normalize(crawler(statement_html=html))
                    self.assertIn('invalid_list_numbering',result['processing_issues'])
                    self.assertEqual(result['processing_status'],'html_pending')
                    self.assertEqual(result['original_statement_html'],html)

    def test_boolean_number_attributes_require_review(self):
        for html in ('<ol start><li>Body</li></ol>','<ol><li value>Body</li></ol>'):
            self.assertIn('invalid_list_numbering',html_statement(html)['issues'])

    def test_alphabetic_and_roman_numbering_require_review(self):
        for kind in ('a','A','i','I','invalid'):
            for html in (f'<ol type="{kind}"><li>Body</li></ol>',f'<ol><li type="{kind}">Body</li></ol>'):
                with self.subTest(html=html):
                    self.assertIn('unsupported_ordered_list_type',html_statement(html)['issues'])
        self.convert('<ol type="1"><li type="1">Decimal</li></ol>',[1])

    def test_custom_css_counters_require_review(self):
        for html in ('<ol style="list-style-type: lower-alpha"><li>Body</li></ol>',
                     '<ol><li style="counter-increment: item 3">Body</li></ol>',
                     '<style>ol { counter-reset: item 7; }</style><ol><li>Body</li></ol>'):
            self.assertIn('custom_list_numbering_requires_review',html_statement(html)['issues'])

    def test_duplicate_number_attributes_are_not_silently_resolved(self):
        for html in ('<ol start="1" start="7"><li>Body</li></ol>',
                     '<ol><li value="1" value="7">Body</li></ol>'):
            self.assertIn('ambiguous_list_numbering',html_statement(html)['issues'])

    def test_orphan_item_requires_review(self):
        self.assertIn('orphan_list_item',html_statement('<li>Body</li>')['issues'])

    def test_malformed_list_content_requires_review_without_dropping_text(self):
        for html in ('<ol>Unexpected text<li>Body</li></ol>','<ol><div><li>Body</li></div></ol>'):
            result=html_statement(html)
            self.assertIn('invalid_list_structure',result['issues'])
            self.assertIn('Body',result['text'])

    def test_formulas_code_and_item_paragraphs_remain_intact(self):
        text=self.convert('<ol start="3"><li><p>Read <var>N</var>.</p><pre>1  2\n\n3\n</pre>'
                          '<p>Print <code>a+b</code>.</p></li><li>Finish</li></ol>',[3,4])
        self.assertIn('$N$',text)
        self.assertIn('```\n1  2\n\n3\n```',text)
        self.assertIn('`a+b`',text)

    def test_reliable_numbered_input_is_ready_and_original_html_is_retained(self):
        html='<p>Read a query.</p><ol start="3"><li>Insert.</li><li value="7">Remove.</li></ol>'
        row=normalize(crawler(statement_html=html,statement_text='Lossy fallback'))
        self.assertEqual(row['processing_status'],'ready')
        self.assertEqual(row['processing_issues'],[])
        self.assertEqual(row['original_statement_html'],html)
        self.assertIn('7\\. Remove.',row['original_statement'])

    def test_changed_numbers_change_semantic_input_hashes(self):
        first=normalize(crawler(statement_html='<ol start="3"><li>Insert.</li></ol>'))
        second=normalize(crawler(statement_html='<ol start="7"><li>Insert.</li></ol>'))
        for key in ('content_hash','annotation_input_hash','translation_input_hash'):
            self.assertNotEqual(first[key],second[key])

    def test_repeated_conversion_is_stable_and_does_not_mutate_source(self):
        source=crawler(statement_html='<ol start="3"><li>Insert.</li><li value="7">Remove.</li></ol>')
        original=deepcopy(source)
        first=normalize(source)
        self.assertEqual(first,normalize(source))
        self.assertEqual(first,normalize(first))
        self.assertEqual(source,original)

    def test_translation_keeps_counter_prefixes_local_during_mock_round_trip(self):
        html='<ol start="3"><li>Insert the item.</li><li value="7">Remove the item.</li></ol>'
        p=normalize(crawler(statement_html=html))
        prepared=prepare_layout_request(p,language_plan(p))
        payload=json.loads(prepared['messages'][1]['content'])
        self.assertTrue(payload['segments'])
        for segment in payload['segments']:
            self.assertNotRegex(segment['text'],r'^[37]')
        response=MockTranslationClient().call(prepared['messages'])
        _,statement=parse_translation(response.content,prepared)
        self.assertEqual(re.findall(r'^(-?\d+)\\\. ',statement,re.M),['3','7'])
        self.assertIn('\n\n7\\. ',statement)

    def test_empty_items_still_advance_and_retain_counter(self):
        result=html_statement('<ol start="3"><li></li><li>Body</li></ol>')
        self.assertEqual(result['issues'],[])
        self.assertIn('3\\.',result['text']);self.assertIn('4\\. Body',result['text'])


if __name__=='__main__':unittest.main()
