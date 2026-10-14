const avatarTargetBytes = 1800 * 1024;
async function decodeAvatar(file) {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file);
      return {
        width: bitmap.width,
        height: bitmap.height,
        draw: (context, width, height) => context.drawImage(bitmap, 0, 0, width, height),
        close: () => bitmap.close?.(),
      };
    } catch {}
  }
  const url = URL.createObjectURL(file),
    image = new Image();
  image.src = url;
  try {
    await image.decode();
  } catch {
    URL.revokeObjectURL(url);
    throw Error('浏览器无法读取这张图片，请换一张常见格式的图片。');
  }
  return {
    width: image.naturalWidth,
    height: image.naturalHeight,
    draw: (context, width, height) => context.drawImage(image, 0, 0, width, height),
    close: () => URL.revokeObjectURL(url),
  };
}
async function compressAvatar(file) {
  if (!file.type.startsWith('image/')) throw Error('请选择图片文件。');
  const image = await decodeAvatar(file);
  try {
    const longest = Math.max(image.width, image.height);
    if (!longest || !image.width || !image.height) throw Error('图片尺寸无效，请换一张图片。');
    let edge = Math.min(1024, longest),
      quality = 0.86,
      outputType = 'image/webp';
    for (let attempt = 0; attempt < 48; attempt++) {
      const scale = Math.min(1, edge / longest),
        canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const context = canvas.getContext('2d');
      if (!context) throw Error('浏览器无法处理这张图片。');
      if (outputType === 'image/jpeg') {
        context.fillStyle = '#fff';
        context.fillRect(0, 0, canvas.width, canvas.height);
      }
      image.draw(context, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, outputType, quality));
      if (!blob) throw Error('图片压缩失败，请换一张图片再试。');
      if (blob.type !== outputType) {
        if (outputType === 'image/webp') {
          outputType = 'image/jpeg';
          quality = 0.86;
          continue;
        }
        throw Error('浏览器无法导出头像图片，请换一张图片再试。');
      }
      if (blob.size <= avatarTargetBytes) {
        const extension = outputType === 'image/webp' ? 'webp' : 'jpg';
        return new File([blob], `avatar.${extension}`, {
          type: outputType,
          lastModified: Date.now(),
        });
      }
      if (quality > 0.3) quality = Math.max(0.3, quality * 0.72);
      else if (edge > 64) {
        edge = Math.max(64, Math.floor(edge * 0.7));
        quality = 0.82;
      } else if (quality > 0.12) quality = Math.max(0.12, quality * 0.7);
      else if (edge > 1) {
        edge = Math.max(1, Math.floor(edge * 0.5));
        quality = 0.82;
      } else throw Error('图片压缩未能达到 2 MB，请换一张图片再试。');
    }
    throw Error('图片压缩未能达到 2 MB，请换一张图片再试。');
  } finally {
    image.close();
  }
}

export { compressAvatar };
