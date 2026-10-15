import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { setAuth } from '../src/lib/api.js';
import { originalProblemUrl, renderProblemContent } from '../src/lib/problem-content.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Problem = (await import(await loadSfc('src/views/Problem.vue'))).default;
const Problems = (await import(await loadSfc('src/admin/Problems.vue'))).default;
const keys = ['document', 'Document', 'Node', 'ShadowRoot', 'navigator', 'fetch', 'location'];
const originals = new Map(
  keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const sample = { index: 1, input: ' 1 2\n3 4 \n', output: '<answer>\n$$$literal$$$\n' };
const saved = (extra = {}) => ({
  platform: 'codeforces',
  problem_id: 'cf_1843A',
  problem_name: 'Saved Example',
  problem_url: 'https://codeforces.com/contest/1843/problem/A',
  tags: ['math'],
  problem_rating: 800,
  statement_language: 'en',
  content_available: true,
  statement_html:
    '<p>Solve $$$x &lt; y$$$.</p><div class="sample-test"><div class="input"><pre>old</pre></div><div class="output"><pre>old</pre></div></div>',
  statement_fetched_at: '2026-10-15T01:00:00Z',
  last_fetch_status: 'ok',
  samples: [sample],
  ...extra,
});
let dom, mounted, calls, copied, responseData, responseStatus, holdId, held;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => {
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://127.0.0.1:8088/problem.html',
  });
  for (const key of ['document', 'Document', 'Node', 'ShadowRoot'])
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      writable: true,
      configurable: true,
    });
  Object.defineProperty(globalThis, 'navigator', {
    value: {
      clipboard: {
        async writeText(value) {
          copied.push(value);
        },
      },
    },
    configurable: true,
  });
  globalThis.location = {
    pathname: '/problem.html',
    search: '',
    assign() {
      throw Error('Unexpected redirect');
    },
  };
  mounted = null;
  calls = [];
  copied = [];
  held = [];
  holdId = '';
  responseData = saved();
  responseStatus = 200;
  setAuth(
    { authenticated: true, qq_id: '12345678', role: 'member', csrf_token: 'fixture-csrf' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (holdId && url.endsWith('/' + holdId))
      return new Promise((resolve) =>
        held.push(() => resolve(response(saved({ problem_id: holdId, problem_name: 'Stale' })))),
      );
    if (url === '/api/admin/database') return response({ initialized: true, platforms: [] });
    if (url === '/api/tasks') return response([]);
    if (url.startsWith('/api/problems?') || url.startsWith('/api/me/problems?'))
      return response({ items: [saved()], total: 1 });
    if (/^\/api\/(me\/)?problems\/[^/]+\/[^/]+$/.test(url))
      return response(responseData, responseStatus);
    throw Error('Unexpected request: ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  held.forEach((resolve) => resolve());
  await settle();
  setAuth({ authenticated: false }, true);
  dom.window.close();
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});
after(cleanupCompiled);
async function page(
  component = Problem,
  path = '/problem.html?platform=codeforces&problem_id=cf_1843A',
) {
  mounted = await mount(
    component,
    [
      { path: '/problem.html', component: Problem },
      { path: '/admin.html', component: Problems },
      { path: '/problem-bank.html', component: Problems },
    ],
    path,
  );
  return mounted;
}
function element(id) {
  return find(mounted.root, (node) => node.props.id === id)[0];
}
function parsed(detail) {
  const result = renderProblemContent(detail);
  const container = document.createElement('div');
  container.innerHTML = result.html;
  return { container, ...result };
}

test('CF samples stay embedded, retain whitespace/literal markup and receive copy controls', () => {
  const { container, samplesEmbedded } = parsed(saved());
  assert.equal(samplesEmbedded, true);
  assert.equal(container.querySelector('.input pre').textContent, sample.input);
  assert.equal(container.querySelector('.output pre').textContent, sample.output);
  assert.equal(container.querySelectorAll('button[data-sample-index="0"]').length, 2);
  assert.equal(container.querySelectorAll('answer').length, 0);
  assert.equal(container.querySelectorAll('pre math').length, 0);
  assert.equal(container.querySelectorAll('p math').length, 1);
});

test('AtCoder sample headings and var formulas render without duplicating samples', () => {
  const { container, samplesEmbedded } = parsed(
    saved({
      platform: 'atcoder',
      statement_html:
        '<h3>Problem Statement</h3><p><var>N^2</var></p><h3>Sample Input 1</h3><pre>1</pre><h3>Sample Output 1</h3><pre>2</pre>',
    }),
  );
  assert.equal(samplesEmbedded, true);
  assert.equal(container.querySelectorAll('var math').length, 1);
  assert.equal(container.querySelectorAll('pre')[0].textContent, sample.input);
});

test('statement HTML cannot inject scripts, actions, global styles or fake copy controls', () => {
  const { container } = parsed(
    saved({
      statement_html:
        '<script>alert(1)</script><iframe src="https://evil.test"></iframe><svg onload="alert(1)"></svg><div id="app" class="admin-console section-title" style="position:fixed" onclick="alert(1)" data-sample-index="9">Safe</div><button data-sample-index="0" data-sample-kind="input">Fake</button><a href="javascript:alert(1)">bad</a><a href="https://user:pass@evil.test">credentials</a>',
      samples: [],
    }),
  );
  assert.equal(
    container.querySelector('script,iframe,svg,button,[style],[onclick],[id],[data-sample-index]'),
    null,
  );
  assert.equal(container.querySelector('div').className, 'section-title');
  assert.equal(container.querySelector('a[href]'), null);
});

test('only trusted HTTPS images are retained and external links are isolated', () => {
  const { container } = parsed(
    saved({
      statement_html:
        '<img src="http://img.atcoder.jp/test.png"><img src="https://evil.test/a.png" alt="diagram unavailable"><img src="https://codeforces.com.evil.test/a.png"><a href="https://atcoder.jp/">source</a>',
      samples: [],
    }),
  );
  assert.equal(container.querySelectorAll('img').length, 1);
  assert.equal(container.querySelector('img').src, 'https://img.atcoder.jp/test.png');
  assert.equal(container.querySelector('img').getAttribute('referrerpolicy'), 'no-referrer');
  assert.ok(container.textContent.includes('diagram unavailable'));
  assert.equal(container.querySelector('a').rel, 'noopener noreferrer');
});

test('plain statements remain text and KaTeX cannot enable trusted HTML or URLs', () => {
  const plain = '<img src=x onerror=alert(1)>\n  text\n';
  assert.equal(
    parsed(saved({ statement_html: '', statement_text: plain })).container.querySelector('pre')
      .textContent,
    plain,
  );
  const { container } = parsed(
    saved({
      statement_html: String.raw`<p>$$$\href{javascript:alert(1)}{click}$$$</p><p>$$x^2$$</p>`,
      samples: [],
    }),
  );
  assert.equal(container.querySelector('a,[href]'), null);
  assert.ok(container.querySelector('math[display="block"]'));
  assert.equal(originalProblemUrl('javascript:alert(1)'), '');
  assert.equal(originalProblemUrl('https://user:pass@codeforces.com/'), '');
});

test('both member and admin lists open the local viewer rather than problem_url', async () => {
  for (const role of ['member', 'admin']) {
    setAuth({ authenticated: true, qq_id: '12345678', role }, true);
    await page(Problems, role === 'member' ? '/problem-bank.html' : '/admin.html?section=problems');
    const link = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '打开题目')[0];
    assert.equal(link.props.href, '/problem.html?platform=codeforces&problem_id=cf_1843A');
    assert.equal(link.props.target, '_blank');
    mounted.unmount();
    mounted = null;
  }
});

test('local viewer reads member detail, shows saved content and exposes a separate original link', async () => {
  await page();
  assert.equal(calls[0].url, '/api/me/problems/codeforces/cf_1843A');
  assert.equal(element('problem-original').props.href, responseData.problem_url);
  assert.equal(element('problem-original').props.target, '_blank');
  const statement = document.createElement('div');
  statement.innerHTML = element('problem-statement').props.innerHTML;
  assert.equal(statement.querySelector('.input pre').textContent, sample.input);
  assert.equal(element('problem-samples'), undefined);
  assert.ok(textOf(mounted.root).includes('已采集题面'));
  assert.equal(document.title, 'Saved Example · ACM Forever');
  assert.equal(calls.length, 1, 'viewing never starts collection or calls an external OJ');
  const button = statement.querySelector('button');
  await element('problem-statement').props.onClick({ target: button, currentTarget: statement });
  await settle();
  assert.deepEqual(copied, [sample.input]);
  assert.ok(textOf(mounted.root).includes('已复制样例 1 输入'));
});

test('admin detail uses the admin API and retains content after a failed refresh', async () => {
  setAuth({ authenticated: true, qq_id: '12345678', role: 'root' }, true);
  responseData = saved({ last_fetch_status: 'failed' });
  await page();
  assert.equal(calls[0].url, '/api/problems/codeforces/cf_1843A');
  assert.ok(element('problem-statement'));
  assert.ok(textOf(mounted.root).includes('最近更新失败，展示上次保存的内容'));
  assert.equal(
    find(mounted.root, (node) => node.type === 'a' && textOf(node) === '← 返回题库')[0].props.href,
    '/admin.html?section=problems',
  );
});

test('catalog-only detail stays local, can reload and never automatically crawls', async () => {
  responseData = saved({
    content_available: false,
    statement_html: null,
    samples: [],
    last_fetch_status: 'never',
  });
  await page();
  assert.ok(textOf(mounted.root).includes('题面尚未采集'));
  assert.equal(element('problem-statement'), undefined);
  assert.ok(element('problem-original'));
  responseData = saved();
  await find(
    mounted.root,
    (node) => node.type === 'button' && textOf(node) === '重新检查',
  )[0].props.onClick();
  await settle();
  assert.ok(element('problem-statement'));
  assert.equal(calls.length, 2);
  assert.ok(calls.every((call) => !call.options.method || call.options.method === 'GET'));
});

test('unmatched sample layout falls back to local text and copy buttons', async () => {
  responseData = saved({ statement_html: '<p>Statement with no sample markup.</p>' });
  await page();
  assert.ok(element('problem-samples'));
  assert.deepEqual(find(element('problem-samples'), (node) => node.type === 'pre').map(textOf), [
    sample.input,
    sample.output,
  ]);
  await find(element('problem-samples'), (node) => node.type === 'button')[1].props.onClick();
  assert.deepEqual(copied, [sample.output]);
});

test('missing parameters and 404 show local errors rather than redirecting', async () => {
  await page(Problem, '/problem.html');
  assert.equal(calls.length, 0);
  assert.ok(textOf(mounted.root).includes('缺少题目平台或题号'));
  responseData = { message: '题库中没有这道题目。' };
  responseStatus = 404;
  await mounted.router.push('/problem.html?platform=atcoder&problem_id=missing');
  await settle();
  assert.ok(textOf(mounted.root).includes('题库中没有这道题目。'));
  assert.equal(element('problem-original'), undefined);
});

test('query changes cancel old detail requests and late responses cannot replace the new problem', async () => {
  holdId = 'old';
  await page(Problem, '/problem.html?platform=codeforces&problem_id=old');
  assert.equal(calls.length, 1);
  responseData = saved({ problem_id: 'new', problem_name: 'New problem' });
  await mounted.router.push('/problem.html?platform=codeforces&problem_id=new');
  await settle();
  assert.equal(calls[0].options.signal.aborted, true);
  held.forEach((resolve) => resolve());
  held = [];
  await settle();
  assert.equal(document.title, 'New problem · ACM Forever');
  assert.ok(!textOf(mounted.root).includes('Stale'));
  mounted.unmount();
  mounted = null;
});

test('leaving the page cancels its pending detail request', async () => {
  holdId = 'old';
  await page(Problem, '/problem.html?platform=codeforces&problem_id=old');
  mounted.unmount();
  mounted = null;
  assert.equal(calls[0].options.signal.aborted, true);
});
