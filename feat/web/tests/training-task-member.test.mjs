import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Member = (await import(await loadSfc('src/views/TrainingTasks.vue'))).default;
const Overview = (await import(await loadSfc('src/components/AssignedTaskOverview.vue'))).default;
const Root = { render: () => h(RouterView) };
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
const original = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let dom, mounted, calls, fail, queued;
const task = () => ({
  id: 17,
  title: '固定名单训练',
  description: '完成全部必做题',
  state: 'published',
  phase: 'active',
  starts_at: 1700000000,
  due_at: 1900000000,
  original_due_at: 1900000000,
  creator_name: '训练管理员',
  rule: 'period_ac',
  recipient: {
    id: 21,
    status_snapshot: '发布时身份',
    problem_count: 2,
    completed_problems: 1,
    on_time_problems: 1,
    late_problems: 0,
    pending: true,
    completion: 'incomplete',
    checked_at: 1800000000,
    last_success_at: 1800000000,
  },
  problems: [
    {
      platform: 'codeforces',
      problem_id: 'cf_1A',
      problem_name: '已核验合成题',
      status: 'on_time',
      verification: 'verified',
      evidence: { accepted_at: 1800000000, external_submission_id: '801' },
      tags: ['图论'],
    },
    {
      platform: 'codeforces',
      problem_id: 'cf_2A',
      problem_name: '历史合成题',
      status: 'history_ac',
      verification: 'coverage_missing',
      evidence: { accepted_at: 1600000000 },
      tags: [],
    },
  ],
  refresh: queued ? { id: 'queue-1', status: 'running' } : null,
});
const json = (data, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => {
  dom = new JSDOM('<!doctype html><body></body>', { url: 'http://127.0.0.1/training-tasks.html' });
  for (const key of keys.filter((k) => k !== 'fetch'))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      configurable: true,
      writable: true,
    });
  setAuth(
    { authenticated: true, role: 'member', qq_id: '22345678', csrf_token: 'synthetic' },
    true,
  );
  calls = [];
  fail = false;
  queued = false;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (fail) return json({ message: '合成网络异常，已有进度保留' }, 503);
    if (url.endsWith('/refresh')) {
      queued = true;
      return json({ status: 'queued', task: { id: 'queue-1' } }, 202);
    }
    if (url === '/api/me/training-tasks/17') return json(task());
    if (url.startsWith('/api/me/training-tasks?')) {
      const tab = new URL(url, 'https://acm.test').searchParams.get('tab');
      return json({ items: tab === 'active' ? [task()] : [], total: tab === 'active' ? 1 : 0 });
    }
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  await settle();
  dom.window.close();
  for (const [key, descriptor] of original)
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  setAuth({ authenticated: false }, true);
});
after(cleanupCompiled);
const click = async (label) => {
  const node = find(mounted.root, (n) => n.type === 'button' && textOf(n).includes(label))[0];
  assert(node, label);
  await node.props.onClick({ button: 0, preventDefault() {} });
  await settle();
};
const routes = [
  { path: '/training-tasks.html', component: Member },
  { path: '/home.html', component: Overview },
  { path: '/problem.html', component: { render: () => null } },
];
test('member lists preserve server progress and history filters in the URL', async () => {
  mounted = await mount(Root, routes, '/training-tasks.html');
  assert(textOf(mounted.root).includes('1 / 2 题'));
  const link = find(mounted.root, (n) => n.type === 'a' && textOf(n).includes('查看任务'))[0];
  assert(link.props.href.includes('task_id=17'));
  await click('历史任务');
  assert.equal(mounted.router.currentRoute.value.query.tab, 'history');
  assert(textOf(mounted.root).includes('暂无历史任务'));
  assert(calls.every((c) => !c.url.includes('qq_id=')));
});
test('detail keeps historical AC separate, surfaces queue errors and clears polling on exit', async () => {
  mounted = await mount(Root, routes, '/training-tasks.html?task_id=17');
  assert(textOf(mounted.root).includes('历史已做'));
  assert(textOf(mounted.root).includes('历史覆盖不足'));
  assert(textOf(mounted.root).includes('提交 #801'));
  await click('刷新进度');
  assert(textOf(mounted.root).includes('同步请求已排队'));
  const post = calls.find((c) => c.url.endsWith('/refresh'));
  assert.deepEqual(JSON.parse(post.options.body), {});
  fail = true;
  await click('返回任务列表');
  assert(textOf(mounted.root).includes('合成网络异常'));
  const count = calls.length;
  await new Promise((r) => setTimeout(r, 3100));
  assert.equal(calls.length, count, 'no orphaned polling after leaving detail');
});
test('personal-center summary uses own nearest task and direct continuation target', async () => {
  mounted = await mount(Root, routes, '/home.html');
  assert(textOf(mounted.root).includes('我的训练安排'));
  assert(textOf(mounted.root).includes('固定名单训练'));
  const link = find(mounted.root, (n) => n.type === 'a' && textOf(n).includes('继续训练'))[0];
  assert(link.props.href.includes('task_id=17'));
});
