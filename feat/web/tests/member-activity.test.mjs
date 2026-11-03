import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { adminFilters } from '../src/lib/admin.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Header = (await import(await loadSfc('src/components/Header.vue'))).default;
const View = { render: () => h(RouterView) };
const names = [
  'window',
  'document',
  'Document',
  'Node',
  'ShadowRoot',
  'location',
  'history',
  'localStorage',
  'fetch',
];
const originals = new Map(
  names.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
);
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
let dom,
  mounted,
  calls,
  historyFailed,
  reviewFailed,
  reviewSaveFailed,
  heldContest,
  releases,
  Training,
  Review,
  AdminTraining,
  AdminReview;
const historyRow = {
  id: 1,
  platform: 'codeforces',
  problem_id: 'cf_100A',
  problem_name: 'Own training history',
  problem_rating: 1000,
  problem_url: 'https://codeforces.com/contest/100/problem/A',
  status: 'active',
  created_at: 1700000000,
};

beforeEach(() => {
  dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/challenge.html' });
  for (const name of names.filter((name) => name !== 'fetch'))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      writable: true,
      value: dom.window[name],
    });
  mounted = null;
  calls = [];
  historyFailed = reviewFailed = reviewSaveFailed = false;
  heldContest = null;
  releases = [];
  identity('member');
  globalThis.fetch = async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    const method = options.method || 'GET';
    calls.push({ url, method, body });
    if (url === '/api/me/notifications/count') return response({ unread_count: 0 });
    if (url === '/api/me/training/challenges' || url.startsWith('/api/challenge/list?'))
      return historyFailed
        ? response({ message: 'Synthetic history outage' }, 503)
        : response([historyRow]);
    if (['/api/me/challenge/start', '/api/challenge/start'].includes(url))
      return response({
        success: true,
        ...historyRow,
        recommendation_reason: 'Synthetic recommendation',
      });
    if (url.startsWith('/api/me/contest/reviews') || url.startsWith('/api/contest/reviews')) {
      if (method === 'PUT')
        return reviewSaveFailed
          ? response({ message: 'Synthetic save outage' }, 503)
          : response({ success: true });
      if (reviewFailed) return response({ message: 'Synthetic review outage' }, 503);
      const contest = new URL(url, 'https://acm.test').searchParams.get('contest_id');
      const data = [
        { problem_id: `cf_${contest}A`, verdict: 'WRONG_ANSWER', rating: 1400, status: 'unsolved' },
      ];
      if (contest === heldContest)
        return new Promise((resolve) => releases.push(() => resolve(response(data))));
      return response(data);
    }
    throw Error(`Unexpected activity request: ${method} ${url}`);
  };
});

afterEach(async () => {
  mounted?.unmount();
  releases.forEach((release) => release());
  await settle();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [name, descriptor] of originals)
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
});
after(cleanupCompiled);

function identity(role) {
  setAuth({ authenticated: true, role, qq_id: '12345678', csrf_token: 'synthetic-csrf' }, true);
  // A personal page must not reuse a different member previously selected in administration.
  adminFilters.training = { owner: '99999999', platform: 'luogu', difficulty: '入门', tag: '' };
  adminFilters.contests = { owner_qq_id: '99999999', contest_id: '999' };
}
async function routes() {
  Training ||= (await import(await loadSfc('src/views/MemberTraining.vue'))).default;
  Review ||= (await import(await loadSfc('src/views/MemberContestReview.vue'))).default;
  return [
    { path: '/challenge.html', component: Training },
    { path: '/contest-review.html', component: Review },
    ...[
      'home',
      'my-problems',
      'problem',
      'index',
      'leaderboard',
      'wiki',
      'admin',
      'notifications',
    ].map((name) => ({ path: `/${name}.html`, component: { render: () => null } })),
  ];
}
async function open(path, role = 'member') {
  identity(role);
  mounted = await mount(View, await routes(), path);
}
const controls = (root, type) => find(root, (node) => node.type === type);
function field(label, type) {
  const parent = find(
    mounted.root,
    (node) => node.type === 'label' && textOf(node).trim().startsWith(label),
  )[0];
  assert.ok(parent, `field label ${label}`);
  const control = controls(parent, type)[0];
  assert.ok(control, `${label} ${type}`);
  return control;
}
async function model(control, value) {
  control.props['onUpdate:modelValue'](value);
  await settle();
}
async function submit() {
  const form = controls(mounted.root, 'form')[0];
  assert.ok(form, 'activity form exists');
  await form.props.onSubmit({ preventDefault() {} });
  await settle();
}
async function click(label) {
  const button = controls(mounted.root, 'button').find((node) => textOf(node).trim() === label);
  assert.ok(button, `button ${label}`);
  await button.props.onClick({ button: 0, preventDefault() {} });
  await settle();
}
function noOwner(call) {
  const query = new URL(call.url, 'https://acm.test').searchParams;
  for (const name of ['qq_id', 'owner_qq_id', 'owner']) {
    assert.equal(query.has(name), false, `${name} absent from personal query`);
    assert.equal(Object.hasOwn(call.body || {}, name), false, `${name} absent from personal body`);
  }
}

for (const role of ['member', 'admin', 'root']) {
  test(`${role} uses session-owned training, independent from administration`, async () => {
    await open('/challenge.html?qq_id=99999999&owner_qq_id=99999999', role);
    assert.ok(textOf(mounted.root).includes('今日训练'));
    assert.ok(textOf(mounted.root).includes('Own training history'));
    assert.equal(textOf(mounted.root).includes('成员 QQ'), false);
    await model(field('平台', 'select'), 'codeforces');
    await model(field('难度', 'input'), 1000);
    await submit();
    const generated = calls.filter((call) => call.method === 'POST');
    assert.equal(generated.length, 3, 'training produces all three difficulty zones');
    assert.deepEqual(
      generated.map((call) => call.body.difficulty),
      [850, 1000, 1150],
    );
    assert.ok(generated.every((call) => call.url === '/api/me/challenge/start'));
    assert.ok(calls.every((call) => call.url.startsWith('/api/me/')));
    calls.forEach(noOwner);
    const links = controls(mounted.root, 'a').filter((node) =>
      node.props.href?.startsWith('/problem.html?'),
    );
    assert.ok(links.length >= 3, 'generated tasks open the local problem view');
  });

  test(`${role} reads and saves only their own contest review`, async () => {
    await open('/contest-review.html?contest_id=200&qq_id=99999999&owner_qq_id=99999999', role);
    assert.ok(textOf(mounted.root).includes('cf_200A'));
    assert.equal(textOf(mounted.root).includes('成员 QQ'), false);
    await model(field('比赛 ID', 'input'), '300');
    // Editing a search field must not silently retarget the already rendered rows.
    const status = field('逐题状态', 'select');
    await status.props.onChange({ target: { value: 'reviewed' } });
    await settle();
    const write = calls.find((call) => call.method === 'PUT');
    assert.ok(write);
    assert.equal(write.url, '/api/me/contest/reviews');
    assert.equal(write.body.contest_id, '200');
    assert.equal(write.body.problem_id, 'cf_200A');
    assert.equal(write.body.status, 'reviewed');
    calls.forEach(noOwner);
    await submit();
    assert.ok(textOf(mounted.root).includes('cf_300A'));
    assert.equal(textOf(mounted.root).includes('cf_200A'), false);
  });
}

test('training history failure stays visible and can be retried', async () => {
  historyFailed = true;
  await open('/challenge.html');
  assert.ok(textOf(mounted.root).includes('Synthetic history outage'));
  assert.equal(textOf(mounted.root).includes('暂无挑战记录'), false);
  historyFailed = false;
  await click('重试加载历史');
  assert.ok(textOf(mounted.root).includes('Own training history'));
  assert.equal(textOf(mounted.root).includes('Synthetic history outage'), false);
});

test('contest review failure offers retry without pretending no submissions exist', async () => {
  reviewFailed = true;
  await open('/contest-review.html?contest_id=200');
  assert.ok(textOf(mounted.root).includes('Synthetic review outage'));
  assert.equal(textOf(mounted.root).includes('无题目记录时请先同步'), false);
  reviewFailed = false;
  await click('重试查询');
  assert.ok(textOf(mounted.root).includes('cf_200A'));
  assert.equal(textOf(mounted.root).includes('Synthetic review outage'), false);
});

test('a slow older contest query cannot overwrite the latest selected contest', async () => {
  heldContest = '200';
  await open('/contest-review.html?contest_id=200');
  assert.equal(releases.length, 1, 'the first query remains in flight');
  await model(field('比赛 ID', 'input'), '300');
  await submit();
  assert.ok(textOf(mounted.root).includes('cf_300A'));
  releases.forEach((release) => release());
  await settle();
  assert.ok(textOf(mounted.root).includes('cf_300A'));
  assert.equal(textOf(mounted.root).includes('cf_200A'), false);
  assert.equal(controls(mounted.root, 'select').length, 1);
});

test('a failed review save restores the selected state and a retry can succeed', async () => {
  await open('/contest-review.html?contest_id=200');
  reviewSaveFailed = true;
  const failedEvent = { target: { value: 'reviewed' } };
  await field('逐题状态', 'select').props.onChange(failedEvent);
  await settle();
  assert.equal(failedEvent.target.value, 'unsolved');
  assert.equal(field('逐题状态', 'select').props.value, 'unsolved');
  assert.ok(textOf(mounted.root).includes('Synthetic save outage'));
  reviewSaveFailed = false;
  const retryEvent = { target: { value: 'reviewed' } };
  await field('逐题状态', 'select').props.onChange(retryEvent);
  await settle();
  assert.equal(retryEvent.target.value, 'reviewed');
  assert.equal(field('逐题状态', 'select').props.value, 'reviewed');
  assert.equal(textOf(mounted.root).includes('Synthetic save outage'), false);
});

for (const role of ['member', 'admin', 'root']) {
  test(`header ${role === 'member' ? 'hides' : 'retains'} administration for ${role}`, async () => {
    identity(role);
    mounted = await mount(Header, await routes(), '/home.html', {
      setDesignTemplate() {},
      openTheme() {},
      toggleTheme() {},
    });
    const management = controls(mounted.root, 'a').filter((node) =>
      textOf(node).includes('管理后台'),
    );
    assert.equal(management.length, role === 'member' ? 0 : 1);
    const account = controls(mounted.root, 'a').find(
      (node) => node.props['aria-label'] === '账户中心',
    );
    assert.equal(account.props.href, role === 'member' ? '/home.html' : '/admin.html');
  });
}

test('administration keeps explicit member selection and administrative endpoints', async () => {
  identity('admin');
  AdminTraining ||= (await import(await loadSfc('src/admin/Training.vue'))).default;
  AdminReview ||= (await import(await loadSfc('src/admin/Contests.vue'))).default;
  mounted = await mount(AdminTraining, await routes(), '/home.html?qq_id=99999999');
  assert.ok(textOf(mounted.root).includes('成员 QQ'));
  const history = calls.find((call) => call.url.startsWith('/api/challenge/list?'));
  assert.ok(history, 'administrative training does not call the personal history endpoint');
  assert.equal(new URL(history.url, 'https://acm.test').searchParams.get('qq_id'), '99999999');
  mounted.unmount();
  calls = [];
  mounted = await mount(AdminReview, await routes(), '/home.html?contest_id=999');
  assert.ok(textOf(mounted.root).includes('成员 QQ'));
  await submit();
  const review = calls.find((call) => call.url.startsWith('/api/contest/reviews?'));
  assert.ok(review, 'administrative review does not call the personal review endpoint');
  assert.equal(new URL(review.url, 'https://acm.test').searchParams.get('owner_qq_id'), '99999999');
});
