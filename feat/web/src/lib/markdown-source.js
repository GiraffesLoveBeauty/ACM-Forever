import { controlledImage } from './markdown.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
export const markdownLimits = Object.freeze({ file: 102400, title: 120, body: 20000 });
export function sourceFields({ title = '', body = '' }) {
  title = title.trim();
  body = body.replace(/\r\n?/g, '\n').replace(/^\uFEFF/, '');
  if (Array.from(title).length > markdownLimits.title) throw Error('标题不能超过 120 个字符。');
  if (Array.from(body).length > markdownLimits.body) throw Error('正文不能超过 20000 个字符。');
  return { title, body };
}
export function findFirstMarkdownH1(source) {
  let offset = 0;
  for (const token of marked.lexer(source, { gfm: true })) {
    const raw = String(token.raw || '');
    if (!raw) continue;
    let startOffset = source.indexOf(raw, offset);
    if (token.type === 'heading' && token.depth === 1) {
      while (startOffset >= 0) {
        const lineStart = source.lastIndexOf('\n', startOffset - 1) + 1;
        if (/^[\t ]{0,3}$/.test(source.slice(lineStart, startOffset))) break;
        startOffset = source.indexOf(raw, startOffset + 1);
      }
    }
    if (startOffset < 0) continue;
    if (token.type === 'heading' && token.depth === 1) {
      const inlineHtml = DOMPurify.sanitize(marked.parseInline(token.text || '', { gfm: true }));
      const titleNode = document.createElement('div');
      titleNode.innerHTML = inlineHtml;
      return {
        startOffset,
        endOffset: startOffset + raw.length,
        title: titleNode.textContent.trim(),
      };
    }
    offset = startOffset + raw.length;
  }
  return null;
}

export async function importMarkdownFile(file) {
  if (!/\.(md|markdown)$/i.test(file.name)) throw Error('请选择 .md 或 .markdown 文件。');
  if (file.size > markdownLimits.file) throw Error('Markdown 文件不能超过 100 KB。');
  // Fatal UTF-8 decoding prevents silently corrupting imported source.
  const source = new TextDecoder('utf-8', { fatal: true })
    .decode(await file.arrayBuffer())
    .replace(/^\uFEFF/, '')
    .replace(/\r\n?/g, '\n');
  const heading = findFirstMarkdownH1(source);
  const title = Array.from(heading ? heading.title : file.name.replace(/\.(md|markdown)$/i, ''))
    .slice(0, markdownLimits.title)
    .join('');
  const body = heading
    ? (source.slice(0, heading.startOffset) + source.slice(heading.endOffset)).replace(/^\n+/, '')
    : source;
  if (Array.from(body).length > markdownLimits.body)
    throw Error('Markdown 正文超过 20000 个字符，请精简后再导入。');
  return { title, body };
}
export function missingImages(body) {
  const missing = new Set();
  marked.walkTokens(marked.lexer(body || ''), (token) => {
    if (token.type === 'image' && !controlledImage(token.href || ''))
      missing.add(token.href || '未命名图片');
  });
  return [...missing];
}
export const markdownFormats = {
  h1: ['# ', ''],
  h2: ['## ', ''],
  bold: ['**', '**'],
  italic: ['*', '*'],
  strike: ['~~', '~~'],
  quote: ['> ', ''],
  ul: ['- ', ''],
  ol: ['1. ', ''],
  code: ['`', '`'],
  codeblock: ['\n```cpp\n', '\n```\n'],
  link: ['[', '](https://)'],
};
export function insertMarkdown(node, body, before, after = '', placeholder = '文字') {
  const start = node?.selectionStart ?? body.length,
    end = node?.selectionEnd ?? start;
  const selected = body.slice(start, end) || placeholder;
  return {
    body: body.slice(0, start) + before + selected + after + body.slice(end),
    start: start + before.length,
    end: start + before.length + selected.length,
  };
}
