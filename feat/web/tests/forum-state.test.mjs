import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { forumState, forumQuery, forumReturn } from '../src/lib/forum-state.js';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Forum = (await import(await loadSfc('src/views/Forum.vue'))).default;
const previousFetch = globalThis.fetch;
let mounted, calls, fail;
beforeEach(() => {
  calls = [];
  fail = false;
  setAuth({ authenticated: false }, true);
  globalThis.fetch = async (url) => {
    calls.push(url);
    let data = [];
    if (url.includes('/forum/posts?')) {
      const query = new URL(url, 'http://localhost').searchParams;
      if (query.get('page_size') === '4') data = { rows: [] };
      else
        data = {
          total: 25,
          rows: [{ id: Number(query.get('page')), title: '分页话题', excerpt: '正文' }],
        };
    }
    return new Response(JSON.stringify(fail ? { message: '临时故障' } : data), {
      status: fail ? 503 : 200,
    });
  };
});
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  globalThis.fetch = previousFetch;
});
after(cleanupCompiled);
const open = async (path) => {
  mounted = await mount(
    { render: () => h(RouterView) },
    [
      { path: '/index.html', component: Forum },
      { path: '/post.html', component: { render: () => h('p', '帖子') } },
    ],
    path,
  );
};
const click = async (label) => {
  const button = find(
    mounted.root,
    (node) => node.type === 'button' && textOf(node).trim() === label,
  )[0];
  assert.ok(button, label);
  await button.props.onClick();
  await settle();
};
test('URL state is bounded and forum return targets cannot escape the listing', () => {
  assert.deepEqual(
    forumState({ sort: 'bad', page: 'no', q: ['private'], category: '../x', view: 'bad' }),
    { sort: 'latest', page: 1, q: '', category: '', view: 'list' },
  );
  assert.equal(forumState({ page: '999999999999' }).page, 1000000);
  const state = forumState({ sort: 'hot', page: '2', q: ' 图论 ', category: 'help', view: 'grid' });
  assert.deepEqual(forumState(forumQuery(state)), state);
  for (const value of ['//example.org', '/admin.html', '/post.html?id=1', '/\\evil', null])
    assert.equal(forumReturn(value), '/index.html');
  assert.equal(forumReturn('/index.html?page=2&view=grid'), '/index.html?page=2&view=grid');
});
test('opening a shared page restores filtering, pagination and grid mode', async () => {
  await open('/index.html?category=help&q=图论&page=2&view=grid');
  const call = calls.find((url) => url.includes('page_size=12'));
  const query = new URL(call, 'http://localhost').searchParams;
  assert.equal(query.get('page'), '2');
  assert.equal(query.get('q'), '图论');
  assert.equal(query.get('category'), 'help');
  assert.ok(
    find(mounted.root, (node) => String(node.props.class).includes('forum-feed-posts-grid')).length,
  );
  const post = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '分页话题')[0];
  assert.equal(
    new URL(post.props.href, 'http://localhost').searchParams.get('from'),
    encodeURI(mounted.router.currentRoute.value.fullPath),
  );
});
test('pagination and browser back restore the actual page from the URL', async () => {
  await open('/index.html?page=2&view=list');
  await click('下一页');
  assert.equal(mounted.router.currentRoute.value.query.page, '3');
  mounted.router.back();
  await settle();
  assert.equal(mounted.router.currentRoute.value.query.page, '2');
  assert.match(calls.at(-1), /page=2/);
});

test('hash navigation and back keep loaded posts without another request while offline', async () => {
  await open('/index.html?page=2&view=grid');
  const requested = [...calls];
  assert.match(textOf(mounted.root), /分页话题/);
  fail = true;
  await mounted.router.push('/index.html?page=2&view=grid#forum-feed');
  await settle();
  assert.deepEqual(calls, requested);
  assert.match(textOf(mounted.root), /分页话题/);
  assert.doesNotMatch(textOf(mounted.root), /话题加载失败|临时故障/);
  mounted.router.back();
  await settle();
  assert.equal(mounted.router.currentRoute.value.hash, '');
  assert.deepEqual(calls, requested);
  assert.match(textOf(mounted.root), /分页话题/);
});

test('equivalent listing queries do not reload or discard posts', async () => {
  await open('/index.html?q=图论&page=2&view=list');
  const requested = [...calls];
  fail = true;
  await mounted.router.replace('/index.html?view=list&page=02&q=图论&tracking=test');
  await settle();
  assert.deepEqual(calls, requested);
  assert.match(textOf(mounted.root), /分页话题/);
});

test('sorting resets the page and retains the current search', async () => {
  await open('/index.html?q=图论&page=2&view=list');
  await click('热门');
  assert.equal(mounted.router.currentRoute.value.query.page, undefined);
  assert.equal(mounted.router.currentRoute.value.query.sort, 'hot');
  assert.equal(mounted.router.currentRoute.value.query.q, '图论');
});
test('view mode can be shared and a page beyond the end is corrected', async () => {
  await open('/index.html?page=99&view=list');
  assert.equal(mounted.router.currentRoute.value.query.page, '3');
  await click('网格');
  assert.equal(mounted.router.currentRoute.value.query.view, 'grid');
});
test('an empty failed listing provides a working retry action', async () => {
  fail = true;
  await open('/index.html');
  assert.match(textOf(mounted.root), /话题加载失败/);
  fail = false;
  await click('重试');
  assert.match(textOf(mounted.root), /分页话题/);
});
