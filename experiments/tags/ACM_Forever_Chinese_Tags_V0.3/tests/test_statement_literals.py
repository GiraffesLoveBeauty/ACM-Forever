"""Literal HTML/Markdown and dedicated code/math paths, synthetic and offline."""
import html
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from problem_processing.adapter import normalize
from problem_processing.markdown_text import escape_text
from problem_processing.statement import html_statement
from problem_processing.translation import language_plan, prepare_layout_request, parse_translation
from problem_processing.translation_layout import build_layout, fill_layout, text_literal
from test_crawler_adapter import crawler

FIXTURES=Path(__file__).parent/'fixtures/statement_literals.json'


class StatementLiteralTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK'))
        guard.start();self.addCleanup(guard.stop)

    def test_shared_browser_fixtures_match_actual_html_conversion(self):
        for row in json.loads(FIXTURES.read_text(encoding='utf-8')):
            with self.subTest(name=row['name']):
                result=html_statement(row['html'])
                self.assertEqual(result['issues'],[])
                self.assertEqual(result['text'],row['markdown'])

    def test_encoded_break_is_prose_not_a_fixed_tag(self):
        result=html_statement('<p>Print &lt;br&gt;.</p>')
        self.assertEqual(result['text'],'Print &lt;br&gt;.')
        layout=build_layout(result['text'])
        self.assertEqual(layout['segments'],[{'id':0,'text':'Print <br>.'}])
        self.assertNotIn('<br>',''.join(p for p in layout['parts'] if isinstance(p,str)))

    def test_unknown_tag_literal_reaches_model_as_text(self):
        layout=build_layout(html_statement('<p>Print &lt;YES&gt;.</p>')['text'])
        self.assertEqual(layout['segments'][0]['text'],'Print <YES>.')

    def test_numeric_and_named_entities_share_literal_semantics(self):
        expected=html_statement('<p>Print &lt;YES&gt;.</p>')
        for value in ('&#60;YES&#62;','&#x3c;YES&#x3e;'):
            self.assertEqual(html_statement('<p>Print '+value+'.</p>'),expected)

    def test_entities_are_decoded_once_for_model_and_encoded_once_on_return(self):
        source=html_statement('<p>Print &amp;lt;br&amp;gt; and &amp;amp;.</p>')['text']
        layout=build_layout(source)
        self.assertEqual(layout['segments'][0]['text'],'Print &lt;br&gt; and &amp;.')
        _,returned=fill_layout({'title_zh':'Mock title','segments':layout['segments']},layout)
        self.assertEqual(returned,source)

    def test_numeric_entities_do_not_split_at_hash_mark(self):
        source=escape_text('Print [YES](answer) for $5 and \\times.')
        layout=build_layout(source)
        self.assertEqual(layout['segments'][0]['text'],'Print [YES](answer) for $5 and \\times.')
        self.assertEqual(fill_layout({'title_zh':'Mock','segments':layout['segments']},layout)[1],source)

    def test_markdown_markers_are_escaped_in_ordinary_text(self):
        result=html_statement('<p>*bold* _under_ ~~cut~~ # heading</p>')['text']
        self.assertEqual(result,r'\*bold\* \_under\_ \~\~cut\~\~ \# heading')

    def test_literal_markdown_image_is_not_an_image(self):
        result=html_statement('<p>![diagram](https://example.org/a.png)</p>')['text']
        layout=build_layout(result)
        self.assertEqual(layout['image_count'],0)
        self.assertIn('&#91;',result);self.assertIn('&#40;',result)

    def test_literal_numbered_and_unordered_prefixes_are_not_lists(self):
        self.assertEqual(html_statement('<p>1. Literal line</p>')['text'],r'1\. Literal line')
        self.assertEqual(html_statement('<p>- Literal line</p>')['text'],r'\- Literal line')
        self.assertEqual(html_statement('<p><span>1</span>. Literal line</p>')['text'],r'1\. Literal line')

    def test_text_between_real_inline_elements_keeps_spaces(self):
        self.assertEqual(html_statement('<p>Print <strong>&lt;YES&gt;</strong> now.</p>')['text'],
                         'Print **&lt;YES&gt;** now.')

    def test_real_break_and_literal_break_remain_distinct(self):
        self.assertEqual(html_statement('<p>Print &lt;br&gt;.<br>Continue.</p>')['text'],
                         'Print &lt;br&gt;.\nContinue.')

    def test_real_link_keeps_structure_but_label_is_literal(self):
        result=html_statement('<a href="https://example.org/help">&lt;YES&gt; [help]</a>')['text']
        self.assertEqual(result,'[&lt;YES&gt; &#91;help&#93;](https://example.org/help)')

    def test_inline_code_keeps_decoded_raw_characters(self):
        result=html_statement('<code>&lt;br&gt; *x* $5 &amp; y_1</code>')['text']
        self.assertEqual(result,'`<br> *x* $5 & y_1`')
        self.assertEqual(build_layout(result)['segments'],[])

    def test_inline_code_fence_and_edge_spaces_are_safe(self):
        for raw,expected in [('`x`','`` `x` ``'),(' x ','`  x  `')]:
            self.assertEqual(html_statement('<code>'+raw+'</code>')['text'],expected)
            self.assertEqual(build_layout(expected)['segments'],[])

    def test_multiline_inline_code_is_preserved_but_needs_review(self):
        raw='<code>first\nsecond</code>'
        result=normalize(crawler(statement_html=raw))
        self.assertIn('first\nsecond',result['original_statement'])
        self.assertEqual(result['processing_status'],'html_pending')
        self.assertIn('multiline_inline_code_requires_review',result['processing_issues'])

    def test_pre_and_samples_keep_exact_whitespace_and_symbols(self):
        raw='  <br>\n*YES* & \\times\n\n'
        self.assertEqual(html_statement('<pre>'+html.escape(raw)+'</pre>')['text'],
                         '```\n'+raw+'```')

    def test_var_preserves_math_entities_subscripts_and_operators(self):
        self.assertEqual(html_statement('<var>x<sub>i+1</sub> &lt; y * 2</var>')['text'],
                         '$x_{i+1} < y * 2$')

    def test_standalone_superscript_preserves_formula_body(self):
        self.assertEqual(html_statement('<p>x<sup>n+1</sup></p>')['text'],'x^{n+1}')

    def test_tex_script_stays_raw(self):
        self.assertEqual(html_statement(r'<script type="math/tex">x_1 \le y & z</script>')['text'],
                         r'$x_1 \le y & z$')

    def test_explicit_math_in_text_is_not_markdown_escaped(self):
        for formula in (r'$x_1 < y$',r'$$x_1 + 1$$',r'$$$N^2$$$',r'\(x_1 < y\)',
                        r'\[x_1 + 1\]',r'\begin{cases}x & x>0\\0 & x\le 0\end{cases}'):
            with self.subTest(formula=formula):
                self.assertIn(formula,html_statement('<p>Use '+html.escape(formula)+'.</p>')['text'])

    def test_shared_fixtures_round_trip_through_actual_translation_protocol(self):
        for row in json.loads(FIXTURES.read_text(encoding='utf-8')):
            with self.subTest(name=row['name']):
                p=normalize(crawler(statement_html=row['html']))
                prepared=prepare_layout_request(p,language_plan(p))
                payload=json.loads(prepared['messages'][1]['content'])
                # An echo is a Mock response, not a purported AI translation.
                _,returned=parse_translation(json.dumps({'title_zh':'Mock title','segments':payload['segments']}),prepared)
                self.assertEqual(returned,row['markdown'])

    def test_model_authored_html_and_markdown_still_cannot_change_structure(self):
        result=text_literal('![fake](https://example.org/a) <br> $5 \\times')
        self.assertNotIn('<br>',result);self.assertNotIn('![',result)
        self.assertNotIn('$',result);self.assertNotIn('\\times',result)

    def test_actual_list_and_literal_list_are_distinguished(self):
        result=html_statement('<ol start="7"><li>*literal* [YES]</li></ol>')['text']
        self.assertEqual(result,r'7\. \*literal\* &#91;YES&#93;')

    def test_repeated_normalization_is_stable_and_preserves_original_html(self):
        raw='<p>Print &lt;br&gt; and [YES].</p>'
        record=crawler(statement_html=raw);before=dict(record)
        first=normalize(record)
        self.assertEqual(first['original_statement_html'],raw)
        self.assertEqual(normalize(record),first);self.assertEqual(normalize(first),first)
        self.assertEqual(record,before)

    def test_unsupported_formula_markup_is_not_marked_ready(self):
        p=normalize(crawler(statement_html='<var><b>x</b> + 1</var>'))
        self.assertEqual(p['processing_status'],'html_pending')
        self.assertIn('unsupported_math_markup',p['processing_issues'])

    def test_unsupported_code_markup_is_not_silently_dropped_as_reliable(self):
        raw='<code>Print <img src="/diagram.png" alt="required diagram"></code>'
        p=normalize(crawler(statement_html=raw))
        self.assertEqual(p['processing_status'],'html_pending')
        self.assertIn('unsupported_code_markup',p['processing_issues'])
        self.assertEqual(p['original_statement_html'],raw)


if __name__=='__main__':unittest.main()
