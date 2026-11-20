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
let mounted,
  calls,
  jobs,
  polls,
  heldPost,
  failTasks,
  holdTasks,
  delayedTasks,
  postStatus,
  scheduleState;
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
  scheduleState = {
    global_enabled: true,
    timezone: 'Asia/Shanghai',
    hour: 4,
    platforms: ['atcoder', 'codeforces', 'luogu'].map((platform) => ({
      platform,
      enabled: platform !== 'luogu',
      effective_enabled: platform !== 'luogu',
    })),
  };
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
    if (url === '/api/admin/problems/schedule') {
      if (options.method === 'PUT') {
        const body = JSON.parse(options.body);
        for (const [platform, enabled] of Object.entries(body.platforms)) {
          const row = scheduleState.platforms.find((item) => item.platform === platform);
          row.enabled = enabled;
          row.effective_enabled = enabled;
        }
      }
      return response(scheduleState);
    }
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
  // Collection moved behind an explicit tab; preserve the existing collection regression coverage.
  const collectionTab = find(
    mounted.root,
    (n) => n.type === 'button' && textOf(n).trim() === '采集与数据库工具',
  )[0];
  if (collectionTab) {
    await collectionTab.props.onClick();
    await settle();
  }
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
  assert.match(textOf(mounted.root), /部分完成/);
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

test('the task page separates actual Luogu failures, retries without requests, and successes', async () => {
  jobs = [
    {
      id: 'all-account-sync',
      kind: '全员平台同步',
      qq_id: '*',
      status: 'partial',
      result: {
        11111111: { luogu: -1, atcoder: 2 },
        22222222: { luogu: -1 },
        33333333: { luogu: 0 },
        44444444: { luogu: -4 },
        55555555: { luogu: -1 },
        66666666: { luogu: -5 },
        77777777: { luogu: -3 },
      },
      errors: {
        11111111: {
          luogu: {
            message: '洛谷练习页拒绝访问',
            http_status: 403,
            request_attempted: true,
            consecutive_failures: 2,
            next_retry_at: 1700000000,
          },
        },
        22222222: {
          luogu: {
            message: '洛谷站点冷却中',
            cause_http_status: 429,
            request_attempted: false,
            deferred: true,
            consecutive_failures: 0,
            next_retry_at: 1700000000,
          },
        },
        55555555: { luogu: { message: 'UID 格式无效', request_attempted: false } },
      },
      luogu_members: {
        11111111: { name: '小吴', uid: '2249860' },
        22222222: { name: '小赵', uid: '2240405' },
        33333333: { name: '小陈', uid: '2240404' },
        44444444: { name: '小林', uid: '2240406' },
        55555555: { name: '小张', uid: 'invalid' },
        66666666: { name: '小周', uid: '2240407' },
        77777777: { name: '小孙', uid: '2240408' },
      },
    },
  ];
  await page(Tasks);
  function section(title) {
    const summary = find(
      mounted.root,
      (node) => node.type === 'summary' && textOf(node).startsWith(title),
    )[0];
    assert.ok(summary, title);
    return textOf(summary.parent).replace(/\s+/g, ' ');
  }

  const failed = section('洛谷实际请求失败 1 人');
  assert.match(failed, /小吴 · QQ 11111111 · 洛谷 UID 2249860/);
  assert.match(failed, /洛谷练习页拒绝访问（HTTP 403；可重试时间：[^）]+）.*连续失败 2 次/);
  const waiting = section('洛谷等待重试 1 人（本次未发送请求）');
  assert.match(waiting, /小赵 · QQ 22222222 · 洛谷 UID 2240405/);
  assert.match(
    waiting,
    /洛谷站点冷却中（触发冷却的状态：HTTP 429；可重试时间：[^）]+）.*连续失败 0 次/,
  );
  assert.match(section('洛谷同步成功 1 人'), /小陈 · QQ 33333333 · 洛谷 UID 2240404 · 新增 0 条/);
  assert.match(
    section('其他洛谷结果 4 人'),
    /绑定已变更，已跳过.*UID 格式无效.*已暂停，保留已有记录.*同步未完成，请重试/,
  );
  const content = textOf(mounted.root);
  assert.match(content, /11111111：atcoder：新增 2 条/);
  assert.doesNotMatch(content, /11111111：luogu/);
});

test('Luogu collection submits normalized P IDs without contest fields', async () => {
  await page();
  await model('sync-platform', 'luogu');
  assert.equal(element('sync-language').props.disabled, true);
  assert.equal(textOf(element('sync-language')).trim(), '中文优先');
  assert.equal(find(mounted.root, (n) => n.props.id === 'sync-contest').length, 0);
  await model('sync-problems', 'p1001，P1002 P1001');
  await submit();
  assert.deepEqual(JSON.parse(syncPosts()[0].options.body), {
    platform: 'luogu',
    scope: 'problems',
    language: 'zh-CN',
    refresh: false,
    problem_ids: ['P1001', 'P1002'],
  });
});
test('Luogu whole-platform collection sends batch size without a statement total limit', async () => {
  await page();
  await model('sync-platform', 'luogu');
  await model('sync-scope', 'platform');
  await model('sync-batch-size', 25);
  await submit();
  const body = JSON.parse(syncPosts()[0].options.body);
  assert.equal('limit' in body, false);
  assert.equal(body.batch_size, 25);
  assert.equal(body.language, 'zh-CN');
  assert.equal('contest_id' in body, false);
});
test('Luogu validation rejects source URLs before any task is submitted', async () => {
  await page();
  await model('sync-platform', 'luogu');
  await model('sync-problems', 'https://www.luogu.com.cn/problem/P1001');
  await submit();
  assert.equal(syncPosts().length, 0);
  assert.match(textOf(mounted.root), /仅支持 P/);
});

test('successful explicit Luogu collection does not report an incomplete directory', async () => {
  jobs = [
    running({
      platform: 'luogu',
      status: 'completed',
      result: {
        scope: 'problems',
        success_count: 1,
        failure_count: 0,
        remaining_count: 0,
        catalog_complete: false,
      },
      progress: { phase: 'statements', done: 1, total: 1, problem_id: 'P1001' },
    }),
  ];
  await page(Tasks);
  const content = textOf(mounted.root);
  assert.match(content, /拉取完成/);
  assert.match(content, /成功 1 题/);
  assert.doesNotMatch(content, /目录尚未完整同步|目录同步结果/);
});

test('Luogu directory warnings remain visible after failed or cancelled directory collection', async () => {
  for (const scope of ['catalog', 'platform']) {
    for (const status of ['failed', 'cancelled']) {
      jobs = [
        running({
          platform: 'luogu',
          status,
          result: { scope, catalog_complete: false, catalog_pages: 1, metadata_count: 3 },
          progress: { phase: 'catalog', done: 3, total: 6 },
        }),
      ];
      await page(Tasks);
      const content = textOf(mounted.root);
      assert.match(content, /目录尚未完整同步/);
      assert.match(content, /已读取 1 页 · 已导入 3 道题目/);
      assert.doesNotMatch(content, /正在同步|拉取完成|目录同步完成/);
      mounted.unmount();
      mounted = null;
    }
  }
});

test('completed Luogu directory collection shows saved counts without ongoing phase text', async () => {
  jobs = [
    running({
      platform: 'luogu',
      status: 'completed',
      result: { scope: 'catalog', catalog_complete: true, catalog_pages: 1, metadata_count: 3 },
      progress: { phase: 'catalog', done: 3, total: 3 },
    }),
  ];
  await page(Tasks);
  const content = textOf(mounted.root);
  assert.match(content, /拉取完成/);
  assert.match(content, /已读取 1 页 · 已导入 3 道题目/);
  assert.doesNotMatch(content, /正在同步|目录尚未完整同步/);
});

test('Luogu tasks that skip saved statements show final statistics after the last discovery phase', async () => {
  for (const scope of ['problems', 'platform']) {
    jobs = [
      running({
        platform: 'luogu',
        status: 'completed',
        result: {
          scope,
          skipped_count: 1,
          catalog_complete: scope === 'platform',
          catalog_pages: scope === 'platform' ? 1 : 0,
          metadata_count: scope === 'platform' ? 1 : 0,
        },
        progress: { phase: scope === 'platform' ? 'catalog' : 'taxonomy', done: 0, total: 0 },
      }),
    ];
    await page(Tasks);
    const content = textOf(mounted.root);
    assert.match(content, /拉取完成/);
    assert.match(content, /跳过 1 题/);
    assert.doesNotMatch(content, /正在更新|正在同步|目录尚未完整同步/);
    mounted.unmount();
    mounted = null;
  }
});

test('active collection phases keep their progress wording for each platform', async () => {
  for (const [platform, phase, expected] of [
    ['luogu', 'taxonomy', /正在更新洛谷原生难度与标签/],
    ['luogu', 'catalog', /正在同步洛谷目录/],
    ['atcoder', 'metadata', /正在导入题目目录 2 \/ 3 题/],
    ['codeforces', 'contest_catalog', /正在补全比赛题目列表 1 \/ 2 场/],
    ['atcoder', 'catalog', /正在读取全平台题目目录/],
    ['codeforces', 'catalog', /正在读取全平台题目目录/],
  ]) {
    jobs = [
      running({
        platform,
        result: { scope: 'platform', catalog_complete: false },
        progress: {
          phase,
          done: 0,
          total: 0,
          metadata_done: 2,
          metadata_total: 3,
          contests_done: 1,
          contests_total: 2,
        },
      }),
    ];
    await page(Tasks);
    const content = textOf(mounted.root);
    assert.match(content, expected);
    assert.doesNotMatch(content, /目录尚未完整同步|目录同步结果/);
    mounted.unmount();
    mounted = null;
  }
});

test('terminal legacy discovery phases show final counts instead of ongoing wording', async () => {
  for (const [platform, phase] of [
    ['atcoder', 'metadata'],
    ['codeforces', 'contest_catalog'],
  ]) {
    for (const status of ['completed', 'partial', 'failed', 'cancelled']) {
      jobs = [
        running({
          platform,
          status,
          result: { scope: 'platform', skipped_count: 2 },
          progress: { phase, done: 1, total: 4, metadata_done: 3, metadata_total: 5 },
        }),
      ];
      await page(Tasks);
      const content = textOf(mounted.root);
      assert.match(content, /跳过 2 题/);
      assert.match(content, phase === 'metadata' ? /已处理 3 \/ 5 题/ : /已处理 1 \/ 4 题/);
      assert.doesNotMatch(content, /正在导入|正在补全/);
      mounted.unmount();
      mounted = null;
    }
  }
});

test('Luogu platform collection reports completed batches while running and after stopping', async () => {
  for (const [status, completed] of [
    ['running', 1],
    ['completed', 2],
    ['cancelled', 1],
  ]) {
    jobs = [
      running({
        platform: 'luogu',
        status,
        result: { scope: 'platform', batch_count: 2, completed_batches: completed },
        progress: { phase: 'statements', done: completed, total: 3 },
      }),
    ];
    await page(Tasks);
    assert.ok(textOf(mounted.root).includes('已完成批次 ' + completed + ' / 2'));
    mounted.unmount();
    mounted = null;
  }
});

test('Codeforces and AtCoder retain their current batch number display', async () => {
  for (const platform of ['codeforces', 'atcoder']) {
    jobs = [
      running({
        platform,
        result: { scope: 'platform', batch_count: 3, completed_batches: 1 },
        progress: { phase: 'statements', done: 3, total: 5, batch: 2 },
      }),
    ];
    await page(Tasks);
    const content = textOf(mounted.root);
    assert.match(content, /批次 2 \/ 3/);
    assert.doesNotMatch(content, /已完成批次/);
    mounted.unmount();
    mounted = null;
  }
});

test('per-OJ daily switches persist through the authenticated API independently', async () => {
  await page();
  const input = find(
    mounted.root,
    (n) => n.type === 'input' && n.props['aria-label'] === 'Codeforces每日自动同步',
  )[0];
  const target = { checked: false };
  await input.props.onChange({ target });
  await settle();
  const saved = calls.find(
    (call) => call.url === '/api/admin/problems/schedule' && call.options.method === 'PUT',
  );
  assert.deepEqual(JSON.parse(saved.options.body), { platforms: { codeforces: false } });
  assert.equal(saved.options.headers['X-CSRF-Token'], 'fixture-csrf');
  assert.equal(scheduleState.platforms.find((row) => row.platform === 'atcoder').enabled, true);
  assert.equal(scheduleState.platforms.find((row) => row.platform === 'luogu').enabled, false);
  assert.equal(target.checked, false);
});
test('manual date range sends absolute Beijing boundaries and a clear time basis', async () => {
  await page();
  await model('sync-platform', 'codeforces');
  await model('sync-scope', 'platform');
  await model('sync-range', 'time');
  const dates = find(mounted.root, (n) => n.type === 'input' && n.props.type === 'datetime-local');
  dates[0].props.onChange({ target: { value: '2026-11-01T08:00' } });
  dates[1].props.onChange({ target: { value: '2026-11-02T08:00' } });
  await settle();
  await submit();
  const body = JSON.parse(syncPosts()[0].options.body);
  assert.equal(body.start_at, 1793491200);
  assert.equal(body.end_at, 1793577600);
  assert.equal(body.time_basis, 'contest');
  assert.equal('limit' in body, false);
  assert.equal('contest_id' in body, false);
});
test('empty manual time ranges stay on the form instead of creating tasks', async () => {
  await page();
  await model('sync-platform', 'luogu');
  await model('sync-scope', 'platform');
  await model('sync-range', 'time');
  await submit();
  assert.equal(syncPosts().length, 0);
  assert.match(textOf(mounted.root), /至少选择开始或结束时间/);
});
