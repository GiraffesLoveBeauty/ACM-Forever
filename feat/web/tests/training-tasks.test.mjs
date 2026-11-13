import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { localTime, utcTime, trainingReturn } from '../src/lib/training-tasks.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Training = (await import(await loadSfc('src/admin/Training.vue'))).default;
const Root = { render: () => h(RouterView) };
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
];
const originals = new Map(keys.map((k) => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
let dom, mounted, calls, guard, stored, conflict, progressItems;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => {
  dom = new JSDOM('<!doctype html><body></body>', {
    url: 'http://127.0.0.1/admin.html?section=training',
  });
  for (const key of keys.filter((k) => k !== 'fetch'))
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      configurable: true,
      writable: true,
    });
  setAuth({ authenticated: true, role: 'admin', qq_id: '12345678', csrf_token: 'synthetic' }, true);
  calls = [];
  guard = null;
  stored = null;
  conflict = false;
  progressItems = [];
  dom.window.confirm = () => false;
  globalThis.fetch = async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url, body, options });
    if (url.endsWith('/options'))
      return response({
        enabled: true,
        statuses: ['动态实验组'],
        capabilities: [{ platform: 'codeforces', label: 'Codeforces' }],
        max_problems: 50,
      });
    if (url.includes('/resolve-problems'))
      return response({
        items: body.problems.map((p, i) => ({
          ...p,
          problem_name: '合成题' + i,
          problem_id: p.problem_id.startsWith('cf_') ? p.problem_id : 'cf_' + p.problem_id,
          tags: [],
          supported: true,
        })),
        errors: [],
        duplicates: 0,
      });
    if (options.method === 'POST' && url === '/api/admin/training-tasks') {
      stored = { ...body, id: 17, version: 1, state: 'draft', creator_name: '管理员', audit: [] };
      return response(stored, 201);
    }
    if (options.method === 'PATCH') {
      stored = { ...stored, ...body, version: stored.version + 1 };
      return response(stored);
    }
    if (url.includes('/audience-preview'))
      return response({
        preview_token: 'preview-proof',
        recipient_count: 2,
        excluded_count: 1,
        unbound_count: 1,
        total: 3,
        page: 1,
        items: [{ qq_id: '22345678', name: '合成成员', status: '动态实验组', unbound: true }],
      });
    if (url.endsWith('/publish'))
      return conflict
        ? response({ code: 'audience_changed', message: '名单已变化，请重新预览' }, 409)
        : response({
            ...stored,
            state: 'published',
            version: 2,
            phase: 'active',
            problems: stored.problems,
          });
    if (url.startsWith('/api/admin/training-tasks/17/progress?'))
      return response({
        summary: {
          recipient_count: progressItems.length,
          completed_problem_count: 12,
          total_problem_count: 40,
        },
        items: progressItems,
        total: progressItems.length,
      });
    if (url.startsWith('/api/admin/training-tasks/17/progress/'))
      return response({
        recipient: progressItems.find((m) => m.id === Number(url.split('/').at(-1))),
        problems: [],
      });
    if (url === '/api/admin/training-tasks/17')
      return response({ ...stored, phase: stored.state === 'draft' ? 'draft' : 'active' });
    if (url.startsWith('/api/admin/training-tasks?')) return response({ items: [], total: 0 });
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  await settle();
  dom.window.close();
  for (const [key, descriptor] of originals)
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  setAuth({ authenticated: false }, true);
});
after(cleanupCompiled);
const buttons = (word) =>
  find(mounted.root, (n) => n.type === 'button' && textOf(n).includes(word));
const click = async (word) => {
  const button = buttons(word)[0];
  assert(button, 'button: ' + word);
  await button.props.onClick({ button: 0, preventDefault() {} });
  await settle();
};
const control = (label, type = 'input') => {
  const wrapper = find(mounted.root, (n) => n.type === 'label' && textOf(n).startsWith(label))[0];
  assert(wrapper, label);
  return find(wrapper, (n) => n.type === type)[0];
};
const set = async (label, value, type) => {
  control(label, type).props['onUpdate:modelValue'](value);
  await settle();
};
async function setupEditor() {
  mounted = await mount(
    Root,
    [{ path: '/admin.html', component: Training }],
    '/admin.html?section=training&task_id=new&tab=edit&step=1',
    {
      registerLeaveGuard: (fn) => {
        guard = fn;
        return () => {
          guard = null;
        };
      },
    },
  );
  await set('任务标题', '真实接口训练');
  await set('标准题号', '1A 2A', 'textarea');
  await click('校验并添加');
}
async function preview() {
  await setupEditor();
  await click('下一步');
  await set('动态实验组', ['动态实验组']);
  await click('保存并预览');
}

test('Shanghai time and return targets preserve task identity and reject unsafe destinations', () => {
  const stamp = 1794391200;
  assert.equal(utcTime(localTime(stamp)), stamp);
  assert.equal(
    trainingReturn('/training-tasks.html?task_id=17&tab=history&qq_id=evil'),
    '/training-tasks.html?task_id=17&tab=history',
  );
  assert.equal(
    trainingReturn('/admin.html?section=training&task_id=17&tab=progress'),
    '/admin.html?section=training&task_id=17&tab=progress',
  );
  for (const value of [
    '//evil.test',
    '/admin.html?section=accounts',
    'https://evil.test/training-tasks.html',
    '/\\evil',
  ])
    assert.equal(trainingReturn(value), null);
});
test('admin uses dynamic identities, preserves order, and requires exclusion confirmation before publish', async () => {
  await preview();
  assert.equal(mounted.router.currentRoute.value.query.step, '3');
  assert(textOf(mounted.root).includes('未绑定也可接收'));
  const create = calls.find(
    (c) => c.options.method === 'POST' && c.url === '/api/admin/training-tasks',
  );
  assert.deepEqual(
    create.body.problems.map((p) => p.problem_id),
    ['cf_1A', 'cf_2A'],
  );
  assert.deepEqual(create.body.statuses, ['动态实验组']);
  assert(buttons('确认发布任务')[0].props.disabled);
  await set('我已确认以上排除原因', true);
  assert(!buttons('确认发布任务')[0].props.disabled);
  await click('确认发布任务');
  const publish = calls.find((c) => c.url.endsWith('/publish'));
  assert.equal(publish.body.preview_token, 'preview-proof');
  assert(publish.options.headers['Idempotency-Key']);
  assert.equal(mounted.router.currentRoute.value.query.tab, 'overview');
});
test('unsaved internal navigation is guarded and changed audiences discard publish proof', async () => {
  await setupEditor();
  assert.equal(guard({ path: '/admin.html', query: { section: 'members' } }), false);
  assert.equal(
    guard({
      path: '/admin.html',
      query: { section: 'training', task_id: 'new', tab: 'edit', step: 2 },
    }),
    true,
  );
  await click('下一步');
  await set('动态实验组', ['动态实验组']);
  await click('保存并预览');
  await set('我已确认以上排除原因', true);
  conflict = true;
  await click('确认发布任务');
  assert(textOf(mounted.root).includes('名单已变化'));
  assert(buttons('确认发布任务')[0].props.disabled);
  assert(textOf(mounted.root).includes('预览尚未生成或已失效'));
});

test('actual site guard preserves training editor and progress query parameters', async () => {
  const url = new URL('../src/lib/api.js?training-route-regression', import.meta.url).href;
  const session = await import(url);
  const fallback = globalThis.fetch;
  globalThis.fetch = async (target, options) =>
    target === '/api/auth/me'
      ? response({
          authenticated: true,
          role: 'admin',
          qq_id: '12345678',
          account_epoch: 1,
          csrf_token: 'synthetic',
        })
      : target === '/api/ui/preferences'
        ? response({})
        : fallback(target, options);
  let source = await readFile(new URL('../src/router.js', import.meta.url), 'utf8');
  source = source
    .replace(
      "from 'vue-router'",
      "from '" +
        new URL('../node_modules/vue-router/dist/vue-router.mjs', import.meta.url).href +
        "'",
    )
    .replace("from './lib/api.js'", "from '" + url + "'")
    .replace(
      /\(\) => import\('\.\/views\/[^']+'\)/g,
      '() => Promise.resolve({default:{render(){return null}}})',
    );
  const realRouter = (
    await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
  ).default;
  try {
    for (const tab of ['edit', 'overview', 'progress']) {
      await realRouter.push('/admin.html?section=training&task_id=17&tab=' + tab + '&step=3');
      assert.equal(realRouter.currentRoute.value.query.tab, tab);
      assert.equal(realRouter.currentRoute.value.query.task_id, '17');
    }
  } finally {
    realRouter.options.history.destroy();
  }
});

function holdResponse(matches) {
  const fetcher = globalThis.fetch;
  let release,
    started,
    held = false;
  const gate = new Promise((resolve) => (release = resolve));
  const pending = new Promise((resolve) => (started = resolve));
  globalThis.fetch = async (url, options = {}) => {
    const result = await fetcher(url, options);
    if (!held && matches(url, options)) {
      held = true;
      started();
      await gate;
    }
    return result;
  };
  return { pending, release: () => release() };
}

test('saving retains later text and keeps it unsaved until an explicit second save', async () => {
  await setupEditor();
  await click('保存草稿');
  await set('任务标题', 'Submitted title');
  const delayed = holdResponse((url, options) => options.method === 'PATCH');
  const saving = click('保存草稿');
  try {
    await delayed.pending;
    await set('任务标题', 'Text entered during saving');
    await set('训练说明', 'Description entered during saving', 'textarea');
  } finally {
    delayed.release();
  }
  await saving;
  assert.equal(stored.title, 'Submitted title');
  assert.equal(control('任务标题').value, 'Text entered during saving');
  assert.equal(control('训练说明', 'textarea').value, 'Description entered during saving');
  assert.equal(guard({ path: '/admin.html', query: { section: 'settings' } }), false);
  await click('保存草稿');
  assert.equal(stored.title, 'Text entered during saving');
  assert.equal(stored.description, 'Description entered during saving');
  assert.equal(guard({ path: '/admin.html', query: { section: 'settings' } }), true);
});

test('save and preview keeps concurrent identities and dates in the editor without previewing stale data', async () => {
  await setupEditor();
  await click('下一步');
  await set('动态实验组', ['动态实验组']);
  const originalDue = control('截止时间').value;
  const laterDue = localTime(Math.floor(Date.now() / 1000) + 14 * 86400);
  const delayed = holdResponse(
    (url, options) => url === '/api/admin/training-tasks' && options.method === 'POST',
  );
  const saving = click('保存并预览');
  try {
    await delayed.pending;
    await set('动态实验组', []);
    await set('截止时间', laterDue);
  } finally {
    delayed.release();
  }
  await saving;
  assert.deepEqual(stored.statuses, ['动态实验组']);
  assert.equal(stored.due_at, utcTime(originalDue));
  assert.equal(mounted.router.currentRoute.value.query.step, '2');
  assert.equal(control('截止时间').value, laterDue);
  assert.equal(calls.filter((call) => call.url.includes('/audience-preview')).length, 0);
  assert.equal(guard({ path: '/admin.html', query: { section: 'settings' } }), false);
  const savedVersion = stored.version;
  await click('保存并预览');
  assert(textOf(mounted.root).includes('请至少选择一种成员身份'));
  assert.equal(stored.version, savedVersion);
  await set('动态实验组', ['动态实验组']);
  await click('保存并预览');
  assert.equal(stored.due_at, utcTime(laterDue));
  assert.equal(mounted.router.currentRoute.value.query.step, '3');
});

test('edits made while a preview response is pending must be saved and previewed again', async () => {
  await setupEditor();
  await click('下一步');
  await set('动态实验组', ['动态实验组']);
  const delayed = holdResponse((url) => url.includes('/audience-preview'));
  const saving = click('保存并预览');
  const laterDue = localTime(Math.floor(Date.now() / 1000) + 21 * 86400);
  try {
    await delayed.pending;
    await set('截止时间', laterDue);
  } finally {
    delayed.release();
  }
  await saving;
  assert.equal(control('截止时间').value, laterDue);
  assert.equal(mounted.router.currentRoute.value.query.step, '2');
  assert.equal(guard({ path: '/admin.html', query: { section: 'settings' } }), false);
  await click('保存并预览');
  assert.equal(mounted.router.currentRoute.value.query.step, '3');
  assert.equal(stored.due_at, utcTime(laterDue));
});

test('completion rows use real names and proportional progress without QQ or status columns', async () => {
  stored = {
    id: 17,
    title: '合成任务',
    version: 2,
    state: 'published',
    statuses: ['动态实验组'],
    audit: [],
    problems: [],
  };
  progressItems = [
    {
      id: 1,
      qq_id: '22345678',
      name: '昵称甲',
      real_name: '合成实名甲',
      completed_problems: 0,
      account_status: 'active',
    },
    {
      id: 2,
      qq_id: '32345678',
      name: '昵称乙',
      real_name: '合成实名乙',
      completed_problems: 4,
      account_status: 'active',
    },
    {
      id: 3,
      qq_id: '42345678',
      name: '数字昵称',
      real_name: null,
      completed_problems: 8,
      account_status: 'active',
    },
    {
      id: 4,
      qq_id: null,
      name: '已注销成员',
      real_name: null,
      completed_problems: 0,
      account_status: 'closed',
    },
    {
      id: 5,
      qq_id: '52345678',
      name: '历史昵称',
      real_name: null,
      completed_problems: 0,
      account_status: 'changed',
    },
  ].map((m) => ({ ...m, problem_count: 8, status_snapshot: '动态实验组' }));
  mounted = await mount(
    Root,
    [{ path: '/admin.html', component: Training }],
    '/admin.html?section=training&task_id=17&tab=progress',
  );
  await settle();
  const table = find(
    mounted.root,
    (n) => n.type === 'table' && n.props['aria-label'] === '成员完成情况',
  )[0];
  assert(table);
  assert.deepEqual(find(table, (n) => n.type === 'th').map(textOf), [
    '成员 / 身份快照',
    '完成进度',
    '操作',
  ]);
  const copy = textOf(table);
  for (const label of ['合成实名甲', '合成实名乙', '未填写姓名', '已注销成员', '历史成员'])
    assert(copy.includes(label));
  for (const hidden of [
    '22345678',
    '32345678',
    '42345678',
    '52345678',
    '昵称甲',
    '任务状态',
    '核验与账号',
  ])
    assert(!copy.includes(hidden), hidden);
  const bars = find(table, (n) => n.props.role === 'progressbar');
  assert.equal(bars.length, 5);
  assert.deepEqual(
    bars.slice(0, 3).map((n) => [n.props['aria-valuenow'], n.props['aria-valuemax']]),
    [
      [0, 8],
      [4, 8],
      [8, 8],
    ],
  );
  assert.deepEqual(
    bars.slice(0, 3).map((n) => n.children[0].props.style.width),
    ['0%', '50%', '100%'],
  );
  assert.equal(bars[1].props['aria-label'], '合成实名乙的做题进度');
  assert.equal(bars[1].props['aria-valuetext'], '已完成 4 / 8 题');
  await click('逐题证据');
  assert(textOf(mounted.root).includes('合成实名甲 · 逐题证据'));
  assert(calls.some((c) => c.url === '/api/admin/training-tasks/17/progress/1'));
  await set('成员搜索', '合成实名乙');
  const form = find(mounted.root, (n) => n.type === 'form' && textOf(n).includes('成员搜索'))[0];
  await form.props.onSubmit({ preventDefault() {} });
  await settle();
  assert(
    calls.some(
      (c) =>
        c.url.includes('/progress?') &&
        new URL(c.url, location.origin).searchParams.get('search') === '合成实名乙',
    ),
  );
});
