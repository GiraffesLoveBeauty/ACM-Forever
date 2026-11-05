// Keep trusted OJ images at their local skeleton positions, without a proxy or AI vision.
export function trustedStatementImage(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.port) return '';
    if (!['atcoder.jp', 'img.atcoder.jp', 'codeforces.com'].includes(url.hostname) &&
        !url.hostname.endsWith('.codeforces.com')) return '';
    url.protocol = 'https:';
    return url.href;
  } catch { return ''; }
}

export function retainStatementImages(root) {
  const doc = root.ownerDocument;
  for (const image of root.querySelectorAll('img')) {
    const source = trustedStatementImage(image.getAttribute('src'));
    if (source) {
      image.src = source;
      image.removeAttribute('srcset');
      image.setAttribute('loading', 'lazy');
      image.setAttribute('referrerpolicy', 'no-referrer');
      image.classList.add('statement-source-image');
      image.title = '保留原图；图片内文字未翻译。无法加载时可查看原图。';
      if (!image.closest('a')) {
        const link = doc.createElement('a');
        link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = '查看原图'; link.className = 'statement-image-link';
        image.after(link);
      }
      continue;
    }
    const notice = doc.createElement('span');
    notice.className = 'statement-image-reference';
    notice.textContent = `[图片：${image.alt || '待关联资源'}；来源未获支持]`;
    image.replaceWith(notice);
  }
}
