import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { renderStatementMarkdown } from '../src/lib/statement-math.js';
const render = text => { const dom = new JSDOM('<body/>',{url:'http://localhost'});const root=dom.window.document.createElement('div');root.innerHTML=renderStatementMarkdown(text,dom.window.document);return root; };
test('bare list constraint renders actual mathematical symbols',()=>{
  const root=render('- 1 \\le N \\le 3 \\times 10^5');
  assert.equal(root.querySelectorAll('li math').length,1);assert.ok(root.querySelector('msup'));
  assert.ok(root.querySelector('math').textContent.includes('≤'));assert.ok(root.querySelector('math').textContent.includes('×'));
});
test('inline and display delimited math survive Markdown parsing',()=>{
  const root=render('范围 $N_i \\le 10^5$。\n\n$$\\frac{1}{2}$$');
  assert.equal(root.querySelectorAll('math').length,2);assert.ok(root.querySelector('mfrac'));
});
test('backslash parentheses and brackets are rendered',()=>{
  const root=render('\\(x^2\\)\n\n\\[y^3\\]');assert.equal(root.querySelectorAll('math').length,2);
});
test('literal Chinese parentheses around a raw constraint are rendered',()=>{
  assert.equal(render('约束（1 \\le N \\le 100）。').querySelectorAll('math').length,1);
});
test('inline bare TeX in Chinese prose is mathematical rather than literal backslashes',()=>{
  const root=render('所求概率为 \\frac{1}{3}。');assert.ok(root.querySelector('mfrac'));
});
test('fenced sample and inline code stay literal with no math rendering',()=>{
  const root=render('```\n1 \\le 2\n```\n\n`x \\times y`');assert.equal(root.querySelectorAll('math').length,0);
  assert.equal(root.querySelector('pre code').textContent,'1 \\le 2\n');
});
test('malicious source HTML and URLs cannot execute',()=>{
  const root=render('<img src=x onerror="alert(1)"><script>alert(2)</script>\n\n[link](javascript:alert(1))');
  assert.equal(root.querySelectorAll('script,img,[onerror],[onclick],a[href^="javascript:"]').length,0);
});
test('untrusted TeX cannot introduce linked or executable HTML',()=>{
  const root=render('$\\href{javascript:alert(1)}{x}$');assert.equal(root.querySelectorAll('[href^="javascript:"],script').length,0);
});
test('invalid math remains readable rather than becoming a placeholder',()=>{
  const root=render('$\\notARealCommand{x}$');assert.ok(root.textContent.includes('notARealCommand'));assert.ok(!root.textContent.includes('ACMSTATEMENT'));
});
test('placeholder-like original source remains literal',()=>{
  const root=render('ACMSTATEMENTPLACEHOLDER0END\n\n$x$');assert.ok(root.textContent.includes('ACMSTATEMENTPLACEHOLDER0END'));assert.equal(root.querySelectorAll('math').length,1);
});
test('rendering is deterministic and never modifies its input',()=>{
  const text='- 1 \\le N \\le 3 \\times 10^5\n\n```\n1 2\n```';assert.equal(render(text).innerHTML,render(text).innerHTML);assert.ok(text.includes('\\times'));
});
test('Chinese prose and Markdown headings stay intact',()=>{
  const root=render('### 约束\n\n- 所有输入值均为整数。');assert.equal(root.querySelector('h3').textContent,'约束');assert.equal(root.querySelector('li').textContent,'所有输入值均为整数。');
});
test('named TeX groups in prose render without leaking raw commands',()=>{
  const root=render('每个查询 \\mathrm{query}_q 的格式如下：');assert.equal(root.querySelectorAll('math').length,1);assert.ok(root.querySelector('msub'));
  root.querySelectorAll('math').forEach(n=>n.remove());assert.ok(!root.textContent.includes('\\'));
});
test('TeX spacing around parenthesized bounds remains readable',()=>{
  const root=render('对于每个 i\\ (1\\leq i\\lt 2^{N-1})，继续。');assert.equal(root.querySelectorAll('math').length,1);
  root.querySelectorAll('math').forEach(n=>n.remove());assert.ok(!root.textContent.includes('\\'));
});
test('sample trailing blank lines and spaces survive Markdown code rendering',()=>{
  assert.equal(render('```\n5 2 \n\n```').querySelector('pre code').textContent,'5 2 \n\n');
});
const tex = root => [...root.querySelectorAll('math annotation')].map(n=>n.textContent);
test('reported permutation replacement renders every bare subscript and prime',()=>{
  const root=render("将 P_1、\\dots、P_N 的值分别替换为 P'_1、\\dots、P'_N。");
  assert.deepEqual(tex(root),['P_1','\\dots','P_N',"P'_1",'\\dots',"P'_N"]);
  assert.equal(root.querySelectorAll('msubsup').length,2);
  assert.equal(root.querySelectorAll('br').length,0);
  assert.equal(root.querySelectorAll('.katex-html').length,6);
  assert.ok([...root.querySelectorAll('math')].every(n=>n.getAttribute('display')!=='block'));
});
test('nested subscript and exponent braces retain their mathematical grouping',()=>{
  const root=render("关系 P_{P'_i} = i；规模 2^{N-1}，以及 a_{b_{c_i}}。");
  assert.deepEqual(tex(root),["P_{P'_i}",'2^{N-1}','a_{b_{c_i}}']);
  assert.ok(root.querySelector('msup'));
});
test('prime variants and prose are separated without interpreting English words',()=>{
  const root=render("排列 P' 和 P_1'、P′_N；don't change snake_case or file_P_1.txt.");
  assert.deepEqual(tex(root),["P'","P_1'","P'_N"]);
  assert.ok(root.textContent.includes("don't change snake_case or file_P_1.txt."));
});
test('link URLs, labels and HTML attributes cannot be rewritten as mathematics',()=>{
  const root=render('[P_1](https://atcoder.jp/P_1) <a href="https://atcoder.jp/P_2">source</a>');
  assert.deepEqual(tex(root),[]);
  assert.deepEqual([...root.querySelectorAll('a')].map(n=>n.href),['https://atcoder.jp/P_1','https://atcoder.jp/P_2']);
});
test('CF triple and six-dollar delimiters render inline and block correctly',()=>{
  const root=render('范围 $$$N_i$$$。\n\n$$$$$$\\frac{1}{2}$$$$$$');
  assert.deepEqual(tex(root),['N_i','\\frac{1}{2}']);
  assert.equal(root.querySelectorAll('math[display="block"]').length,1);
});
test('multiline cases, aligned equations and matrices render as complete environments',()=>{
  const root=render('\\begin{cases}x^2 & x>0\\\\\n0 & x\\le 0\\end{cases}\n\n'+
    '\\begin{aligned}a&=b+c\\\\d&=e\\end{aligned}\n\n'+
    '$$\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}$$');
  assert.equal(root.querySelectorAll('math').length,3);
  assert.equal(root.querySelectorAll('mtable').length,3);
});
test('fenced, indented and inline samples retain bare variable syntax literally',()=>{
  const root=render("```\nP_1 P'_N\n\n```\n\n`P_2`\n\n    P_3\n");
  assert.equal(root.querySelector('pre code').textContent,"P_1 P'_N\n\n");
  assert.deepEqual(tex(root),[]);
});
test('raw HTML code is never interpreted as math',()=>{
  const root=render('<pre><code>P_1 \\dots P_N</code></pre>');
  assert.equal(root.querySelector('code').textContent,'P_1 \\dots P_N');assert.deepEqual(tex(root),[]);
});
test('invalid explicit math remains literal and gets a visible review marker',()=>{
  const root=render('$\\unsupported{x_i}$');
  assert.equal(root.querySelector('.statement-math-unparsed').textContent,'$\\unsupported{x_i}$');
  assert.equal(root.querySelectorAll('em').length,0);
});
test('trusted images retain their positions and a traceable source link',()=>{
  const root=render('![示意图](https://img.atcoder.jp/example/P_1.png)');
  assert.equal(root.querySelectorAll('img').length,1);
  assert.equal(root.querySelector('img').getAttribute('loading'),'lazy');
  assert.equal(root.querySelector('img').getAttribute('referrerpolicy'),'no-referrer');
  assert.equal(root.querySelector('a').href,'https://img.atcoder.jp/example/P_1.png');
  assert.ok(root.textContent.includes('查看原图'));assert.deepEqual(tex(root),[]);
});
test('unsafe and credential-bearing image links are not offered',()=>{
  const root=render('<img src="javascript:alert(1)" alt="x"><img src="https://user:pass@atcoder.jp/x.png">');
  assert.equal(root.querySelectorAll('img,a[href]').length,0);
});
test('permutation enumerations stay in a shared inline layout group',()=>{
  const root=render("将 P_1、\\dots、P_N 分别替换为 P'_1、\\dots、P'_N。");
  assert.equal(root.querySelectorAll('.statement-math-sequence').length,2);
  for(const group of root.querySelectorAll('.statement-math-sequence'))
    assert.equal(group.querySelectorAll('math').length,3);
});
test('literal ellipsis groups mathematical endpoints without altering punctuation',()=>{
  const root=render('数列 P_1、…、P_N。');
  assert.equal(root.querySelectorAll('.statement-math-sequence').length,1);
  assert.ok(root.querySelector('.statement-math-sequence').textContent.includes('、…、'));
});
test('formula grouping never crosses a source newline, paragraph, or code',()=>{
  const root=render('P_1、\nP_2\n\nP_3、`P_4`');
  assert.equal(root.querySelectorAll('.statement-math-sequence').length,0);
  assert.equal(root.querySelector('code').textContent,'P_4');
  assert.equal(root.querySelectorAll('br').length,1);
});
test('reported multi-case input template renders case subscripts and vertical dots',()=>{
  const source='输入\n输入从标准输入按以下格式给出：\n\n```\nT\n\\mathrm{case}_1\n\\mathrm{case}_2\n\\vdots\n\\mathrm{case}_T\n\n```';
  const root=render(source);
  assert.equal(root.querySelectorAll('.statement-io-format').length,1);
  assert.deepEqual(tex(root),['T','\\mathrm{case}_1','\\mathrm{case}_2','\\vdots','\\mathrm{case}_T']);
  assert.equal(root.querySelector('details pre code').textContent,'T\n\\mathrm{case}_1\n\\mathrm{case}_2\n\\vdots\n\\mathrm{case}_T\n\n');
});
test('following per-case input format inherits section and retains variable spacing',()=>{
  const root=render('## 输入\n\n```\nT\n```\n\n每组测试用例按以下格式给出：\n\n```\nK\nA_1 A_2 \\dots A_{K+1}\n```');
  assert.equal(root.querySelectorAll('.statement-io-format').length,2);
  assert.ok(tex(root).includes('A_1\\;A_2\\;\\dots\\;A_{K+1}'));
});
test('real numeric and text samples after format templates remain byte identical',()=>{
  const root=render('输入\n\n```\nN\nA_1 A_N\n```\n\n样例输入 1\n\n```\n 3  \n1 2 3\n\n```\n\n样例输出 1\n\n```\nAlice\nBob\n\\vdots\n\n```');
  assert.equal(root.querySelectorAll('.statement-io-format').length,1);
  const blocks=[...root.querySelectorAll('pre code')].map(n=>n.textContent);
  assert.deepEqual(blocks,['N\nA_1 A_N\n',' 3  \n1 2 3\n\n','Alice\nBob\n\\vdots\n\n']);
  assert.equal(root.querySelectorAll('pre math').length,0);
});
for(const [heading,sample] of [['Input','Sample Input 1'],['Output','Sample Output 1'],['入力','入力例 1'],['出力','出力例 1'],['输入格式','输入样例 1'],['输出格式','输出示例 1']]){
  test(`${heading} format is mathematical while ${sample} remains literal`,()=>{
    const root=render(`### ${heading}\n\n\`\`\`\nN\nA_1 A_N\n\`\`\`\n\n### ${sample}\n\n\`\`\`\nP_1 \\dots\n\`\`\``);
    assert.equal(root.querySelectorAll('.statement-io-format').length,1);
    assert.equal(root.querySelectorAll('pre code')[1].textContent,'P_1 \\dots\n');
  });
}
test('programming code and string values are never inferred as format mathematics',()=>{
  const root=render('输入\n\n```cpp\nN\n```\n\n```\nprint(N)\n```\n\n```\nAlice\nBob\n```');
  assert.equal(root.querySelectorAll('.statement-io-format,math').length,0);
});
test('a numeric-only block cannot become an input format by section alone',()=>{
  const root=render('输入\n\n```\n3\n1 2 3\n```');
  assert.equal(root.querySelectorAll('.statement-io-format,math').length,0);
});
test('unknown commands and malformed templates fall back to original bytes',()=>{
  const root=render('输入\n\n```\nN\n\\unsupported{x}\n```\n\n```\nA_{i\n```');
  assert.equal(root.querySelectorAll('.statement-io-format').length,0);
  assert.deepEqual([...root.querySelectorAll('pre code')].map(n=>n.textContent),['N\n\\unsupported{x}\n','A_{i\n']);
});
test('format inference ends at a different section and does not change stored source',()=>{
  const source='输入\n\n```\nN\n```\n\n## 说明\n\n```\nP_1\n```',root=render(source);
  assert.equal(root.querySelectorAll('.statement-io-format').length,1);
  assert.equal(root.querySelectorAll('pre code')[1].textContent,'P_1\n');
  assert.ok(source.includes('```\nN\n```'));
});
