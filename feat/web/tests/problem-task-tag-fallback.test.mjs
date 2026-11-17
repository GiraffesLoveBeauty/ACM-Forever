import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { h } from 'vue';
import { cleanupCompiled, find, loadSfc, mount, textOf } from './helpers/vue-harness.mjs';

const TaskProblems = (await import(await loadSfc('src/components/TaskProblemList.vue'))).default;
after(cleanupCompiled);

const from = '/training-tasks.html?id=42';
const problem = (fields = {}) => ({
  platform: 'luogu',
  problem_id: 'P1001',
  problem_name: 'A+B Problem',
  problem_url: 'https://www.luogu.com.cn/problem/P1001',
  content_available: true,
  ...fields,
});
const includesClass = (node, name) =>
  String(node.props.class || '')
    .split(/\s+/)
    .includes(name);
const algorithmTags = (root) => find(root, (node) => includesClass(node, 'algorithm-tag'));
const nativeTags = (root) => find(root, (node) => includesClass(node, 'luogu-tag'));
async function render(fields) {
  const App = { render: () => h(TaskProblems, { problems: [problem(fields)], from }) };
  return mount(
    App,
    [
      { path: '/training-tasks.html', component: App },
      { path: '/problem.html', component: { render: () => null } },
    ],
    from,
  );
}
function assertNeutralLabels(root, labels) {
  const tags = algorithmTags(root);
  assert.deepEqual(tags.map(textOf), labels);
  for (const tag of tags) {
    assert(includesClass(tag, 'problem-tone-neutral'));
    assert.equal(tag.type, 'span', 'fallback labels do not introduce filter buttons');
    assert.equal(
      tag.props['data-tag-category'],
      undefined,
      'raw names do not guess native categories',
    );
    assert.match(tag.props.title, /原始标签.*未.*原生分类/);
  }
}

test('Luogu task API tags remain visible without native_tags and preserve both problem links', async () => {
  const mounted = await render({ tags: ['模拟', '数学'] });
  try {
    assertNeutralLabels(mounted.root, ['模拟', '数学']);
    const links = find(mounted.root, (node) => node.type === 'a');
    const local = links.find((node) => textOf(node) === '查看题目');
    const target = new URL(local.props.href, 'https://acm.invalid');
    assert.equal(target.pathname, '/problem.html');
    assert.equal(target.searchParams.get('platform'), 'luogu');
    assert.equal(target.searchParams.get('problem_id'), 'P1001');
    assert.equal(target.searchParams.get('from'), from);
    assert.equal(
      links.find((node) => textOf(node).includes('原题')).props.href,
      'https://www.luogu.com.cn/problem/P1001',
    );
  } finally {
    mounted.unmount();
  }
});

test('raw Luogu task tags use the existing normalization for legacy and JSON strings', async () => {
  for (const tags of ['模拟,数学', '["模拟", "数学", "模拟"]', ['模拟', '', '数学', '模拟']]) {
    const mounted = await render({ tags });
    try {
      assertNeutralLabels(mounted.root, ['模拟', '数学']);
    } finally {
      mounted.unmount();
    }
  }
});

test('an empty or unavailable native list does not suppress nonempty task tags', async () => {
  for (const native_tags of [[], null, undefined]) {
    const mounted = await render({ native_tags, tags: ['模拟', '数学'] });
    try {
      assertNeutralLabels(mounted.root, ['模拟', '数学']);
      assert.equal(nativeTags(mounted.root).length, 0);
    } finally {
      mounted.unmount();
    }
  }
});

test('actual Luogu native tags retain their own taxonomy instead of legacy names', async () => {
  const mounted = await render({
    tags: ['旧标签'],
    native_tags: [{ id: 1, name: '模拟', category: { name: '来源分类', color: 'blue-3' } }],
  });
  try {
    assert.equal(algorithmTags(mounted.root).length, 0);
    const tags = nativeTags(mounted.root);
    assert.equal(tags.length, 1);
    assert.equal(textOf(tags[0]), '模拟');
    assert.match(tags[0].props.title, /来源分类.*原生标签 ID 1/);
    assert(!textOf(mounted.root).includes('旧标签'));
  } finally {
    mounted.unmount();
  }
});

test('omitted task tags stay hidden without a misleading empty-tag placeholder', async () => {
  for (const tags of [undefined, null]) {
    const mounted = await render({ tags });
    try {
      assert.equal(algorithmTags(mounted.root).length, 0);
      assert.equal(nativeTags(mounted.root).length, 0);
      assert(!textOf(mounted.root).includes('无标签'));
      assert(!textOf(mounted.root).includes('暂无原生标签'));
    } finally {
      mounted.unmount();
    }
  }
});

test('CF task tags keep their classified colours', async () => {
  const mounted = await render({
    platform: 'codeforces',
    problem_id: 'cf_100A',
    problem_url: 'https://codeforces.com/contest/100/problem/A',
    tags: ['math', 'graphs'],
  });
  try {
    const tags = algorithmTags(mounted.root);
    assert.deepEqual(tags.map(textOf), ['math', 'graphs']);
    assert.deepEqual(
      tags.map((tag) => tag.props['data-tag-category']),
      ['math', 'graph'],
    );
    assert(includesClass(tags[0], 'problem-tone-yellow'));
    assert(includesClass(tags[1], 'problem-tone-blue'));
  } finally {
    mounted.unmount();
  }
});
