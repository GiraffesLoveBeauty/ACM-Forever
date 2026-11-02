import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h, onMounted } from 'vue';
import { api, setAuth, safeNext, pageLoadError } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const App = (await import(await loadSfc('src/App.vue'))).default;
const Header = (await import(await loadSfc('src/components/Header.vue'))).default;
const names = ['window', 'document', 'location', 'history', 'localStorage'];
const original = new Map(
  names.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
);
const originalFetch = globalThis.fetch;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
let dom,
  router,
  mounted,
  releaseAuth,
  guardId = 0;

beforeEach(() => {
  dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/index.html' });
  for (const name of names)
    Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
  router = mounted = releaseAuth = null;
  pageLoadError.value = null;
  setAuth({ authenticated: false }, true);
  globalThis.fetch = async () => response({ authenticated: false });
});
afterEach(async () => {
  releaseAuth?.();
  await settle();
  mounted?.unmount();
  router?.options.history.destroy();
  pageLoadError.value = null;
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [name, descriptor] of original)
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
  globalThis.fetch = originalFetch;
});
after(cleanupCompiled);

async function actualGuard(failingView) {
  const apiUrl = new URL(`../src/lib/api.js?access=${++guardId}`, import.meta.url).href;
  const session = await import(apiUrl);
  let source = await readFile(new URL('../src/router.js', import.meta.url), 'utf8');
  source = source
    .replace(
      "from 'vue-router'",
      `from '${new URL('../node_modules/vue-router/dist/vue-router.mjs', import.meta.url).href}'`,
    )
    .replace("from './lib/api.js'", `from '${apiUrl}'`)
    .replace(/\(\) => import\('\.\/views\/([^']+)'\)/g, (_match, view) =>
      view === failingView
        ? "() => Promise.reject(Error('offline page chunk'))"
        : '() => Promise.resolve({default:{render(){return null}}})',
    );
  router = (await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64')))
    .default;
  return session;
}
function heldAuth(identity) {
  globalThis.fetch = () =>
    new Promise((resolve) => {
      releaseAuth = () => resolve(response(identity));
    });
}

test('return targets preserve query and anchors but reject authentication loops and external URLs', () => {
  const target = '/post.html?id=9&comment_id=21#comment-21';
  assert.equal(safeNext(target), target);
  for (const value of [
    '/login.html',
    '/login.html?next=/post.html',
    '/auth-unavailable.html?next=/home.html',
    '/forbidden.html',
    '/x/../login.html',
    '/%6cogin.html',
    '/%2flogin.html',
    '/%5cexample.org',
    '/post.html%00',
    '//example.org',
    'https://example.org',
    '/\\example.org',
    '/bad%zz',
    null,
    ['x'],
  ])
    assert.equal(safeNext(value, '/home.html'), '/home.html', String(value));
  assert.equal(safeNext('/change-password.html'), '/change-password.html');
  assert.equal(
    safeNext('/change-password.html', '/home.html', ['/change-password.html']),
    '/home.html',
  );
});

for (const target of ['/index.html', '/login.html?next=/compose.html', '/wiki.html?page=guide']) {
  test(`${target} opens before a slow authentication request finishes`, async () => {
    heldAuth({ authenticated: false });
    await actualGuard();
    let opened = false;
    const navigation = router.push(target).then(() => {
      opened = true;
    });
    await settle();
    assert.equal(opened, true);
    assert.equal(router.currentRoute.value.fullPath, target);
    releaseAuth();
    await navigation;
  });
}

test('a background login check returns signed-in users to the requested page', async () => {
  heldAuth({ authenticated: true, role: 'member', qq_id: '12345678' });
  await actualGuard();
  await router.push('/login.html?next=%2Fpost.html%3Fid%3D9%23comment-21');
  releaseAuth();
  await settle();
  assert.equal(router.currentRoute.value.fullPath, '/post.html?id=9#comment-21');
});

test('an ordinary login can return to the requested password change page', async () => {
  globalThis.fetch = async () =>
    response({ authenticated: true, role: 'member', qq_id: '12345678' });
  await actualGuard();
  await router.push('/login.html?next=%2Fchange-password.html');
  await settle();
  assert.equal(router.currentRoute.value.path, '/change-password.html');
});

test('a late authentication check does not redirect a user who has left the login page', async () => {
  heldAuth({ authenticated: true, role: 'member', qq_id: '12345678' });
  await actualGuard();
  await router.push('/login.html?next=%2Fhome.html');
  await router.push('/post.html?id=9');
  releaseAuth();
  await settle();
  assert.equal(router.currentRoute.value.fullPath, '/post.html?id=9');
});

test('first password change keeps the actual destination instead of nesting the login URL', async () => {
  heldAuth({ authenticated: true, role: 'member', qq_id: '12345678', must_change_password: true });
  const session = await actualGuard();
  const next = '/compose.html?draft_id=12#editor';
  await router.push({ path: '/login.html', query: { next } });
  releaseAuth();
  await settle();
  assert.equal(router.currentRoute.value.path, '/change-password.html');
  assert.equal(router.currentRoute.value.query.next, next);
  session.auth.must_change_password = false;
  await router.push(next);
  assert.equal(router.currentRoute.value.fullPath, next);
});

test('legacy administration links and corrected filters retain their anchors', async () => {
  globalThis.fetch = async (url) =>
    response(
      url === '/api/auth/me' ? { authenticated: true, role: 'admin', qq_id: '12345678' } : {},
    );
  await actualGuard();
  await router.push('/member.html?qq_id=12345678#member-profile');
  assert.equal(
    router.currentRoute.value.fullPath,
    '/admin.html?qq_id=12345678&section=members#member-profile',
  );
  await router.push('/admin.html?section=bad&tab=bad#dashboard');
  assert.equal(router.currentRoute.value.fullPath, '/admin.html#dashboard');
});

test('header login returns to the current post and anchor', async () => {
  mounted = await mount(
    Header,
    [
      { path: '/post.html', component: { render: () => null } },
      { path: '/login.html', component: { render: () => null } },
      { path: '/index.html', component: { render: () => null } },
    ],
    '/post.html?id=9#comment-21',
  );
  const link = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '登录社区')[0];
  const href = new URL(link.props.href, location.origin);
  assert.equal(href.pathname, '/login.html');
  assert.equal(href.searchParams.get('next'), '/post.html?id=9#comment-21');
});

for (const [status, page] of [
  [401, '/login.html'],
  [428, '/change-password.html'],
]) {
  test(`HTTP ${status} retains the current query and anchor during session recovery`, async () => {
    const redirects = [];
    Object.defineProperty(globalThis, 'location', {
      configurable: true,
      value: {
        pathname: '/post.html',
        search: '?id=9',
        hash: '#comment-21',
        assign: (url) => redirects.push(url),
      },
    });
    setAuth({ authenticated: true, role: 'member', qq_id: '12345678' }, true);
    globalThis.fetch = async () => response({ message: 'session changed' }, status);
    await assert.rejects(api('/forum/posts/9/comments'), { status });
    const target = new URL(redirects[0], 'http://localhost');
    assert.equal(target.pathname, page);
    assert.equal(target.searchParams.get('next'), '/post.html?id=9#comment-21');
  });
}

test('a failed page import exposes the intended destination and successful navigation clears it', async () => {
  globalThis.fetch = async () =>
    response({ authenticated: true, role: 'member', qq_id: '12345678' });
  const session = await actualGuard('Post.vue');
  await router.push('/home.html');
  await assert.rejects(router.push('/post.html?id=9#comment-21'), /offline page chunk/);
  assert.equal(session.pageLoadError.value.target, '/post.html?id=9#comment-21');
  assert.equal(router.currentRoute.value.path, '/home.html');
  await router.push('/index.html');
  assert.equal(session.pageLoadError.value, null);
});

test('the first page import can fail without leaving recovery state empty', async () => {
  const session = await actualGuard('Forum.vue');
  await assert.rejects(router.push('/index.html'), /offline page chunk/);
  assert.equal(session.pageLoadError.value.target, '/index.html');
});

test('the load failure panel preserves the current view and reloads the failed destination on demand', async () => {
  let mounts = 0;
  const Current = {
    setup() {
      onMounted(() => mounts++);
      return () => h('p', '当前内容');
    },
  };
  mounted = await mount(App, [{ path: '/index.html', component: Current, meta: { public: true } }]);
  pageLoadError.value = { target: '/post.html?id=9#comment-21' };
  await settle();
  assert.match(textOf(mounted.root), /页面加载失败/);
  assert.match(textOf(mounted.root), /当前内容/);
  assert.equal(mounts, 1);
  const redirects = [];
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { assign: (url) => redirects.push(url) },
  });
  const button = (name) =>
    find(mounted.root, (node) => node.type === 'button' && textOf(node).trim() === name)[0];
  button('重新加载目标页面').props.onClick();
  assert.deepEqual(redirects, ['/post.html?id=9#comment-21']);
  button('继续当前页面').props.onClick();
  await settle();
  assert.equal(pageLoadError.value, null);
  assert.equal(mounts, 1);
});
