import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h, ref } from 'vue';
import { luoguTagCategories, searchLuoguTags } from '../src/lib/luogu-tags.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Picker = (await import(await loadSfc('src/components/LuoguTagPicker.vue'))).default;
const keys = ['document', 'Document', 'Node', 'ShadowRoot'];
const originals = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const dom = new JSDOM('<!doctype html><body></body>');
let mounted, value, changes, retryCount;
const taxonomy = {
  tag_types: [
    { id: 1, name: '区域', order: 4 },
    { id: 2, name: '算法', order: 1 },
    { id: 3, name: '来源', order: 2 },
    { id: 4, name: '时间', order: 3 },
    { id: 5, name: '特殊题目', order: 5 },
  ],
  tags: [
    { id: -2, name: '语言入门', type: 2, parent: null },
    { id: 353, name: '顺序结构', type: 2, parent: -2 },
    { id: 2, name: '字符串', type: 2, parent: null },
    { id: 37, name: '字典树 Trie', type: 2, parent: 2 },
    { id: 38, name: 'AC 自动机', type: 2, parent: 37 },
    { id: 100, name: '浙江', type: 1, parent: null },
    { id: 200, name: 'CSP-J', type: 3, parent: null },
    { id: 300, name: '2026', type: 4, parent: null },
    { id: 400, name: '交互题', type: 5, parent: null },
  ],
};
const hasClass = (node, name) =>
  String(node.props.class || '')
    .split(' ')
    .includes(name);
const button = (name) =>
  find(mounted.root, (node) => node.type === 'button' && textOf(node).trim() === name)[0];
const tag = (name) =>
  find(
    mounted.root,
    (node) =>
      node.type === 'button' &&
      Object.hasOwn(node.props, 'aria-pressed') &&
      node.props['aria-label'] === name,
  )[0];
const dialogs = () => find(mounted.root, (node) => node.type === 'dialog');
async function open() {
  await find(
    mounted.root,
    (node) => node.type === 'button' && hasClass(node, 'luogu-picker-trigger'),
  )[0].props.onClick();
  await settle();
}
async function render(initial = [], data = taxonomy, extra = {}) {
  value = ref(initial);
  changes = [];
  retryCount = 0;
  const App = {
    render: () =>
      h(Picker, {
        modelValue: value.value,
        taxonomy: data,
        ...extra,
        'onUpdate:modelValue': (next) => {
          value.value = next;
          changes.push(next);
        },
        onRetry: () => retryCount++,
      }),
  };
  mounted = await mount(App, [{ path: '/:pathMatch(.*)*', component: { render: () => null } }]);
}
beforeEach(() => {
  for (const key of keys)
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  document.body.style.overflow = 'scroll';
});
afterEach(() => {
  mounted?.unmount();
  mounted = null;
});
after(async () => {
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
  dom.window.close();
  await cleanupCompiled();
});

test('native type order and parent chains produce complete algorithm groups', () => {
  const categories = luoguTagCategories(taxonomy);
  assert.deepEqual(
    categories.map((item) => item.name),
    ['算法', '来源', '时间', '区域', '特殊题目'],
  );
  assert.deepEqual(
    categories[0].groups.map((group) => group.items.map((item) => item.id)),
    [
      ['-2', '353'],
      ['2', '37', '38'],
    ],
  );
  assert.deepEqual(
    searchLuoguTags(categories, ' TRIE ')[0].groups[0].items.map((item) => item.id),
    ['37'],
  );
  assert.equal(searchLuoguTags(categories, 'CSP-J')[0].name, '来源');
  assert.equal(searchLuoguTags(categories, '字符串')[0].groups[0].items.length, 3);
  assert.equal(searchLuoguTags(categories, '不存在').length, 0);
});
test('orphaned parents, unknown types and cycles cannot hide or duplicate tags', () => {
  const categories = luoguTagCategories({
    tags: [
      { id: 1, type: 2, name: 'A', parent: 2 },
      { id: 2, type: 2, name: 'B', parent: 1 },
      { id: 3, type: 2, name: 'C', parent: 99 },
      { id: 4, type: 5, name: 'D', parent: 3 },
    ],
  });
  const ids = categories.flatMap((item) =>
    item.groups.flatMap((group) => group.items.map((tag) => tag.id)),
  );
  assert.deepEqual([...ids].sort(), ['1', '2', '3', '4']);
});
test('selections are drafts until confirmation and cancellation preserves applied IDs', async () => {
  await render(['-2']);
  await open();
  assert.equal(document.body.style.overflow, 'hidden');
  tag('字符串').props.onClick();
  await settle();
  assert.deepEqual(value.value, ['-2']);
  assert.equal(changes.length, 0);
  button('取消').props.onClick();
  await settle();
  assert.equal(dialogs().length, 0);
  assert.equal(document.body.style.overflow, 'scroll');
  await open();
  assert.equal(tag('字符串').props['aria-pressed'], false);
  tag('字符串').props.onClick();
  await settle();
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ['-2', '2']);
  assert.deepEqual(changes, [['-2', '2']]);
  assert.equal(dialogs().length, 0);
});
test('search crosses categories, no-results is explicit and category arrows change tabs', async () => {
  await render();
  await open();
  const input = () =>
    find(mounted.root, (node) => node.type === 'input' && node.props.type === 'search')[0];
  input().props['onUpdate:modelValue']('CSP');
  await settle();
  assert.ok(tag('CSP-J'));
  assert.match(textOf(mounted.root), /全部分类中找到 1 个标签/);
  tag('CSP-J').props.onClick();
  await settle();
  input().props['onUpdate:modelValue']('没有这个标签');
  await settle();
  assert.match(textOf(mounted.root), /没有找到匹配的标签/);
  button('算法').props.onClick();
  await settle();
  assert.ok(tag('字符串'));
  let prevented = false;
  button('算法').props.onKeydown({
    key: 'ArrowRight',
    preventDefault: () => {
      prevented = true;
    },
  });
  await settle();
  assert.equal(prevented, true);
  assert.equal(button('来源').props['aria-selected'], true);
  assert.ok(tag('CSP-J'));
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ['200']);
});
test('the twentieth tag blocks additional choices while removals remain available', async () => {
  const data = {
    tag_types: taxonomy.tag_types,
    tags: Array.from({ length: 22 }, (_, n) => ({
      id: n + 1,
      name: '算法 ' + (n + 1),
      type: 2,
      parent: null,
    })),
  };
  await render(
    Array.from({ length: 20 }, (_, n) => String(n + 1)),
    data,
  );
  await open();
  assert.equal(tag('算法 21').props.disabled, true);
  const remove = find(mounted.root, (node) => node.props['aria-label'] === '移除标签：算法 1')[0];
  remove.props.onClick();
  await settle();
  assert.equal(tag('算法 21').props.disabled, false);
  tag('算法 21').props.onClick();
  await settle();
  button('确认筛选').props.onClick();
  await settle();
  assert.equal(value.value.length, 20);
  assert.equal(value.value.includes('1'), false);
  assert.equal(value.value.includes('21'), true);
});
test('over-limit legacy selections remain intact until the user removes enough tags', async () => {
  const ids = Array.from({ length: 21 }, (_, n) => String(n + 1));
  await render(ids, {});
  await open();
  assert.equal(
    find(mounted.root, (node) => String(node.props['aria-label'] || '').startsWith('移除标签：'))
      .length,
    21,
  );
  assert.equal(button('确认筛选').props.disabled, true);
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ids);
  assert.equal(changes.length, 0);
  const remove = find(
    mounted.root,
    (node) => node.props['aria-label'] === '移除标签：标签 #21（名称待更新）',
  )[0];
  remove.props.onClick();
  await settle();
  assert.equal(button('确认筛选').props.disabled, false);
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ids.slice(0, 20));
});
test('unknown IDs survive an unavailable taxonomy and can be removed explicitly', async () => {
  await render(['-99'], {}, { error: '分类暂时无法加载' });
  await open();
  assert.match(textOf(mounted.root), /标签 #-99（名称待更新）/);
  button('重试分类').props.onClick();
  assert.equal(retryCount, 1);
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ['-99']);
  await open();
  button('清空已选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], ['-99']);
  button('确认筛选').props.onClick();
  await settle();
  assert.deepEqual([...value.value], []);
});
test('Escape, external filter changes and component exit discard drafts and unlock scrolling', async () => {
  await render(['-2']);
  await open();
  let prevented = false;
  dialogs()[0].props.onCancel({
    preventDefault: () => {
      prevented = true;
    },
  });
  await settle();
  assert.equal(prevented, true);
  assert.equal(dialogs().length, 0);
  assert.deepEqual([...value.value], ['-2']);
  await open();
  value.value = ['2'];
  await settle();
  assert.equal(dialogs().length, 0);
  assert.equal(document.body.style.overflow, 'scroll');
  await open();
  mounted.unmount();
  mounted = null;
  assert.equal(document.body.style.overflow, 'scroll');
});
