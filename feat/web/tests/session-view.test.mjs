import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { defineComponent, h, onMounted } from 'vue';
import { auth, api, logoutSession, setAuth } from '../src/lib/api.js';
import { adminFilters, cfMemory } from '../src/lib/admin.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

// Compile the real client templates and mount them with Vue + Vue Router.
// Only the theme editor and artwork are stubbed. This is not a browser layout test.
const App = (await import(await loadSfc('src/App.vue'))).default;
const Forum = (await import(await loadSfc('src/views/Forum.vue'))).default;
const originalFetch = globalThis.fetch;
const originalDocument = globalThis.document;
const originalLocation = globalThis.location;
let mounted, serverUser, calls, holdFeed, logoutStatus, feedStatus;
const pendingFeeds = [];
const routes = [
  { path: '/index.html', component: Forum, meta: { public: true } },
  { path: '/login.html', component: { render: () => null }, meta: { public: true } },
  { path: '/home.html', component: { render: () => null } },
  { path: '/post.html', component: { render: () => null }, meta: { public: true } },
  { path: '/leaderboard.html', component: { render: () => null }, meta: { public: true } },
  { path: '/compose.html', component: { render: () => null } },
  { path: '/admin.html', component: { render: () => null } },
];
function signedIn(qq = '10000001') {
  serverUser = qq;
  setAuth({ authenticated: true, qq_id: qq, role: 'member', csrf_token: 'test-only' }, true);
}
function response(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
beforeEach(() => {
  mounted = null;
  calls = [];
  holdFeed = false;
  logoutStatus = feedStatus = 200;
  globalThis.document = {
    addEventListener() {},
    removeEventListener() {},
    documentElement: { style: { setProperty() {} } },
  };
  globalThis.location = { pathname: '/index.html', search: '', assign() {} };
  signedIn();
  globalThis.fetch = async (url, options = {}) => {
    const viewer = serverUser;
    calls.push({ url, options, viewer });
    if (url === '/api/auth/logout') {
      if (logoutStatus === 200) serverUser = null;
      return response({ message: 'logout' }, logoutStatus);
    }
    if (url === '/api/forum/categories') return response([]);
    if (url.startsWith('/api/forum/posts?')) {
      const data = {
        rows: [
          {
            id: 1,
            title: 'session regression topic',
            excerpt: 'fixture',
            viewer_liked: viewer === '10000001',
            viewer_bookmarked: Boolean(viewer),
            likes_count: 1,
          },
        ],
        total: 1,
      };
      if (holdFeed && url.includes('sort=latest'))
        return new Promise((resolve) => pendingFeeds.push(() => resolve(response(data))));
      return response(data, feedStatus);
    }
    throw Error(`Unexpected test request: ${url}`);
  };
});
afterEach(async () => {
  mounted?.unmount();
  while (pendingFeeds.length) pendingFeeds.shift()();
  await settle();
  setAuth({ authenticated: false }, true);
  globalThis.fetch = originalFetch;
  globalThis.document = originalDocument;
  globalThis.location = originalLocation;
});
after(cleanupCompiled);

function cards() {
  return find(mounted.root, (n) => n.type === 'article' && n.props.class === 'forum-post-card');
}
function actions() {
  return find(cards()[0], (n) => n.type === 'button');
}
function active(button) {
  return String(button.props.class || '').includes('is-active');
}
function feedCalls() {
  return calls.filter((c) => c.url.includes('/forum/posts?') && c.url.includes('sort=latest'));
}

test('logout on the current forum route reloads anonymous like and bookmark states', async () => {
  mounted = await mount(App, routes);
  assert.ok(active(actions()[0]));
  assert.ok(active(actions()[1]));
  const logout = find(mounted.root, (n) => n.type === 'button' && textOf(n) === '退出')[0];
  await logout.props.onClick();
  await settle();
  assert.equal(auth.authenticated, false);
  assert.equal(mounted.router.currentRoute.value.path, '/index.html');
  assert.equal(feedCalls().length, 2);
  assert.equal(active(actions()[0]), false);
  assert.equal(active(actions()[1]), false);
});

test('switching accounts on the same route renders the next account states', async () => {
  mounted = await mount(App, routes);
  signedIn('10000002');
  await settle();
  assert.equal(feedCalls().length, 2);
  assert.equal(active(actions()[0]), false);
  assert.equal(active(actions()[1]), true);
});

test('failed logout preserves the current session and viewer states', async () => {
  mounted = await mount(App, routes);
  logoutStatus = 500;
  const logout = find(mounted.root, (n) => n.type === 'button' && textOf(n) === '退出')[0];
  await logout.props.onClick();
  await settle();
  assert.equal(auth.authenticated, true);
  assert.equal(feedCalls().length, 1);
  assert.ok(active(actions()[0]));
  assert.ok(active(actions()[1]));
});

test('cancelling the leave guard prevents the logout request', async () => {
  mounted = await mount(App, routes, '/home.html');
  mounted.router.beforeEach(() => false);
  const logout = find(mounted.root, (n) => n.type === 'button' && textOf(n) === '退出')[0];
  await logout.props.onClick();
  await settle();
  assert.equal(auth.authenticated, true);
  assert.equal(mounted.router.currentRoute.value.path, '/home.html');
  assert.equal(calls.filter((c) => c.url === '/api/auth/logout').length, 0);
});

test('a 401 expires the current view and removes its personalized cards', async () => {
  mounted = await mount(App, routes);
  feedStatus = 401;
  await assert.rejects(api('/forum/posts?sort=latest'), { status: 401 });
  await settle();
  assert.equal(auth.authenticated, false);
  assert.equal(cards().length, 0);
});

test('a late authenticated feed cannot replace the anonymous feed after logout', async () => {
  holdFeed = true;
  mounted = await mount(App, routes);
  assert.equal(cards().length, 0);
  holdFeed = false;
  await logoutSession();
  await settle();
  assert.equal(cards().length, 1);
  while (pendingFeeds.length) pendingFeeds.shift()();
  await settle();
  assert.equal(active(actions()[0]), false);
  assert.equal(active(actions()[1]), false);
});

test('failed anonymous reload shows an empty error instead of the previous account cards', async () => {
  mounted = await mount(App, routes);
  feedStatus = 500;
  await logoutSession();
  await settle();
  assert.equal(cards().length, 0);
  assert.match(textOf(mounted.root), /话题加载失败/);
});

test('a protected page is removed without remounting it under anonymous credentials', async () => {
  let mounts = 0;
  const Protected = defineComponent({
    setup() {
      onMounted(() => mounts++);
      return () => h('div', { 'data-private': true }, 'protected account data');
    },
  });
  mounted = await mount(
    App,
    [
      ...routes.filter((r) => r.path !== '/home.html'),
      { path: '/home.html', component: Protected },
    ],
    '/home.html',
  );
  assert.equal(mounts, 1);
  await logoutSession();
  await settle();
  assert.equal(mounts, 1);
  assert.equal(find(mounted.root, (n) => n.props['data-private']).length, 0);
});

test('ordinary duplicate navigation preserves the mounted forum and avoids extra requests', async () => {
  mounted = await mount(App, routes);
  const oldCard = cards()[0];
  await mounted.router.push('/index.html');
  await settle();
  assert.equal(feedCalls().length, 1);
  assert.equal(cards()[0], oldCard);
});

test('logout clears CF tasks, candidate input, member scopes and all saved admin filters', async () => {
  Object.assign(cfMemory, {
    job: { id: 42 },
    submission: { id: 42 },
    input: '1843A',
    statuses: ['fixture'],
    excluded: ['10000003'],
    recheck: true,
  });
  adminFilters.training = { owner: '10000003' };
  adminFilters.problems = { search: 'fixture' };
  await logoutSession();
  assert.equal(cfMemory.job, null);
  assert.equal(cfMemory.submission, null);
  assert.equal(cfMemory.input, '');
  assert.deepEqual(cfMemory.statuses, []);
  assert.deepEqual(cfMemory.excluded, []);
  assert.equal(cfMemory.recheck, false);
  assert.deepEqual(adminFilters, {});
  assert.equal(auth.qq_id, null);
});

test('an API response from an earlier session is discarded even when fetch ignores abort', async () => {
  holdFeed = true;
  const oldRequest = api('/forum/posts?sort=latest');
  const rejected = assert.rejects(oldRequest, { name: 'AbortError' });
  signedIn('10000002');
  pendingFeeds.shift()();
  await rejected;
});
