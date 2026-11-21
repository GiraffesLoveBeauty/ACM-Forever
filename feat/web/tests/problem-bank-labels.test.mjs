import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { h } from 'vue';
import { JSDOM } from 'jsdom';
import { setAuth } from '../src/lib/api.js';
import { memberFilters, memberQuery, problemReturn } from '../src/lib/member-problems.js';
import { cleanupCompiled, find, loadSfc, mount, textOf } from './helpers/vue-harness.mjs';

const Bank = (await import(await loadSfc('src/views/MemberProblems.vue'))).default;
const facets = [
  { id: 'difference_array', name_zh: '差分', tag_kind: 'specific', count: 1 },
  { id: 'enumeration', name_zh: '枚举', tag_kind: 'specific', count: 1 },
];
const items = [
  {
    platform: 'atcoder',
    problem_id: 'demo_a',
    problem_name: '示例题',
    has_secondary: true,
    raw_tags: [],
    effective_tags: [{ id: 'difference_array', name_zh: '差分', source: 'ai' }],
    review_status: 'auto',
    tags: ['差分'],
  },
];
let dom, mounted, calls;
const keys = ['window', 'document', 'Document', 'Node', 'ShadowRoot', 'fetch', 'location'];
const originals = new Map(keys.map((k) => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
beforeEach(() => {
  dom = new JSDOM('<!doctype html><body></body>', { url: 'http://127.0.0.1/my-problems.html' });
  for (const k of ['window', 'document', 'Document', 'Node', 'ShadowRoot'])
    Object.defineProperty(globalThis, k, {
      value: dom.window[k],
      configurable: true,
      writable: true,
    });
  globalThis.location = { pathname: '/my-problems.html', search: '', assign() {} };
  setAuth({ authenticated: true, qq_id: '10000001', role: 'member', csrf_token: 'fixture' }, true);
  calls = [];
  mounted = null;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (/^\/api\/(?:me\/)?problems\/taxonomy\?/.test(url))
      return new Response(JSON.stringify({ difficulties: [], tags: [], tag_types: [] }));
    if (url.startsWith('/api/me/problems/tags?')) return new Response(JSON.stringify({ tags: [] }));
    if (url.startsWith('/api/me/problems?'))
      return new Response(JSON.stringify({ items, total: 1, tag_facets: facets }));
    throw Error('Unexpected request ' + url);
  };
});
afterEach(() => {
  mounted?.unmount();
  dom.window.close();
  setAuth({ authenticated: false }, true);
  for (const [k, v] of originals) {
    if (v) Object.defineProperty(globalThis, k, v);
    else delete globalThis[k];
  }
});
after(cleanupCompiled);
const View = { render: () => h(Bank) };
async function page(path = '/my-problems.html?platform=all') {
  mounted = await mount(
    View,
    [
      { path: '/my-problems.html', component: View },
      { path: '/problem.html', component: { template: '<div />' } },
    ],
    path,
  );
}

test('list defaults to Luogu while explicit all and tracker platforms remain available', () => {
  assert.equal(memberFilters({}).platform, 'luogu');
  assert.equal(memberFilters({ platform: 'all' }).platform, 'all');
  assert.equal(memberFilters({ view: 'tracker' }).platform, 'codeforces');
  assert.equal(memberFilters({ scope: 'solved' }).platform, 'all');
  assert.equal(memberFilters({ problem_tag: 'Math' }).platform, 'all');
  assert.equal(memberFilters({ labels: 'dp' }).platform, 'luogu');
  assert.equal(memberFilters({ platform: 'unknown' }).platform, 'all');
});
test('unqualified entry renders Luogu filters and queries that same platform exactly once', async () => {
  await page('/my-problems.html');
  const select = find(
    mounted.root,
    (node) => node.type === 'label' && textOf(node).startsWith('平台'),
  ).flatMap((label) => find(label, (node) => node.type === 'select'))[0];
  assert.equal(select.options[select.selectedIndex]?.props.value, 'luogu');
  assert.equal(textOf(find(mounted.root, (node) => node.type === 'h1')[0]), '题库');
  assert.ok(textOf(mounted.root).includes('按题目标签寻找练习题'));
  assert.doesNotMatch(textOf(mounted.root), /洛谷题库|浏览洛谷公开 P 题|从熟悉的分类开始练习/);
  assert.equal(textOf(mounted.root).includes('人工修正后的有效标签'), false);
  assert.ok(textOf(mounted.root).includes('洛谷难度下限'));
  assert.equal(find(mounted.root, (node) => node.props.class === 'bank-label-filter').length, 0);
  const requests = calls.filter((call) => call.url.startsWith('/api/me/problems?'));
  assert.equal(requests.length, 1);
  assert.equal(
    new URL(requests[0].url, 'https://local.invalid').searchParams.get('platform'),
    'luogu',
  );
  assert.equal(calls.filter((call) => call.url.startsWith('/api/me/problems/tags?')).length, 0);
  assert.equal(
    calls.filter((call) => /^\/api\/(?:me\/)?problems\/taxonomy\?/.test(call.url)).length,
    1,
  );
});
test('default platform normalization preserves native filters and the detail return route', () => {
  const filters = memberFilters({ native_difficulty: '0', native_tags: '1,-2', page: 2 });
  assert.equal(filters.platform, 'luogu');
  assert.equal(filters.native_difficulty, '0');
  assert.equal(filters.native_tags, '1,-2');
  const returned = new URL(
    problemReturn('/my-problems.html?native_tags=1,-2'),
    'https://local.invalid',
  );
  assert.equal(returned.searchParams.get('platform'), 'luogu');
  assert.equal(returned.searchParams.get('native_tags'), '1,-2');
});
test('retired algorithm filters are omitted from member queries and detail return', () => {
  const query = memberQuery({
    platform: 'atcoder',
    labels: 'enumeration,difference_array,enumeration',
    match: 'any',
    page: 3,
  });
  assert.equal(query.labels, undefined);
  assert.equal(query.match, undefined);
  const path = '/my-problems.html?platform=atcoder&labels=difference_array&match=any&page=3';
  const returned = new URL(problemReturn(path), 'https://local.invalid');
  assert.equal(returned.searchParams.get('labels'), null);
  assert.equal(returned.searchParams.get('match'), null);
  assert.equal(returned.searchParams.get('platform'), 'atcoder');
  assert.equal(returned.searchParams.get('page'), '3');
});
test('tracker does not inherit algorithm-only filters', () => {
  const query = memberQuery({ view: 'tracker', labels: 'enumeration', match: 'any' });
  assert.equal(query.labels, undefined);
  assert.equal(query.match, undefined);
});

test('member algorithm labels retain category colours and source hints as static badges', async () => {
  await page('/my-problems.html?platform=atcoder&labels=difference_array&match=any&page=3');
  const result = find(
    mounted.root,
    (n) => n.type === 'span' && String(n.props.class).split(' ').includes('bank-result-tag'),
  )[0];
  assert.match(String(result.props.class), /problem-tone-orange/);
  assert.match(result.props.title, /difference_array.*AI 自动/);
  assert.doesNotMatch(result.props.title, /点击筛选/);
  assert.equal(result.props['data-tag-category'], 'strategy');
  assert.equal(result.props.onClick, undefined);
  assert.equal(find(mounted.root, (node) => node.props.class === 'bank-label-filter').length, 0);
  const request = calls.find((call) => call.url.startsWith('/api/me/problems?'));
  const queried = new URL(request.url, 'https://local.invalid').searchParams;
  assert.equal(queried.get('platform'), 'atcoder');
  assert.equal(queried.get('page'), '3');
  assert.equal(queried.get('labels'), null);
  assert.equal(queried.get('match'), null);
});
test('members see effective labels but no modification action', async () => {
  await page();
  assert.ok(textOf(mounted.root).includes('差分'));
  assert.equal(
    find(mounted.root, (n) => n.type === 'button' && textOf(n).trim() === '修改标签').length,
    0,
  );
});
test('administrators use the backstage management entry rather than a public editor', async () => {
  setAuth({ authenticated: true, qq_id: '10000002', role: 'admin', csrf_token: 'fixture' }, true);
  await page();
  assert.equal(
    find(mounted.root, (n) => n.type === 'button' && textOf(n).trim() === '修改标签').length,
    0,
  );
  assert.equal(
    find(mounted.root, (n) => n.type === 'a' && textOf(n).trim() === '后台管理').length,
    1,
  );
});
