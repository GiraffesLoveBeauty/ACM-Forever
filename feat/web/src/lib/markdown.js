import { marked } from 'marked';
import DOMPurify from 'dompurify';
export function markdown(source) {
  const rendered =
    typeof window !== 'undefined' && window.renderForumMarkdown
      ? window.renderForumMarkdown(String(source || ''))
      : DOMPurify.sanitize(marked.parse(String(source || ''), { gfm: true, breaks: true }), {
          ALLOWED_TAGS: [
            'img',
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
          ALLOWED_ATTR: ['href', 'title', 'class', 'start', 'src', 'alt'],
        });
  const root = document.createElement('div');
  root.innerHTML = rendered;
  for (const image of root.querySelectorAll('img')) {
    if (!controlledImage(image.getAttribute('src'))) {
      image.replaceWith(document.createTextNode(`[图片待上传：${image.alt || '未关联资源'}]`));
    } else {
      image.loading = 'lazy';
      image.decoding = 'async';
    }
  }
  for (const link of root.querySelectorAll('a')) link.setAttribute('rel', 'noopener noreferrer');
  return root.innerHTML;
}
export function controlledImage(value) {
  try {
    const url = new URL(value, location.origin);
    return (
      url.origin === location.origin &&
      !url.search &&
      !url.hash &&
      /^\/api\/(?:markdown\/assets|forum\/images)\/[a-f0-9]{32}$/.test(url.pathname)
    );
  } catch {
    return false;
  }
}
