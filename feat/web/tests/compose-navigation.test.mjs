import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';

// These editor checks survive independently of the removed Wiki editor suite.
const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/compose.html' });
for (const name of [
  'window',
  'document',
  'Node',
  'Element',
  'Event',
  'HTMLElement',
  'SVGElement',
  'location',
  'history',
  'localStorage',
])
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
const { createApp, h, nextTick } = await import('vue');
const { createRouter, createMemoryHistory, RouterView } = await import('vue-router');
const { setAuth } = await import('../src/lib/api.js');
const { loadSfc, cleanupCompiled } = await import('./helpers/vue-harness.mjs');
const Compose = (await import(await loadSfc('src/views/Compose.vue'))).default;
const originalFetch = globalThis.fetch;
let app, host, router, writes;
async function settle() {
  for (let i = 0; i < 10; i++) {
    await new Promise((resolve) => setImmediate(resolve));
    await nextTick();
  }
}
async function input(selector, value) {
  const node = host.querySelector(selector);
  assert.ok(node, selector);
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
  await settle();
}
beforeEach(async () => {
  writes = [];
  localStorage.clear();
  setAuth(
    { authenticated: true, role: 'member', qq_id: '10000001', csrf_token: 'test-only' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    const response = (data) => new Response(JSON.stringify(data), { status: 200 });
    if (url === '/api/forum/categories') return response([{ id: 2, name: '求助问答' }]);
    if (url === '/api/forum/drafts' && !options.method) return response([]);
    if (/^\/api\/forum\/drafts(?:\/12)?$/.test(url) && ['POST', 'PUT'].includes(options.method)) {
      writes.push({ method: options.method, body: JSON.parse(options.body) });
      return response({ id: 12 });
    }
    throw Error(`Unexpected request: ${url}`);
  };
  host = document.createElement('div');
  document.body.append(host);
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/compose.html', component: Compose },
      { path: '/elsewhere', component: { render: () => h('p', '其他页面') } },
    ],
  });
  await router.push('/compose.html');
  app = createApp({ render: () => h(RouterView) });
  app.directive('forum-math', {});
  app.use(router);
  app.mount(host);
  await settle();
});
afterEach(() => {
  app.unmount();
  host.remove();
  router.options.history.destroy();
  globalThis.fetch = originalFetch;
  setAuth({ authenticated: false }, true);
});
after(async () => {
  await cleanupCompiled();
  dom.window.close();
});

for (const failed of [false, true]) {
  test(`editor keeps saving after navigation is ${failed ? 'failed' : 'cancelled'}`, async () => {
    await input('input[maxlength="120"]', '导航失败后的草稿');
    await input('textarea[aria-label="帖子 Markdown 正文"]', '先保存的内容');
    const unregister = router.beforeEach(() => {
      if (failed) throw Error('合成导航失败');
      return false;
    });
    if (failed) await assert.rejects(router.push('/elsewhere'), /合成导航失败/);
    else await router.push('/elsewhere');
    unregister();
    assert.equal(router.currentRoute.value.fullPath, '/compose.html');
    assert.equal(writes[0].method, 'POST');
    await input('textarea[aria-label="帖子 Markdown 正文"]', '继续编辑的内容');
    const save = [...host.querySelectorAll('button')].find(
      (node) => node.textContent.trim() === '保存草稿',
    );
    save.click();
    await settle();
    assert.equal(router.currentRoute.value.query.draft_id, '12');
    assert.equal(
      host.querySelector('textarea[aria-label="帖子 Markdown 正文"]').value,
      '继续编辑的内容',
    );
    assert.equal(writes.at(-1).method, 'PUT');
    assert.equal(writes.at(-1).body.body, '继续编辑的内容');
  });
}
