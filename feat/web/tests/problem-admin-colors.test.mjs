import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { JSDOM } from 'jsdom';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Editor = (await import(await loadSfc('src/views/TagManagement.vue'))).default;
const View = {
  render: () => h(Editor, { embedded: true, platform: 'codeforces', problemId: 'cf_100A' }),
};
const Root = { render: () => h(RouterView) };
const keys = ['window', 'document', 'Document', 'Node', 'ShadowRoot', 'fetch', 'location'];
const originals = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const dp = { id: 'dp', name_zh: '动态规划', tag_kind: 'specific', source: 'cf_rule_mapping' };
const greedy = { id: 'greedy', name_zh: '贪心', tag_kind: 'specific', source: 'manual_add' };
let dom, view, writes, effective;
const detail = () => ({
  revision: 'synthetic-version',
  effective_tags: effective,
  auto_tags: { tags: [dp] },
  review_status: 'auto',
  needs_review_reasons: [],
  history: [],
  manual_overrides: { added_tag_ids: [], removed_tag_ids: [] },
  fully_human_verified: false,
});
const response = (data) => new Response(JSON.stringify(data));

beforeEach(() => {
  dom = new JSDOM('<!doctype html><body></body>', { url: 'http://127.0.0.1/admin.html' });
  for (const key of keys.filter((key) => !['fetch', 'location'].includes(key)))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      configurable: true,
      writable: true,
    });
  globalThis.location = { pathname: '/admin.html', search: '', assign() {} };
  setAuth({ authenticated: true, qq_id: '10000002', role: 'admin', csrf_token: 'fixture' }, true);
  writes = [];
  effective = [dp];
  view = null;
  globalThis.fetch = async (url, options = {}) => {
    if (url === '/api/secondary/tag-management')
      return response({
        taxonomy: [dp, greedy],
        items: [
          {
            platform: 'codeforces',
            problem_id: 'cf_100A',
            problem_key: 'codeforces:cf_100A',
            title: '合成题目',
            effective_tags: effective,
            review_status: 'auto',
          },
        ],
      });
    if (url === '/api/secondary/tag-management/codeforces/cf_100A') {
      if (options.method === 'POST') {
        const body = JSON.parse(options.body);
        writes.push(body);
        effective = body.tag_ids.map((id) => ({
          ...[dp, greedy].find((tag) => tag.id === id),
          source: 'manual_add',
        }));
        return response({ detail: detail(), message: '已保存合成标签' });
      }
      return response(detail());
    }
    throw Error('Unexpected request ' + url);
  };
});
afterEach(() => {
  view?.unmount();
  dom.window.close();
  setAuth({ authenticated: false }, true);
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});
after(cleanupCompiled);

test('colored algorithm buttons retain source hints, selection IDs, and guarded save behavior', async () => {
  view = await mount(
    Root,
    [
      { path: '/admin.html', component: View },
      { path: '/problem.html', component: { render: () => null } },
    ],
    '/admin.html',
  );
  const selected = find(
    view.root,
    (node) => node.type === 'button' && node.props['aria-label'] === '移除动态规划',
  )[0];
  assert.equal(selected.props['data-tag-category'], 'dp');
  assert.match(textOf(selected), /CF 映射/);
  assert.equal(writes.length, 0);
  await selected.props.onClick();
  await settle();
  const add = find(view.root, (node) => node.type === 'button' && node.props.title === 'greedy')[0];
  assert.equal(add.props['data-tag-category'], 'strategy');
  assert.equal(add.props['aria-pressed'], false);
  await add.props.onClick();
  await settle();
  assert.equal(
    find(view.root, (node) => node.type === 'button' && node.props.title === 'greedy')[0].props[
      'aria-pressed'
    ],
    true,
  );
  const save = () => find(view.root, (node) => node.props['data-testid'] === 'save-tags')[0];
  assert.equal(save().props.disabled, true);
  find(view.root, (node) => node.type === 'textarea' && node.props.id === 'edit-reason')[0].props[
    'onUpdate:modelValue'
  ]('依据合成题面修正');
  await settle();
  assert.equal(save().props.disabled, false);
  await save().props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].tag_ids, ['greedy']);
  assert.equal(writes[0].operation, 'save');
  assert.equal(writes[0].reason, '依据合成题面修正');
  assert.match(textOf(view.root), /已保存合成标签/);
  assert.match(
    textOf(
      find(
        view.root,
        (node) => node.type === 'button' && node.props['aria-label'] === '移除贪心',
      )[0],
    ),
    /人工添加/,
  );
});
