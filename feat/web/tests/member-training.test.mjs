import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { adminFilters } from '../src/lib/admin.js';
import { memberFilters, memberQuery, problemReturn } from '../src/lib/member-problems.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Home = (await import(await loadSfc('src/views/Home.vue'))).default;
const MemberDetail = (await import(await loadSfc('src/admin/MemberDetail.vue'))).default;
const Header = (await import(await loadSfc('src/components/Header.vue'))).default;
const Problems = (await import(await loadSfc('src/views/MemberProblems.vue'))).default;
const Problem = (await import(await loadSfc('src/views/Problem.vue'))).default;
const Bindings = (await import(await loadSfc('src/components/OjBindings.vue'))).default;
const View = { render: () => h(RouterView) };
const PersonalView = { render: () => h('div', [h(Header), h(RouterView)]) };
const keys = [
  'window',
  'document',
  'Document',
  'Node',
  'ShadowRoot',
  'navigator',
  'fetch',
  'location',
  'history',
];
const original = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let dom, mounted, calls, failed, hold, releases, realRouter;
const profile = {
  user: { name: '合成成员', status: '训练组' },
  platform_counts: { codeforces: 1 },
  total_count: 1,
  recent_ac: [
    { platform: 'codeforces', problem_id: 'cf_1A', problem_name: '已 AC 示例', submit_time: 100 },
  ],
  bindings: [],
};
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => {
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://127.0.0.1/home.html',
  });
  for (const key of [
    'window',
    'document',
    'Document',
    'Node',
    'ShadowRoot',
    'navigator',
    'location',
    'history',
  ])
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      writable: true,
      configurable: true,
    });
  mounted = null;
  calls = [];
  failed = false;
  hold = false;
  releases = [];
  realRouter = null;
  setAuth(
    { authenticated: true, role: 'member', qq_id: '12345678', csrf_token: 'test-only' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, body: options.body ? JSON.parse(options.body) : undefined });
    if (hold) await new Promise((resolve) => releases.push(resolve));
    if (failed) return response({ message: '合成网络错误' }, 503);
    if (url === '/api/me/profile') return response(profile);
    if (url.startsWith('/api/forum/mine/')) return response([]);
    if (url.startsWith('/api/me/problems/tags?')) {
      const platform = new URL(url, 'https://acm.test').searchParams.get('platform');
      return response({ tags: platform === 'atcoder' ? ['dp', 'graphs'] : ['math', 'greedy'] });
    }
    if (url.startsWith('/api/me/problems?'))
      return response({
        items: [
          { platform: 'codeforces', problem_id: 'cf_1A', problem_name: '列表题目', ac_at: 100 },
        ],
        total: 25,
      });
    if (url.startsWith('/api/me/problems/') || url.startsWith('/api/problems/'))
      return response({
        platform: 'codeforces',
        problem_id: 'cf_1A',
        problem_name: '列表题目',
        tags: [],
        content_available: false,
        samples: [],
      });
    if (url.includes('/verification'))
      return response({
        verification_id: 'server-verification',
        account: options.body ? JSON.parse(options.body).account : 'NewHandle',
        code: 'ACM-code',
        expires_at: 1900000000,
      });
    if (url.includes('/bindings/')) return response({ message: '操作已保存' });
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  releases.forEach((resolve) => resolve());
  await settle();
  realRouter?.options.history.destroy();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [key, value] of original)
    if (value) Object.defineProperty(globalThis, key, value);
    else delete globalThis[key];
});
after(cleanupCompiled);
const buttons = (word) =>
  find(mounted.root, (node) => node.type === 'button' && textOf(node).includes(word));
const links = (word) =>
  find(mounted.root, (node) => node.type === 'a' && textOf(node).includes(word));
const click = async (node) => {
  await node.props.onClick({ button: 0, preventDefault() {} });
  await settle();
};
const tagChoices = () =>
  find(
    mounted.root,
    (node) => node.type === 'button' && String(node.props.class).includes('luogu-picker-chip'),
  );
const tagChoice = (name) => tagChoices().find((node) => node.props['aria-label'] === name);
const labeledControl = (label, type = 'select') => {
  const wrapper = find(
    mounted.root,
    (node) => node.type === 'label' && textOf(node).startsWith(label),
  )[0];
  assert(wrapper, `filter label exists: ${label}`);
  return find(wrapper, (node) => node.type === type)[0];
};
const submitFilters = async () => {
  await find(mounted.root, (node) => node.type === 'form')[0].props.onSubmit({
    preventDefault() {},
  });
  await settle();
};
const queryOf = (url) => new URL(url, 'https://acm.test').searchParams;
const routes = [
  { path: '/home.html', component: Home },
  { path: '/problem-bank.html', component: Problems },
  { path: '/my-problems.html', component: Problems },
  { path: '/problem.html', component: Problem },
  { path: '/admin.html', component: MemberDetail },
];

test('personal and administrator summaries render confirmed AtCoder model colours without guessing unknown sources', async () => {
  const originalFetch = globalThis.fetch;
  const recent = [
    {
      platform: 'atcoder',
      problem_id: 'abc200_a',
      problem_name: 'Confirmed model',
      problem_rating: 1450,
      difficulty_source: 'atcoder_problems',
      difficulty_raw: 1450,
      tags: [],
    },
    {
      platform: 'atcoder',
      problem_id: 'abc200_b',
      problem_name: 'Legacy points',
      problem_rating: 1450,
      tags: [],
    },
  ];
  const data = {
    ...profile,
    recent_ac: recent,
    cf: { rating: 1900 },
    atcoder: { rating: 1600 },
    challenge_rating: 1200,
  };
  globalThis.fetch = async (url, options) =>
    ['/api/me/profile', '/api/member/12345678'].includes(url)
      ? response(data)
      : originalFetch(url, options);
  setAuth({ authenticated: true, role: 'admin', qq_id: '12345678' }, true);
  for (const [View, path] of [
    [Home, '/home.html'],
    [MemberDetail, '/admin.html?qq_id=12345678'],
  ]) {
    mounted = await mount(View, routes, path);
    const badges = find(mounted.root, (node) =>
      String(node.props.class).includes('problem-difficulty'),
    );
    assert.equal(badges.length, 2, path);
    assert.match(String(badges[0].props.class), /problem-tone-cyan/);
    assert.match(badges[0].props.title, /AtCoder Problems 估计难度/);
    assert.match(String(badges[1].props.class), /problem-tone-neutral/);
    assert.match(badges[1].props.title, /来源未标注/);
    if (View === MemberDetail) assert.match(textOf(mounted.root), /AtCoder Rating 1600/);
    mounted.unmount();
    mounted = null;
  }
});

test('member filters and return sources exclude owner/admin state and external URLs', () => {
  const normalized = memberFilters({
    scope: 'solved',
    page: '3',
    platform: 'codeforces',
    owner_qq_id: '99999999',
  });
  assert.equal(normalized.page, 3);
  assert.equal(normalized.scope, 'solved');
  assert(!('owner_qq_id' in normalized));
  assert.equal(memberFilters({ page: ['2'], scope: 'unsafe' }).page, 2);
  for (const platform of [undefined, ''])
    assert.equal(memberFilters({ platform }).platform, 'luogu');
  assert.equal(memberFilters({ platform: 'unknown' }).platform, 'all');
  assert.equal(memberFilters({ platform: 'atcoder' }).platform, 'atcoder');
  assert.equal(problemReturn('/home.html'), '/home.html');
  assert.equal(
    problemReturn('/problem-bank.html?scope=solved&page=3&qq_id=99999999'),
    '/problem-bank.html?scope=solved&platform=all&page=3',
  );
  assert.equal(
    problemReturn(
      '/my-problems.html?scope=solved&page=2&platform=codeforces&owner_qq_id=99999999',
      true,
    ),
    '/my-problems.html?scope=solved&platform=codeforces&page=2',
  );
  for (const source of [
    'https://evil.test',
    '//evil.test',
    '/admin.html?section=members',
    '/problem-bank.html/../post.html',
    '/\\evil.test',
  ])
    assert.equal(problemReturn(source), '/problem-bank.html');
});

test('Home distinguishes pending and failed profile data from zero, and retry recovers', async () => {
  hold = true;
  mounted = await mount(Home, routes, '/home.html');
  assert(textOf(mounted.root).includes('正在加载个人资料'));
  assert(textOf(mounted.root).includes('—'));
  assert(!textOf(mounted.root).includes('暂无 AC 记录'));
  failed = true;
  hold = false;
  releases.forEach((resolve) => resolve());
  await settle();
  assert(textOf(mounted.root).includes('个人资料加载失败'));
  assert(textOf(mounted.root).includes('—'));
  failed = false;
  await click(buttons('重试')[0]);
  assert(textOf(mounted.root).includes('欢迎回来，合成成员'));
});

test('Home recent AC and complete list point to member-owned internal statement flow', async () => {
  mounted = await mount(Home, routes, '/home.html');
  const recent = find(
    mounted.root,
    (node) => node.type === 'a' && node.props['aria-label'] === '查看站内题面',
  )[0];
  const url = new URL(recent.props.href, 'https://acm.test');
  assert.equal(url.pathname, '/problem.html');
  assert.equal(url.searchParams.get('from'), '/home.html');
  assert.equal(links('查看全部已 AC')[0].props.href, '/my-problems.html?scope=solved');
});

test('MemberProblems reads URL filters and never inherits administrator owner selections', async () => {
  adminFilters.problems = { owner_qq_id: '99999999', tag: 'administrator-only' };
  mounted = await mount(
    Problems,
    routes,
    '/problem-bank.html?scope=solved&platform=codeforces&tag=member&problem_tag=math&page=2',
  );
  const call = calls.find((item) => item.url.startsWith('/api/me/problems?'));
  const query = new URL(call.url, 'https://acm.test').searchParams;
  assert.equal(query.get('scope'), 'solved');
  assert.equal(query.get('page'), '2');
  assert.equal(query.get('tag'), 'member');
  assert.equal(query.get('problem_tag'), 'math');
  assert.equal(query.has('owner_qq_id'), false);
  assert(textOf(mounted.root).includes('本人已 AC'));
  assert(!textOf(mounted.root).includes('题库管理'));
});

test('Luogu solved records with unknown times stay visible without a fabricated date', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (url.startsWith('/api/me/problems?'))
      return response({
        items: [
          { platform: 'luogu', problem_id: 'P1001', problem_name: '合成洛谷已通过题', ac_at: 0 },
        ],
        total: 1,
      });
    return originalFetch(url, options);
  };
  mounted = await mount(Problems, routes, '/problem-bank.html?scope=solved&platform=luogu');
  assert(textOf(mounted.root).includes('合成洛谷已通过题'));
  assert(textOf(mounted.root).includes('已 AC，时间未知'));
  assert(!textOf(mounted.root).includes('1970'));
});

test('MemberProblems failure provides retry without an empty-data claim', async () => {
  failed = true;
  mounted = await mount(Problems, routes, '/problem-bank.html?scope=solved');
  assert(textOf(mounted.root).includes('题目加载失败'));
  assert(!textOf(mounted.root).includes('暂未同步到匹配'));
  failed = false;
  await click(buttons('重试').find((node) => textOf(node) === '重试'));
  assert(textOf(mounted.root).includes('列表题目'));
});

test('statement round trip preserves solved scope, search, exact tag, platform and page', async () => {
  const path =
    '/problem-bank.html?scope=solved&platform=codeforces&tag=member&problem_tag=math&page=2';
  mounted = await mount(View, routes, path);
  await click(links('查看题面')[0]);
  assert.equal(mounted.router.currentRoute.value.path, '/problem.html');
  const back = links('返回题库')[0];
  assert.equal(back.props.href, path);
  await click(back);
  assert.equal(mounted.router.currentRoute.value.fullPath, path);
  assert(calls.filter((item) => item.url.startsWith('/api/me/problems?')).length >= 2);
});

test('exact tag filters normalize independently of keyword search and survive safe return URLs', () => {
  const normalized = memberFilters({ tag: 'keyword', problem_tag: '  Math  ' });
  assert.equal(normalized.tag, 'keyword');
  assert.equal(normalized.problem_tag, 'Math');
  assert.equal(memberFilters({ problem_tag: ['math'] }).problem_tag, '');
  assert.equal(memberFilters({ problem_tag: 'x'.repeat(101) }).problem_tag.length, 100);
  assert(!('problem_tag' in memberQuery({ problem_tag: '' })));
  const back = queryOf(problemReturn('/my-problems.html?problem_tag=Math&owner_qq_id=99999999'));
  assert.equal(back.get('problem_tag'), 'Math');
  assert(!back.has('owner_qq_id'));
});

test('Codeforces tag picker submits Chinese selections using raw IDs and resets pagination', async () => {
  mounted = await mount(
    View,
    routes,
    '/my-problems.html?scope=solved&platform=codeforces&tag=member&page=2',
  );
  labeledControl('收藏').props['onUpdate:modelValue']('favorite');
  await click(buttons('按标签筛选')[0]);
  assert.match(textOf(mounted.root), /Codeforces 原生标签/);
  await click(buttons('贪心')[0]);
  const dialog = find(mounted.root, (node) => node.type === 'dialog')[0];
  const search = find(dialog, (node) => node.type === 'input' && node.props.type === 'search')[0];
  search.props['onUpdate:modelValue']('math');
  await settle();
  await click(buttons('数学').find((node) => node.props['aria-pressed'] === false));
  assert(!queryOf(mounted.router.currentRoute.value.fullPath).has('problem_tags'));
  await click(buttons('确认筛选')[0]);
  const query = queryOf(calls.filter(({ url }) => url.startsWith('/api/me/problems?')).at(-1).url);
  assert.equal(query.get('tag'), 'member');
  assert.equal(query.get('problem_tags'), 'greedy,math');
  assert.equal(
    queryOf(problemReturn(mounted.router.currentRoute.value.fullPath)).get('problem_tags'),
    'greedy,math',
  );
  assert.equal(query.get('state'), 'favorite');
  assert.equal(query.get('scope'), 'solved');
  assert.equal(query.get('page'), '1');
  assert(!query.has('owner_qq_id'));
  await click(buttons('清除筛选')[0]);
  assert(!queryOf(mounted.router.currentRoute.value.fullPath).has('problem_tags'));
  assert(!queryOf(mounted.router.currentRoute.value.fullPath).has('tag'));
});

test('problem cards display JSON, array and legacy tags as readable labels', async () => {
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) =>
    url.startsWith('/api/me/problems?')
      ? response({
          items: [
            { platform: 'codeforces', problem_id: 'cf_1A', tags: '["math","dp"]' },
            { platform: 'codeforces', problem_id: 'cf_1B', tags: ['graphs', 'trees'] },
            { platform: 'codeforces', problem_id: 'cf_1C', tags: 'greedy,sortings' },
            { platform: 'codeforces', problem_id: 'cf_1D', tags: '[]' },
          ],
          total: 4,
        })
      : fetch(url, options);
  mounted = await mount(Problems, routes, '/my-problems.html');
  const cards = find(mounted.root, (node) => node.type === 'article');
  const labels = cards.map((card) =>
    find(card, (node) => String(node.props.class).includes('algorithm-tag')).map(textOf),
  );
  assert.deepEqual(labels, [['数学', '动态规划'], ['图论', '树上算法'], ['贪心', '排序'], []]);
  assert(!textOf(cards[0]).includes('["math"'));
  assert(textOf(cards[3]).includes('无标签'));
});

test('changing platform replaces tag choices and clears stale selection without losing search', async () => {
  mounted = await mount(
    Problems,
    routes,
    '/my-problems.html?platform=codeforces&tag=keyword&problem_tag=math',
  );
  labeledControl('平台').props['onUpdate:modelValue']('atcoder');
  await settle();
  await click(buttons('按标签筛选')[0]);
  assert.deepEqual(tagChoices().map((node) => node.props['aria-label']), ['dp', 'graphs']);
  await click(buttons('取消')[0]);
  await submitFilters();
  const query = queryOf(mounted.router.currentRoute.value.fullPath);
  assert.equal(query.get('platform'), 'atcoder');
  assert.equal(query.get('tag'), 'keyword');
  assert(!query.has('problem_tag'));
  await mounted.router.push('/my-problems.html?platform=codeforces&problem_tag=legacy');
  await settle();
  assert.match(textOf(mounted.root), /已选：legacy/);
  assert.equal(
    queryOf(calls.filter(({ url }) => url.startsWith('/api/me/problems?')).at(-1).url).get(
      'problem_tag',
    ),
    'legacy',
  );
});

test('AtCoder tag picker replaces a draft and submits one raw tag on confirmation', async () => {
  mounted = await mount(
    Problems,
    routes,
    '/my-problems.html?platform=atcoder&problem_tag=dp&page=2',
  );
  await click(buttons('按标签筛选')[0]);
  assert.equal(tagChoice('dp').props['aria-pressed'], true);
  await click(tagChoice('graphs'));
  assert.equal(tagChoice('graphs').props['aria-pressed'], true);
  assert.equal(tagChoice('dp').props['aria-pressed'], false);
  assert.equal(mounted.router.currentRoute.value.query.problem_tag, 'dp');
  await click(buttons('确认筛选')[0]);
  const query = queryOf(calls.filter(({ url }) => url.startsWith('/api/me/problems?')).at(-1).url);
  assert.equal(query.get('problem_tag'), 'graphs');
  assert.equal(query.get('page'), '1');
  assert.equal(query.has('problem_tags'), false);
  assert.equal(mounted.router.currentRoute.value.query.problem_tag, 'graphs');
  await click(buttons('清空')[0]);
  assert.equal(mounted.router.currentRoute.value.query.problem_tag, undefined);
});

test('tag endpoint failures retain the problem list and retry only the tag choices', async () => {
  const fetch = globalThis.fetch;
  let tagsFailed = true;
  globalThis.fetch = async (url, options) =>
    tagsFailed && url.startsWith('/api/me/problems/tags?')
      ? response({ message: '标签服务暂不可用' }, 503)
      : fetch(url, options);
  mounted = await mount(Problems, routes, '/my-problems.html?problem_tag=legacy');
  assert(textOf(mounted.root).includes('列表题目'));
  assert(textOf(mounted.root).includes('标签服务暂不可用'));
  assert.match(textOf(mounted.root), /已选：legacy/);
  const listRequests = calls.filter(({ url }) => url.startsWith('/api/me/problems?')).length;
  tagsFailed = false;
  await click(buttons('重试标签')[0]);
  await click(buttons('按标签筛选')[0]);
  assert(tagChoice('数学'));
  assert(!textOf(mounted.root).includes('标签服务暂不可用'));
  assert.equal(calls.filter(({ url }) => url.startsWith('/api/me/problems?')).length, listRequests);
});

test('a delayed old platform tag response cannot replace current choices', async () => {
  const fetch = globalThis.fetch;
  let release;
  let pending;
  globalThis.fetch = async (url, options) => {
    if (url.startsWith('/api/me/problems/tags?') && queryOf(url).get('platform') === 'codeforces') {
      pending = options;
      await new Promise((resolve) => {
        release = resolve;
        releases.push(resolve);
      });
      return response({ tags: ['old-platform-only'] });
    }
    return fetch(url, options);
  };
  mounted = await mount(Problems, routes, '/my-problems.html?platform=codeforces');
  await click(buttons('按标签筛选')[0]);
  assert.match(textOf(mounted.root), /正在加载/);
  labeledControl('平台').props['onUpdate:modelValue']('atcoder');
  await settle();
  assert(pending.signal.aborted);
  const picker = buttons('按标签筛选')[0];
  if (!picker.props['aria-expanded']) await click(picker);
  assert.deepEqual(tagChoices().map((node) => node.props['aria-label']), ['dp', 'graphs']);
  release();
  await settle();
  assert.equal(tagChoice('old-platform-only'), undefined);
});
for (const scope of ['all', 'solved']) {
  for (const platform of ['', 'all', 'codeforces', 'atcoder']) {
    test(`member list sends backend-compatible platform: ${platform || 'default'}, scope: ${scope}`, async () => {
      const records = [
        { platform: 'codeforces', problem_id: 'cf_1A', problem_name: 'CF 合成题', ac_at: 100 },
        { platform: 'atcoder', problem_id: 'demo_a', problem_name: 'ATC 合成题', ac_at: 200 },
        { platform: 'luogu', problem_id: 'P1001', problem_name: '洛谷合成题', ac_at: 300 },
      ];
      globalThis.fetch = async (url) => {
        const parsed = new URL(url, 'https://local.invalid');
        if (parsed.pathname === '/api/me/problems/taxonomy')
          return response({ difficulties: [], tags: [], tag_types: [] });
        if (parsed.pathname === '/api/me/problems/tags') {
          assert.notEqual(parsed.searchParams.get('platform'), 'all');
          return response({ tags: [] });
        }
        assert.equal(parsed.pathname, '/api/me/problems');
        calls.push({ url });
        // Match the formal backend: nonempty platform values filter by equality.
        const selected = parsed.searchParams.get('platform');
        const items = records.filter((row) => !selected || row.platform === selected);
        return response({ items, total: items.length });
      };
      const query = new URLSearchParams({ scope, ...(platform ? { platform } : {}) });
      mounted = await mount(Problems, routes, '/problem-bank.html?' + query);
      const params = new URL(calls[0].url, 'https://local.invalid').searchParams;
      assert.equal(params.get('scope'), scope);
      const expectedPlatform = platform || (scope === 'solved' ? 'all' : 'luogu');
      if (expectedPlatform === 'all') {
        assert.equal(params.has('platform'), false);
        for (const row of records) assert(textOf(mounted.root).includes(row.problem_name));
      } else {
        assert.equal(params.get('platform'), expectedPlatform);
        for (const row of records)
          assert.equal(
            textOf(mounted.root).includes(row.problem_name),
            row.platform === expectedPlatform,
          );
      }
    });
  }
}

test('binding form requires current password and confirmation; cancellation clears secrets', async () => {
  const binding = {
    platform: 'codeforces',
    label: 'Codeforces',
    account: 'Original',
    binding_status: 'bound',
    self_service: true,
    sync_status: 'never',
  };
  mounted = await mount(
    { render: () => h(Bindings, { bindings: [binding] }) },
    routes,
    '/home.html',
  );
  await click(buttons('解绑')[0]);
  assert(buttons('确认解绑')[0].props.disabled);
  const password = find(
    mounted.root,
    (node) => node.type === 'input' && node.props.type === 'password',
  )[0];
  password.props['onUpdate:modelValue']('TemporaryPassword');
  const checkbox = find(
    mounted.root,
    (node) => node.type === 'input' && node.props.type === 'checkbox',
  )[0];
  checkbox.props['onUpdate:modelValue'](true);
  await settle();
  assert.equal(buttons('确认解绑')[0].props.disabled, false);
  await click(buttons('取消')[0]);
  await click(buttons('解绑')[0]);
  assert.equal(
    find(mounted.root, (node) => node.type === 'input' && node.props.type === 'password')[0].value,
    '',
  );
  assert.equal(calls.filter((item) => item.url.includes('/bindings/')).length, 0);
});

test('imported CF account can verify its current handle without a destructive rebind warning', async () => {
  const binding = {
    platform: 'codeforces',
    label: 'Codeforces',
    account: 'Imported84',
    binding_status: 'bound',
    self_service: true,
    sync_status: 'success',
    provenance: { source: 'admin_import', owner_verified_at: null },
  };
  mounted = await mount({ render: () => h(Bindings, { bindings: [binding] }) }, routes);
  assert.equal(buttons('核验当前账号').length, 1);
  assert.equal(buttons('改绑账号').length, 1);
  await click(buttons('核验当前账号')[0]);
  const account = find(
    mounted.root,
    (node) => node.type === 'input' && node.props.maxlength === '64',
  )[0];
  assert.equal(account.value, 'Imported84');
  assert.equal(account.props.readonly, true);
  assert(textOf(mounted.root).includes('保留现有绑定、AC、提交证据和训练挑战'));
  const form = find(mounted.root, (node) => node.type === 'form')[0];
  await form.props.onSubmit({ preventDefault() {} });
  await settle();
  assert.equal(calls.find((item) => item.url.endsWith('/verification')).body.account, 'Imported84');
  assert(!textOf(mounted.root).includes('解绑或成功改绑会清理'));
  const confirm = buttons('确认核验')[0];
  assert(confirm.props.disabled);
  find(mounted.root, (node) => node.type === 'input' && node.props.type === 'password')[0].props[
    'onUpdate:modelValue'
  ]('MemberPassword');
  find(mounted.root, (node) => node.type === 'input' && node.props.type === 'checkbox')[0].props[
    'onUpdate:modelValue'
  ](true);
  await settle();
  assert.equal(buttons('确认核验')[0].props.disabled, false);
  await click(buttons('确认核验')[0]);
  assert.deepEqual(calls.find((item) => item.url.endsWith('/confirm')).body, {
    verification_id: 'server-verification',
    password: 'MemberPassword',
    confirmed: true,
    current_account: 'Imported84',
  });
  assert.equal(
    find(mounted.root, (node) => node.type === 'input' && node.props.type === 'password').length,
    0,
  );
});

test('pending current-handle verification resumes separately from changing the account', async () => {
  const binding = {
    platform: 'codeforces',
    label: 'Codeforces',
    account: 'Imported84',
    binding_status: 'pending',
    self_service: true,
    provenance: { source: 'admin_import', owner_verified_at: null },
    verification: {
      account: 'imported84',
      verification_id: 'pending-id',
      code: 'ACM-pending',
      expires_at: 1900000000,
    },
  };
  mounted = await mount({ render: () => h(Bindings, { bindings: [binding] }) }, routes);
  await click(buttons('核验当前账号')[0]);
  assert(textOf(mounted.root).includes('ACM-pending'));
  assert.equal(buttons('确认核验').length, 1);
  await click(buttons('取消')[0]);
  await click(buttons('改绑账号')[0]);
  const input = find(
    mounted.root,
    (node) => node.type === 'input' && node.props.maxlength === '64',
  )[0];
  assert.equal(Boolean(input.props.readonly), false);
  assert.equal(input.value, '');
  assert(!textOf(mounted.root).includes('ACM-pending'));
  assert.equal(calls.filter((item) => item.url.includes('/bindings/')).length, 0);
});

test('current-handle verification is offered only for an unverified self-service import', async () => {
  const bindings = [
    {
      platform: 'codeforces',
      label: 'Codeforces',
      account: 'Verified',
      self_service: true,
      provenance: { source: 'member_verified', owner_verified_at: 100 },
    },
    {
      platform: 'atcoder',
      label: 'AtCoder',
      account: 'Imported',
      self_service: false,
      provenance: { source: 'admin_import', owner_verified_at: null },
    },
    {
      platform: 'luogu',
      label: '洛谷',
      account: 'AlreadyVerified',
      self_service: true,
      provenance: { source: 'admin_import', owner_verified_at: 100 },
    },
  ];
  mounted = await mount({ render: () => h(Bindings, { bindings }) }, routes);
  assert.equal(buttons('核验当前账号').length, 0);
  assert.equal(buttons('改绑账号').length, 2);
});

let guardId = 0;
async function loadActualGuard() {
  // Use a fresh initialization promise for each case; stub only SFC loading.
  const apiUrl = new URL(`../src/lib/api.js?member-training=${++guardId}`, import.meta.url).href;
  const session = await import(apiUrl);
  let source = await readFile(new URL('../src/router.js', import.meta.url), 'utf8');
  source = source
    .replace(
      "from 'vue-router'",
      `from '${new URL('../node_modules/vue-router/dist/vue-router.mjs', import.meta.url).href}'`,
    )
    .replace("from './lib/api.js'", `from '${apiUrl}'`)
    .replace(
      /\(\) => import\('\.\/views\/[^']+'\)/g,
      '() => Promise.resolve({default:{render(){return null}}})',
    );
  realRouter = (
    await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
  ).default;
  return { router: realRouter, session };
}

test('actual route guard exposes retry after auth failure and retains the requested module', async () => {
  let unavailable = true;
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    if (unavailable) throw Error('offline');
    return response({ authenticated: true, role: 'member', qq_id: '12345678' });
  };
  await loadActualGuard();
  await realRouter.push('/home.html?source=training');
  assert.equal(realRouter.currentRoute.value.path, '/auth-unavailable.html');
  assert.equal(realRouter.currentRoute.value.query.next, '/home.html?source=training');
  assert.equal(requests, 1);
  unavailable = false;
  await realRouter.push(realRouter.currentRoute.value.query.next);
  assert.equal(requests, 2);
  assert.equal(realRouter.currentRoute.value.fullPath, '/home.html?source=training');
  await realRouter.push('/admin.html');
  assert.equal(realRouter.currentRoute.value.path, '/forbidden.html');
  await realRouter.push('/problem-bank.html?scope=solved');
  assert.equal(realRouter.currentRoute.value.meta.title, '题库');
});

test('authentication timeout reaches recovery after one request and retries only on navigation', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let unavailable = true;
  let requests = 0;
  globalThis.fetch = async (_url, options) => {
    requests++;
    if (unavailable)
      await new Promise((_resolve, reject) =>
        options.signal.addEventListener(
          'abort',
          () => reject(new DOMException('Timed out', 'AbortError')),
          { once: true },
        ),
      );
    return response({ authenticated: true, role: 'member', qq_id: '12345678' });
  };
  await loadActualGuard();
  const navigation = realRouter.push('/my-problems.html?scope=solved&page=2');
  await settle();
  assert.equal(requests, 1);
  t.mock.timers.tick(15000);
  await settle();
  // Check before awaiting navigation: the broken guard starts another pending request here.
  assert.equal(requests, 1);
  assert.equal(realRouter.currentRoute.value.path, '/auth-unavailable.html');
  await navigation;
  assert.equal(realRouter.currentRoute.value.query.next, '/my-problems.html?scope=solved&page=2');
  unavailable = false;
  await realRouter.push(realRouter.currentRoute.value.query.next);
  assert.equal(requests, 2);
  assert.equal(realRouter.currentRoute.value.fullPath, '/my-problems.html?scope=solved&page=2');
});

test('direct authentication recovery opens without starting session initialization', async () => {
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    throw Error('Recovery must not request authentication');
  };
  await loadActualGuard();
  await realRouter.push({
    path: '/auth-unavailable.html',
    query: { next: '/home.html?source=training' },
  });
  assert.equal(realRouter.currentRoute.value.path, '/auth-unavailable.html');
  assert.equal(realRouter.currentRoute.value.query.next, '/home.html?source=training');
  assert.equal(requests, 0);
});

for (const role of ['member', 'admin', 'root']) {
  test(`${role} personal-center catalog stays in the member flow under the actual guard`, async () => {
    setAuth({ authenticated: true, role, qq_id: '12345678', csrf_token: 'test-only' }, true);
    mounted = await mount(PersonalView, routes, '/home.html', {
      openTheme() {},
      toggleTheme() {},
      setDesignTemplate() {},
    });
    const catalog = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '题库')[0];
    const navigation = find(
      mounted.root,
      (node) => node.type === 'a' && textOf(node) === '▦ 题库',
    )[0];
    assert(navigation, 'global navigation exposes the independent problem bank');
    assert.equal(navigation.props.href, catalog.props.href);
    const request = globalThis.fetch;
    globalThis.fetch = (url, options) =>
      url === '/api/auth/me'
        ? Promise.resolve(response({ authenticated: true, role, qq_id: '12345678' }))
        : request(url, options);
    await loadActualGuard();
    await realRouter.push(catalog.props.href);
    assert.equal(realRouter.currentRoute.value.fullPath, '/my-problems.html');
    await click(catalog);
    assert.equal(mounted.router.currentRoute.value.fullPath, '/my-problems.html');
    assert(calls.some(({ url }) => url.startsWith('/api/me/problems?')));
    const list = calls.find(({ url }) => url.startsWith('/api/me/problems?'));
    assert.equal(new URL(list.url, 'https://acm.test').searchParams.get('platform'), 'luogu');
    assert.equal(textOf(find(mounted.root, (node) => node.type === 'h1')[0]), '题库');
    assert(
      !calls.some(({ url }) => url.startsWith('/api/admin/') || url.startsWith('/api/problems?')),
    );
    await click(links('查看题面')[0]);
    const back = links('返回题库')[0];
    await realRouter.push(back.props.href);
    assert.equal(realRouter.currentRoute.value.fullPath, '/my-problems.html?platform=luogu');
    await click(back);
    assert.equal(mounted.router.currentRoute.value.fullPath, '/my-problems.html?platform=luogu');
  });

  test(`${role} Home complete AC link stays in personal problems during filtering and statement round trips`, async () => {
    setAuth({ authenticated: true, role, qq_id: '12345678', csrf_token: 'test-only' }, true);
    mounted = await mount(View, routes, '/home.html');
    await click(links('查看全部已 AC')[0]);
    assert.equal(mounted.router.currentRoute.value.fullPath, '/my-problems.html?scope=solved');
    assert(
      calls.some(({ url }) => url.startsWith('/api/me/problems?') && url.includes('scope=solved')),
    );
    await click(buttons('下一页')[0]);
    assert.equal(
      mounted.router.currentRoute.value.fullPath,
      '/my-problems.html?scope=solved&platform=all&page=2',
    );
    await click(links('查看题面')[0]);
    assert.equal(
      links('返回题库')[0].props.href,
      '/my-problems.html?scope=solved&platform=all&page=2',
    );
    await click(links('返回题库')[0]);
    assert.equal(
      mounted.router.currentRoute.value.fullPath,
      '/my-problems.html?scope=solved&platform=all&page=2',
    );
    await click(buttons('清除筛选')[0]);
    assert.equal(
      mounted.router.currentRoute.value.fullPath,
      '/my-problems.html?scope=solved&platform=all',
    );
    await click(buttons('收藏')[0]);
    assert(
      calls.some(
        ({ url, body }) => url === '/api/me/problems/codeforces/cf_1A/state' && body.is_favorite,
      ),
    );
    assert(!calls.some(({ url }) => url.startsWith('/api/problems?')));
  });

  test(`${role} actual guard preserves personal AC address and the legacy catalog role behavior`, async () => {
    globalThis.fetch = async (url) =>
      response(url === '/api/auth/me' ? { authenticated: true, role, qq_id: '12345678' } : {});
    await loadActualGuard();
    const target = '/my-problems.html?scope=solved&platform=codeforces&page=2';
    await realRouter.push(target);
    assert.equal(realRouter.currentRoute.value.fullPath, target);
    await realRouter.push('/problem-bank.html?scope=solved');
    assert.equal(
      realRouter.currentRoute.value.path,
      role === 'member' ? '/problem-bank.html' : '/admin.html',
    );
    if (role !== 'member') assert.equal(realRouter.currentRoute.value.query.section, 'problems');
  });
}
