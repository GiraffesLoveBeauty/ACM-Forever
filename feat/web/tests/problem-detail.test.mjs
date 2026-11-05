import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h, ref } from 'vue';
import { setAuth } from '../src/lib/api.js';
import { originalProblemUrl, renderProblemContent } from '../src/lib/problem-content.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';

const Problem = (await import(await loadSfc('src/views/Problem.vue'))).default;
const PdfPreview = (await import(await loadSfc('src/components/PdfPreview.vue'))).default;
const Problems = (await import(await loadSfc('src/admin/Problems.vue'))).default;
const MemberProblems = (await import(await loadSfc('src/views/MemberProblems.vue'))).default;
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
test('original plain-text statement shares subscript rendering with the translation',()=>{
  const root=dom.window.document.createElement('div');
  root.innerHTML=renderProblemContent({platform:'atcoder',statement_text:"Permutation P_1 to P'_N.",samples:[]},dom.window.document).html;
  assert.deepEqual([...root.querySelectorAll('math annotation')].map(n=>n.textContent),['P_1',"P'_N"]);
  assert.equal(root.querySelectorAll('.katex-html').length,2);
});
let dom, mounted, calls, copied, responseData, responseStatus, holdId, held, secondaryMissing, secondaryOverrides;
let pdfOpened, pdfRendered, pdfDestroyed, pdfHold, pdfDelayed, pdfFailure;
const renderer = {
  openPdf(src) {
    pdfOpened.push(src);
    const document = {
      numPages: 2,
      async getPage(number) {
        return {
          getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }),
          render(context) {
            pdfRendered.push({ number, viewport: context.viewport });
            return { promise: Promise.resolve(), cancel() {} };
          },
        };
      },
    };
    const promise = pdfFailure
      ? Promise.reject(Error('Unavailable'))
      : pdfHold
        ? new Promise((resolve) => pdfDelayed.push(() => resolve(document)))
        : Promise.resolve(document);
    return {
      promise,
      async destroy() {
        pdfDestroyed.push(src);
      },
    };
  },
};
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
  pdfOpened = [];
  pdfRendered = [];
  pdfDestroyed = [];
  pdfDelayed = [];
  pdfHold = false;
  pdfFailure = false;
  copied = [];
  held = [];
  holdId = '';
  responseData = saved();
  responseStatus = 200;
  secondaryMissing = false;
  secondaryOverrides = {};
  setAuth(
    { authenticated: true, qq_id: '12345678', role: 'member', csrf_token: 'fixture-csrf' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.startsWith('/api/secondary/problems/') && secondaryMissing)
      return response({message:'该题暂无二次处理结果'},404);
    if (url.startsWith('/api/secondary/problems/')) return response({
      problem_key: 'codeforces:1843:A', taxonomy_version: '0.3-draft', model: 'fixture-model',
      auto_tags: [{id:'enumeration',name_zh:'枚举',source:'ai'}],
      effective_tags: [{id:'enumeration',name_zh:'枚举',source:'ai',tag_kind:'specific'}],
      review_status:'auto', manual_history_count:0, manual_added_ids:[], manual_removed_ids:[],
      needs_review_reasons:[], annotation_status:'success', content_hash:'fixture-content',
      source_links:['https://codeforces.com/contest/1843/problem/A'],
      translation_status:'missing', translation_active:false, translation_task_states:[],
      ...secondaryOverrides,
    });
    if (holdId && url.endsWith('/' + holdId))
      return new Promise((resolve) =>
        held.push(() => resolve(response(saved({ problem_id: holdId, problem_name: 'Stale' })))),
      );
    if (url === '/api/admin/database') return response({ initialized: true, platforms: [] });
    if (url.startsWith('/api/admin/database/problems?'))
      return response({ items: [saved()], total: 1, page: 1 });
    if (url === '/api/tasks') return response([]);
    if (url.startsWith('/api/me/problems/tags?')) return response({ tags: ['math'] });
    if (url.startsWith('/api/me/problems?')) return response({ items: [saved()], total: 1 });
    if (/^\/api\/me\/problems\/[^/]+\/[^/]+\/state$/.test(url) && options.method === 'PUT')
      return response({ success: true });
    if (/^\/api\/(me\/)?problems\/[^/]+\/[^/]+$/.test(url))
      return response(responseData, responseStatus);
    throw Error('Unexpected request: ' + url);
  };
});
afterEach(async () => {
  mounted?.unmount();
  held.forEach((resolve) => resolve());
  pdfDelayed.forEach((resolve) => resolve());
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
      { path: '/problem-bank.html', component: MemberProblems },
      { path: '/my-problems.html', component: MemberProblems },
      { path: '/home.html', component: { render: () => null } },
    ],
    path,
    { loadPdfRenderer: async () => renderer },
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

for (const role of ['admin','root']) test(`new crawler-only problem keeps translation management entry for ${role}`, async () => {
  secondaryMissing=true;
  setAuth({authenticated:true,qq_id:'1',role,csrf_token:'fixture'},true);
  await page();
  const content=textOf(mounted.root);
  assert.ok(content.includes('这道题尚未进行二次处理'));
  assert.ok(!content.includes('二次处理数据暂不可用'));
  const link=find(mounted.root,n=>n.type==='a' && textOf(n).includes('后台管理'))[0];
  assert.ok(link);
  assert.ok(link.props.href.includes('action=translation'));
  assert.ok(link.props.href.includes('problem_id=cf_1843A'));
  assert.ok(calls.every(c=>!c.options.method || c.options.method==='GET'));
});

test('unprocessed problem shows a normal empty state without admin actions for member',async()=>{
  secondaryMissing=true;
  await page();
  assert.ok(textOf(mounted.root).includes('这道题尚未进行二次处理'));
  assert.equal(find(mounted.root,n=>n.type==='a' && textOf(n).includes('后台管理')).length,0);
});

test('refresh loads newly saved labels and translation without issuing an AI request',async()=>{
  await page();
  secondaryOverrides={
    effective_tags:[{id:'construction',name_zh:'构造',source:'ai',tag_kind:'specific'},
      {id:'bit_operations',name_zh:'位运算',source:'ai',tag_kind:'specific'}],
    translation_status:'auto',translation_active:true,translated_title:'模拟题中文标题',
    translation_validation_mode:'parse_only',
    translated_statement:'## 题目描述\n\n模拟中文译文。',
  };
  await find(mounted.root,n=>n.type==='button' && textOf(n)==='刷新标签与译文')[0].props.onClick();
  await settle();
  const content=textOf(mounted.root);
  assert.ok(content.includes('构造'));assert.ok(content.includes('位运算'));
  assert.ok(content.includes('模拟题中文标题'));
  assert.ok(content.includes('未进行本地内容一致性校验'));
  const article=find(mounted.root,n=>typeof n.props.innerHTML==='string' && n.props.innerHTML.includes('模拟中文译文'));
  assert.equal(article.length,1);
  assert.equal(calls.filter(c=>c.url.startsWith('/api/secondary/problems/')).length,2);
  assert.ok(calls.every(c=>!c.options.method || c.options.method==='GET'));
});

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
  assert.equal(container.querySelector('h3.statement-sample-heading button').dataset.sampleIndex,'0');
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

for (const role of ['member', 'admin', 'root']) {
  test(`${role} browses and favorites in the independent personal problem bank without choosing a QQ`, async () => {
    setAuth({ authenticated: true, qq_id: '12345678', role, csrf_token: 'fixture-csrf' }, true);
    const path = '/my-problems.html?platform=codeforces&page=2';
    await page(MemberProblems, path);
    assert.doesNotMatch(textOf(mounted.root), /成员 QQ|题库管理|拉取题目/);
    assert.equal(find(mounted.root, (node) => node.props.inputmode === 'numeric').length, 0);
    const list = calls.find((call) => call.url.startsWith('/api/me/problems?'));
    assert.ok(list);
    const query = new URL(list.url, 'http://localhost').searchParams;
    assert.equal(query.get('page'), '2');
    assert.equal(query.get('platform'), 'codeforces');
    assert.equal(query.has('qq_id'), false);
    assert.equal(query.has('owner_qq_id'), false);
    const link = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '查看题面')[0];
    assert.ok(link);
    const target = new URL(link.props.href, 'http://localhost');
    assert.equal(target.pathname, '/problem.html');
    assert.equal(target.searchParams.get('platform'), 'codeforces');
    assert.equal(target.searchParams.get('problem_id'), 'cf_1843A');
    assert.equal(target.searchParams.get('from'), path);
    const favorite = find(
      mounted.root,
      (node) => node.type === 'button' && textOf(node).trim() === '收藏',
    )[0];
    await favorite.props.onClick();
    await settle();
    const update = calls.find((call) => call.options.method === 'PUT');
    assert.equal(update.url, '/api/me/problems/codeforces/cf_1843A/state');
    assert.deepEqual(JSON.parse(update.options.body), { is_favorite: true });
    assert.equal(update.options.headers['X-CSRF-Token'], 'fixture-csrf');
    assert.ok(calls.filter((call) => call.url.startsWith('/api/me/problems?')).length >= 2);
    assert.equal(
      calls.some(
        (call) => call.url.startsWith('/api/admin/') || call.url.startsWith('/api/problems?'),
      ),
      false,
    );
  });
}

test('management opens saved database records in the local viewer and has no personal browsing list', async () => {
  setAuth({ authenticated: true, qq_id: '12345678', role: 'admin' }, true);
  await page(Problems, '/admin.html?section=problems');
  assert.equal(element('problem-list'), undefined);
  assert.doesNotMatch(textOf(mounted.root), /成员 QQ|收藏/);
  assert.equal(
    calls.some((call) => /^\/api\/(?:me\/)?problems\?/.test(call.url)),
    false,
  );
  const link = find(mounted.root, (node) => node.type === 'a' && textOf(node) === '查看题面')[0];
  assert.equal(link.props.href, '/problem.html?platform=codeforces&problem_id=cf_1843A');
  assert.equal(link.props.target, '_blank');
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
  assert.equal(calls.length, 2, 'reads local problem and local secondary results only');
  assert.ok(calls.every(call => call.url.startsWith('/api/') && (!call.options.method || call.options.method === 'GET')));
  assert.ok(textOf(mounted.root).includes('自动生效 · 未人工确认'));
  assert.ok(textOf(mounted.root).includes('当前没有已激活的真实中文译文'));
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
  assert.equal(calls.filter(call => !call.url.startsWith('/api/secondary/')).length, 2);
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

test('officially omitted output shows an explanation without an answer copy button', async () => {
  const note = 'Output omitted because it is too long. The minimum cost is <3739.378294998>.';
  responseData = saved({
    platform: 'atcoder',
    statement_html:
      '<h3>Sample Input 1</h3><pre>1\n</pre><h3>Sample Output 1</h3><p>Output omitted because it is too long.</p>',
    samples: [{ index: 1, input: '1\n', output: null, output_note: note }],
  });
  await page(Problem, '/problem.html?platform=atcoder&problem_id=arc021_4');
  const panel = element('problem-samples');
  assert.ok(textOf(panel).includes('样例 1 · 输出说明'));
  assert.ok(textOf(panel).includes(note));
  assert.deepEqual(find(panel, (node) => node.type === 'pre').map(textOf), ['1\n']);
  const buttons = find(panel, (node) => node.type === 'button');
  assert.deepEqual(
    buttons.map((button) => textOf(button).trim()),
    ['复制样例 1 输入'],
  );
  await buttons[0].props.onClick();
  assert.deepEqual(copied, ['1\n']);
});

test('official ZIP samples show input/output explanations and safe attachment links without copy buttons', async () => {
  const attachment = {
    url: 'https://img.atcoder.jp/example/samples.zip',
    name: '官方入出力例 ZIP',
  };
  responseData = saved({
    platform: 'atcoder',
    statement_html: '<p>Sample input and output are provided in an archive.</p>',
    samples: [
      {
        index: 1,
        input: null,
        output: null,
        input_note: 'Input is provided in the official archive.',
        output_note: 'Output is provided in the official archive.',
        attachments: [attachment],
      },
    ],
  });
  await page(Problem, '/problem.html?platform=atcoder&problem_id=attachment_only');
  const panel = element('problem-samples');
  assert.ok(textOf(panel).includes('样例 1 · 输入说明'));
  assert.ok(textOf(panel).includes(responseData.samples[0].input_note));
  assert.ok(textOf(panel).includes('样例 1 · 输出说明'));
  assert.ok(textOf(panel).includes(responseData.samples[0].output_note));
  assert.equal(find(panel, (node) => node.type === 'button').length, 0);
  assert.equal(find(panel, (node) => node.type === 'pre').length, 0);
  assert.deepEqual(copied, []);
  const links = find(panel, (node) => node.type === 'a');
  assert.equal(links.length, 1);
  assert.equal(links[0].props.href, attachment.url);
  assert.equal(links[0].props.target, '_blank');
  assert.equal(links[0].props.rel, 'noopener noreferrer');
  assert.equal(textOf(links[0]), attachment.name);
});

test('sample attachment links reject malformed lists, foreign hosts, credentials, ports and non-ZIP files', async () => {
  const invalid = [
    null,
    {},
    { url: 123 },
    { url: '/samples.zip' },
    { url: 'javascript:alert(1)' },
    { url: 'http://img.atcoder.jp/samples.zip' },
    { url: 'https://evil.test/samples.zip' },
    { url: 'https://img.atcoder.jp.evil.test/samples.zip' },
    { url: 'https://user:password@img.atcoder.jp/samples.zip' },
    { url: 'https://img.atcoder.jp:444/samples.zip' },
    { url: 'https://img.atcoder.jp/samples.txt' },
    { url: 'https://img.atcoder.jp/samples.zip/other' },
  ];
  responseData = saved({
    platform: 'atcoder',
    statement_html: '<p>Official attached samples.</p>',
    samples: [
      ...[undefined, null, {}, 'https://img.atcoder.jp/samples.zip', invalid].map(
        (attachments) => ({
          input: null,
          output: null,
          input_note: 'Input in ZIP.',
          output_note: 'Output in ZIP.',
          attachments,
        }),
      ),
      {
        input: null,
        output: null,
        input_note: 'Input in ZIP.',
        output_note: 'Output in ZIP.',
        attachments: [...invalid, { url: 'https://img.atcoder.jp/official/sample.ZIP', name: '' }],
      },
    ],
  });
  await page(Problem, '/problem.html?platform=atcoder&problem_id=attachment_only');
  const links = find(element('problem-samples'), (node) => node.type === 'a');
  assert.deepEqual(
    links.map((link) => link.props.href),
    ['https://img.atcoder.jp/official/sample.ZIP'],
  );
  assert.equal(textOf(links[0]), '官方样例 ZIP');
  assert.equal(find(element('problem-samples'), (node) => node.type === 'button').length, 0);
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

test('PDF detail opens saved bytes on this site for both members and administrators', async () => {
  for (const role of ['member', 'admin']) {
    setAuth({ authenticated: true, qq_id: '12345678', role }, true);
    responseData = saved({
      problem_id: 'cf_497D',
      statement_format: 'pdf',
      statement_html: null,
      statement_text: null,
      samples: [],
    });
    await page(Problem, '/problem.html?platform=codeforces&problem_id=cf_497D');
    const panel = element('problem-pdf');
    assert.ok(panel);
    assert.equal(element('problem-statement'), undefined);
    assert.ok(textOf(panel).includes('样例见 PDF 原文'));
    const preview = find(panel, (node) => node.type === 'canvas')[0];
    assert.ok(preview, 'PDF is rendered in the detail page');
    assert.equal(
      pdfOpened.at(-1),
      `/api/${role === 'member' ? 'me/' : ''}problems/codeforces/cf_497D/statement.pdf`,
    );
    assert.equal(pdfRendered.at(-1).number, 1);
    const link = find(panel, (node) => node.type === 'a')[0];
    assert.equal(
      link.props.href,
      `/api/${role === 'member' ? 'me/' : ''}problems/codeforces/cf_497D/statement.pdf`,
    );
    assert.equal(link.props.target, '_blank');
    assert.ok(!textOf(mounted.root).includes('0 组样例'));
    assert.ok(!textOf(mounted.root).includes('题面尚未采集'));
    assert.ok(element('problem-original'));
    mounted.unmount();
    mounted = null;
  }
});

test('HTML statements with no samples still show the stored statement', async () => {
  responseData = saved({
    statement_html: '<p>Print the answer. No input is provided.</p>',
    samples: [],
  });
  await page();
  assert.ok(element('problem-statement').props.innerHTML.includes('No input is provided.'));
  assert.equal(element('problem-samples'), undefined);
  assert.equal(element('problem-pdf'), undefined);
});

async function previewPage(source) {
  const component = { setup: () => () => h(PdfPreview, { src: source.value }) };
  mounted = await mount(component, [{ path: '/', component }], '/', {
    loadPdfRenderer: async () => renderer,
  });
}
function previewButton(label) {
  const button = find(
    mounted.root,
    (node) =>
      node.type === 'button' && (textOf(node) === label || node.props['aria-label'] === label),
  )[0];
  assert.ok(button, label);
  return button;
}
test('PDF page navigation and zoom redraw the document without fetching it again', async () => {
  await previewPage(ref('/api/me/problems/codeforces/cf_497D/statement.pdf'));
  assert.equal(previewButton('上一页').props.disabled, true);
  assert.ok(textOf(mounted.root).includes('第 1 / 2 页'));
  previewButton('下一页').props.onClick();
  await settle();
  assert.equal(pdfRendered.at(-1).number, 2);
  assert.equal(previewButton('下一页').props.disabled, true);
  previewButton('放大 PDF').props.onClick();
  await settle();
  assert.ok(Math.abs(pdfRendered.at(-1).viewport.width - 1000) < 0.001);
  previewButton('适应宽度').props.onClick();
  await settle();
  assert.equal(pdfRendered.at(-1).viewport.width, 800);
  assert.equal(pdfOpened.length, 1);
});
test('changing PDF source or leaving destroys old loading tasks and ignores delayed results', async () => {
  const source = ref('/old.pdf');
  pdfHold = true;
  await previewPage(source);
  assert.equal(pdfOpened.length, 1);
  source.value = '/new.pdf';
  pdfHold = false;
  await settle();
  assert.deepEqual(pdfDestroyed, ['/old.pdf']);
  assert.equal(pdfRendered.length, 1);
  pdfDelayed.forEach((resolve) => resolve());
  pdfDelayed = [];
  await settle();
  assert.equal(pdfRendered.length, 1);
  mounted.unmount();
  mounted = null;
  assert.deepEqual(pdfDestroyed, ['/old.pdf', '/new.pdf']);
});
test('PDF load errors expose retry and a retry can render successfully', async () => {
  pdfFailure = true;
  await previewPage(ref('/statement.pdf'));
  assert.ok(textOf(mounted.root).includes('PDF 加载失败'));
  pdfFailure = false;
  await previewButton('重新加载').props.onClick();
  await settle();
  assert.equal(pdfRendered.length, 1);
  assert.ok(!textOf(mounted.root).includes('PDF 加载失败'));
});
