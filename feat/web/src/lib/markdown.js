import { marked } from 'marked';
import DOMPurify from 'dompurify';
export function markdown(source) {
  if (typeof window !== 'undefined' && window.renderForumMarkdown)
    return window.renderForumMarkdown(String(source || ''));
  return DOMPurify.sanitize(marked.parse(String(source || ''), { gfm: true, breaks: true }), {
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
    ALLOWED_ATTR: ['href', 'title', 'class', 'start'],
  });
}
