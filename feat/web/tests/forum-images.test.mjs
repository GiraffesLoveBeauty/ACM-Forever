import assert from 'node:assert/strict';
import { after, afterEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const name of [
  'window',
  'document',
  'Node',
  'Element',
  'HTMLElement',
  'SVGElement',
  'navigator',
  'location',
])
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.open = false;
  this.dispatchEvent(new dom.window.Event('close'));
};
const { createApp, nextTick } = await import('vue');
const { loadSfc, cleanupCompiled } = await import('./helpers/vue-harness.mjs');
const Cover = (await import(await loadSfc('src/components/PostCover.vue'))).default;
const Lightbox = (await import(await loadSfc('src/components/ImageLightbox.vue'))).default;
const source = '/api/forum/images/' + 'a'.repeat(32);
let app, host, instance;
function mount(component, props) {
  host = document.createElement('div');
  document.body.append(host);
  app = createApp(component, props);
  instance = app.mount(host);
}
afterEach(() => {
  app?.unmount();
  host?.remove();
});
after(async () => {
  await cleanupCompiled();
  dom.window.close();
});

test('list cover loads a lazy thumbnail and detail requests the original', async () => {
  mount(Cover, { src: source, thumbnail: true });
  assert.equal(host.querySelector('img').getAttribute('src'), source + '?variant=thumb');
  assert.equal(host.querySelector('img').getAttribute('loading'), 'lazy');
  host.querySelector('img').dispatchEvent(new dom.window.Event('error'));
  await nextTick();
  assert.match(host.textContent, /无法显示/);
  assert.equal(host.querySelector('button'), null); // Covers in cards sit inside a link.
});
test('keyboard opens the original and closing removes it from the modal', async () => {
  mount(Cover, { src: source, zoom: true, eager: true, alt: '算法配图' });
  const cover = host.querySelector('img');
  assert.equal(cover.getAttribute('src'), source);
  assert.equal(cover.getAttribute('loading'), 'eager');
  assert.equal(cover.getAttribute('tabindex'), '0');
  cover.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await nextTick();
  assert.equal(host.querySelector('dialog').open, true);
  assert.equal(host.querySelector('dialog img').getAttribute('src'), source);
  host.querySelector('dialog button').click();
  await nextTick();
  assert.equal(host.querySelector('dialog').open, false);
  assert.equal(host.querySelector('dialog img'), null);
});
test('failed detail and enlarged images can retry without changing the original URL', async () => {
  mount(Cover, { src: source, zoom: true });
  host.querySelector('img').dispatchEvent(new dom.window.Event('error'));
  await nextTick();
  host.querySelector('figcaption button').click();
  await nextTick();
  host.querySelector('img').click();
  await nextTick();
  host.querySelector('dialog img').dispatchEvent(new dom.window.Event('error'));
  await nextTick();
  assert.match(host.querySelector('[role=alert]').textContent, /无法加载/);
  host.querySelector('[role=alert] button').click();
  await nextTick();
  assert.equal(host.querySelector('dialog img').getAttribute('src'), source);
});
test('lightbox rejects external and query-bearing image sources', async () => {
  mount(Lightbox);
  for (const url of [
    'https://other.test/a.png',
    source + '?variant=thumb',
    'javascript:alert(1)',
  ]) {
    instance.open(url);
    await nextTick();
    assert.equal(host.querySelector('dialog').open, false);
    assert.equal(host.querySelector('img'), null);
  }
});
