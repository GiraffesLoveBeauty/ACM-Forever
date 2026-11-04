import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { api, setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Import = (await import(await loadSfc('src/admin/AccountImport.vue'))).default;
const Preview = (
  await import(await loadSfc('src/components/account-import/ImportPreviewTable.vue'))
).default;
const Results = (await import(await loadSfc('src/components/account-import/ImportResults.vue')))
  .default;
const Root = { render: () => h(RouterView) };
const id = 'synthetic-batch-abcdefghijklmnopqr';
const row = (i) => ({
  row_id: `row-${i}`,
  excel_row_number: i + 2,
  qq_id: String(10000084 + i),
  name: '合成成员' + i,
  action: 'create_member_and_account',
  status: 'ready',
  can_submit: true,
  errors: [],
  warnings: [],
  ignored_fields: [],
  bindings: {},
});
const credential = {
  row_id: 'row-0',
  qq_id: '10000084',
  name: '合成成员',
  temporary_password: 'Synthetic-secret!84',
  expires_at: 1900000000,
};
const batch = (extra = {}) => ({
  id,
  preview_version: 1,
  status: 'preview_ready',
  expires_at: 1900000000,
  summary: { total: 1, created: 0, conflict: 0, invalid: 0, skipped: 0, remaining: 0 },
  temporary_password_ttl_hours: 72,
  ...extra,
});
const json = (data, status = 200) => new Response(JSON.stringify(data), { status });
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
  'confirm',
];
const original = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let dom,
  mounted,
  calls,
  serverBatch,
  serverRows,
  serverEnabled,
  saveSettings,
  commit,
  guard,
  releases;
beforeEach(() => {
  dom = new JSDOM('<!doctype html><body></body>', {
    url: 'http://127.0.0.1/admin.html?section=accounts&tab=import',
  });
  for (const key of keys.filter((k) => !['fetch', 'confirm'].includes(k)))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      writable: true,
      configurable: true,
    });
  globalThis.confirm = () => true;
  mounted = null;
  calls = [];
  serverBatch = batch();
  serverRows = [row(0)];
  serverEnabled = true;
  saveSettings = async (options) => {
    serverEnabled = JSON.parse(options.body).enabled;
    return json({ enabled: serverEnabled });
  };
  guard = null;
  releases = [];
  setAuth(
    { authenticated: true, role: 'admin', qq_id: '10000001', csrf_token: 'synthetic-csrf' },
    true,
  );
  commit = async () => {
    serverBatch = batch({
      status: 'completed',
      summary: { total: 1, created: 1, conflict: 0, invalid: 0, skipped: 0, remaining: 0 },
    });
    serverRows = [{ ...row(0), status: 'created', can_submit: false, selected: true }];
    return { ...serverBatch, credentials: [credential] };
  };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith('/capabilities'))
      return json({ enabled: serverEnabled, max_rows: 200, max_file_bytes: 5 * 1024 * 1024 });
    if (url.endsWith('/settings')) return saveSettings(options);
    if (url.endsWith('/commit')) return json(await commit(options));
    if (url.includes('/rows?')) return json({ items: serverRows, total: serverRows.length });
    if (url.endsWith('/' + id)) return json(serverBatch);
    if (url.endsWith('/template'))
      return new Response('workbook', {
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
      });
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  releases.forEach((done) => done());
  await settle();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [key, value] of original)
    if (value) Object.defineProperty(globalThis, key, value);
    else delete globalThis[key];
});
after(cleanupCompiled);
async function open(
  Component = Import,
  path = '/admin.html?section=accounts&tab=import&import_id=' + id,
) {
  mounted = await mount(Root, [{ path: '/admin.html', component: Component }], path, {
    registerLeaveGuard: (handler) => {
      guard = handler;
      return () => {
        guard = null;
      };
    },
  });
  await settle();
  return mounted;
}
const buttons = (word) =>
  find(mounted.root, (n) => n.type === 'button' && textOf(n).includes(word));
const click = async (node) => {
  assert.ok(node);
  await node.props.onClick({ button: 0, preventDefault() {} });
  await settle();
};
async function selectPage() {
  await click(buttons('选中本页')[0]);
}

test('restoring a preview never automatically creates an account', async () => {
  await open();
  assert.match(textOf(mounted.root), /Excel 批量开户/);
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 0);
  assert.equal(buttons('确认创建所选账号')[0].props.disabled, true);
});
test('selection and explicit confirmation send only selected server row IDs', async () => {
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  const body = JSON.parse(calls.find((c) => c.url.endsWith('/commit')).options.body);
  assert.deepEqual(body.selected_row_ids, ['row-0']);
  assert.equal(body.role, undefined);
  assert.match(textOf(mounted.root), /本页已领取 1 份/);
  assert.ok(guard());
});
test('a received credential is guarded on leave and cleared on unmount', async () => {
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  globalThis.confirm = () => false;
  assert.equal(guard(), false);
  mounted.unmount();
  mounted = null;
  await open();
  assert.doesNotMatch(textOf(mounted.root), /本页已领取/);
  assert.match(textOf(mounted.root), /本页未领取其初始密码/);
});
test('unknown commit result queries progress and never automatically retries', async () => {
  commit = async () => {
    serverBatch = batch({
      status: 'completed',
      summary: { total: 1, created: 1, conflict: 0, invalid: 0, skipped: 0, remaining: 0 },
    });
    throw Error('synthetic network loss');
  };
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 1);
  assert.match(textOf(mounted.root), /本次请求结果尚未确认/);
});
test('a restored paused batch needs an explicit continue action', async () => {
  serverBatch = batch({
    status: 'paused',
    selection_digest: 'frozen',
    next_chunk_token: 'next',
    summary: { total: 1, created: 0, remaining: 1 },
  });
  serverRows = [{ ...row(0), selected: true }];
  await open();
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 0);
  assert.equal(buttons('继续未处理成员').length, 1);
  await click(buttons('继续未处理成员')[0]);
  const body = JSON.parse(calls.find((c) => c.url.endsWith('/commit')).options.body);
  assert.equal(body.selection_digest, 'frozen');
  assert.equal(body.continuation_token, 'next');
  assert.equal(body.selected_row_ids, undefined);
});
test('interrupted chunks stop the automatic loop even with a continuation token', async () => {
  commit = async () => {
    serverBatch = batch({
      status: 'paused',
      selection_digest: 'frozen',
      next_chunk_token: 'next',
      summary: { total: 1, created: 0, remaining: 1 },
    });
    return { ...serverBatch, chunk_status: 'interrupted', credentials: [] };
  };
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 1);
  assert.match(textOf(mounted.root), /当前段已暂停/);
});
test('account/session changes clear all received credential content', async () => {
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  setAuth(
    { authenticated: true, role: 'admin', qq_id: '10000002', csrf_token: 'another-session' },
    true,
  );
  await settle();
  assert.doesNotMatch(textOf(mounted.root), /本页已领取/);
  assert.equal(
    find(mounted.root, (n) => n.props.value === credential.temporary_password).length,
    0,
  );
});
test('selecting a page does not silently include invisible rows', async () => {
  const rows = Array.from({ length: 22 }, (_, i) => row(i));
  let selected = [];
  const Component = {
    render: () =>
      h(Preview, {
        rows,
        selected: new Set(),
        onSelect: (ids) => {
          selected = ids;
        },
      }),
  };
  await open(Component, '/admin.html');
  await click(buttons('选中本页')[0]);
  assert.equal(selected.length, 20);
  assert.ok(!selected.includes('row-21'));
});
test('credentials remain text and failed clipboard copy has a manual fallback', async () => {
  Object.defineProperty(navigator, 'clipboard', {
    value: {
      writeText: async () => {
        throw Error('denied');
      },
    },
    configurable: true,
  });
  const Component = { render: () => h(Results, { credentials: [credential], missing: 1 }) };
  await open(Component, '/admin.html');
  await click(buttons('复制已领取凭据')[0]);
  const textarea = find(mounted.root, (n) => n.type === 'textarea')[0];
  assert.match(textarea.props.value, /Synthetic-secret!84/);
  assert.equal(find(mounted.root, (n) => n.type === 'input')[0].props.type, 'password');
});
test('blob downloads use the same API session and CSRF handling', async () => {
  const data = await api('/admin/account-imports/template', { responseType: 'blob' });
  assert.ok(data instanceof Blob);
  assert.equal(await data.text(), 'workbook');
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'synthetic-csrf');
});

test('an earlier batch response cannot restore credentials after the recovery URL changes', async () => {
  let release;
  const held = new Promise((done) => {
    release = done;
  });
  releases.push(release);
  commit = async () => {
    await held;
    return { ...batch({ status: 'completed' }), credentials: [credential] };
  };
  await open();
  await selectPage();
  const action = buttons('确认创建所选账号')[0].props.onClick({ button: 0, preventDefault() {} });
  await settle();
  await mounted.router.push('/admin.html?section=accounts&tab=import');
  await settle();
  release();
  await action;
  await settle();
  assert.doesNotMatch(textOf(mounted.root), /本页已领取/);
  assert.equal(
    find(mounted.root, (n) => n.props.value === credential.temporary_password).length,
    0,
  );
  assert.equal(mounted.router.currentRoute.value.query.import_id, undefined);
});

const importSwitch = () => find(mounted.root, (n) => n.props.role === 'switch')[0];
const settingsCalls = () => calls.filter((c) => c.url.endsWith('/settings'));

test('disabled imports keep a visible switch that enables upload without creating accounts', async () => {
  serverEnabled = false;
  await open(Import, '/admin.html?section=accounts&tab=import');
  assert.equal(importSwitch().props['aria-checked'], false);
  assert.equal(find(mounted.root, (n) => n.type === 'input' && n.props.type === 'file').length, 0);
  await click(importSwitch());
  assert.equal(importSwitch().props['aria-checked'], true);
  assert.equal(find(mounted.root, (n) => n.type === 'input' && n.props.type === 'file').length, 1);
  assert.equal(settingsCalls()[0].options.method, 'PATCH');
  assert.deepEqual(JSON.parse(settingsCalls()[0].options.body), { enabled: true });
  assert.equal(settingsCalls()[0].options.headers['X-CSRF-Token'], 'synthetic-csrf');
  assert.equal(calls.filter((c) => /\/(preview|commit)$/.test(c.url)).length, 0);
});

test('confirmed closing survives remount and can be reopened without auto-submitting a preview', async () => {
  await open();
  await selectPage();
  await click(importSwitch());
  assert.equal(importSwitch().props['aria-checked'], false);
  assert.equal(buttons('确认创建所选账号')[0].props.disabled, true);
  assert.match(textOf(mounted.root), /已有批次仍可查询结果/);
  assert.deepEqual(JSON.parse(settingsCalls()[0].options.body), { enabled: false });
  mounted.unmount();
  await open();
  assert.equal(importSwitch().props['aria-checked'], false);
  await click(importSwitch());
  assert.equal(importSwitch().props['aria-checked'], true);
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 0);
});

test('cancelling closure keeps the confirmed switch and sends no write', async () => {
  globalThis.confirm = () => false;
  await open();
  await click(importSwitch());
  assert.equal(importSwitch().props['aria-checked'], true);
  assert.equal(settingsCalls().length, 0);
});

test('failed setting save keeps the old state and allows an explicit retry', async () => {
  saveSettings = async () => json({ message: '设置保存失败，请重试。' }, 503);
  await open();
  await click(importSwitch());
  assert.equal(importSwitch().props['aria-checked'], true);
  assert.equal(importSwitch().props.disabled, false);
  assert.match(textOf(mounted.root), /设置保存失败/);
  assert.equal(settingsCalls().length, 1);
});

test('saving locks the switch and upload actions and ignores double clicks', async () => {
  let release;
  const held = new Promise((done) => {
    release = done;
  });
  releases.push(release);
  saveSettings = async () => {
    await held;
    return json({ enabled: false });
  };
  await open();
  const saving = importSwitch().props.onClick({ button: 0, preventDefault() {} });
  await settle();
  assert.equal(importSwitch().props.disabled, true);
  assert.equal(buttons('下载 Excel 模板')[0].props.disabled, true);
  assert.match(textOf(importSwitch()), /正在保存/);
  await click(importSwitch());
  assert.equal(settingsCalls().length, 1);
  release();
  await saving;
  await settle();
  assert.equal(importSwitch().props['aria-checked'], false);
});

test('an active creation locks the global switch until its result is known', async () => {
  let release;
  const held = new Promise((done) => {
    release = done;
  });
  releases.push(release);
  commit = async () => {
    await held;
    return batch({ status: 'completed' });
  };
  await open();
  await selectPage();
  const creating = buttons('确认创建所选账号')[0].props.onClick({ button: 0, preventDefault() {} });
  await settle();
  assert.equal(importSwitch().props.disabled, true);
  await click(importSwitch());
  assert.equal(settingsCalls().length, 0);
  release();
  await creating;
});

test('a late switch save cannot restore controls after logout', async () => {
  let release;
  const held = new Promise((done) => {
    release = done;
  });
  releases.push(release);
  saveSettings = async () => {
    await held;
    return json({ enabled: false });
  };
  await open();
  const saving = importSwitch().props.onClick({ button: 0, preventDefault() {} });
  await settle();
  setAuth({ authenticated: false }, true);
  await settle();
  release();
  await saving;
  await settle();
  assert.equal(importSwitch(), undefined);
});

test('another administrator closing imports is reflected after a rejected commit without retrying', async () => {
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/commit')) {
      calls.push({ url, options });
      return json({ code: 'import_disabled', message: 'Excel 导入已关闭。' }, 503);
    }
    return fetch(url, options);
  };
  await open();
  await selectPage();
  await click(buttons('确认创建所选账号')[0]);
  assert.equal(importSwitch().props['aria-checked'], false);
  assert.equal(buttons('确认创建所选账号')[0].props.disabled, true);
  assert.match(textOf(mounted.root), /Excel 导入已关闭/);
  assert.doesNotMatch(textOf(mounted.root), /本次请求结果尚未确认/);
  assert.equal(calls.filter((c) => c.url.endsWith('/commit')).length, 1);
});
