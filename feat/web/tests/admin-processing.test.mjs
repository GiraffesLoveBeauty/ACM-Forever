import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { setAuth } from '../src/lib/api.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Problems = (await import(await loadSfc('src/admin/Problems.vue'))).default;
const Workbench = (await import(await loadSfc('src/components/AdminProblemProcessing.vue')))
  .default;
const keys = ['window', 'document', 'Document', 'Node', 'ShadowRoot', 'fetch', 'location'];
const originals = new Map(keys.map((k) => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
let dom, view, calls, executionAllowed, executionStatus, finishPost, savedJobs;
beforeEach(() => {
  dom = new JSDOM('<body/>', { url: 'http://localhost/admin.html?section=problems' });
  for (const k of ['window', 'document', 'Document', 'Node', 'ShadowRoot'])
    Object.defineProperty(globalThis, k, {
      value: dom.window[k],
      configurable: true,
      writable: true,
    });
  globalThis.location = { pathname: '/admin.html', search: '?section=problems', assign() {} };
  setAuth({ authenticated: true, qq_id: '10000002', role: 'admin', csrf_token: 'fixture' }, true);
  calls = [];
  view = null;
  executionAllowed=false;executionStatus='needs_translation';finishPost=null;
  savedJobs={};
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if(url.endsWith('/execute') && options.method==='POST'){
      if(finishPost)await finishPost;
      return new Response(JSON.stringify({status:'completed',message:'模拟执行完成',real_api_calls:0,usage:{total_tokens:30}}));
    }
    if (url.startsWith('/api/admin/database/problems?'))
      return new Response(
        JSON.stringify({
          total: 1,
          items: [
            {
              platform: 'atcoder',
              problem_id: 'mock_a',
              problem_name: '模拟爬虫题',
              tags: ['差分'],
              has_secondary: true,
              content_available: true,
              last_fetch_status: 'ok',
              sample_count: 2,
            },
          ],
          tag_facets: [{ id: 'difference_array', name_zh: '差分', count: 1 }],
        }),
      );
    if (url.startsWith('/api/admin/problem-processing/'))
      return new Response(
        JSON.stringify({
          title: '模拟爬虫题',
          problem_key: 'atcoder:mock:mock_a',
          edit_available: false,
          edit_block_reason: '尚未纳入标签持久目录',
          processing_status: 'ready',
          statement_preview: 'Synthetic statement',
          sample_count: 2,
          issues: [],
          raw_tags: [],
          language: { source_language: 'en', reason: '英文题面' },
          plan: {
            annotation: { status: 'needs_annotation' },
            translation: { status: 'needs_translation' },
          },
          execution_enabled: false,
          execution: {
            annotation:{can_execute:executionAllowed,status:executionStatus,revision:'a'.repeat(64),config_ready:true,request_settings:{model:'offline-fixture',base_url:'https://offline.invalid/v1'}},
            translation:{can_execute:executionAllowed,status:executionStatus,revision:'a'.repeat(64),config_ready:true,request_settings:{model:'offline-fixture',base_url:'https://offline.invalid/v1'}},
          },
          real_api_calls: 0,
          jobs:savedJobs,
          image_handling_notice:'默认保留原图及其相对位置，仅翻译文字；图片内文字不翻译。',
        }),
      );
    throw Error('Unexpected request ' + url);
  };
});
afterEach(() => {
  view?.unmount();
  dom.window.close();
  setAuth({ authenticated: false }, true);
  for (const [k, d] of originals) {
    if (d) Object.defineProperty(globalThis, k, d);
    else delete globalThis[k];
  }
});
after(cleanupCompiled);
async function page(component = Problems) {
  view = await mount(
    component,
    [{ path: '/admin.html', component }],
    '/admin.html?section=problems',
  );
}
test('admin defaults to crawler bank instead of initialization or collection', async () => {
  await page();
  assert.ok(textOf(view.root).includes('模拟爬虫题'));
  assert.equal(find(view.root, (n) => n.props.id === 'problem-sync-form').length, 0);
  assert.ok(calls.every((c) => c.url.startsWith('/api/admin/database/problems?')));
});
test('every crawler row exposes translation annotation and manual actions', async () => {
  await page();
  for (const label of ['AI 翻译', 'AI 标签', '人工标签'])
    assert.equal(
      find(view.root, (n) => n.type === 'button' && textOf(n).trim() === label).length,
      1,
    );
});
test('admin effective label filter is sent to backend', async () => {
  await page();
  await find(view.root, (n) => n.props['data-admin-tag'] === 'difference_array')[0].props.onClick();
  await settle();
  assert.ok(
    calls.some(
      (c) => new URL(c.url, 'http://local').searchParams.get('labels') === 'difference_array',
    ),
  );
});
test('members cannot mount the administrator tools or request crawler records', async () => {
  setAuth({ authenticated: true, qq_id: '10000001', role: 'member' }, true);
  await page();
  assert.equal(calls.length, 0);
});
test('AI action reads fresh crawler state and offers no execution POST', async () => {
  await page();
  await find(
    view.root,
    (n) => n.type === 'button' && textOf(n).trim() === 'AI 翻译',
  )[0].props.onClick();
  await settle();
  assert.ok(textOf(view.root).includes('AI 中文翻译预检'));
  assert.notEqual(
    find(view.root, (n) => n.type === 'button' && textOf(n).trim() === '执行 AI 翻译')[0]
      .props.disabled,
    undefined,
  );
  assert.ok(calls.some((c) => c.url === '/api/admin/problem-processing/atcoder/mock_a'));
  assert.ok(calls.every((c) => !c.options.method || c.options.method === 'GET'));
});

test('admin confirms exactly one translation POST and sees completion',async()=>{
  executionAllowed=true;await page();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='AI 翻译')[0].props.onClick();await settle();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='执行 AI 翻译')[0].props.onClick();await settle();
  assert.ok(textOf(view.root).includes('最多新增一次付费请求'));
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='确认执行单题')[0].props.onClick();await settle();
  const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(JSON.parse(posts[0].options.body),{task_type:'translation',revision:'a'.repeat(64),confirm:true});
  assert.equal(posts[0].options.headers['X-CSRF-Token'],'fixture');
  assert.ok(textOf(view.root).includes('模拟执行完成'));
});

test('root can open confirmation and cancelling sends no request',async()=>{
  setAuth({authenticated:true,qq_id:'10000002',role:'root',csrf_token:'fixture'},true);
  executionAllowed=true;await page();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='AI 标签')[0].props.onClick();await settle();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='执行 AI 标签')[0].props.onClick();await settle();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='取消')[0].props.onClick();await settle();
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
});

test('direct member mount has no preview or execution access',async()=>{
  setAuth({authenticated:true,qq_id:'10000001',role:'member'},true);
  await page(Workbench);assert.equal(calls.length,0);assert.ok(textOf(view.root).includes('仅限 admin 或 root'));
});

test('existing results disable paid execution',async()=>{
  executionStatus='reuse_existing';await page();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='AI 翻译')[0].props.onClick();await settle();
  const button=find(view.root,n=>n.type==='button' && textOf(n).trim()==='已有结果，无需调用')[0];
  assert.equal(button.props.disabled,true);await button.props.onClick();await settle();
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
});
test('unimported crawler manual action explains missing persistence without inventing tags', async () => {
  await page();
  await find(
    view.root,
    (n) => n.type === 'button' && textOf(n).trim() === '人工标签',
  )[0].props.onClick();
  await settle();
  assert.ok(textOf(view.root).includes('尚未纳入标签持久目录'));
  assert.ok(!calls.some((c) => c.options.method === 'POST'));
});

test('translation tab shows its own saved receipt rather than an annotation failure',async()=>{
  savedJobs={
    annotation:{task_type:'annotation',status:'blocked',message:'标签图片需复核'},
    translation:{task_type:'translation',status:'uncertain',message:'未取得可用响应，是否计费尚无法确认'},
  };
  await page();
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='AI 翻译')[0].props.onClick();await settle();
  assert.ok(textOf(view.root).includes('翻译任务：未取得可用响应'));
  assert.ok(textOf(view.root).includes('默认保留原图及其相对位置'));
  assert.ok(textOf(view.root).includes('本地请求尝试不等于中转站接收或计费成功'));
  assert.ok(!textOf(view.root).includes('标签任务：标签图片需复核'));
  await find(view.root,n=>n.type==='button' && textOf(n).trim()==='AI 标签' && n.props['aria-pressed']!==undefined)[0].props.onClick();await settle();
  assert.ok(textOf(view.root).includes('标签任务：标签图片需复核'));
  assert.ok(!textOf(view.root).includes('翻译任务：未取得可用响应'));
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
});
