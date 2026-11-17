import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Problems = (await import(await loadSfc('src/views/MemberProblems.vue'))).default;
const Database = (await import(await loadSfc('src/components/ProblemDatabaseBrowser.vue'))).default;
const keys = [
  'window',
  'document',
  'Document',
  'Node',
  'ShadowRoot',
  'navigator',
  'location',
  'history',
  'fetch',
];
const originals = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let dom, mounted, calls, holdTags;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
const query = (url) => new URL(url, 'https://acm.test').searchParams;
const lists = () => calls.filter((call) => !/\/(?:tags|taxonomy)\?/.test(call.url));
const button = (name) =>
  find(mounted.root, (node) => node.type === 'button' && textOf(node).trim() === name)[0];
const control = (name, kind = 'select') =>
  find(
    mounted.root,
    (node) => node.type === 'label' && textOf(node).trim().startsWith(name),
  ).flatMap((label) => find(label, (node) => node.type === kind))[0];
const submit = async () => {
  find(mounted.root, (node) => node.type === 'form')[0].props.onSubmit({ preventDefault() {} });
  await settle();
};
async function platform(value) {
  const select = control('平台');
  select.props['onUpdate:modelValue'](value);
  select.props.onChange?.({ target: { value } });
  await settle();
}
const item = (name, platform = 'codeforces') => ({
  platform,
  problem_id: platform === 'atcoder' ? 'abc100_a' : 'cf_100A',
  problem_name: name,
  tags: [],
  sample_count: 0,
});
const data = (view, name) => ({
  items:
    view === 'tracker'
      ? [
          {
            platform: 'atcoder',
            contest_id: 'abc100',
            contest_name: name,
            total_count: 1,
            solved_count: 0,
            attempted_count: 0,
            problems: [{ ...item(name, 'atcoder'), problem_index: 'A', status: 'unseen' }],
          },
        ]
      : [item(name)],
  total: 1,
  page: 1,
  page_size: 20,
});
async function open(view = 'list', suffix = '') {
  mounted = await mount(
    Problems,
    [
      { path: '/my-problems.html', component: Problems },
      { path: '/home.html', component: { render: () => null } },
      { path: '/problem.html', component: { render: () => null } },
    ],
    `/my-problems.html?platform=codeforces${view === 'tracker' ? '&view=tracker' : ''}${suffix}`,
  );
}
async function admin() {
  setAuth({ authenticated: true, role: 'root', qq_id: '12345678', csrf_token: 'synthetic' }, true);
  mounted = await mount(
    Database,
    [
      { path: '/admin.html', component: Database },
      { path: '/problem.html', component: { render: () => null } },
    ],
    '/admin.html',
  );
}
beforeEach(() => {
  mounted = null;
  calls = [];
  holdTags = false;
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://acm.test/my-problems.html',
  });
  for (const key of keys.filter((key) => key !== 'fetch'))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      writable: true,
      configurable: true,
    });
  setAuth(
    { authenticated: true, role: 'member', qq_id: '12345678', csrf_token: 'synthetic' },
    true,
  );
  globalThis.fetch = (url, options = {}) => {
    const call = { url, options };
    calls.push(call);
    if (url.includes('/problems/taxonomy?'))
      return Promise.resolve(response({ difficulties: [], tags: [], tag_types: [], stale: false }));
    if (url.startsWith('/api/me/problems/tags?') && !holdTags)
      return Promise.resolve(response({ tags: [query(url).get('platform') + '-tag'] }));
    assert(
      url.startsWith('/api/me/problems') || url.startsWith('/api/admin/database/problems?'),
      'unexpected request: ' + url,
    );
    return new Promise((resolve, reject) => {
      call.resolve = (value, status = 200) => resolve(response(value, status));
      call.reject = reject;
    });
  };
});
afterEach(async () => {
  mounted?.unmount();
  calls.forEach((call) => call.resolve?.({ items: [], total: 0, tags: [] }));
  await settle();
  dom.window.close();
});
after(async () => {
  await cleanupCompiled();
  for (const [key, descriptor] of originals)
    descriptor ? Object.defineProperty(globalThis, key, descriptor) : delete globalThis[key];
});
for (const view of ['list', 'tracker']) {
  test(`${view}: OJ switching replaces a slow first query without locking controls`, async () => {
    await open(view, '&page=3&problem_tag=math');
    assert(!button('查询').props.disabled);
    assert(!button('清除筛选').props.disabled);
    const old = lists()[0];
    await platform('atcoder');
    assert.equal(lists().length, 2);
    assert(old.options.signal.aborted);
    const latest = lists()[1];
    assert.equal(query(latest.url).get('platform'), 'atcoder');
    assert.equal(query(latest.url).get('page'), '1');
    assert(!query(latest.url).get('problem_tag'));
    old.resolve(data(view, 'stale result'));
    await settle();
    assert(textOf(mounted.root).includes(view === 'tracker' ? '正在加载比赛进度' : '正在加载题目'));
    assert(!textOf(mounted.root).includes('stale result'));
    latest.resolve(data(view, 'current result'));
    await settle();
    assert(textOf(mounted.root).includes('current result'));
  });
  test(`${view}: search and clear replace slow queries; duplicate submissions are coalesced`, async () => {
    await open(view, '&page=3');
    control('搜索', 'input').props['onUpdate:modelValue']('new keyword');
    await submit();
    assert.equal(lists().length, 2);
    assert(lists()[0].options.signal.aborted);
    assert.equal(query(lists()[1].url).get('tag'), 'new keyword');
    await submit();
    assert.equal(lists().length, 2);
    button('清除筛选').props.onClick();
    await settle();
    assert.equal(lists().length, 3);
    assert(lists()[1].options.signal.aborted);
    assert(!query(lists()[2].url).get('tag'));
    lists()[0].reject(new Error('stale failure'));
    lists()[1].reject(new Error('another stale failure'));
    await settle();
    assert(!textOf(mounted.root).includes('stale failure'));
    assert(textOf(mounted.root).includes('正在加载'));
    lists()[2].resolve({ items: [], total: 0 });
    await settle();
    assert(!textOf(mounted.root).includes('正在加载'));
    assert(textOf(mounted.root).includes('没有匹配'));
  });
}
test('slow or failed tag choices do not block queries, and late old tags stay discarded', async () => {
  holdTags = true;
  await open();
  const oldTags = calls.find((call) => call.url.startsWith('/api/me/problems/tags?'));
  assert(control('标签').props.disabled);
  assert(!button('查询').props.disabled);
  await platform('atcoder');
  assert(oldTags.options.signal.aborted);
  const latestTags = calls.filter((call) => call.url.startsWith('/api/me/problems/tags?')).at(-1);
  lists()[1].resolve(data('list', 'independent problem result'));
  await settle();
  assert(textOf(mounted.root).includes('independent problem result'));
  latestTags.resolve({ message: 'tag failure' }, 503);
  oldTags.resolve({ tags: ['old tag'] });
  await settle();
  assert(textOf(mounted.root).includes('tag failure'));
  assert(!textOf(mounted.root).includes('old tag'));
  assert(!button('查询').props.disabled);
});
test('numeric ranges clear before switching OJs and restore with browser history', async () => {
  await open('list', '&rating_min=1200&rating_max=1600');
  assert.equal(query(lists()[0].url).get('rating_min'), '1200');
  await platform('atcoder');
  assert.equal(query(lists().at(-1).url).get('platform'), 'atcoder');
  assert.equal(query(lists().at(-1).url).get('rating_min'), null);
  assert.equal(query(lists().at(-1).url).get('rating_max'), null);
  mounted.router.back();
  await settle();
  assert.equal(query(lists().at(-1).url).get('platform'), 'codeforces');
  assert.equal(query(lists().at(-1).url).get('rating_min'), '1200');
  assert.equal(query(lists().at(-1).url).get('rating_max'), '1600');
});
test('rapid OJ changes and history navigation keep the newest URL and results', async () => {
  await open();
  await platform('atcoder');
  await platform('luogu');
  assert.equal(lists().length, 3);
  assert(lists()[0].options.signal.aborted && lists()[1].options.signal.aborted);
  lists()[2].resolve({ items: [item('Luogu result', 'luogu')], total: 1 });
  await settle();
  lists()[0].resolve(data('list', 'old CF result'));
  lists()[1].resolve(data('list', 'old AC result'));
  await settle();
  assert(textOf(mounted.root).includes('Luogu result'));
  assert(!textOf(mounted.root).includes('old CF result'));
  mounted.router.back();
  await settle();
  assert.equal(query(lists().at(-1).url).get('platform'), 'atcoder');
  assert.equal(query(mounted.router.currentRoute.value.fullPath).get('platform'), 'atcoder');
  mounted.unmount();
  mounted = null;
  assert(lists().at(-1).options.signal.aborted);
});
test('admin OJ switching and reset remain available during loading, with guarded old callbacks', async () => {
  await admin();
  assert(!button('筛选').props.disabled);
  assert(!button('重置').props.disabled);
  await platform('atcoder');
  assert.equal(lists().length, 2);
  assert(lists()[0].options.signal.aborted);
  lists()[0].resolve({ items: [item('old admin result')], total: 1, page: 1 });
  await settle();
  assert(textOf(mounted.root).includes('正在读取题库记录'));
  assert(!textOf(mounted.root).includes('old admin result'));
  await submit();
  assert.equal(lists().length, 2);
  button('重置').props.onClick();
  await settle();
  assert.equal(lists().length, 3);
  assert(lists()[1].options.signal.aborted);
  lists()[1].reject(new Error('old admin failure'));
  await settle();
  assert(textOf(mounted.root).includes('正在读取题库记录'));
  assert(!textOf(mounted.root).includes('old admin failure'));
  lists()[2].resolve({ items: [item('current admin result')], total: 1, page: 1 });
  await settle();
  assert(textOf(mounted.root).includes('current admin result'));
});
test('admin pending search is coalesced and unmount cancels its request', async () => {
  await admin();
  control('搜索题目', 'input').props['onUpdate:modelValue']('abc100');
  await submit();
  assert.equal(lists().length, 2);
  await submit();
  assert.equal(lists().length, 2);
  assert.equal(query(lists()[1].url).get('q'), 'abc100');
  mounted.unmount();
  mounted = null;
  assert(lists()[1].options.signal.aborted);
});

for (const owner of ['member', 'admin']) {
  test(`${owner}: Luogu picker enforces the limit and applies reduced or cleared selections`, async () => {
    const fetch = globalThis.fetch;
    globalThis.fetch = (url, options) =>
      url.includes('/problems/taxonomy?')
        ? Promise.resolve(
            response({
              difficulties: [],
              tags: Array.from({ length: 21 }, (_, i) => ({
                id: i + 1,
                name: '标签 ' + (i + 1),
                type: 1,
              })),
              tag_types: [{ id: 1, name: '算法' }],
            }),
          )
        : fetch(url, options);
    if (owner === 'member') await open();
    else await admin();
    await platform('luogu');
    const pickerTrigger = () =>
      find(
        mounted.root,
        (node) => node.type === 'button' && node.props['aria-haspopup'] === 'dialog',
      )[0];
    const tag = (id) =>
      find(
        mounted.root,
        (node) =>
          node.type === 'button' &&
          Object.hasOwn(node.props, 'aria-pressed') &&
          node.props['aria-label'] === '标签 ' + id,
      )[0];
    await pickerTrigger().props.onClick();
    await settle();
    for (let id = 1; id <= 20; id++) {
      tag(id).props.onClick();
      await settle();
    }
    assert.equal(tag(21).props.disabled, true);
    assert.match(textOf(mounted.root), /已达 20 个标签上限/);
    // The handler guards the limit even when invoked without a native disabled button.
    tag(21).props.onClick();
    await settle();
    assert.equal(tag(21).props['aria-pressed'], false);
    button('确认筛选').props.onClick();
    await settle();
    assert.equal(
      query(lists().at(-1).url).get('native_tags'),
      Array.from({ length: 20 }, (_, i) => String(i + 1)).join(','),
    );
    const applied = lists().length;
    await pickerTrigger().props.onClick();
    await settle();
    assert.equal(tag(21).props.disabled, true);
    tag(20).props.onClick();
    await settle();
    assert.equal(tag(21).props.disabled, false);
    assert.doesNotMatch(textOf(mounted.root), /已达 20 个标签上限/);
    assert.equal(lists().length, applied);
    button('确认筛选').props.onClick();
    await settle();
    assert.equal(
      query(lists().at(-1).url).get('native_tags'),
      Array.from({ length: 19 }, (_, i) => String(i + 1)).join(','),
    );
    button('清空').props.onClick();
    await settle();
    assert.equal(query(lists().at(-1).url).get('native_tags'), null);
    assert.doesNotMatch(textOf(mounted.root), /已达 20 个标签上限/);
  });
}

test('continuous pages use the returned cursor and changing filters discards it', async () => {
  await open();
  lists()[0].resolve({
    ...data('list', 'first page'),
    total: 60,
    page: 1,
    next_cursor: 'page-two-cursor',
  });
  await settle();
  await mounted.router.push({
    path: '/my-problems.html',
    query: { platform: 'codeforces', page: 2 },
  });
  await settle();
  assert.equal(query(lists().at(-1).url).get('cursor'), 'page-two-cursor');
  lists()
    .at(-1)
    .resolve({
      ...data('list', 'second page'),
      total: 60,
      page: 2,
      next_cursor: 'page-three-cursor',
    });
  await settle();
  await platform('atcoder');
  assert.equal(query(lists().at(-1).url).get('cursor'), null);
});
test('tag options are reused while versions match and refreshed after a data change', async () => {
  holdTags = true;
  await open();
  const tagCalls = () => calls.filter((call) => call.url.startsWith('/api/me/problems/tags?'));
  tagCalls()[0].resolve({ tags: ['math'], tags_version: '1:0' });
  lists()[0].resolve({ ...data('list', 'first page'), total: 60, page: 1, tags_version: '1:0' });
  await settle();
  await mounted.router.push({
    path: '/my-problems.html',
    query: { platform: 'codeforces', page: 2 },
  });
  await settle();
  lists()
    .at(-1)
    .resolve({ ...data('list', 'same data'), total: 60, page: 2, tags_version: '1:0' });
  await settle();
  assert.equal(tagCalls().length, 1);
  await mounted.router.push({
    path: '/my-problems.html',
    query: { platform: 'codeforces', page: 3 },
  });
  await settle();
  lists()
    .at(-1)
    .resolve({ ...data('list', 'updated data'), total: 60, page: 3, tags_version: '2:0' });
  await settle();
  assert.equal(tagCalls().length, 2);
  tagCalls()[1].resolve({ tags: ['new tag'], tags_version: '2:0' });
  await settle();
  assert(textOf(mounted.root).includes('new tag'));
});

test('a late outdated tag response refreshes against the latest list version', async () => {
  holdTags = true;
  await open();
  const tagCalls = () => calls.filter((call) => call.url.startsWith('/api/me/problems/tags?'));
  lists()[0].resolve({ ...data('list', 'new directory'), tags_version: '2:0' });
  await settle();
  tagCalls()[0].resolve({ tags: ['old'], tags_version: '1:0' });
  await settle();
  assert.equal(tagCalls().length, 2);
  tagCalls()[1].resolve({ tags: ['latest'], tags_version: '2:0' });
  await settle();
  assert(textOf(mounted.root).includes('latest'));
  assert.equal(tagCalls().length, 2);
});
