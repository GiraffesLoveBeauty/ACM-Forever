import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h, ref } from 'vue';
import { createDefaultTheme, presetProfile } from '../src/lib/theme-colors.js';
import {
  themeStorageKey,
  libraryStorageKey,
  templateTheme,
  normalizeTemplate,
} from '../src/lib/design-template.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Editor = (await import(await loadSfc('src/components/ThemeEditor.vue'))).default;
const Library = (await import(await loadSfc('src/components/TemplateLibrary.vue'))).default;
const keys = ['document', 'Document', 'Node', 'ShadowRoot', 'localStorage', 'matchMedia', 'prompt'];
const savedGlobals = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let dom, mounted, editor;
const accent = () => document.body.style.getPropertyValue('--accent');
const button = (label) =>
  find(mounted.root, (item) => item.type === 'button' && textOf(item) === label)[0];
async function click(label) {
  assert.ok(button(label), label);
  button(label).props.onClick();
  await settle();
}
function dialogStub() {
  const dialog = find(mounted.root, (item) => item.type === 'dialog')[0];
  dialog.close = () => {};
  dialog.showModal = () => {};
  dialog.querySelector = () => null;
}
async function mountEditor() {
  editor = ref();
  mounted = await mount({ render: () => h(Editor, { ref: editor }) }, [
    { path: '/index.html', component: { render: () => null } },
  ]);
  dialogStub();
}
beforeEach(() => {
  dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/' });
  for (const [key, value] of Object.entries({
    document: dom.window.document,
    Document: dom.window.Document,
    Node: dom.window.Node,
    ShadowRoot: dom.window.ShadowRoot,
    localStorage: dom.window.localStorage,
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    prompt: () => '测试方案',
  }))
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
});
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  dom.window.close();
  for (const key of keys) {
    const descriptor = savedGlobals.get(key);
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});
after(cleanupCompiled);

test('original storage/defaults stay compatible and unknown templates fall back', () => {
  assert.equal(themeStorageKey('original'), 'acm.theme.v1');
  assert.equal(libraryStorageKey('original'), 'acm.theme.library.v1');
  assert.deepEqual(templateTheme('original'), createDefaultTheme());
  assert.equal(normalizeTemplate('__proto__'), 'original');
  assert.equal(themeStorageKey('removed-template'), 'acm.theme.v1');
});

test('real editor isolates saved colors, dark modes and libraries across template switches', async () => {
  const original = createDefaultTheme();
  original.light = presetProfile('mint', 'light');
  localStorage.setItem('acm.theme.v1', JSON.stringify(original));
  await mountEditor();
  assert.equal(accent(), '#efcf63');
  editor.value.setTemplate('phase');
  await settle();
  assert.equal(accent(), '#d5f500');
  editor.value.open();
  await click('柔粉');
  await click('收藏方案');
  await click('保存主题');
  assert.equal(accent(), '#f0c4af');
  assert.ok(localStorage.getItem(libraryStorageKey('phase')));
  assert.equal(localStorage.getItem(libraryStorageKey('original')), null);
  editor.value.toggle();
  await settle();
  assert.equal(document.body.dataset.theme, 'dark');
  editor.value.setTemplate('original');
  await settle();
  assert.equal(accent(), '#efcf63');
  assert.equal(document.body.dataset.theme, 'light');
  assert.deepEqual(JSON.parse(localStorage.getItem('acm.theme.v1')), original);
  editor.value.open();
  assert.equal(button('测试方案'), undefined);
  await click('取消');
  editor.value.setTemplate('phase');
  await settle();
  assert.equal(document.body.dataset.theme, 'dark');
  editor.value.open();
  assert.ok(button('测试方案'));
  await click('取消');
});

test('cancel rolls back reset and page-only palette survives template switches without persistence', async () => {
  await mountEditor();
  editor.value.setTemplate('phase');
  await settle();
  editor.value.open();
  await click('柔粉');
  await click('保存主题');
  const persisted = localStorage.getItem(themeStorageKey('phase'));
  editor.value.open();
  await click('恢复此模板原配色');
  assert.equal(accent(), '#d5f500');
  await click('取消');
  assert.equal(accent(), '#f0c4af');
  editor.value.open();
  await click('清绿');
  await click('仅本页应用');
  editor.value.setTemplate('original');
  editor.value.setTemplate('phase');
  await settle();
  assert.equal(accent(), '#efcf63');
  assert.equal(localStorage.getItem(themeStorageKey('phase')), persisted);
  mounted.unmount();
  mounted = null;
  localStorage.setItem('acm.design-template.v1', 'phase');
  await mountEditor();
  assert.equal(accent(), '#f0c4af');
});

test('unavailable storage still allows template selection and fallback palettes', async () => {
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem() {
        throw Error('blocked');
      },
      setItem() {
        throw Error('blocked');
      },
    },
    configurable: true,
  });
  await mountEditor();
  editor.value.setTemplate('phase');
  await settle();
  assert.equal(accent(), '#d5f500');
  editor.value.toggle();
  await settle();
  assert.equal(document.body.dataset.theme, 'dark');
  editor.value.setTemplate('original');
  await settle();
  assert.equal(accent(), '#f1f547');
});

test('category browsing has no selection side effect and empty categories expose no fake templates', async () => {
  const selections = [];
  mounted = await mount(
    { render: () => h(Library, { current: 'original', onSelect: (id) => selections.push(id) }) },
    [{ path: '/index.html', component: { render: () => null } }],
  );
  dialogStub();
  const category = (id) =>
    find(mounted.root, (item) => item.type === 'button' && item.props['data-category'] === id)[0];
  category('genshin').props.onClick();
  await settle();
  assert.match(textOf(mounted.root), /此分类暂无模板/);
  assert.deepEqual(selections, []);
  category('arknights').props.onClick();
  await settle();
  const cards = find(
    mounted.root,
    (item) => item.type === 'button' && item.props['aria-label'] === '使用相变信号',
  );
  assert.equal(cards.length, 1);
  cards[0].props.onClick();
  assert.deepEqual(selections, ['phase']);
  assert.match(textOf(mounted.root), /制作与投稿说明/);
});
