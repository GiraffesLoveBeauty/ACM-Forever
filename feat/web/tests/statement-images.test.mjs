import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { trustedStatementImage } from '../src/lib/statement-images.js';
import { renderStatementMarkdown } from '../src/lib/statement-math.js';
const render = text => {
  const dom = new JSDOM('<body/>', { url:'http://localhost' });
  const root = dom.window.document.createElement('div');
  root.innerHTML = renderStatementMarkdown(text, dom.window.document);
  return root;
};

test('translated paragraphs, two images, math and samples retain their relative positions', () => {
  const root = render('第一段。\n\n![图一](https://img.atcoder.jp/one.png)\n\n第二段 $N$。\n\n![图二](https://codeforces.com/two.png)\n\n'+
    '```\n1  2\n\n```\n\n第三段。');
  const paragraphs = [...root.querySelectorAll('p')];
  assert.equal(paragraphs[0].textContent,'第一段。');
  assert.ok(paragraphs[1].querySelector('img[src$="one.png"]'));
  assert.ok(paragraphs[2].querySelector('math'));
  assert.ok(paragraphs[3].querySelector('img[src$="two.png"]'));
  assert.equal(root.querySelector('pre code').textContent,'1  2\n\n');
  assert.equal(paragraphs.at(-1).textContent,'第三段。');
});

test('a linked image keeps its existing link without nested anchors', () => {
  const root = render('[![原图](https://img.atcoder.jp/one.png)](https://atcoder.jp/contests/example)');
  assert.equal(root.querySelectorAll('a').length,1);
  assert.equal(root.querySelectorAll('a a').length,0);
  assert.equal(root.querySelector('img').getAttribute('referrerpolicy'),'no-referrer');
});

test('trusted HTTP images are upgraded to HTTPS and image attributes cannot execute scripts', () => {
  const root = render('<img src="http://img.atcoder.jp/one.png" srcset="https://evil.invalid/x 2x" onerror="alert(1)">');
  assert.equal(root.querySelector('img').src,'https://img.atcoder.jp/one.png');
  assert.equal(root.querySelectorAll('[srcset],[onerror],script').length,0);
});

for (const url of ['https://evil.invalid/a.png','https://atcoder.jp.evil.invalid/a.png',
  'https://user:password@img.atcoder.jp/a.png','https://img.atcoder.jp:8443/a.png',
  'data:image/svg+xml,anything','javascript:alert(1)','/untrusted-relative.png']) {
  test('untrusted image is not loaded: '+url.replace('user:password@','credentials@'), () => {
    assert.equal(trustedStatementImage(url),'');
    const root = render('<img src="'+url+'" alt="图片说明">');
    assert.equal(root.querySelectorAll('img,a[href]').length,0);
    assert.ok(root.textContent.includes('来源未获支持'));
  });
}

test('allowed image host variants keep a deterministic normalized URL', () => {
  for (const url of ['https://atcoder.jp/x.png','https://img.atcoder.jp/x.png','https://espresso.codeforces.com/x.png']) {
    assert.equal(trustedStatementImage(url),url);
  }
});
