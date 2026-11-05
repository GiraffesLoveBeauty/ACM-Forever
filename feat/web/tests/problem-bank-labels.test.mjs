import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { h } from 'vue';
import { JSDOM } from 'jsdom';
import { auth, setAuth } from '../src/lib/api.js';
import { memberFilters, memberQuery, problemReturn } from '../src/lib/member-problems.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

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
    if (url.startsWith('/api/me/problems/tags?'))
      return new Response(JSON.stringify({ tags: [] }));
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
async function page(path = '/my-problems.html') {
  mounted = await mount(
    View,
    [
      { path: '/my-problems.html', component: View },
      { path: '/problem.html', component: { template: '<div />' } },
    ],
    path,
  );
}

test('list defaults to all platforms but tracker preserves its old platform rule', () => {
  assert.equal(memberFilters({}).platform, 'all');
  assert.equal(memberFilters({ view: 'tracker' }).platform, 'codeforces');
});
test('algorithm filters survive query normalization and detail return', () => {
  const query = memberQuery({
    platform: 'atcoder',
    labels: 'enumeration,difference_array,enumeration',
    match: 'any',
    page: 3,
  });
  assert.equal(query.labels, 'difference_array,enumeration');
  const path = '/my-problems.html?' + new URLSearchParams(query);
  const returned = new URL(problemReturn(path), 'https://local.invalid');
  assert.equal(returned.searchParams.get('labels'), 'difference_array,enumeration');
  assert.equal(returned.searchParams.get('match'), 'any');
  assert.equal(returned.searchParams.get('page'), '3');
});
test('tracker does not inherit algorithm-only filters', () => {
  const query = memberQuery({ view: 'tracker', labels: 'enumeration', match: 'any' });
  assert.equal(query.labels, undefined);
  assert.equal(query.match, undefined);
});
test('clicking taxonomy label changes URL and sends server-side filter', async () => {
  await page('/my-problems.html?platform=atcoder&page=3');
  const tag = find(mounted.root, (n) => n.props['data-tag-id'] === 'difference_array')[0];
  await tag.props.onClick();
  await settle();
  assert.equal(mounted.router.currentRoute.value.query.labels, 'difference_array');
  assert.equal(mounted.router.currentRoute.value.query.page, undefined);
  assert.ok(
    calls.some(
      (c) =>
        new URL(c.url, 'https://local.invalid').searchParams.get('labels') === 'difference_array',
    ),
  );
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
test('clicking a result tag uses the same algorithm filter', async () => {
  await page();
  const tag = find(
    mounted.root,
    (n) => n.type === 'button' && String(n.props.class).includes('bank-result-tag'),
  )[0];
  await tag.props.onClick();
  await settle();
  assert.equal(mounted.router.currentRoute.value.query.labels, 'difference_array');
});
