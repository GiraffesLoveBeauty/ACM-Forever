import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/' });
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
globalThis.IntersectionObserver = class {
  observe() {}
  disconnect() {}
};
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
const { createApp, h, nextTick } = await import('vue');
const { createRouter, createMemoryHistory, RouterView } = await import('vue-router');
const { auth, setAuth } = await import('../src/lib/api.js');
const { notificationsChanged } = await import('../src/lib/forum-notifications.js');
const { loadSfc, cleanupCompiled } = await import('./helpers/vue-harness.mjs');
const load = async (path) => (await import(await loadSfc(path))).default;
const Bell = await load('src/components/NotificationBell.vue');
const Notifications = await load('src/views/Notifications.vue');
const MyPost = await load('src/views/MyPost.vue');
const Moderation = await load('src/admin/Moderation.vue');
const Post = await load('src/views/Post.vue');
const Home = await load('src/views/Home.vue');
const originalFetch = globalThis.fetch;
let app, host, router, calls, rows, failList, releaseList, holdList, holdCount, releaseCount, post;
const fixture = (id, kind = 'comment') => ({
  id,
  kind,
  post_id: 12,
  comment_id: id + 20,
  post_title: `通知话题 ${id}`,
  created_at: 1000 + id,
  read_at: null,
  actor_name: '演示学长',
  review_reason: '',
  target_url: `/post.html?id=12&comment_id=${id + 20}#comment-${id + 20}`,
});
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
async function settle() {
  for (let i = 0; i < 10; i++) {
    await new Promise((resolve) => setImmediate(resolve));
    await nextTick();
  }
}
const button = (label) =>
  [...host.querySelectorAll('button')].find((node) => node.textContent.trim() === label);
async function click(label) {
  assert.ok(button(label), label);
  button(label).click();
  await settle();
}
async function mount(path = '/notifications.html', bellOnly = false) {
  host = document.createElement('div');
  document.body.append(host);
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/notifications.html', component: Notifications },
      { path: '/my-post.html', component: MyPost },
      { path: '/admin.html', component: Moderation },
      { path: '/post.html', component: Post },
      { path: '/home.html', component: Home },
      { path: '/index.html', component: { render: () => h('p', '论坛') } },
    ],
  });
  app = createApp({ render: () => (bellOnly ? h(Bell) : h(RouterView)) });
  app.directive('forum-math', {});
  app.use(router);
  await router.push(path);
  await router.isReady();
  app.mount(host);
  await settle();
}
beforeEach(() => {
  calls = [];
  rows = [
    fixture(3),
    {
      ...fixture(2, 'rejected'),
      review_reason: '<img src=x onerror=alert(1)> 请补充思路。',
      target_url: '/my-post.html?id=12',
    },
  ];
  failList = holdList = holdCount = false;
  releaseList = releaseCount = null;
  post = {
    id: 12,
    title: '我的求助话题',
    body: '这是投稿正文',
    category_name: '求助问答',
    status: 'pending',
    created_at: 1000,
    reviewed_at: null,
    review_reason: '',
    comments: [],
  };
  setAuth(
    { authenticated: true, qq_id: '10000001', role: 'member', csrf_token: 'feedback-test-only' },
    true,
  );
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/me/notifications/count') {
      if (holdCount)
        return new Promise((resolve) => {
          releaseCount = () => resolve(response({ unread_count: 88 }));
        });
      return response({ unread_count: rows.filter((row) => !row.read_at).length });
    }
    if (url.startsWith('/api/me/notifications?')) {
      const unread = new URL(url, location.origin).searchParams.get('unread') === '1';
      const result = {
        rows: rows.filter((row) => !unread || !row.read_at),
        total: rows.filter((row) => !unread || !row.read_at).length,
        page_size: 20,
        unread_count: rows.filter((row) => !row.read_at).length,
        latest_id: 3,
      };
      if (holdList)
        return new Promise((resolve) => {
          releaseList = () => resolve(response(result));
        });
      return response(failList ? { message: '临时不可用' } : result, failList ? 503 : 200);
    }
    if (/\/api\/me\/notifications\/\d+\/read$/.test(url)) {
      rows.find((row) => row.id === Number(url.split('/').at(-2))).read_at = 2000;
      return response({ success: true });
    }
    if (url === '/api/me/notifications/read-all') {
      const { through_id } = JSON.parse(options.body);
      rows
        .filter((row) => row.id <= through_id)
        .forEach((row) => {
          row.read_at = 2000;
        });
      return response({ success: true });
    }
    if (url === '/api/forum/mine/posts/12') return response(post);
    if (url.startsWith('/api/forum/posts/12'))
      return response({
        ...post,
        status: 'published',
        comments: [
          { id: 20, body: '讨论根评论', parent_id: null, author_name: '同学甲', created_at: 1000 },
          { id: 23, body: '讨论回复', parent_id: 20, author_name: '同学乙', created_at: 1001 },
        ],
      });
    if (url === '/api/forum/moderation/posts')
      return response([{ id: 12, title: post.title, body: post.body }]);
    if (url === '/api/forum/moderation/posts/12') return response({ success: true });
    if (url === '/api/me/profile')
      return response({
        user: { name: '演示成员' },
        recent_ac: [],
        bindings: [],
        platform_counts: {},
      });
    if (url === '/api/forum/mine/posts')
      return response([
        { id: 12, title: '待审核的投稿', status: 'pending', category_name: '求助问答' },
        {
          id: 13,
          title: '被退回的投稿',
          status: 'rejected',
          category_name: '求助问答',
          review_reason: '请补充题目链接。',
        },
      ]);
    throw Error(`Unexpected request ${url}`);
  };
});
afterEach(async () => {
  app?.unmount();
  app = null;
  releaseCount?.();
  releaseList?.();
  await settle();
  host?.remove();
  setAuth({ authenticated: false }, true);
  globalThis.fetch = originalFetch;
});
after(async () => {
  await cleanupCompiled();
  dom.window.close();
});

test('notification list shows unread feedback and renders rejection reasons as plain text', async () => {
  await mount();
  assert.match(host.textContent, /有人评论了你的话题/);
  assert.match(host.textContent, /话题被退回/);
  assert.match(host.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(host.querySelector('.forum-feedback-reason img'), null);
  assert.equal(host.querySelectorAll('.forum-notification-item.unread').length, 2);
  await click('标为已读');
  assert.equal(host.querySelectorAll('.forum-notification-item.unread').length, 1);
  const write = calls.find((call) => call.url.endsWith('/3/read'));
  assert.equal(write.options.headers['X-CSRF-Token'], 'feedback-test-only');
});

test('opening a reply marks it read and navigates to real comment anchors', async () => {
  await mount();
  await click('查看讨论');
  assert.equal(router.currentRoute.value.fullPath, '/post.html?id=12&comment_id=23#comment-23');
  assert.ok(calls.some((call) => call.url === '/api/forum/posts/12?comment_id=23'));
  assert.ok(host.querySelector('#comment-20'));
  assert.ok(host.querySelector('#comment-23'));
  assert.ok(host.querySelector('#comment-23.is-highlighted-comment'));
  assert.equal(host.querySelector('#comment-20.is-highlighted-comment'), null);
  await router.push('/post.html?id=12&comment_id=20#comment-20');
  await settle();
  assert.ok(host.querySelector('#comment-20.is-highlighted-comment'));
  assert.equal(host.querySelector('#comment-23.is-highlighted-comment'), null);
});

test('read all sends the loaded snapshot and leaves newer arrivals unread', async () => {
  await mount();
  rows.unshift(fixture(4));
  await click('全部标为已读');
  const call = calls.find((call) => call.url.endsWith('/read-all'));
  assert.deepEqual(JSON.parse(call.options.body), { through_id: 3 });
  assert.equal(host.querySelectorAll('.forum-notification-item.unread').length, 1);
});

test('a failed notification load exposes retry without pretending there are no notifications', async () => {
  failList = true;
  await mount();
  assert.match(host.textContent, /通知加载失败：临时不可用/);
  assert.doesNotMatch(host.textContent, /暂无通知/);
  failList = false;
  await click('重试');
  assert.equal(host.querySelectorAll('.forum-notification-item').length, 2);
});

test('switching filters discards a late response from the previous query', async () => {
  holdList = true;
  await mount();
  const release = releaseList;
  holdList = false;
  rows[1].read_at = 2000;
  await router.push('/notifications.html?unread=1');
  await settle();
  release();
  await settle();
  assert.equal(host.querySelectorAll('.forum-notification-item').length, 1);
  assert.doesNotMatch(host.textContent, /话题被退回/);
});

test('the bell refreshes its unread count and clears it across account changes', async () => {
  await mount('/index.html', true);
  assert.equal(host.querySelector('a').getAttribute('aria-label'), '通知，2 条未读');
  rows.pop();
  notificationsChanged();
  await settle();
  assert.equal(host.querySelector('a').getAttribute('aria-label'), '通知，1 条未读');
  setAuth({ authenticated: false }, true);
  await settle();
  assert.equal(host.querySelector('a'), null);
});

test('a late counter result cannot reintroduce the previous account count', async () => {
  holdCount = true;
  await mount('/index.html', true);
  const release = releaseCount;
  holdCount = false;
  rows = [];
  setAuth({ authenticated: true, qq_id: '10000002', role: 'member', csrf_token: 'other' }, true);
  await settle();
  release();
  await settle();
  assert.equal(host.querySelector('a').getAttribute('aria-label'), '通知');
  assert.equal(host.querySelector('.forum-notification-count'), null);
});

test('hidden pages do not poll the server and refresh when visible again', async () => {
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  await mount('/index.html', true);
  assert.equal(calls.length, 0);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  document.dispatchEvent(new Event('visibilitychange'));
  await settle();
  assert.equal(host.querySelector('a').getAttribute('aria-label'), '通知，2 条未读');
});

test('first-password-change and legacy sessions do not request personal notifications', async () => {
  setAuth(
    { authenticated: true, qq_id: '10000001', role: 'member', must_change_password: true },
    true,
  );
  await mount('/index.html', true);
  assert.equal(calls.length, 0);
  assert.equal(host.querySelector('a'), null);
  setAuth({ authenticated: true, qq_id: null, role: 'root' }, true);
  await settle();
  assert.equal(calls.length, 0);
});

test('the author can inspect pending progress and the eventual rejection explanation', async () => {
  await mount('/my-post.html?id=12');
  assert.match(host.textContent, /等待管理员审核/);
  assert.match(host.textContent, /这是投稿正文/);
  post = { ...post, status: 'rejected', review_reason: '请补充测试样例。', reviewed_at: 2000 };
  await click('刷新状态');
  assert.match(host.textContent, /审核未通过/);
  assert.match(host.textContent, /退回原因：请补充测试样例/);
});

test('a deleted pending submission does not still promise an upcoming review', async () => {
  post.status = 'removed';
  await mount('/my-post.html?id=12');
  assert.match(host.textContent, /未完成审核，投稿已删除/);
  assert.doesNotMatch(host.textContent, /等待管理员审核|审核结果会通过站内通知告知你/);
});

test('historical reviewed posts without a timestamp do not appear pending', async () => {
  post.status = 'published';
  await mount('/my-post.html?id=12');
  assert.match(host.textContent, /审核通过，已发布/);
  assert.match(host.textContent, /已完成审核/);
  assert.match(host.textContent, /此前未记录审核时间/);
  assert.doesNotMatch(host.textContent, /等待管理员审核/);
});

test('moderators must explain rejection and that explanation is submitted to the API', async () => {
  await mount('/admin.html');
  await click('退回');
  assert.match(host.textContent, /请填写退回原因/);
  assert.equal(calls.filter((call) => call.options.method === 'POST').length, 0);
  const textarea = host.querySelector('textarea');
  textarea.value = '请补充题目链接。';
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  await settle();
  await click('退回');
  const write = calls.find((call) => call.options.method === 'POST');
  assert.deepEqual(JSON.parse(write.options.body), {
    decision: 'reject',
    reason: '请补充题目链接。',
  });
});

test('personal posts provide progress links for pending and rejected submissions', async () => {
  await mount('/home.html');
  assert.equal(
    host.querySelector('a[href="/my-post.html?id=12"]').textContent.includes('待审核的投稿'),
    true,
  );
  assert.equal(
    host.querySelector('a[href="/my-post.html?id=13"]').textContent.includes('请补充题目链接'),
    true,
  );
});
