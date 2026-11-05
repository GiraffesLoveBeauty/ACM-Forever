// Logic-only checks in a VM. No browser, HTTP connection or product demo data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'prototype/training-v0.2.0.js'), 'utf8');
function setup(offline) {
  let requests = 0;
  const elements = new Map(), storage = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', textContent: '', value: '', open: false,
      querySelectorAll: () => [], addEventListener() {}, classList: { toggle() {} },
      showModal() { this.open = true; }, close() { this.open = false; },
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    URLSearchParams, AbortController, setTimeout, clearTimeout, console,
    location: { search: offline ? '?offline=1' : '' }, navigator: { onLine: true },
    document: { getElementById: element, querySelectorAll: () => [], addEventListener() {} },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, val) => storage.set(key, val), removeItem: key => storage.delete(key) },
    AcmReader: { html: x => x, math() {} },
    fetch: async url => {
      requests++;
      let data;
      if (url.includes('/forum/posts?')) data = { rows: [], total: 0 };
      else if (url.includes('/community/leaderboard?')) data = { rows: [], total: 0 };
      else if (url.endsWith('/me/club/reviews')) data = [{ platform: 'luogu', problem_id: 'P1001', due: true }];
      else throw Error('Unexpected test request: ' + url);
      return { ok: true, status: 200, json: async () => data };
    },
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'prototype/templates.js'), 'utf8'), context);
  vm.runInContext(source, context);
  return { context, element, requests: () => requests };
}
(async () => {
  const offline = setup(true);
  await new Promise(setImmediate);
  const html = await vm.runInContext("render('templates')", offline.context);
  assert.match(html, /算法模板速查/);
  assert.match(html, /并查集/);
  assert.match(await vm.runInContext("render('compose')", offline.context), /离线：分类不可用/);
  await assert.rejects(vm.runInContext("request('/api/club/sheets')", offline.context), /离线预览/);
  assert.equal(offline.requests(), 0, 'offline mode must never call fetch');
  const online = setup(false);
  await new Promise(setImmediate);
  assert.match(await vm.runInContext("render('rank')", online.context), /排行榜/);
  await assert.rejects(vm.runInContext("render('sheets')", online.context), /未登录/);
  vm.runInContext("state.csrf='synthetic-test-csrf'", online.context);
  assert.match(await vm.runInContext("render('training')", online.context), /P1001/);
  vm.runInContext("dialog('first','保留输入'); dialog('second','替换输入')", online.context);
  assert.equal(online.element('popup-title').textContent, 'first');
  assert.equal(online.element('popup-body').innerHTML, '保留输入');
  assert.equal(vm.runInContext("esc('<script>')", online.context), '&lt;script&gt;');
  assert.equal(vm.runInContext("loginPayload('900002','test-only').qq_id", online.context), '900002');
  assert.equal(vm.runInContext("'qq_id' in loginPayload('legacy-test','test-only')", online.context), false);
  console.log('PASS: offline 0 fetch, templates/composer, public rank, login guard, due reviews, modal deduplication and escaping');
})().catch(error => { console.error(error); process.exitCode = 1; });
