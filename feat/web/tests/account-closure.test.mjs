import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { api, auth, setAuth, finishAccountClosure } from '../src/lib/api.js';
import { readClosure, rememberClosure } from '../src/lib/account-closure.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Closure = (await import(await loadSfc('src/views/AccountClosure.vue'))).default;
const memory = () => {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    data,
  };
};
const preview = {
  request_id: 'a'.repeat(32),
  receipt_token: 'b'.repeat(43),
  receipt_expires_at: Math.floor(Date.now() / 1000) + 3600,
  policy_version: 'closure-v2',
  account_epoch: 1,
  can_close: true,
  blockers: [],
  delete_counts: { submissions: 3 },
  retain_counts: { posts: 2 },
  retention_notice: { text: '即时生效且不可恢复；公共内容匿名保留。' },
};
const closed = { request_id: preview.request_id, status: 'closed', cleanup_state: 'completed' };
let mounted, calls, destinations, submitMode, receiptStatus;
const response = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const original = new Map(
  ['sessionStorage', 'localStorage', 'fetch', 'location', 'document', 'Document', 'ShadowRoot'].map(
    (key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)],
  ),
);
beforeEach(() => {
  globalThis.sessionStorage = memory();
  globalThis.localStorage = memory();
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  globalThis.document = dom.window.document;
  globalThis.Document = dom.window.Document;
  globalThis.ShadowRoot = dom.window.ShadowRoot;
  destinations = [];
  calls = [];
  submitMode = 'success';
  receiptStatus = 'closed';
  mounted = null;
  globalThis.location = {
    pathname: '/account-closure.html',
    search: '',
    assign: (v) => destinations.push(v),
  };
  finishAccountClosure();
  setAuth({
    authenticated: true,
    role: 'member',
    qq_id: '12345678',
    csrf_token: 'fixture',
    account_closure_enabled: true,
  });
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/auth/me') return response({ ...auth });
    if (url === '/api/me/account-closure/preview') return response(preview);
    if (url === '/api/me/account-closure') {
      if (submitMode === 'lost') throw Error('synthetic network loss');
      if (submitMode === 'unauthorized')
        return response({ code: 'AUTH_REQUIRED', message: '请重新登录' }, 401);
      if (submitMode === 'wrong')
        return response({ code: 'REAUTH_FAILED', message: '当前密码不正确' }, 403);
      return response(closed);
    }
    if (url.startsWith('/api/account-closures/'))
      return receiptStatus === 'expired'
        ? response({ message: '回执不存在或已过期' }, 404)
        : response({ ...closed, status: receiptStatus });
    if (url === '/api/private') return response({ message: '登录失效' }, 401);
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  await settle();
  for (const [key, value] of original) {
    if (value) Object.defineProperty(globalThis, key, value);
    else delete globalThis[key];
  }
});
after(cleanupCompiled);
const button = (label) =>
  find(mounted.root, (n) => n.type === 'button' && textOf(n).includes(label))[0];
async function start() {
  mounted = await mount(
    Closure,
    [{ path: '/account-closure.html', component: Closure, meta: { public: true } }],
    '/account-closure.html',
  );
}
async function completeForm(password = ' current password ') {
  const inputs = find(mounted.root, (n) => n.type === 'input');
  inputs.find((n) => n.props.type === 'password').props['onUpdate:modelValue'](password);
  inputs.find((n) => n.props.type === 'checkbox').props['onUpdate:modelValue'](true);
  inputs.find((n) => n.props.autocomplete === 'off').props['onUpdate:modelValue']('注销账号');
  await settle();
}
async function submit() {
  await find(mounted.root, (n) => n.type === 'form')[0].props.onSubmit({ preventDefault() {} });
  await settle();
}

test('receipt storage has an explicit allowlist and expires without retaining passwords or QQ', () => {
  rememberClosure(
    { ...preview, current_password: 'secret', qq_id: '12345678', csrf_token: 'csrf' },
    true,
  );
  const data = [...sessionStorage.data.values()].join('');
  for (const secret of ['secret', '12345678', 'csrf']) assert(!data.includes(secret));
  assert.equal(readClosure().submitted, true);
  assert.equal(readClosure(sessionStorage, preview.receipt_expires_at * 1000 + 1), null);
  assert.equal(sessionStorage.data.size, 0);
});
test('confirmation requires password, checkbox and exact words, then clears local session', async () => {
  await start();
  assert.equal(button('永久注销账号').props.disabled, true);
  assert(textOf(mounted.root).includes('AC 记录'));
  await completeForm();
  assert.equal(button('永久注销账号').props.disabled, false);
  await submit();
  assert(textOf(mounted.root).includes('账号已注销'));
  assert.equal(auth.authenticated, false);
  const call = calls.find((c) => c.url === '/api/me/account-closure');
  assert.equal(JSON.parse(call.options.body).current_password, ' current password ');
  assert.equal(call.options.headers['Idempotency-Key'], preview.request_id);
  assert.equal(call.options.headers['X-CSRF-Token'], 'fixture');
  assert(![...localStorage.data.values()].join('').includes(preview.receipt_token));
  assert(![...sessionStorage.data.values()].join('').includes('current password'));
});
test('wrong password is cleared while the confirmation remains reviewable', async () => {
  submitMode = 'wrong';
  await start();
  await completeForm();
  await submit();
  assert(textOf(mounted.root).includes('当前密码不正确'));
  assert(!textOf(mounted.root).includes('账号已注销'));
  assert.equal(
    find(mounted.root, (n) => n.type === 'input' && n.props.type === 'password')[0].value,
    '',
  );
  assert.equal(auth.authenticated, true);
});
test('lost submission stays uncertain until a receipt proves completion', async () => {
  submitMode = 'lost';
  await start();
  await completeForm();
  await submit();
  assert(textOf(mounted.root).includes('结果待确认'));
  assert(!textOf(mounted.root).includes('账号已注销'));
  assert.equal(readClosure().submitted, true);
  await button('用回执查询结果').props.onClick();
  await settle();
  assert(textOf(mounted.root).includes('账号已注销'));
  assert.equal(destinations.length, 0);
});
test('refresh with a submitted receipt only queries, and expired receipts never imply success', async () => {
  rememberClosure(preview, true);
  receiptStatus = 'expired';
  await start();
  assert.equal(calls.filter((c) => c.url === '/api/me/account-closure').length, 0);
  assert(textOf(mounted.root).includes('结果待确认'));
  assert(textOf(mounted.root).includes('不能以未登录判断注销成功'));
  assert(!textOf(mounted.root).includes('账号已注销'));
});
test('closure 401 remains on the receipt page, other protected requests still go to login', async () => {
  submitMode = 'unauthorized';
  await start();
  await completeForm();
  await submit();
  assert.equal(auth.authenticated, false);
  assert(textOf(mounted.root).includes('结果待确认'));
  assert.equal(destinations.length, 0);
  await assert.rejects(api('/private'));
  assert.equal(destinations.length, 1);
  assert(destinations[0].startsWith('/login.html?next='));
});

test('a previous receipt cannot log out a different currently authenticated account', async () => {
  rememberClosure(preview, true);
  setAuth(
    {
      authenticated: true,
      role: 'member',
      qq_id: '87654321',
      csrf_token: 'other',
      account_closure_enabled: true,
    },
    true,
  );
  await start();
  assert(textOf(mounted.root).includes('账号已注销'));
  assert.equal(auth.authenticated, true);
  assert.equal(auth.qq_id, '87654321');
});

test('an older receipt in the same view cannot log out a new generation of the same QQ', async () => {
  submitMode = 'lost';
  await start();
  await completeForm();
  await submit();
  setAuth({ ...auth, authenticated: true, account_epoch: 3, csrf_token: 'new-generation' }, true);
  await button('用回执查询结果').props.onClick();
  await settle();
  assert(textOf(mounted.root).includes('账号已注销'));
  assert.equal(auth.authenticated, true);
  assert.equal(auth.account_epoch, 3);
});
