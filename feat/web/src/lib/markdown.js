import { marked } from 'marked';
import DOMPurify from 'dompurify';
export function markdown(source) {
  if (typeof window !== 'undefined' && window.renderForumMarkdown)
    return window.renderForumMarkdown(String(source || ''));
  const html = DOMPurify.sanitize(marked.parse(String(source || ''), { gfm: true, breaks: true }), {
    ALLOWED_TAGS: [
      'a',
      'blockquote',
      'br',
      'code',
      'del',
      'em',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'hr',
      'img',
      'li',
      'ol',
      'p',
      'pre',
      'strong',
      'sub',
      'sup',
      'table',
      'tbody',
      'td',
      'th',
      'thead',
      'tr',
      'ul',
    ],
    ALLOWED_ATTR: ['href', 'title', 'class', 'start', 'src', 'alt'],
  });
  const container = document.createElement('template');
  container.innerHTML = html;
  for (const image of container.content.querySelectorAll('img')) {
    if (!/^\/api\/forum\/images\/[a-f0-9]{32}$/.test(image.getAttribute('src') || '')) {
      image.replaceWith(document.createTextNode(image.alt || '[图片未上传]'));
      continue;
    }
    image.setAttribute('loading', 'lazy');
    image.setAttribute('decoding', 'async');
  }
  return container.innerHTML;
}
