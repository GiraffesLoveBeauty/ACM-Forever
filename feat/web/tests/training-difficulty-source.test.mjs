import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { setAuth } from '../src/lib/api.js';
import { adminFilters } from '../src/lib/admin.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const TrainingPanel = (await import(await loadSfc('src/components/TrainingPanel.vue'))).default;
const names = [
  'window',
  'document',
  'Document',
  'Node',
  'ShadowRoot',
  'location',
  'history',
  'fetch',
];
const originals = new Map(
  names.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
);
const response = (data) => new Response(JSON.stringify(data));
const hasClass = (node, name) =>
  String(node.props.class || '')
    .split(/\s+/)
    .includes(name);
const known = {
  platform: 'atcoder',
  problem_id: 'abc200_a',
  problem_name: 'Confirmed model',
  problem_rating: 1450,
  difficulty_source: 'atcoder_problems',
  difficulty_raw: 1450,
  difficulty_is_experimental: true,
  tags: ['dp', 'math'],
  status: 'active',
  created_at: 1700000000,
  challenge_rating: 1100,
};
const legacy = {
  platform: 'atcoder',
  problem_id: 'abc200_b',
  problem_name: 'Legacy points',
  problem_rating: 1450,
  tags: ['graphs'],
  status: 'failed',
  created_at: 1700000100,
  challenge_rating: 1100,
};
const zero = {
  ...known,
  problem_id: 'abc200_c',
  problem_name: 'Confirmed zero',
  problem_rating: 0,
  difficulty_raw: -10000,
  difficulty_is_experimental: false,
};
let dom, mounted, calls, generatedCount;

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
  generatedCount = 0;
});

afterEach(async () => {
  mounted?.unmount();
  await settle();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [name, descriptor] of originals)
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
});
after(cleanupCompiled);

function badge(container) {
  const badges = find(container, (node) => hasClass(node, 'problem-difficulty'));
  assert.equal(badges.length, 1);
  return badges[0];
}
function assertKnown(container, value = 1450, tone = 'cyan') {
  const current = badge(container);
  assert.equal(textOf(current), `难度 ${value}`);
  assert(hasClass(current, `problem-tone-${tone}`));
  assert.equal(current.props['data-rating-system'], 'atcoder_problems');
  assert.match(current.props.title, /AtCoder Problems 估计难度/);
}
function assertLegacy(container) {
  const current = badge(container);
  assert.equal(textOf(current), '难度 1450');
  assert(hasClass(current, 'problem-tone-neutral'));
  assert.match(current.props.title, /来源未标注/);
}

for (const personal of [true, false]) {
  test(`${personal ? 'member' : 'administrator'} training uses confirmed difficulty sources for generated zones and history`, async () => {
    setAuth(
      {
        authenticated: true,
        role: personal ? 'member' : 'admin',
        qq_id: '12345678',
        csrf_token: 'synthetic',
      },
      true,
    );
    // Personal training must not inherit another member's administrative selection.
    adminFilters.training = {
      owner: '87654321',
      platform: 'atcoder',
      tag: 'dp',
      difficulty: 1450,
      weak_tag: false,
    };
    const historyPath = personal
      ? '/api/me/training/challenges'
      : '/api/challenge/list?qq_id=87654321';
    const startPath = personal ? '/api/me/challenge/start' : '/api/challenge/start';
    globalThis.fetch = async (url, options = {}) => {
      const method = options.method || 'GET';
      const body = options.body == null ? undefined : JSON.parse(options.body);
      calls.push({ url, method, body });
      if (url === historyPath) return response([known, legacy]);
      if (url === startPath) {
        const row = [known, legacy, zero][generatedCount++];
        assert(row, 'only the three requested training zones are generated');
        return response({
          ...row,
          recommendation_reason: `Synthetic recommendation ${row.problem_id}`,
        });
      }
      throw Error('Unexpected training request: ' + method + ' ' + url);
    };
    const App = { render: () => h(TrainingPanel, { personal }) };
    mounted = await mount(
      App,
      [
        { path: '/challenge.html', component: App },
        { path: '/problem.html', component: { render: () => null } },
      ],
      personal ? '/challenge.html?owner_qq_id=99999999' : '/challenge.html?qq_id=87654321',
    );

    const historyRows = () => find(mounted.root, (node) => hasClass(node, 'training-history-row'));
    assert.equal(historyRows().length, 2);
    assertKnown(historyRows()[0]);
    assert.match(badge(historyRows()[0]).props.title, /实验模型/);
    assertLegacy(historyRows()[1]);

    const platform = find(
      mounted.root,
      (node) => node.type === 'label' && textOf(node).startsWith('平台'),
    )[0];
    find(platform, (node) => node.type === 'select')[0].props['onUpdate:modelValue']('atcoder');
    await settle();
    const difficulty = find(
      mounted.root,
      (node) => node.type === 'label' && textOf(node).startsWith('难度'),
    )[0];
    find(difficulty, (node) => node.type === 'input')[0].props['onUpdate:modelValue'](1450);
    await settle();
    await find(mounted.root, (node) => node.type === 'form')[0].props.onSubmit({
      preventDefault() {},
    });
    await settle();

    const zones = find(mounted.root, (node) => hasClass(node, 'training-zones'))[0];
    const cards = find(zones, (node) => node.type === 'article');
    assert.equal(cards.length, 3);
    assertKnown(cards[0]);
    assertLegacy(cards[1]);
    assertKnown(cards[2], 0, 'gray');
    assertKnown(historyRows()[0]);
    assertLegacy(historyRows()[1]);
    for (let i = 0; i < cards.length; i++) {
      const row = [known, legacy, zero][i];
      assert(textOf(cards[i]).includes(`Synthetic recommendation ${row.problem_id}`));
      assert.deepEqual(
        find(cards[i], (node) => hasClass(node, 'algorithm-tag')).map(textOf),
        row.tags,
      );
      const link = find(cards[i], (node) => node.type === 'a')[0];
      const url = new URL(link.props.href, 'https://acm.invalid');
      assert.equal(url.pathname, '/problem.html');
      assert.equal(url.searchParams.get('platform'), 'atcoder');
      assert.equal(url.searchParams.get('problem_id'), row.problem_id);
    }
    const starts = calls.filter((call) => call.method === 'POST');
    assert.deepEqual(
      starts.map((call) => call.body.difficulty),
      [1300, 1450, 1600],
    );
    assert(starts.every((call) => call.url === startPath));
    assert(
      calls.every((call) => call.url === startPath || call.url === historyPath),
      'presentation does not fetch per-problem details or classifications',
    );
    assert.equal(
      calls.filter((call) => call.url === historyPath).length,
      2,
      'history is refreshed after generation',
    );
    for (const call of starts) {
      assert.equal(Object.hasOwn(call.body, 'challenge_rating'), false);
      assert.equal(Object.hasOwn(call.body, 'rating'), false);
      if (personal) assert.equal(Object.hasOwn(call.body, 'owner_qq_id'), false);
      else assert.equal(call.body.owner_qq_id, '87654321');
    }
    assert.equal(
      known.challenge_rating,
      1100,
      'presentation must not rewrite challenge performance rating',
    );
  });
}
