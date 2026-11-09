/* Run after installing feat/web's existing dev dependencies; no CDN or server. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const webRequire = createRequire(path.resolve(process.env.ACM_READER_TEST_WEB_ROOT || path.join(__dirname, '../../feat/web'), 'package.json'));
const {JSDOM} = webRequire('jsdom');
const assets = path.join(__dirname, '../app/app/src/main/assets/reader');

function render(source, format = 'markdown') {
  const dom = new JSDOM('<!doctype html><html><body><article id="article"></article></body></html>', {runScripts:'outside-only', url:'https://reader.test.invalid/'});
  for (const file of ['marked.min.js', 'purify.min.js', 'katex.min.js', 'auto-render.min.js', 'content.js']) {
    dom.window.eval(fs.readFileSync(path.join(assets, file), 'utf8'));
  }
  dom.window.renderContent(source, format, 'https://reader.test.invalid');
  const article = dom.window.document.getElementById('article');
  return {dom, article, formulas:[...article.querySelectorAll('annotation[encoding="application/x-tex"]')].map(n => n.textContent)};
}

const cases = [
  ['inline dollars preserve Markdown-significant underscores', '正文 $a_1+b_2$ 结束', ['a_1+b_2']],
  ['parentheses preserve backslashes', String.raw`正文 \(\frac{a_1}{b_2}\) 结束`, [String.raw`\frac{a_1}{b_2}`]],
  ['display brackets preserve matrices and line breaks', String.raw`\[
\begin{bmatrix}a_1 & b_2 \\ c_3 & d_4\end{bmatrix}
\]`, [String.raw`\begin{bmatrix}a_1 & b_2 \\ c_3 & d_4\end{bmatrix}`]],
  ['display dollars keep blank lines inside aligned math', '$$\n\\begin{aligned}\na_1&=b_2\\\\\n\nc_3&=d_4\n\\end{aligned}\n$$', [String.raw`\begin{aligned}
a_1&=b_2\\

c_3&=d_4
\end{aligned}`]],
  ['math remains separate from surrounding emphasis', '**重要** $x_1+x_2$，*结束*', ['x_1+x_2']],
  ['list and quote math', String.raw`- \(x_1+x_2\)

> $y_1+y_2$`, ['x_1+x_2', 'y_1+y_2']],
  ['table cells retain formulas', '| 公式 | 值 |\n| --- | --- |\n| $x_1+x_2$ | \\(a_1+a_2\\) |', ['x_1+x_2','a_1+a_2']],
  ['Codeforces triple dollar compatibility', '$$$x_1+x_2$$$ / $$$$$$a_1+a_2$$$$$$', ['x_1+x_2','a_1+a_2']],
  ['escaped dollar inside TeX is not a closing delimiter', String.raw`$\text{price \$5}+x_1+x_2$`, [String.raw`\text{price \$5}+x_1+x_2`]],
  ['literal escaped currency is not math', String.raw`价格 \$5 与 \$10；公式 $x_1+x_2$`, ['x_1+x_2']],
  ['escaped slash delimiters stay literal', String.raw`\\(x_1+x_2\\)`, []],
  ['code spans and fenced code stay literal', '`$a_1+a_2$`\n\n```tex\n\\(b_1+b_2\\)\n$$ c_1+c_2 $$\n```', []],
  ['indented code stays literal', '    \\(a_1+a_2\\)\n    $b_1+b_2$', []],
  ['raw HTML code stays literal', '<pre><code>\\(a_1+a_2\\)</code></pre>', []],
  ['HTML wrappers in Markdown retain their math', String.raw`<div><p>\(\frac{a_1}{b_2}\)</p><pre>$literal$</pre></div>`, [String.raw`\frac{a_1}{b_2}`]],
  ['unclosed math does not consume the rest of a post', '$unfinished\n\n**仍是正文**', []],
];
for (const [name, source, expected] of cases) test(name, () => {
  const result = render(source);
  try {
    assert.deepEqual(result.formulas.map(s => s.trim()), expected.map(s => s.trim()));
    assert.equal(result.article.querySelectorAll('.katex-error').length, 0);
    if (name.includes('emphasis')) assert.equal(result.article.querySelector('strong').textContent, '重要');
    if (name.includes('code spans')) assert.match(result.article.querySelector('pre code').textContent, /\\\(b_1\+b_2\\\)/);
    if (name.includes('unclosed')) assert.equal(result.article.querySelector('strong').textContent, '仍是正文');
  } finally { result.dom.window.close(); }
});

test('math rendering keeps the HTML sanitizer and KaTeX trust boundary', () => {
  const result = render(String.raw`<script>window.mathInjected=1</script><img src="x" onerror="window.mathInjected=2">
$\href{javascript:alert(1)}{x}$
\(\text{<img src=x onerror=alert(1)>}\)`);
  try {
    assert.equal(result.dom.window.mathInjected, undefined);
    assert.equal(result.article.querySelector('script,[onerror],a[href^="javascript:"]'), null);
    assert.equal(result.formulas.length, 2);
  } finally { result.dom.window.close(); }
});

test('HTML problem statements retain their existing automatic delimiters', () => {
  const result = render(String.raw`<p>$$$x_1+x_2$$$</p><p>\(\frac{a}{b}\)</p><pre>$literal$</pre>`, 'html');
  try { assert.deepEqual(result.formulas, ['x_1+x_2', String.raw`\frac{a}{b}`]); }
  finally { result.dom.window.close(); }
});
