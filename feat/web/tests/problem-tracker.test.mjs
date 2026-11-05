import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { problemReturn } from '../src/lib/member-problems.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Problems = (await import(await loadSfc('src/views/MemberProblems.vue'))).default;
const Problem = (await import(await loadSfc('src/views/Problem.vue'))).default;
const View = { render: () => h(RouterView) };
const routes = [
  { path: '/my-problems.html', component: Problems },
  { path: '/problem-bank.html', component: Problems },
  { path: '/problem.html', component: Problem },
  { path: '/home.html', component: { render: () => null } },
];
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
let dom, mounted, calls, trackerFailed, holdTracker, releases, trackerData;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
const makeProblem = (id, index, status, extra = {}) => ({
  platform: 'codeforces',
  problem_id: id,
  problem_index: index,
  problem_name: `Synthetic ${index}`,
  problem_rating: 1400,
  status,
  ...extra,
});
const fixture = () => ({
  items: [
    {
      platform: 'codeforces',
      contest_id: '2000',
      contest_name: 'Synthetic CF Round',
      start_time: 1735700400,
      total_count: 4,
      solved_count: 1,
      attempted_count: 1,
      problems: [
        makeProblem('cf_2000A', 'A', 'solved', { ac_at: 100 }),
        makeProblem('cf_2000B', 'B', 'attempted', { last_submit_at: 200 }),
        makeProblem('cf_2000D1', 'D1', 'unseen', { problem_rating: null }),
        makeProblem('cf_2000D2', 'D2', 'unseen', { problem_rating: 2000 }),
      ],
    },
    {
      platform: 'atcoder',
      contest_id: 'abc001',
      contest_name: 'Synthetic AtCoder Contest',
      total_count: 2,
      solved_count: 1,
      attempted_count: 0,
      problems: [
        makeProblem('abc001_a', 'A', 'solved', { platform: 'atcoder', ac_at: 300 }),
        makeProblem('abc001_b', 'B', 'unseen', { platform: 'atcoder' }),
      ],
    },
  ],
  total: 45,
  page: 1,
  page_size: 20,
});

beforeEach(() => {
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://127.0.0.1/my-problems.html',
  });
  for (const key of keys.filter((key) => key !== 'fetch'))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      writable: true,
      configurable: true,
    });
  mounted = null;
  calls = [];
  trackerFailed = holdTracker = false;
  releases = [];
  trackerData = fixture();
  setAuth(
    { authenticated: true, role: 'member', qq_id: '12345678', csrf_token: 'test-only' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.startsWith('/api/me/problems/tags?')) return response({ tags: ['math', 'greedy'] });
    if (url.startsWith('/api/me/problems/tracker?')) {
      const query = new URL(url, 'https://acm.test').searchParams;
      const delayed = query.get('tag') === 'delayed';
      if (holdTracker || delayed) {
        const data = structuredClone(trackerData);
        await new Promise((resolve) => releases.push(resolve));
        if (delayed) return response(data);
      }
      if (trackerFailed) return response({ message: 'Synthetic tracker outage' }, 503);
      const data = structuredClone(trackerData);
      data.page = Number(query.get('page') || 1);
      return response(data);
    }
    if (url.startsWith('/api/me/problems?'))
      return response({ items: [makeProblem('cf_2000A', 'A', 'solved')], total: 1 });
    if (url.startsWith('/api/me/problems/') || url.startsWith('/api/problems/'))
      return response({
        platform: 'codeforces',
        problem_id: 'cf_2000A',
        problem_name: 'Synthetic A',
        content_available: false,
        tags: [],
        samples: [],
      });
    throw Error('Unexpected request: ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  releases.forEach((resolve) => resolve());
  await settle();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [key, descriptor] of originals)
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
});
after(cleanupCompiled);
const button = (label) =>
  find(mounted.root, (node) => node.type === 'button' && textOf(node).trim() === label)[0];
const problemLinks = () =>
  find(mounted.root, (node) => node.type === 'a' && node.props.href?.startsWith('/problem.html?'));
const click = async (node) => {
  assert(node, 'requested control exists');
  await node.props.onClick({ button: 0, preventDefault() {} });
  await settle();
};
const trackerCalls = () => calls.filter(({ url }) => url.startsWith('/api/me/problems/tracker?'));
const queryOf = (value) => Object.fromEntries(new URL(value, 'https://acm.test').searchParams);
const open = async (path = '/my-problems.html?view=tracker') => {
  mounted = await mount(View, routes, path);
};

test('tracker renders whole contests with explicit solved, attempted and unrecorded states', async () => {
  await open('/my-problems.html?view=tracker&scope=solved&state=favorite');
  const text = textOf(mounted.root);
  assert.equal(find(mounted.root, (node) => node.type === 'table').length, 1);
  assert(text.includes('Synthetic CF Round'));
  assert(text.includes('Synthetic AtCoder Contest'));
  assert(text.includes('开始 2025/1/1'));
  assert(text.includes('比赛时间未收录'));
  assert.equal(
    problemLinks().length,
    6,
    'contest selection does not remove unsolved problems from a selected row',
  );
  for (const [id, label] of [
    ['cf_2000A', '已 AC'],
    ['cf_2000B', '尝试未通过'],
    ['cf_2000D1', '未记录'],
  ]) {
    const cell = problemLinks().find((node) => queryOf(node.props.href).problem_id === id);
    assert(cell, id);
    assert(
      `${cell.props.title || ''} ${cell.props['aria-label'] || ''} ${textOf(cell)}`.includes(label),
      'status has a text equivalent',
    );
  }
  assert(problemLinks().some((node) => queryOf(node.props.href).problem_id === 'cf_2000D2'));
});

for (const role of ['member', 'admin', 'root']) {
  test(`${role} tracker uses the session-owned endpoint without identity parameters`, async () => {
    setAuth({ authenticated: true, role, qq_id: '12345678', csrf_token: 'test-only' }, true);
    await open('/my-problems.html?view=tracker&qq_id=99999999&owner_qq_id=99999999');
    assert.equal(trackerCalls().length, 1);
    const query = queryOf(trackerCalls()[0].url);
    assert.equal(query.platform, 'codeforces');
    assert(!textOf(mounted.root).includes('全部平台'));
    assert(!('qq_id' in query));
    assert(!('owner_qq_id' in query));
    assert(
      !calls.some(({ url }) => url.startsWith('/api/admin/') || url.startsWith('/api/problems?')),
    );
    assert(!textOf(mounted.root).includes('成员 QQ'));
  });
}

test('contest pagination and switching views retain filters and reset the page on view changes', async () => {
  await open(
    '/my-problems.html?view=tracker&scope=solved&platform=codeforces&tag=Round&problem_tag=math&state=favorite&page=2',
  );
  await click(button('下一页'));
  assert.deepEqual(queryOf(mounted.router.currentRoute.value.fullPath), {
    view: 'tracker',
    scope: 'solved',
    platform: 'codeforces',
    tag: 'Round',
    problem_tag: 'math',
    state: 'favorite',
    page: '3',
  });
  assert.equal(queryOf(trackerCalls().at(-1).url).page, '3');
  await click(button('题目列表'));
  const list = queryOf(mounted.router.currentRoute.value.fullPath);
  assert.equal(list.scope, 'solved');
  assert.equal(list.platform, 'codeforces');
  assert.equal(list.tag, 'Round');
  assert.equal(list.problem_tag, 'math');
  assert.equal(list.state, 'favorite');
  assert(!('page' in list));
  assert(!('view' in list));
  assert(calls.some(({ url }) => url.startsWith('/api/me/problems?')));
  await click(button('比赛进度'));
  assert.equal(queryOf(mounted.router.currentRoute.value.fullPath).view, 'tracker');
  assert(!('page' in queryOf(mounted.router.currentRoute.value.fullPath)));
  await click(button('清除筛选'));
  assert.deepEqual(queryOf(mounted.router.currentRoute.value.fullPath), {
    view: 'tracker',
    scope: 'solved',
    platform: 'codeforces',
  });
});

test('entering tracker defaults an unsupported platform to CF and preserves explicit AtCoder selection', async () => {
  await open('/my-problems.html?platform=luogu&problem_tag=trees&page=3');
  await click(button('比赛进度'));
  assert.equal(queryOf(mounted.router.currentRoute.value.fullPath).view, 'tracker');
  assert.equal(queryOf(mounted.router.currentRoute.value.fullPath).platform, 'codeforces');
  assert.equal(queryOf(trackerCalls().at(-1).url).platform, 'codeforces');
  assert(!('problem_tag' in queryOf(mounted.router.currentRoute.value.fullPath)));
  await mounted.router.push('/my-problems.html?view=tracker&platform=atcoder&problem_tag=math');
  await settle();
  assert.equal(queryOf(trackerCalls().at(-1).url).platform, 'atcoder');
  assert.equal(queryOf(trackerCalls().at(-1).url).problem_tag, 'math');
  await click(button('清除筛选'));
  assert.equal(queryOf(trackerCalls().at(-1).url).platform, 'codeforces');
});

test('local statement round trip preserves tracker filters and contest page without identity leakage', async () => {
  const path =
    '/my-problems.html?view=tracker&scope=solved&platform=codeforces&tag=Round&problem_tag=math&state=favorite&page=2';
  await open(path);
  const link = problemLinks().find((node) => queryOf(node.props.href).problem_id === 'cf_2000A');
  assert.equal(queryOf(link.props.href).from, path);
  await click(link);
  assert.equal(mounted.router.currentRoute.value.path, '/problem.html');
  const back = find(
    mounted.root,
    (node) => node.type === 'a' && textOf(node).includes('返回题库'),
  )[0];
  assert.deepEqual(queryOf(back.props.href), queryOf(path));
  await click(back);
  assert.equal(mounted.router.currentRoute.value.path, '/my-problems.html');
  assert.deepEqual(queryOf(mounted.router.currentRoute.value.fullPath), queryOf(path));
  assert(trackerCalls().length >= 2);
  assert.equal(queryOf(problemReturn(path + '&qq_id=99999999', true)).view, 'tracker');
  assert(!('qq_id' in queryOf(problemReturn(path + '&qq_id=99999999', true))));
});

test('tracker loading and request failure do not claim zero progress and retry restores the table', async () => {
  holdTracker = true;
  await open();
  assert(textOf(mounted.root).includes('正在加载'));
  assert.equal(find(mounted.root, (node) => node.type === 'table').length, 0);
  holdTracker = false;
  trackerFailed = true;
  releases.splice(0).forEach((resolve) => resolve());
  await settle();
  assert(textOf(mounted.root).includes('加载失败'));
  assert(!textOf(mounted.root).includes('没有匹配'));
  trackerFailed = false;
  await click(button('重试'));
  assert.equal(find(mounted.root, (node) => node.type === 'table').length, 1);
});

test('late tracker responses cannot replace the current filters and unmount aborts the pending request', async () => {
  await open('/my-problems.html?view=tracker&tag=delayed');
  const old = trackerCalls()[0];
  trackerData.items[0].contest_name = 'Current contest';
  await mounted.router.push('/my-problems.html?view=tracker&tag=current');
  await settle();
  assert(old.options.signal.aborted);
  assert(textOf(mounted.root).includes('Current contest'));
  releases.splice(0).forEach((resolve) => resolve());
  await settle();
  assert(textOf(mounted.root).includes('Current contest'));
  assert(!textOf(mounted.root).includes('Synthetic CF Round'));
  await mounted.router.push('/my-problems.html?view=tracker&tag=delayed');
  await settle();
  const pending = trackerCalls().at(-1);
  mounted.unmount();
  mounted = null;
  assert(pending.options.signal.aborted);
});

test('an empty tracker offers an honest empty state without fabricated problem cells', async () => {
  trackerData = { items: [], total: 0, page: 1, page_size: 20 };
  await open();
  assert.equal(problemLinks().length, 0);
  assert.match(textOf(mounted.root), /暂无|没有匹配/);
  assert(!textOf(mounted.root).includes('加载失败'));
});
