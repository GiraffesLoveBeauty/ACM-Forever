import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import createDOMPurify from 'dompurify';
import { marked } from 'marked';
import { postImage, postExcerpt } from '../src/lib/post-images.js';

const renderer = await readFile(
  new URL('../../api/acm_api/public/assets/forum-markdown.js', import.meta.url),
  'utf8',
);
const image = '/api/forum/images/' + 'a'.repeat(32);

test('forum Markdown allows managed images and removes external and active content', () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'outside-only',
  });
  const { window } = dom;
  window.marked = marked;
  window.DOMPurify = createDOMPurify(window);
  window.eval(renderer);
  window.document.body.innerHTML = window.renderForumMarkdown(
    [
      `![本地插图](${image})`,
      '![外部图片](https://example.com/image.png)',
      '![内嵌数据](data:image/png;base64,AAAA)',
      `<img src="${image}" onerror="alert(1)" srcset="https://example.com/leak.png 2x">`,
      '<iframe src="https://example.com"></iframe>',
      '`![代码里的图片](' + image + ')`',
      '$x^2 + y^2$',
    ].join('\n\n'),
  );
  const images = [...window.document.querySelectorAll('img')];
  assert.equal(images.length, 2);
  for (const node of images) {
    assert.equal(node.getAttribute('src'), image);
    assert.equal(node.hasAttribute('onerror'), false);
    assert.equal(node.hasAttribute('srcset'), false);
    assert.equal(node.getAttribute('loading'), 'lazy');
  }
  assert.equal(window.document.querySelector('iframe'), null);
  assert.match(window.document.querySelector('code').textContent, /代码里的图片/);
  assert.match(window.document.body.textContent, /外部图片/);
  assert.match(window.document.body.textContent, /\$x\^2 \+ y\^2\$/);
  dom.window.close();
});

test('cover URLs are restricted to managed assets and excerpts omit image syntax', () => {
  assert.equal(postImage(image), image);
  for (const value of [
    'https://example.com' + image,
    image + '/../../secret',
    image + '?x=1',
    'javascript:alert(1)',
    null,
  ])
    assert.equal(postImage(value), '');
  assert.equal(
    postExcerpt(`# 标题\n\n![图片](${image})\n说明 **清晰**，见[参考](https://example.com)。`),
    '标题 说明 清晰，见参考。',
  );
});
