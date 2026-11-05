import { marked, Renderer } from 'marked';
import createDOMPurify from 'dompurify';
import katex from 'katex';
import { addStatementSampleButtons } from './statement-samples.js';
import { retainStatementImages } from './statement-images.js';

const command = /\\(?:leq?|geq?|times|cdot|frac|sum|prod|dots|ldots|in|neq?|sqrt|log|lfloor|rfloor|lceil|rceil|mod|bmod)\b/;
const atom = String.raw`(?:\{(?:[^{}\n]|\{[^{}\n]*\})*\}|\\[A-Za-z]+|\\[{},;! ]|(?<![A-Za-z])[A-Za-z](?:_(?:\{[^{}\n]*\}|[A-Za-z0-9']+))?(?![A-Za-z])|\d+(?:\.\d+)?|[{}\[\]()+*/^_=<>|,;:'-])`;
const inlineTex = new RegExp(`(?:${atom}[ \\t]*)*?\\\\[A-Za-z]+(?:[ \\t]*${atom})*`, 'g');
// Protect code, links and tag attributes before interpreting any mathematical syntax.
const protectedBlock = /(?<fence>^ {0,3}(?<marker>`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\k<marker>[ \t]*(?:\n|$))|(?<indented>(?:^(?: {4}|\t).*(?:\n|$))+)|(?<code>(?<ticks>`+)(?!`)[^\n]*?(?<!`)\k<ticks>(?!`))|(?<htmlCode><(?:pre|code)\b[^>]*>[\s\S]*?<\/(?:pre|code)>)|(?<link>!?\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)|https?:\/\/[^\s<>\u3000-\u303f]+)|(?<tag><[A-Za-z/!][^>\n]*>)|(?<dollars>\${6}|\${3}|\${2}|\$)(?!\$)(?<content>[\s\S]+?)\k<dollars>(?!\$)|\\\((?<parens>[\s\S]*?)\\\)|\\\[(?<bracket>[\s\S]*?)\\\]|(?<environment>\\begin\{(?<env>aligned|gathered|cases|[pbBvV]?matrix)\}[\s\S]*?\\end\{\k<env>\})/gm;
let group = String.raw`\{[^{}\n]*\}`;
for (let depth = 0; depth < 4; depth++) group = String.raw`\{(?:[^{}\n]|${group})*\}`;
const suffix = String.raw`(?:['′]+|[_^](?:${group}|[A-Za-z0-9]+))`;
const bareSymbol = new RegExp(String.raw`(?<![A-Za-z0-9_\\])(?:[A-Za-z]|\d+)${suffix}+(?![A-Za-z0-9_])`, 'g');

function mathematicalLine(value) {
  const stripped = value.replace(/\\[A-Za-z]+/g, '').replace(/\\[{}]/g, '');
  return command.test(value) && !/[\u4e00-\u9fff\u3040-\u30ff]/.test(stripped) && !/[A-Za-z]{3,}/.test(stripped);
}

function codeText({ raw, text }) {
  const fenced = raw.match(/^ {0,3}(`{3,}|~{3,})[^\n]*\n([\s\S]*?)^ {0,3}\1[ \t]*(?:\n|$)/m);
  return fenced ? fenced[2] : text + '\n';
}

// Format descriptions use code fences too. Only a known Input/Output section plus
// a conservative mathematical grammar can opt in; samples/programs stay literal.
function ioTemplate(token) {
  if (token.lang && !['text','plaintext'].includes(token.lang.trim().toLowerCase())) return false;
  const value = codeText(token);
  if (!/[A-Za-z]/.test(value)) return false;
  const stripped = value.replace(/\\(?:mathrm|text|operatorname)\{[^{}\n]*\}/g, 'X')
    .replace(/\\(?:dots|ldots|cdots|vdots|ddots|times|cdot|leq?|geq?|lt|gt|neq?|in|infty|frac|sqrt|sum|prod|log|bmod|mod|lfloor|rfloor|lceil|rceil)\b/g, '');
  return !/[A-Za-z]{2,}/.test(stripped) && /^[\sA-Za-z0-9_{}^'′,.+*/=<>()[\]|:\\-]*$/.test(stripped)
    && !/\\/.test(stripped);
}

function markIOFormats(tokens, section = '') {
  for (const token of tokens) {
    if (['heading','paragraph'].includes(token.type)) {
      if (token.type === 'heading') section = '';
      for (const line of token.text.split('\n')) {
        const label = line.trim().replace(/^\*\*|\*\*$/g, '').replace(/[：:]$/, '').trim();
        if (/^(?:样例|示例|输入样例|输出样例|输入示例|输出示例|Sample\b|Example\b|入力例|出力例)/i.test(label)) section = 'sample';
        else if (/^(?:输入|輸入|入力|Input)(?:\s*(?:格式|Format))?$/i.test(label)) section = 'input';
        else if (/^(?:输出|輸出|出力|Output)(?:\s*(?:格式|Format))?$/i.test(label)) section = 'output';
        else if (/^(?:约束|制約|Constraints|说明|解释|Note|Explanation|题目描述|Problem Statement)$/i.test(label)) section = '';
      }
    }
    if (token.type === 'code' && ['input','output'].includes(section) && ioTemplate(token)) token.ioFormat = true;
    if (token.type === 'blockquote') markIOFormats(token.tokens, section);
    if (token.type === 'list') for (const item of token.items) markIOFormats(item.tokens, section);
  }
}

function spaceTemplate(line) {
  let depth = 0, result = '';
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '{') depth++;
    if (ch === '}') depth--;
    if (/\s/.test(ch) && depth === 0) {
      while (i + 1 < line.length && /\s/.test(line[i + 1])) i++;
      result += '\\;';
    } else result += ch;
  }
  return result;
}

// Display transform only. Stored source/translation, protected formulas and sample bytes stay intact.
export function renderStatementMarkdown(source, doc = document) {
  const text = String(source || '').replace(/\r\n?/g, '\n');
  const slots = [];
  let prefix = 'ACMSTATEMENTPLACEHOLDER';
  while (text.includes(prefix)) prefix += 'X';
  const save = (html, kind = 'math') => { const token = `${prefix}${slots.length}END`; slots.push([token, html, kind]); return token; };
  const math = (tex, display = false) => save(katex.renderToString(tex, {
    // Local KaTeX CSS/fonts provide consistent layout; MathML remains for accessibility.
    output: 'htmlAndMathml', throwOnError: true, trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 20, displayMode: display,
  }));
  let prepared = text.replace(protectedBlock, (...args) => {
    const whole = args[0], g = args.at(-1);
    if (g.fence || g.indented || g.code || g.htmlCode || g.link || g.tag) return save(whole, 'markdown');
    if (g.dollars === '$' && g.content.includes('\n')) return save(whole, 'literal');
    try { return math(g.content ?? g.parens ?? g.bracket ?? g.environment,
      Boolean(g.bracket || g.environment || ['$$','$$$$$$'].includes(g.dollars))); }
    catch { return save(whole, 'literal'); }
  });
  prepared = prepared.split('\n').map(line => {
    const match = line.match(/^(\s*(?:[-*+] |\d+[.)] )?)(.*)$/);
    let body = match[2];
    // A bare constraint such as "- 1 \\le N \\le 3 \\times 10^5" has no dollar delimiters.
    if (mathematicalLine(body)) {
      try { return match[1] + math(body); } catch { return line; }
    }
    // Mathematical parentheses embedded in Chinese prose.
    body = body.replace(/[（(]([^()（）\n]+)[）)]/g, (whole, inner) => {
      if (!mathematicalLine(inner)) return whole;
      try { return math('(' + inner + ')'); } catch { return whole; }
    });
    body = body.replace(inlineTex, value => {
      try { return math(value); } catch { return value; }
    });
    // Legacy crawler text often lost <var> delimiters: P_1, P'_N, P_{P'_i}, 2^{N-1}.
    // A suffix is required, so English words and ordinary snake_case identifiers stay prose.
    body = body.replace(bareSymbol, value => {
      try { return math(value.replaceAll('′', "'")); } catch { return value; }
    });
    body = body.replace(/\\[ \t]+/g, ' '); // TeX spacing adjacent to a separately rendered formula.
    return match[1] + body;
  }).join('\n');
  // Only code slots are restored before parsing; MathML bypasses untrusted HTML parsing.
  for (const [token, html, kind] of slots) if (kind === 'markdown') prepared = prepared.replaceAll(token, () => html);
  const purifier = createDOMPurify(doc.defaultView);
  const root = doc.createElement('div');
  const escape = value => value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const renderer = new Renderer();
  renderer.code = function(token) {
    const original = codeText(token), literal = `<pre><code>${escape(original)}</code></pre>\n`;
    if (token.ioFormat) {
      try {
        const lines = original.replace(/\n$/, '').split('\n').map(line =>
          `<div class="statement-io-line">${line.trim() ? math(spaceTemplate(line.trim())) : '<br>'}</div>`).join('');
        return `<div class="statement-io-format" role="group" aria-label="输入输出格式">`+
          `<div class="statement-io-layout">${lines}</div>`+
          `<details class="statement-io-original"><summary>查看原始格式</summary>${literal}</details></div>\n`;
      } catch { /* Unknown syntax remains an unmodified code block for inspection. */ }
    }
    return literal;
  };
  const tokens = marked.lexer(prepared, { gfm:true, breaks:true });
  markIOFormats(tokens);
  root.innerHTML = purifier.sanitize(marked.parser(tokens, {gfm:true,breaks:true,renderer}), {
    FORBID_TAGS:['script','style','iframe','object','embed','form','input'],
    FORBID_ATTR:['style'], ALLOW_DATA_ATTR:false,
  });
  for (const [token, html, kind] of slots) {
    if (kind === 'markdown') continue;
    const walker = doc.createTreeWalker(root, doc.defaultView.NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (!node.textContent.includes(token)) continue;
      const pieces = node.textContent.split(token), fragment = doc.createDocumentFragment();
      pieces.forEach((piece, i) => {
        if (i) {
          const mathNode = doc.createElement('span');
          if (kind === 'literal') { mathNode.className = 'statement-math-unparsed'; mathNode.textContent = html; mathNode.title = '公式未解析，保留原始内容供核对'; }
          else { mathNode.className = html.includes('class="katex-display"') ? 'statement-math-block' : 'statement-math-inline'; mathNode.innerHTML = html; }
          fragment.append(mathNode);
        }
        fragment.append(doc.createTextNode(piece));
      });
      node.replaceWith(fragment);
    }
  }
  // Keep an inline enumeration together on narrow screens: P_1、\dots、P_N.
  // Only join adjacent generated formulas separated by punctuation, never paragraphs or code.
  for (const first of root.querySelectorAll('.statement-math-inline')) {
    if (first.parentElement?.classList.contains('statement-math-sequence')) continue;
    const nodes = [first]; let last = first;
    while (last.nextSibling?.nodeType === 3 &&
        /^[ \t]*(?:[、，,]|[、，,][ \t]*(?:…|⋯|\.{3})[ \t]*[、，,])[ \t]*$/.test(last.nextSibling.textContent) &&
        last.nextSibling.nextSibling?.classList?.contains('statement-math-inline')) {
      nodes.push(last.nextSibling,last.nextSibling.nextSibling);last = nodes.at(-1);
    }
    if (nodes.length === 1) continue;
    const sequence=doc.createElement('span');sequence.className='statement-math-sequence';
    first.before(sequence);sequence.append(...nodes);
  }
  retainStatementImages(root);
  for (const link of root.querySelectorAll('a')) {
    try {
      const href = new URL(link.getAttribute('href'), doc.defaultView.location.origin);
      if (!['http:','https:'].includes(href.protocol) || href.username || href.password) link.removeAttribute('href');
    } catch { link.removeAttribute('href'); }
    link.rel = 'noopener noreferrer';
  }
  addStatementSampleButtons(root);
  return root.innerHTML;
}
