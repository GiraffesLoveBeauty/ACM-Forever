import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { h } from 'vue';
import {
  algorithmCategory,
  difficultyPresentation,
  normalizeTags,
} from '../src/lib/problem-presentation.js';
import { cleanupCompiled, find, loadSfc, mount, textOf } from './helpers/vue-harness.mjs';

const Difficulty = (await import(await loadSfc('src/components/ProblemDifficulty.vue'))).default;
const Tag = (await import(await loadSfc('src/components/AlgorithmTag.vue'))).default;
const Tags = (await import(await loadSfc('src/components/ProblemTags.vue'))).default;
after(cleanupCompiled);
const presentation = (value, platform = 'codeforces', fields = {}) =>
  difficultyPresentation({ platform, problem_rating: value, ...fields });

test('CF rating boundaries use the same seven tones, keeping the actual value', () => {
  for (const [value, tone] of [
    [1, 'gray'],
    [1199, 'gray'],
    [1200, 'green'],
    [1399, 'green'],
    [1400, 'cyan'],
    [1599, 'cyan'],
    [1600, 'blue'],
    [1899, 'blue'],
    [1900, 'purple'],
    [2099, 'purple'],
    [2100, 'orange'],
    [2399, 'orange'],
    [2400, 'red'],
  ]) {
    const row = presentation(value);
    assert.equal(row.tone, tone, String(value));
    assert.equal(row.value, value);
    assert.equal(row.label, '难度 ' + value);
    assert.match(row.title, /Codeforces|CF/);
  }
  assert.equal(presentation(' 1400 ').tone, 'cyan');
});

test('absent, malformed and coerced values do not become a real CF difficulty', () => {
  for (const value of [
    null,
    undefined,
    '',
    ' ',
    0,
    '0',
    -1,
    '-1',
    true,
    false,
    [],
    {},
    NaN,
    Infinity,
    'NaN',
    'Infinity',
    '1e3',
    '1200oops',
  ]) {
    assert.equal(presentation(value).label, '难度未知', String(value));
    assert.equal(presentation(value).tone, 'neutral');
  }
  assert.equal(difficultyPresentation({ rating: 1400 }, 'codeforces').tone, 'cyan');
  assert.equal(
    difficultyPresentation({ problem_rating: null, rating: 1400 }, 'codeforces').label,
    '难度未知',
    'explicit missing canonical rating does not revive an unrelated alias',
  );
});

test('AtCoder estimates retain their own boundaries and source instead of CF colours', () => {
  for (const [value, tone] of [
    [0, 'gray'],
    [399, 'gray'],
    [400, 'brown'],
    [799, 'brown'],
    [800, 'green'],
    [1199, 'green'],
    [1200, 'cyan'],
    [1599, 'cyan'],
    [1600, 'blue'],
    [1999, 'blue'],
    [2000, 'yellow'],
    [2399, 'yellow'],
    [2400, 'orange'],
    [2799, 'orange'],
    [2800, 'red'],
  ]) {
    const row = presentation(value, 'atcoder', { difficulty_source: 'atcoder_problems' });
    assert.equal(row.tone, tone, String(value));
    assert.match(row.title, /AtCoder Problems 估计难度/);
  }
  assert.match(
    presentation(1500, 'atcoder', {
      difficulty_source: 'atcoder_problems',
      difficulty_is_experimental: true,
    }).title,
    /实验模型/,
  );
  const legacy = presentation(1200, 'atcoder');
  assert.equal(legacy.tone, 'neutral');
  assert.equal(legacy.label, '难度 1200');
  assert.match(legacy.title, /来源未标注/);
  for (const value of ['bad', '-1', -1, true, [], {}, null, '', Infinity])
    assert.equal(presentation(value, 'atcoder').label, '难度未知');
});

test('native text remains visible without introducing a CF conversion', () => {
  assert.equal(presentation('2星', 'nowcoder').label, '难度 2星');
  assert.equal(presentation('2星', 'nowcoder').tone, 'neutral');
  assert.match(presentation('2星', 'nowcoder').title, /未换算/);
  assert.equal(presentation(true, 'nowcoder').label, '难度未知');
  assert.equal(presentation('-1', 'nowcoder').label, '难度未知');
});

test('CF tags, Chinese aliases and existing taxonomy IDs share stable category colours', () => {
  const cases = {
    strategy: [
      'greedy',
      '贪心',
      'difference_array',
      '差分',
      'enumeration',
      '枚举',
      'binary search',
      'brute force',
      'constructive algorithms',
      'divide and conquer',
      'implementation',
      'sortings',
      'two pointers',
      'ternary search',
      'bitmasks',
      'meet-in-the-middle',
    ],
    graph: [
      'graphs',
      '图论',
      'dfs and similar',
      'flows',
      'shortest paths',
      'trees',
      '2-sat',
      'graph matchings',
    ],
    dp: ['dp', '动态规划', 'linear_dp', '线性DP', 'pending_dp', '动态规划·待细化'],
    structure: ['data structures', 'dsu', '并查集', 'segment_tree', '线段树'],
    math: [
      'math',
      '数学',
      'combinatorics',
      'number theory',
      'probabilities',
      'games',
      'matrices',
      'fft',
      'chinese remainder theorem',
    ],
    string: ['strings', 'string suffix structures', 'hashing', 'KMP', '后缀数组'],
    geometry: ['geometry', '计算几何', 'convex_hull', '凸包'],
    other: ['interactive', '*special', 'unknown new tag'],
  };
  for (const [category, labels] of Object.entries(cases))
    for (const label of labels) assert.equal(algorithmCategory(label).category, category, label);
  assert.deepEqual(algorithmCategory(' MATH '), algorithmCategory({ id: 'math', name_zh: '数学' }));
  assert.equal(algorithmCategory({ name_zh: '新算法', category: '图论与树' }).category, 'graph');
});

test('normalization accepts existing formats, removes empty/duplicate entries and keeps filter keys', () => {
  const tag = { id: 'linear_dp', name_zh: '线性DP', source: 'manual_add' };
  const input = [null, '', '  math ', 'math', tag, { ...tag }, 'new very long label'];
  const copy = structuredClone(input);
  const result = normalizeTags(input);
  assert.deepEqual(
    result.map((row) => row.key),
    ['math', 'linear_dp', 'new very long label'],
  );
  assert.equal(result[1].label, '线性DP');
  assert.equal(result[1].raw, tag);
  assert.deepEqual(input, copy, 'presentation must not mutate source data');
  assert.deepEqual(
    normalizeTags('math, dp，greedy、math').map((row) => row.label),
    ['math', 'dp', 'greedy'],
  );
  assert.deepEqual(
    normalizeTags('["math", "dp", "math"]').map((row) => row.label),
    ['math', 'dp'],
  );
});

async function render(Component, props, slots) {
  const App = { render: () => h(Component, props, slots) };
  return mount(App, [{ path: '/', component: App }], '/');
}
test('difficulty component preserves Luogu native names and colours', async () => {
  const mounted = await render(Difficulty, {
    problem: {
      platform: 'luogu',
      native_difficulty: { id: 3, name: '普及', color: 'orange-3' },
    },
  });
  try {
    assert.match(textOf(mounted.root), /普及/);
    assert.equal(
      find(mounted.root, (node) => node.props['data-rating-system'] === 'codeforces').length,
      0,
    );
    assert.ok(find(mounted.root, (node) => node.props.class?.includes('luogu-difficulty')).length);
  } finally {
    mounted.unmount();
  }
});

test('legacy Luogu grades stay readable without inventing a native taxonomy ID', async () => {
  for (const native_difficulty of [undefined, {}, { id: null, name: '' }]) {
    const display = presentation('普及/提高-', 'luogu', { native_difficulty });
    assert.equal(display.tone, 'neutral');
    assert.equal(display.label, '难度 普及/提高-');
    assert.equal(display.system, 'luogu_legacy');
    assert.match(display.title, /历史记录原始难度/);
  }
  for (const raw of [null, '', 3, '3', '-1', '1e3', '0xFF', true, {}, 'NaN', 'Infinity'])
    assert.equal(presentation(raw, 'luogu').system, 'luogu', String(raw));
  assert.equal(
    presentation('入门', 'luogu', {
      native_difficulty: { id: 0, name: '暂无评定' },
    }).system,
    'luogu',
    'native level zero remains authoritative',
  );
  const mounted = await render(Difficulty, {
    problem: { platform: 'luogu', problem_rating: '普及-' },
  });
  try {
    assert.equal(textOf(mounted.root), '难度 普及-');
    const badge = find(
      mounted.root,
      (node) => node.props['data-rating-system'] === 'luogu_legacy',
    )[0];
    assert.ok(badge.props.class.includes('problem-tone-neutral'));
    assert.equal(
      find(mounted.root, (node) => node.props.class?.includes('luogu-difficulty')).length,
      0,
    );
  } finally {
    mounted.unmount();
  }
});

test('tag components keep plain labels noninteractive and preserve deliberate button behaviour', async () => {
  const plain = await render(Tags, { tags: ['math', 'math', '', 'a'.repeat(200)] });
  try {
    assert.equal(find(plain.root, (node) => node.type === 'button').length, 0);
    assert.equal(find(plain.root, (node) => node.props.class?.includes('algorithm-tag')).length, 2);
    assert.match(textOf(plain.root), /math/);
  } finally {
    plain.unmount();
  }
  const empty = await render(Tags, { tags: [] });
  try {
    assert.equal(textOf(empty.root), '无标签');
  } finally {
    empty.unmount();
  }
  let selected = false;
  const button = await render(
    Tag,
    {
      as: 'button',
      tag: { id: 'math', name_zh: '数学' },
      title: '数学 · 点击筛选',
      'data-tag-id': 'math',
      onClick: () => {
        selected = true;
      },
    },
    { default: () => ['数学', h('small', '人工')] },
  );
  try {
    const target = find(button.root, (node) => node.type === 'button')[0];
    assert.equal(target.props.title, '数学 · 点击筛选');
    assert.equal(target.props['data-tag-id'], 'math');
    assert.equal(target.props.type, 'button');
    assert.equal(textOf(target), '数学人工');
    target.props.onClick();
    assert.equal(selected, true);
  } finally {
    button.unmount();
  }
});

test('light and dark semantic badge palettes retain readable text on their bounded surfaces', async () => {
  const css = await readFile(new URL('../src/problem-presentation.css', import.meta.url), 'utf8');
  const blocks = [...css.matchAll(/(:root|\[data-theme='dark'\])\s*\{([^}]+)\}/g)];
  const rgb = (color) => [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16));
  const lum = (channels) =>
    channels
      .map((value) => {
        const c = value / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      })
      .reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
  assert.equal(blocks.length, 2);
  for (const [mode, body] of blocks.map((match) => [match[1], match[2]])) {
    const surface = rgb(mode === ':root' ? '#fffefa' : '#192526');
    for (const [, tone, color] of body.matchAll(/--problem-color-([\w]+):\s*(#[0-9a-f]{6})/g)) {
      const foreground = rgb(color),
        background = surface.map((c, i) => c * 0.93 + foreground[i] * 0.07);
      const l1 = lum(foreground),
        l2 = lum(background);
      const contrast = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      assert.ok(contrast >= 4.5, `${mode} ${tone}: ${contrast.toFixed(2)}`);
    }
  }
});
