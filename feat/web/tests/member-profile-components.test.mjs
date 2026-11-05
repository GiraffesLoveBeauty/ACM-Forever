import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Members = (await import(await loadSfc('src/admin/Members.vue'))).default;
const View = { render: () => h(RouterView) };
const globals = [
  'window',
  'document',
  'Document',
  'Node',
  'ShadowRoot',
  'location',
  'localStorage',
  'fetch',
  'confirm',
];
const originals = new Map(
  globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const scope = 'a'.repeat(64);
let dom,
  mounted,
  calls,
  users,
  saveFailure,
  confirming = true;
function user(qq, name) {
  return {
    qq_id: qq,
    name,
    real_name: '',
    school: '学校甲',
    status: '现役',
    role: null,
    is_active: null,
    account_state: 'active',
    account_epoch: 1,
    profile_revision: 'b'.repeat(64),
    binding_versions: { codeforces: 1, atcoder: 1, luogu: 1, nowcoder: 1, cjlu: 1 },
    cf_handle: 'CF_' + qq,
    atcoder_handle: 'AC_' + qq,
    luogu_id: qq,
    nowcoder_id: qq,
  };
}
const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => {
  dom = new JSDOM('', { url: 'https://acm.test/admin.html?section=members' });
  for (const key of globals.filter((key) => !['fetch', 'confirm'].includes(key)))
    Object.defineProperty(globalThis, key, {
      configurable: true,
      writable: true,
      value: dom.window[key],
    });
  globalThis.confirm = () => confirming;
  confirming = true;
  mounted = null;
  calls = [];
  saveFailure = false;
  users = [user('20000001', '昵称甲'), user('20000002', '昵称乙')];
  setAuth(
    {
      authenticated: true,
      role: 'admin',
      qq_id: '10000001',
      account_epoch: 1,
      csrf_token: 'synthetic',
    },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    const method = options.method || 'GET',
      body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url, method, body });
    const path = new URL(url, 'https://acm.test').pathname;
    if (path === '/api/admin/members/options')
      return response({
        schools: ['学校甲', '学校乙'],
        statuses: ['现役', '外校身份'],
        draft_scope: scope,
      });
    if (/^\/api\/admin\/members\/\d+$/.test(path)) {
      const current = users.find((row) => row.qq_id === path.split('/').at(-1));
      if (method === 'PATCH') {
        if (saveFailure)
          return response(
            { message: 'synthetic failure', field_errors: { name: '不能保存' } },
            400,
          );
        for (const key of Object.keys(current))
          if (Object.hasOwn(body, key) && !['profile_revision'].includes(key))
            current[key] = body[key];
        current.profile_revision = 'c'.repeat(64);
        return response({ success: true, member: current });
      }
      return response(current);
    }
    if (path === '/api/admin/members')
      return response({ items: users, total: 2, page: 1, page_size: 20 });
    throw Error('Unexpected API ' + url);
  };
});
afterEach(() => {
  mounted?.unmount();
  dom.window.close();
  for (const [key, descriptor] of originals)
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
});
after(cleanupCompiled);
async function open() {
  mounted = await mount(
    View,
    [{ path: '/admin.html', component: Members }],
    '/admin.html?section=members',
  );
}
function nodes(type) {
  return find(mounted.root, (node) => node.type === type);
}
async function click(label) {
  const button = nodes('button').find((node) => textOf(node).trim() === label);
  assert.ok(button, label);
  await button.props.onClick({ preventDefault() {} });
  await settle();
}
async function edit(qq, label, value) {
  const input = nodes('input').find((node) => node.props['aria-label'] === `${qq} ${label}`);
  assert.ok(input, `${qq} ${label}`);
  input.props.onInput({ target: { value } });
  await settle();
}
function stored() {
  return Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
    .filter((key) => key.startsWith('acm-member-profile:'))
    .map((key) => JSON.parse(localStorage.getItem(key)));
}

test('list shows real name absence and all four OJ accounts with a read-only role', async () => {
  await open();
  const text = textOf(mounted.root);
  for (const value of [
    '真实姓名',
    'Codeforces',
    'AtCoder',
    '洛谷 UID',
    '牛客 UID',
    'CF_20000001',
    'AC_20000001',
    '未开通',
  ])
    assert.ok(text.includes(value), value);
  assert.equal(
    calls.some((call) => call.method === 'PATCH'),
    false,
  );
});
test('typing writes a draft immediately, reverting a field cancels its pending change', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '真实姓名', '本地姓名');
  assert.equal(stored()[0].changes.real_name, '本地姓名');
  assert.equal(
    calls.some((call) => call.method === 'PATCH'),
    false,
  );
  await edit('20000001', '真实姓名', '');
  assert.equal(stored().length, 0);
});
test('exit editing returns to server values while keeping the recoverable draft', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '昵称', '只在草稿');
  await click('退出编辑，保留草稿');
  assert.ok(textOf(mounted.root).includes('昵称甲'));
  assert.equal(stored()[0].changes.name, '只在草稿');
  assert.equal(textOf(mounted.root).includes('只在草稿'), false);
});
test('remount offers explicit recovery and never auto-submits persisted input', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '昵称', '恢复昵称');
  mounted.unmount();
  await open();
  assert.ok(textOf(mounted.root).includes('发现 1 条本地草稿'));
  assert.equal(
    nodes('input').some((node) => node.props['aria-label']),
    false,
  );
  await click('恢复草稿');
  assert.ok(
    nodes('input').some(
      (node) => node.props['aria-label'] === '20000001 昵称' && node.props.value === '恢复昵称',
    ),
  );
  assert.equal(
    calls.some((call) => call.method === 'PATCH'),
    false,
  );
});
test('saving only changed rows clears successful versions and uses PATCH', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '真实姓名', '保存姓名');
  await click('保存全部（1）');
  const writes = calls.filter((call) => call.method === 'PATCH');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].url, '/api/admin/members/20000001');
  assert.equal(writes[0].body.real_name, '保存姓名');
  assert.equal('cjlu_username' in writes[0].body, false);
  assert.equal(stored().length, 0);
});
test('failed save retains draft and attaches backend field errors', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '昵称', '失败昵称');
  saveFailure = true;
  await click('保存全部（1）');
  assert.equal(stored()[0].changes.name, '失败昵称');
  assert.ok(textOf(mounted.root).includes('不能保存'));
});
test('cancelled OJ confirmation sends no requests and preserves input', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', 'Codeforces', 'NewCF');
  confirming = false;
  await click('保存全部（1）');
  assert.equal(calls.filter((call) => call.method === 'PATCH').length, 0);
  assert.equal(stored()[0].changes.cf_handle, 'NewCF');
});
test('identity drawer has complete candidates and creates a pending status without submitting', async () => {
  await open();
  await click('进入编辑模式');
  const button = nodes('button').find((node) => node.props['aria-label'] === '20000001 身份');
  await button.props.onClick();
  await settle();
  assert.ok(textOf(mounted.root).includes('外校身份'));
  await click('＋ 新建身份');
  const input = nodes('input').find((node) => Object.hasOwn(node.props, 'data-new-status'));
  input.props['onUpdate:modelValue']('新集训身份');
  input.props.onInput();
  await settle();
  assert.equal(stored()[0].drawer.text, '新集训身份');
  assert.equal(stored()[0].changes.status, undefined);
  const form = nodes('form').at(-1);
  await form.props.onSubmit({ preventDefault() {} });
  await settle();
  assert.equal(stored()[0].changes.status, '新集训身份');
  assert.equal(
    calls.some((call) => call.method === 'PATCH'),
    false,
  );
});
test('switching administrator clears the old memory and hides its draft candidates', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '昵称', '原管理员草稿');
  setAuth({ authenticated: true, role: 'admin', qq_id: '10000002', account_epoch: 1 }, true);
  await settle();
  assert.equal(textOf(mounted.root).includes('原管理员草稿'), false);
  assert.equal(
    nodes('input').some((node) => node.props.value === '原管理员草稿'),
    false,
  );
});

test('saving other fields preserves unconfirmed identity input, and unmount never recreates successful drafts', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '真实姓名', '已保存姓名');
  const button = nodes('button').find((node) => node.props['aria-label'] === '20000001 身份');
  await button.props.onClick();
  await settle();
  await click('＋ 新建身份');
  const control = nodes('input').find((node) => Object.hasOwn(node.props, 'data-new-status'));
  control.props['onUpdate:modelValue']('未确认输入');
  control.props.onInput();
  await settle();
  const close = nodes('button').find((node) => node.props['aria-label'] === '关闭身份选择器');
  await close.props.onClick();
  await settle();
  await click('保存全部（1）');
  assert.equal(stored().length, 1);
  assert.equal(stored()[0].drawer.text, '未确认输入');
  assert.deepEqual(stored()[0].changes, {});
  mounted.unmount();
  mounted = null;
  assert.equal(stored()[0].drawer.text, '未确认输入');
});

test('partial failure removes only the successful member draft', async () => {
  await open();
  await click('进入编辑模式');
  await edit('20000001', '昵称', '成功昵称');
  await edit('20000002', '昵称', '失败昵称');
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) =>
    options.method === 'PATCH' && url.endsWith('20000002')
      ? response({ message: 'synthetic failure' }, 400)
      : originalFetch(url, options);
  await click('保存全部（2）');
  assert.equal(stored().length, 1);
  assert.equal(stored()[0].qq_id, '20000002');
  mounted.unmount();
  mounted = null;
  assert.equal(stored().length, 1);
});
