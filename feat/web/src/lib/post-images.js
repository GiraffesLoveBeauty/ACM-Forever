import { api } from './api.js';

export function postImage(value) {
  return /^\/api\/forum\/images\/[a-f0-9]{32}$/.test(value || '') ? value : '';
}

export function postExcerpt(value) {
  return String(value || '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/!\[[\s\S]*$/, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[#*_>`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

async function prepareImage(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type))
    throw Error('请选择 PNG、JPEG 或 WebP 图片。');
  if (file.size > 20 * 1024 * 1024) throw Error('原图不能超过 20 MB。');
  const url = URL.createObjectURL(file);
  const image = new Image();
  try {
    image.src = url;
    await image.decode();
    const longest = Math.max(image.naturalWidth, image.naturalHeight);
    if (!longest) throw Error('图片尺寸无效。');
    const scale = Math.min(1, 2560 / longest);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) throw Error('浏览器无法处理这张图片。');
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', 0.9));
    if (!blob || blob.size > 5 * 1024 * 1024) throw Error('图片压缩失败，请缩小后重新上传。');
    return blob;
  } catch (error) {
    throw Error(error.message || '无法读取图片，请换一张图片。');
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function uploadPostImage(file, { signal } = {}) {
  signal?.throwIfAborted();
  const blob = await prepareImage(file);
  signal?.throwIfAborted();
  const body = new FormData();
  body.append('image', blob, 'image.webp');
  return api('/forum/images', { method: 'POST', body, timeoutMs: 60000, signal });
}
