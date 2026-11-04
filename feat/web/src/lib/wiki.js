import { api } from './api.js';
import { affectsPublicWiki, invalidateWikiNavigation } from './wiki-navigation.js';
export const wikiKey = () => crypto.randomUUID();
export const wikiApi = (path, options = {}) => api('/wiki' + path, options);
export async function adminWikiApi(path, options = {}, request = api) {
  const value = await request('/admin/wiki' + path, options);
  if (affectsPublicWiki(path, options)) invalidateWikiNavigation();
  return value;
}
export function headingSlug(text, fallback = 'section') {
  return (
    text
      .normalize('NFKC')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .trim()
      .replace(/\s+/g, '-') || fallback
  );
}
export async function downloadMarkdown(url, signal) {
  if (!url?.startsWith('/api/')) throw Error('请先保存草稿后再下载。');
  const response = await fetch(url, { credentials: 'same-origin', signal });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw Error(data.message || '下载不可用，请重新登录后重试。');
  }
  const blob = await response.blob();
  if (!blob.size || !response.headers.get('Content-Type')?.startsWith('text/markdown'))
    throw Error('未获得有效的 Markdown 文件。');
  const filename =
    /filename="([a-z0-9-]+\.md)"/.exec(response.headers.get('Content-Disposition') || '')?.[1] ||
    'article.md';
  const href = URL.createObjectURL(blob),
    link = document.createElement('a');
  link.href = href;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
