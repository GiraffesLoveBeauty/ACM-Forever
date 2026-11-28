import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { setAuth, notification } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const SyncCenter = (await import(await loadSfc('src/admin/SyncCenter.vue'))).default;
const SyncWorkspace = (await import(await loadSfc('src/admin/SyncWorkspace.vue'))).default;
const originals = Object.fromEntries(
  ['Document', 'ShadowRoot', 'document', 'location', 'fetch', 'setTimeout', 'clearTimeout'].map(
    (key) => [key, globalThis[key]],
  ),
);
const response = (value, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
let mounted, calls, polls, members, releaseEnable, failEnable;

beforeEach(() => {
  mounted = null;
  calls = [];
  polls = new Map();
  releaseEnable = null;
  failEnable = false;
  members = ['22345678', '32345678'].map((qq_id, index) => ({
    qq_id,
    name: `合成成员${index + 1}`,
    member_status: '训练组',
    platforms: { luogu: { status: 'disabled', bound: true, account: String(81000 + index) } },
  }));
  setAuth(
    { authenticated: true, role: 'admin', qq_id: '12345678', csrf_token: 'fixture-csrf' },
    true,
  );
  globalThis.Document = class {};
  globalThis.ShadowRoot = class {};
  globalThis.document = Object.assign(new Document(), { activeElement: null });
  globalThis.location = { pathname: '/admin.html', search: '?section=sync-center', assign() {} };
  globalThis.setTimeout = (callback, delay, ...args) => {
    if (delay === 5000) {
      const id = {};
      polls.set(id, callback);
      return id;
    }
    return originals.setTimeout(callback, delay, ...args);
  };
  globalThis.clearTimeout = (id) => {
    if (!polls.delete(id)) originals.clearTimeout(id);
  };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/admin/members/options') return response({ statuses: ['训练组'] });
    if (url.startsWith('/api/admin/sync/members?'))
      return response({
        items: members,
        total: members.length,
        page: 1,
        page_size: 20,
        platforms: [{ key: 'luogu', label: '洛谷' }],
        summary: {
          disabled: members.filter((row) => row.platforms.luogu.status === 'disabled').length,
        },
      });
    if (url.endsWith('/enable')) {
      if (failEnable) return response({ message: '暂时无法开启' }, 503);
      return new Promise((resolve) => {
        releaseEnable = () => {
          members[0].platforms.luogu.status = 'never';
          resolve(
            response(
              { success: true, task_id: 'synthetic-task', message: '同步任务已排队。' },
              202,
            ),
          );
        };
      });
    }
    if (url === '/api/tasks') return response([]);
    throw Error('Unexpected request: ' + url);
  };
});

afterEach(async () => {
  mounted?.unmount();
  releaseEnable?.();
  await settle();
  polls.clear(); // Notifications also own a five-second timer after an error.
  setAuth({ authenticated: false }, true);
  Object.assign(globalThis, originals);
});
after(cleanupCompiled);

async function page(component = SyncCenter) {
  mounted = await mount(
    component,
    [{ path: '/admin.html', component }],
    '/admin.html?section=sync-center',
  );
}
const buttons = (label) =>
  find(mounted.root, (node) => node.type === 'button' && textOf(node).trim() === label);
const selects = () => find(mounted.root, (node) => node.type === 'select');
async function choose(select, value) {
  select.props['onUpdate:modelValue'](value);
  await select.props.onChange?.();
  await settle();
}

test('collapsed disabled members retain their explicit Luogu re-enable action', async () => {
  await page();
  assert.equal(buttons('重新开启洛谷同步').length, 2);
  assert.equal(buttons('+').length, 2);
  assert.match(textOf(mounted.root), /已停用/);
  await buttons('+')[0].props.onClick();
  await settle();
  assert.equal(buttons('单独同步')[0].props.disabled, true);
});

test('re-enabling targets one member, blocks duplicate posts and refreshes only after success', async () => {
  await page();
  const action = buttons('重新开启洛谷同步')[0];
  const enabling = action.props.onClick();
  await settle();
  assert.equal(buttons('开启中…')[0].props.disabled, true);
  await action.props.onClick();
  const posts = calls.filter((call) => call.options.method === 'POST');
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, '/api/admin/luogu-sync/22345678/enable');
  assert.equal(posts[0].options.headers['X-CSRF-Token'], 'fixture-csrf');
  releaseEnable();
  await enabling;
  await settle();
  assert.equal(buttons('重新开启洛谷同步').length, 1);
  assert.match(textOf(mounted.root), /合成成员1：同步任务已排队/);
  assert.equal(calls.filter((call) => call.url.startsWith('/api/admin/sync/members?')).length, 2);
});

test('a failed re-enable preserves the disabled action and permits retry', async () => {
  failEnable = true;
  await page();
  await buttons('重新开启洛谷同步')[0].props.onClick();
  await settle();
  assert.equal(notification.value, '暂时无法开启');
  assert.equal(buttons('重新开启洛谷同步').length, 2);
  assert.equal(buttons('重新开启洛谷同步')[0].props.disabled, false);
  await buttons('重新开启洛谷同步')[0].props.onClick();
  assert.equal(calls.filter((call) => call.options.method === 'POST').length, 2);
});

test('member identity and disabled status filters reach the API and clear together', async () => {
  await page();
  const identity = selects().find((select) => textOf(select).includes('全部身份'));
  assert.ok(identity, 'member identity filter remains available');
  await choose(identity, '训练组');
  await choose(
    selects().find((select) => textOf(select).includes('全部状态')),
    'disabled',
  );
  const latestQuery = () =>
    new URL(
      calls.filter((call) => call.url.startsWith('/api/admin/sync/members?')).at(-1).url,
      'http://localhost',
    ).searchParams;
  assert.equal(latestQuery().get('member_status'), '训练组');
  assert.equal(latestQuery().get('status'), 'disabled');
  await buttons('清空')[0].props.onClick();
  await settle();
  assert.equal(latestQuery().has('member_status'), false);
  assert.equal(latestQuery().has('status'), false);
});

test('switching between overview and queue stops the outgoing view polling', async () => {
  await page(SyncWorkspace);
  assert.equal(polls.size, 1);
  const overviewPoll = [...polls.keys()][0];
  await mounted.router.push('/admin.html?section=sync-center&tab=queue');
  await settle();
  assert.equal(polls.has(overviewPoll), false);
  assert.equal(polls.size, 1);
  assert.match(textOf(mounted.root), /暂无后台任务/);
  const queuePoll = [...polls.keys()][0];
  await mounted.router.push('/admin.html?section=sync-center');
  await settle();
  assert.equal(polls.has(queuePoll), false);
  assert.equal(polls.size, 1);
  assert.equal(buttons('重新开启洛谷同步').length, 2);
  mounted.unmount();
  mounted = null;
  assert.equal(polls.size, 0, 'leaving the workspace clears polling');
});

test('leaving during the first overview read cannot schedule a late polling timer', async () => {
  const fetch = globalThis.fetch;
  let releaseSnapshot;
  globalThis.fetch = (url, options) => {
    if (url.startsWith('/api/admin/sync/members?')) {
      calls.push({ url, options });
      return new Promise((resolve) => {
        releaseSnapshot = () => resolve(response({ items: [], total: 0 }));
      });
    }
    return fetch(url, options);
  };
  await page(SyncWorkspace);
  const reading = calls.find((call) => call.url.startsWith('/api/admin/sync/members?'));
  await mounted.router.push('/admin.html?section=sync-center&tab=queue');
  await settle();
  assert.equal(reading.options.signal.aborted, true);
  releaseSnapshot();
  await settle();
  assert.equal(polls.size, 1, 'only the active queue may schedule polling');
});

test('the queue identity filter hides other members in both individual and bulk results', async () => {
  const fetch = globalThis.fetch;
  globalThis.fetch = (url, options) => {
    if (url === '/api/tasks')
      return Promise.resolve(
        response([
          {
            id: 'selected',
            kind: '账号全量同步',
            member: { status: '训练组' },
            qq_id: '22345678',
            result: { luogu: 1 },
          },
          {
            id: 'other',
            kind: '账号全量同步',
            member: { status: '集训组' },
            qq_id: '32345678',
            result: { luogu: 2 },
          },
          {
            id: 'bulk',
            kind: '全员平台同步',
            qq_id: '*',
            member_statuses: { 22345678: '训练组', 32345678: '集训组' },
            result: { 22345678: { luogu: 3 }, 32345678: { luogu: 4 } },
          },
        ]),
      );
    return fetch(url, options);
  };
  await page(SyncWorkspace);
  await mounted.router.push('/admin.html?section=sync-center&tab=queue');
  await settle();
  await choose(selects()[0], '训练组');
  const content = textOf(mounted.root);
  assert.match(content, /#selected/);
  assert.match(content, /#bulk/);
  assert.doesNotMatch(content, /#other|32345678/);
  assert.match(content, /22345678：luogu：新增 3 条/);
});
