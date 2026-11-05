import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { setAuth } from '../src/lib/api.js';
import { problemMemory } from '../src/lib/admin.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Problems = (await import(await loadSfc('src/admin/Problems.vue'))).default;
const Tasks = (await import(await loadSfc('src/admin/Tasks.vue'))).default;
const originals = {
  Document: globalThis.Document,
  ShadowRoot: globalThis.ShadowRoot,
  fetch: globalThis.fetch,
  document: globalThis.document,
  location: globalThis.location,
  setTimeout: globalThis.setTimeout,
  clearTimeout: globalThis.clearTimeout,
};
let mounted, calls, jobs, polls, heldPost, failTasks, holdTasks, delayedTasks, postStatus;
const dbStatus = {
  initialized: true,
  platforms: [{ platform: 'atcoder', total: 2, collected: 1, failed: 0, samples: 2 }],
};
const running = (extra = {}) => ({
  id: 'problem-1',
  kind: '题目采集',
  platform: 'atcoder',
  status: 'running',
  result: { scope: 'contest', contest_id: 'abc370', success_count: 0, completed_batches: 0 },
  progress: { done: 0, total: 2, phase: 'statements' },
  ...extra,
});
const response = (value, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => {
  mounted = null;
  calls = [];
  jobs = [];
  polls = new Map();
  heldPost = null;
  postStatus = 202;
  failTasks = holdTasks = false;
  delayedTasks = [];
  setAuth(
    { authenticated: true, qq_id: '12345678', role: 'root', csrf_token: 'fixture-csrf' },
    true,
  );
  globalThis.Document = class {};
  globalThis.ShadowRoot = class {};
  globalThis.document = Object.assign(new Document(), { activeElement: null });
  globalThis.location = { pathname: '/admin.html', search: '?section=problems', assign() {} };
  globalThis.setTimeout = (callback, delay, ...args) => {
    if ([3000, 6000].includes(delay)) {
      const id = {};
      polls.set(id, { callback, delay });
      return id;
    }
    return originals.setTimeout(callback, delay, ...args);
  };
  globalThis.clearTimeout = (id) => {
    if (!polls.delete(id)) originals.clearTimeout(id);
  };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/admin/database') return response(dbStatus);
    if (url === '/api/admin/database/init')
      return response({ ...dbStatus, message: '数据库初始化完成，已有数据已保留。' });
    if (url.startsWith('/api/admin/database/problems?'))
      return response({ items: [], total: 0, page: 1 });
    if (url === '/api/tasks') {
      if (holdTasks)
        return new Promise((resolve) => delayedTasks.push(() => resolve(response(jobs))));
      return response(failTasks ? { message: 'temporary outage' } : jobs, failTasks ? 503 : 200);
    }
    if (url === '/api/admin/problems/sync') {
      if (heldPost)
        return new Promise((resolve) => {
          heldPost.resolve = () => {
            jobs = [running()];
            resolve(response({ task: { id: 'problem-1' } }, 202));
          };
        });
      jobs = [running()];
      return response(
        postStatus === 202 ? { task: { id: 'problem-1' } } : { message: 'ack lost' },
        postStatus,
      );
    }
    if (url === '/api/tasks/problem-1/cancel') {
      jobs = [running({ status: 'cancelled' })];
      return response({ success: true });
    }
    throw Error('Unexpected request: ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  for (const resolve of delayedTasks) resolve();
  heldPost?.resolve?.();
  await settle();
  assert.equal(polls.size, 0, 'unmount clears collection polling');
  setAuth({ authenticated: false }, true);
  Object.assign(globalThis, originals);
});
after(cleanupCompiled);
async function page(component = Problems) {
  mounted = await mount(
    component,
    [
      { path: '/admin.html', component },
      { path: '/home.html', component: { render: () => null } },
    ],
    '/admin.html?section=problems',
  );
  return mounted;
}
function element(id) {
  const node = find(mounted.root, (n) => n.props.id === id)[0];
  assert.ok(node, id + ' exists');
  return node;
}
async function model(id, value) {
  element(id).props['onUpdate:modelValue'](value);
  await settle();
}
async function submit() {
  const pending = element('problem-sync-form').props.onSubmit({ preventDefault() {} });
  await settle();
  return pending;
}
const syncPosts = () => calls.filter((call) => call.url === '/api/admin/problems/sync');
async function tick() {
  const [id, entry] = polls.entries().next().value;
  polls.delete(id);
  await entry.callback();
  await settle();
}

test('Web admin and root see the collection form; members make no admin requests', async () => {
  for (const role of ['admin', 'root', 'member']) {
    setAuth({ authenticated: true, qq_id: '12345678', role, csrf_token: 'fixture-csrf' }, true);
    calls = [];
    await page();
    assert.equal(
      find(mounted.root, (n) => n.props.id === 'problem-sync-form').length,
      role === 'member' ? 0 : 1,
    );
    assert.equal(
      calls.some((call) => call.url === '/api/admin/database'),
      role !== 'member',
    );
    assert.equal(
      calls.some((call) => call.url === '/api/tasks'),
      role !== 'member',
    );
    assert.equal(syncPosts().length, 0);
    assert.equal(
      calls.some((call) => /^\/api\/(?:me\/)?problems\?/.test(call.url)),
      false,
      'collection management does not request the personal browsing list',
    );
    mounted.unmount();
    mounted = null;
  }
});
test('management shows initialization, collection and saved records in that order without personal filters', async () => {
  await page();
  const headings = find(mounted.root, (node) => node.type === 'h2').map((node) =>
    textOf(node).trim(),
  );
  const database = headings.indexOf('服务端数据库');
  const collection = headings.indexOf('拉取题目');
  const records = headings.indexOf('题库记录');
  assert.ok(database >= 0 && database < collection && collection < records);
  assert.equal(find(mounted.root, (node) => node.props.id === 'problem-list').length, 0);
  assert.doesNotMatch(textOf(mounted.root), /成员 QQ|筛选题目|收藏/);
  assert.ok(calls.some((call) => call.url.startsWith('/api/admin/database/problems?')));
  assert.equal(
    calls.some((call) => /^\/api\/(?:me\/)?problems\?/.test(call.url)),
    false,
  );
});

test('AtCoder submission uses the real request layer, locks duplicates and cancels the task', async () => {
  await page();
  await model('sync-contest', 'abc370');
  await model('sync-problems', 'abc370_a，abc370_b abc370_a');
  await model('sync-limit', 2);
  await submit();
  await submit();
  assert.equal(syncPosts().length, 1);
  assert.deepEqual(JSON.parse(syncPosts()[0].options.body), {
    platform: 'atcoder',
    scope: 'contest',
    language: 'en',
    refresh: false,
    contest_id: 'abc370',
    problem_ids: ['abc370_a', 'abc370_b'],
    limit: 2,
  });
  assert.equal(syncPosts()[0].options.headers['X-CSRF-Token'], 'fixture-csrf');
  assert.equal(element('problem-sync-fields').props.disabled, true);
  assert.equal(polls.size, 1);
  const cancel = find(
    mounted.root,
    (n) => n.type === 'button' && textOf(n).trim() === '取消采集',
  )[0];
  await cancel.props.onClick();
  await settle();
  assert.match(textOf(mounted.root), /已取消/);
  assert.equal(element('problem-sync-fields').props.disabled, false);
  assert.equal(polls.size, 0);
});
test('full CF collection sends batch size without a contest or total limit and refreshes on completion', async () => {
  await page();
  await model('sync-language', 'ja');
  await model('sync-platform', 'codeforces');
  await model('sync-scope', 'platform');
  await model('sync-batch-size', 50);
  assert.equal(element('sync-language').props.disabled, true);
  assert.equal(find(mounted.root, (n) => n.props.id === 'sync-contest').length, 0);
  await submit();
  assert.deepEqual(JSON.parse(syncPosts()[0].options.body), {
    platform: 'codeforces',
    scope: 'platform',
    language: 'en',
    refresh: false,
    batch_size: 50,
  });
  const lists = calls.filter((c) => c.url.startsWith('/api/admin/database/problems?')).length;
  jobs = [
    running({
      platform: 'codeforces',
      status: 'partial',
      result: {
        scope: 'platform',
        metadata_count: 120,
        completed_batches: 3,
        batch_count: 3,
        success_count: 119,
        failure_count: 1,
        failures: [{ problem_id: 'cf_1B', error: '<img src=x onerror=alert(1)>' }],
      },
      progress: { done: 120, total: 120, batch: 3 },
    }),
  ];
  await tick();
  assert.equal(element('problem-sync-fields').props.disabled, false);
  assert.match(textOf(mounted.root), /部分题目拉取失败/);
  assert.match(textOf(mounted.root), /<img src=x onerror=alert\(1\)>/);
  assert.equal(find(mounted.root, (n) => n.props.innerHTML).length, 0);
  assert.ok(calls.filter((c) => c.url.startsWith('/api/admin/database/problems?')).length > lists);
  assert.equal(
    calls.some((c) => /^\/api\/(?:me\/)?problems\?/.test(c.url)),
    false,
  );
});
test('initialization posts no reset or database path and updates the visible status', async () => {
  await page();
  const lists = calls.filter((call) => call.url.startsWith('/api/admin/database/problems?')).length;
  await element('problem-db-init').props.onClick();
  await settle();
  const initialization = calls.find((call) => call.url === '/api/admin/database/init');
  assert.deepEqual(JSON.parse(initialization.options.body), {});
  assert.equal(initialization.options.method, 'POST');
  assert.match(textOf(mounted.root), /初始化完成，已有数据已保留/);
  assert.ok(
    calls.filter((call) => call.url.startsWith('/api/admin/database/problems?')).length > lists,
  );
});
test('returning to the page restores an active task without another POST', async () => {
  jobs = [running()];
  await page();
  assert.equal(element('problem-sync-fields').props.disabled, true);
  mounted.unmount();
  mounted = null;
  assert.equal(polls.size, 0);
  await page();
  assert.equal(problemMemory.taskId, 'problem-1');
  assert.equal(syncPosts().length, 0);
  assert.equal(polls.size, 1);
});
test('POST acknowledgement survives leaving the page and is reused after returning', async () => {
  heldPost = {};
  await page();
  await model('sync-contest', 'abc370');
  const pending = element('problem-sync-form').props.onSubmit({ preventDefault() {} });
  await settle();
  mounted.unmount();
  mounted = null;
  await page();
  assert.equal(element('problem-sync-fields').props.disabled, true);
  assert.equal(syncPosts().length, 1);
  heldPost.resolve();
  heldPost = null;
  await pending;
  await settle();
  assert.equal(problemMemory.taskId, 'problem-1');
  assert.match(textOf(mounted.root), /正在拉取/);
  assert.equal(polls.size, 1);
});

test('a new active collection takes over monitoring when the previous task has finished', async () => {
  jobs = [running()];
  await page();
  jobs = [running({ status: 'completed' }), running({ id: 'problem-2', platform: 'codeforces' })];
  await tick();
  assert.equal(problemMemory.taskId, 'problem-2');
  assert.equal(element('problem-sync-fields').props.disabled, true);
  assert.match(textOf(mounted.root), /任务 #problem-2/);
  assert.equal(polls.size, 1);
  assert.equal(syncPosts().length, 0);
});
test('an acknowledgement from the previous account cannot restore its cached task', async () => {
  heldPost = {};
  await page();
  await model('sync-contest', 'abc370');
  const pending = element('problem-sync-form').props.onSubmit({ preventDefault() {} });
  await settle();
  mounted.unmount();
  mounted = null;
  setAuth(
    { authenticated: true, qq_id: '87654321', role: 'member', csrf_token: 'second-session' },
    true,
  );
  heldPost.resolve();
  heldPost = null;
  await pending;
  await settle();
  assert.equal(problemMemory.taskId, null);
  assert.equal(problemMemory.submission, null);
  calls = [];
  await page();
  assert.equal(
    calls.some((call) => call.url.startsWith('/api/admin/') || call.url === '/api/tasks'),
    false,
  );
});
test('unknown task state disables submission until polling recovers', async () => {
  failTasks = true;
  await page();
  assert.equal(element('problem-sync-fields').props.disabled, true);
  assert.match(textOf(mounted.root), /无法读取采集任务/);
  assert.equal([...polls.values()][0].delay, 6000);
  failTasks = false;
  await tick();
  assert.equal(element('problem-sync-fields').props.disabled, false);
  assert.equal(syncPosts().length, 0);
});

test('a failed POST acknowledgement reconciles with the accepted task instead of resubmitting', async () => {
  postStatus = 503;
  await page();
  await model('sync-contest', 'abc370');
  await submit();
  assert.match(textOf(mounted.root), /已恢复后台采集任务进度/);
  assert.equal(element('problem-sync-fields').props.disabled, true);
  await submit();
  assert.equal(syncPosts().length, 1);
});
test('leaving aborts an outstanding task GET and stops its polling', async () => {
  jobs = [running()];
  await page();
  holdTasks = true;
  const [id, entry] = polls.entries().next().value;
  polls.delete(id);
  const reading = entry.callback();
  await settle();
  const request = calls.filter((call) => call.url === '/api/tasks').at(-1);
  mounted.unmount();
  mounted = null;
  assert.equal(request.options.signal.aborted, true);
  delayedTasks.shift()();
  await reading;
  await settle();
  assert.equal(polls.size, 0);
});
test('the task page renders collector progress as problem counts and preserves cancellation', async () => {
  jobs = [
    running({
      result: { scope: 'platform', success_count: 8, sample_count: 20 },
      progress: { done: 8, total: 100, phase: 'statements' },
    }),
  ];
  await page(Tasks);
  assert.match(textOf(mounted.root), /成功 8 题/);
  assert.doesNotMatch(textOf(mounted.root), /新增 8 条/);
  const cancel = find(
    mounted.root,
    (n) => n.type === 'button' && textOf(n).trim() === '取消任务',
  )[0];
  await cancel.props.onClick();
  await settle();
  assert.match(textOf(mounted.root), /已取消/);
});

test('the task page explains paused user crawling alongside other platform results', async () => {
  jobs = [
    {
      id: 'account-sync',
      kind: '账号全量同步',
      platform: 'luogu,atcoder',
      qq_id: '12345678',
      status: 'completed',
      result: { luogu: -5, atcoder: 2 },
    },
    {
      id: 'all-account-sync',
      kind: '全员平台同步',
      status: 'completed',
      result: { 87654321: { luogu: -5 } },
    },
  ];
  await page(Tasks);
  const content = textOf(mounted.root);
  assert.match(content, /luogu：已暂停，保留已有记录；atcoder：新增 2 条/);
  assert.match(content, /87654321：luogu：已暂停，保留已有记录/);
  assert.doesNotMatch(content, /同步失败|新增 -5 条/);
});
