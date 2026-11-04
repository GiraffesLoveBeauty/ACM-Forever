import createDOMPurify from 'dompurify';
import katex from 'katex';
import renderMathInElement from 'katex/contrib/auto-render';
import { renderStatementMarkdown } from './statement-math.js';

const allowedClasses = new Set([
  'header',
  'title',
  'property-title',
  'time-limit',
  'memory-limit',
  'input-file',
  'output-file',
  'section-title',
  'input-specification',
  'output-specification',
  'sample-tests',
  'sample-test',
  'input',
  'output',
  'test-example-line',
  'note',
  'part',
  'lang-en',
  'lang-ja',
]);
const mathOptions = {
  output: 'htmlAndMathml',
  trust: false,
  throwOnError: false,
  maxExpand: 1000,
  maxSize: 20,
  delimiters: [
    { left: '$$$$$$', right: '$$$$$$', display: true },
    { left: '$$$', right: '$$$', display: false },
    { left: '$$', right: '$$', display: true },
    { left: '\\(', right: '\\)', display: false },
    { left: '\\[', right: '\\]', display: true },
  ],
};

export function originalProblemUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
      ? url.href
      : '';
  } catch {
    return '';
  }
}

// Statements are untrusted. Only this sanitized DOM is passed to the view's v-html.
export function renderProblemContent(detail, doc = document) {
  const statement = doc.createElement('div');
  if (detail.statement_html) {
    statement.append(
      createDOMPurify(doc.defaultView).sanitize(detail.statement_html, {
        RETURN_DOM_FRAGMENT: true,
        ALLOWED_TAGS: [
          'div',
          'span',
          'section',
          'p',
          'h1',
          'h2',
          'h3',
          'h4',
          'h5',
          'h6',
          'br',
          'hr',
          'pre',
          'code',
          'var',
          'b',
          'strong',
          'i',
          'em',
          'u',
          's',
          'sub',
          'sup',
          'ul',
          'ol',
          'li',
          'dl',
          'dt',
          'dd',
          'table',
          'caption',
          'thead',
          'tbody',
          'tfoot',
          'tr',
          'th',
          'td',
          'blockquote',
          'a',
          'img',
        ],
        ALLOWED_ATTR: [
          'class',
          'href',
          'src',
          'alt',
          'title',
          'colspan',
          'rowspan',
          'start',
          'lang',
        ],
        ALLOW_DATA_ATTR: false,
        ALLOW_ARIA_ATTR: false,
      }),
    );
    for (const image of statement.querySelectorAll('img')) {
      const href = originalProblemUrl(image.getAttribute('src'));
      const url = href && new URL(href);
      if (
        !url ||
        url.port ||
        !(
          url.hostname === 'codeforces.com' ||
          url.hostname.endsWith('.codeforces.com') ||
          ['atcoder.jp', 'img.atcoder.jp'].includes(url.hostname)
        )
      ) {
        image.replaceWith(doc.createTextNode(image.alt || '[图片未保存]'));
        continue;
      }
      url.protocol = 'https:';
      image.src = url.href;
      image.setAttribute('loading', 'lazy');
      image.setAttribute('referrerpolicy', 'no-referrer');
    }
    for (const link of statement.querySelectorAll('a')) {
      const href = originalProblemUrl(link.getAttribute('href'));
      if (!href) link.removeAttribute('href');
      else {
        link.href = href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
    }
    for (const node of statement.querySelectorAll('[class]')) {
      const names = [...node.classList].filter((name) => allowedClasses.has(name));
      if (names.length) node.className = names.join(' ');
      else node.removeAttribute('class');
    }
  } else {
    const text = detail.statement_text || '';
    if (/\\[A-Za-z]+|\$[^$]+\$|```|~~~|^\s*(?:#{1,6} |[-*+] )|\b[A-Za-z](?:['′]+|[_^](?:\{|[A-Za-z0-9]))/m.test(text)) {
      statement.innerHTML = renderStatementMarkdown(text, doc);
    } else {
      const plain = doc.createElement('pre'); plain.textContent = text; statement.append(plain);
    }
  }

  const samples = Array.isArray(detail.samples) ? detail.samples : [];
  let inputs = [],
    outputs = [];
  if (detail.platform === 'codeforces') {
    inputs = [...statement.querySelectorAll('.sample-test .input pre')];
    outputs = [...statement.querySelectorAll('.sample-test .output pre')];
  } else if (detail.platform === 'atcoder') {
    for (const heading of statement.querySelectorAll('h3')) {
      const pre = heading.nextElementSibling;
      if (pre?.tagName !== 'PRE') continue;
      if (/^(Sample Input|入力例)\s*\d*/i.test(heading.textContent.trim())) inputs.push(pre);
      if (/^(Sample Output|出力例)\s*\d*/i.test(heading.textContent.trim())) outputs.push(pre);
    }
  }
  const samplesEmbedded =
    samples.length > 0 && inputs.length === samples.length && outputs.length === samples.length;
  if (samplesEmbedded) {
    samples.forEach((sample, index) => {
      for (const [kind, label, nodes] of [
        ['input', '输入', inputs],
        ['output', '输出', outputs],
      ]) {
        const pre = nodes[index];
        pre.textContent = String(sample[kind] ?? '');
        const button = doc.createElement('button');
        button.type = 'button';
        button.className = 'btn problem-copy';
        button.dataset.sampleIndex = String(index);
        button.dataset.sampleKind = kind;
        button.textContent = `复制样例 ${index + 1} ${label}`;
        const heading=pre.previousElementSibling;
        if (heading?.matches('h1,h2,h3,h4,h5,h6,.title')) {
          heading.querySelectorAll('button[data-statement-sample],.statement-sample-copy-status').forEach(node=>node.remove());
          heading.classList.add('statement-sample-heading');heading.append(button);
        } else pre.before(button);
      }
    });
  }
  // Local KaTeX layout plus accessible MathML; commands embedding URLs/HTML stay disabled.
  renderMathInElement(statement, mathOptions);
  if (detail.platform === 'atcoder') {
    for (const variable of statement.querySelectorAll('var')) {
      if (!variable.querySelector('math') && !variable.closest('pre,code'))
        katex.render(variable.textContent, variable, mathOptions);
    }
  }
  return { html: statement.innerHTML, samplesEmbedded };
}
