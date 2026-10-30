import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { File } from 'node:buffer';
import { JSDOM } from 'jsdom';

// Initialize the DOM before importing Vue and DOMPurify so the tests mount real DOM.
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://127.0.0.1/wiki.html',
  runScripts: 'outside-only',
});
for (const name of [
  'window',
  'document',
  'Document',
  'Node',
  'Element',
  'HTMLElement',
  'SVGElement',
  'navigator',
  'location',
  'history',
  'localStorage',
])
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
const { createApp, h, nextTick, ref } = await import('vue');
const { createRouter, createMemoryHistory, RouterView } = await import('vue-router');
const { setAuth } = await import('../src/lib/api.js');
const { importMarkdownFile, missingImages, sourceFields } = await import(
  '../src/lib/markdown-source.js'
);
const { markdown } = await import('../src/lib/markdown.js');
const { loadSfc, cleanupCompiled } = await import('./helpers/vue-harness.mjs');
const Header = (await import(await loadSfc('src/components/Header.vue'))).default;
const Editor = (await import(await loadSfc('src/components/MarkdownEditor.vue'))).default;
const Wiki = (await import(await loadSfc('src/views/Wiki.vue'))).default;
const Pages = (await import(await loadSfc('src/components/WikiPages.vue'))).default;
const Compose = (await import(await loadSfc('src/views/Compose.vue'))).default;
const asset = '/api/markdown/assets/' + 'a'.repeat(32);
const nav = {
  categories: [
    { id: 1, name: '知识总览', parent_id: null, published_count: 1 },
    { id: 2, name: '数据结构', parent_id: 1, published_count: 1 },
  ],
  default_category_id: 1,
  navigation_version: 3,
};
const source = {
  title: '并查集',
  body: '## 路径压缩\n\n公开正文',
  summary: '',
  tags: ['图论'],
  aliases: ['DSU'],
  source: '',
  license: '',
  exercises: [],
};
let app, router, host, calls, releases, savedPage, conflict, holdCreate, failUpload, heldUpload;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
const settle = async () => {
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setImmediate(r));
    await nextTick();
  }
};
const q = (s) => host.querySelector(s);
const button = (word) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent.trim() === word);
async function input(node, value) {
  node.value = value;
  node.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  await settle();
}
async function click(word) {
  assert.ok(button(word), word);
  button(word).click();
  await settle();
}
async function mount(component, path, props = {}) {
  host = document.createElement('div');
  document.body.append(host);
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/wiki.html', component: Wiki },
      { path: '/admin.html', component: Pages },
      { path: '/compose.html', component: Compose },
      { path: '/elsewhere', component: { render: () => h('p', '其他页面') } },
    ],
  });
  await router.push(path);
  await router.isReady();
  app = createApp(component || { render: () => h(RouterView) }, props);
  app.directive('forum-math', () => {});
  app.use(router);
  app.mount(host);
  await settle();
}
beforeEach(() => {
  calls = [];
  releases = [];
  savedPage = null;
  conflict = false;
  holdCreate = false;
  failUpload = false;
  heldUpload = false;
  localStorage.clear();
  globalThis.confirm = () => true;
  globalThis.alert = () => {};
  setAuth(
    { authenticated: true, role: 'admin', qq_id: 'test-admin', csrf_token: 'test-only' },
    true,
  );
  globalThis.fetch = async (url, options = {}) => {
    const body =
      options.body instanceof FormData
        ? options.body
        : options.body
          ? JSON.parse(options.body)
          : null;
    calls.push({ url, body, signal: options.signal });
    if (url === '/api/markdown/assets') {
      if (heldUpload)
        return new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () =>
            reject(new DOMException('取消', 'AbortError')),
          );
        });
      if (failUpload) return response({ message: '合成上传错误' }, 503);
      return response({ url: asset, id: 'a'.repeat(32) }, 201);
    }
    if (url === '/api/wiki/navigation' || url === '/api/admin/wiki/categories')
      return response(nav);
    if (url === '/api/wiki/categories/1')
      return response({
        category: nav.categories[0],
        path: [nav.categories[0]],
        children: [nav.categories[1]],
      });
    if (url === '/api/wiki/categories/2')
      return response({ category: nav.categories[1], path: nav.categories, children: [] });
    if (url.startsWith('/api/wiki/pages?'))
      return response({
        items: [
          {
            ...source,
            slug: 'dsu',
            parent_name: '知识总览',
            category_name: '数据结构',
            updated_at: 1,
          },
        ],
        total: 1,
      });
    if (url === '/api/wiki/pages/dsu')
      return response({
        ...source,
        id: 1,
        slug: 'dsu',
        path: nav.categories,
        published_at: 1,
        maintainer: '维护者',
      });
    if (url.startsWith('/api/wiki/search?'))
      return new Promise((resolve) =>
        releases.push(() =>
          resolve(
            response({
              items: [
                {
                  ...source,
                  title: new URL(url, location.origin).searchParams.get('q'),
                  slug: 'dsu',
                },
              ],
              total: 1,
            }),
          ),
        ),
      );
    if (url.startsWith('/api/admin/wiki/pages?'))
      return response({
        items: savedPage
          ? [{ ...savedPage, title: savedPage.draft.title, category_name: '数据结构' }]
          : [],
        total: savedPage ? 1 : 0,
      });
    if (url === '/api/admin/wiki/pages' && options.method === 'POST') {
      if (holdCreate) await new Promise((resolve) => releases.push(resolve));
      savedPage = {
        id: 1,
        slug: body.slug,
        category_id: body.category_id,
        draft_revision_id: 1,
        version: 2,
        published_revision_id: null,
        draft: { ...source, ...body },
      };
      return response(savedPage);
    }
    if (url === '/api/admin/wiki/pages/1/revisions' && options.method === 'POST') {
      if (conflict) return response({ message: '版本冲突', code: 'version_conflict' }, 409);
      savedPage = {
        ...savedPage,
        draft: { ...source, ...body },
        version: savedPage.version + 1,
        draft_revision_id: savedPage.draft_revision_id + 1,
      };
      return response(savedPage);
    }
    if (url === '/api/admin/wiki/pages/1') return response(savedPage);
    if (url === '/api/admin/wiki/pages/1/revisions')
      return response([{ id: 1, title: source.title, published_at: 1 }]);
    if (url === '/api/forum/categories') return response([{ id: 1, name: '算法讨论' }]);
    if (url === '/api/forum/drafts' && !options.method) return response([]);
    if (url === '/api/forum/drafts' && options.method === 'POST')
      return response({ id: 12, ...body });
    if (url === '/api/forum/drafts/12' && options.method === 'PUT')
      return response({ id: 12, ...body });
    if (url === '/api/forum/drafts/12/submit') return response({ message: '待审核', id: 99 });
    if (url.startsWith('/api/wiki/')) return response({ message: '内容不可用' }, 404);
    throw Error('Unexpected request ' + url);
  };
});
afterEach(async () => {
  app?.unmount();
  app = null;
  router?.options.history.destroy();
  document.body.innerHTML = '';
  releases.forEach((r) => r());
  await settle();
  delete window.renderForumMarkdown;
});
after(async () => {
  await cleanupCompiled();
  dom.window.close();
});

test('shared Markdown import handles BOM, LF, fenced H1 and fallback filename without corrupting source', async () => {
  const parsed = await importMarkdownFile(
    new File(
      ['\uFEFF```cpp\r\n# 假标题\r\n```\r\n\r\n# **并查集**\r\n\r\n公式 $a+b$\r\n![图](a.png)'],
      '算法.markdown',
    ),
  );
  assert.equal(parsed.title, '并查集');
  assert.ok(parsed.body.includes('# 假标题'));
  assert.ok(parsed.body.includes('$a+b$'));
  assert.ok(!parsed.body.includes('\r'));
  assert.deepEqual(await importMarkdownFile(new File(['普通正文'], '无标题.md')), {
    title: '无标题',
    body: '普通正文',
  });
  await assert.rejects(importMarkdownFile(new File([new Uint8Array([255, 254])], 'bad.md')));
  await assert.rejects(importMarkdownFile(new File(['a'.repeat(102401)], 'large.md')), /100 KB/);
  await assert.rejects(importMarkdownFile(new File(['😀'.repeat(20001)], 'body.md')), /20000/);
  const emoji = await importMarkdownFile(
    new File(['# ' + '😀'.repeat(120) + '\n\n正文'], 'emoji.md'),
  );
  assert.equal(Array.from(emoji.title).length, 120);
});

test('both renderer paths reject foreign and local disk images and unsafe HTML while allowing controlled assets', async () => {
  const body = `![安全](${asset}) ![远程](https://example.test/a.png) ![本机](file:///secret.png)<img src="${asset}" onerror="alert(1)"><script>alert(1)</script>`;
  for (const shared of [false, true]) {
    if (shared) {
      window.marked = (await import('marked')).marked;
      window.DOMPurify = (await import('dompurify')).default;
      window.eval(
        await readFile(
          new URL('../../api/acm_api/public/assets/forum-markdown.js', import.meta.url),
          'utf8',
        ),
      );
    }
    const result = markdown(body);
    const target = document.createElement('div');
    target.innerHTML = result;
    assert.equal(target.querySelectorAll('img').length, 2);
    assert.ok(!target.querySelector('[onerror],script'));
    assert.ok(result.includes('图片待上传'));
    assert.ok(missingImages(body).includes('https://example.test/a.png'));
  }
});

test('editor import cancel and invalid input preserve the existing title and body', async () => {
  const title = ref('原题目'),
    body = ref('原正文');
  await mount(
    {
      render: () =>
        h(Editor, {
          title: title.value,
          modelValue: body.value,
          'onUpdate:title': (v) => (title.value = v),
          'onUpdate:modelValue': (v) => (body.value = v),
        }),
    },
    '/wiki.html',
  );
  const fileInput = q('[aria-label="选择 Markdown 文件"]');
  const choose = async (file) => {
    Object.defineProperty(fileInput, 'files', { configurable: true, value: [file] });
    fileInput.dispatchEvent(new dom.window.Event('change'));
    await settle();
  };
  globalThis.confirm = () => false;
  await choose(new File(['# 新标题\n\n新正文'], 'new.md'));
  assert.equal(body.value, '原正文');
  globalThis.confirm = () => true;
  await choose(new File([new Uint8Array([255])], 'bad.md'));
  assert.equal(title.value, '原题目');
  assert.equal(body.value, '原正文');
  await choose(new File(['# 新标题\n\n新正文'], 'new.md'));
  assert.equal(title.value, '新标题');
  assert.equal(body.value, '新正文');
});

test('upload failure keeps source and retry inserts at the original caret; unmount aborts pending upload', async () => {
  const body = ref('前后');
  const Parent = {
    render: () =>
      h(Editor, {
        modelValue: body.value,
        'onUpdate:modelValue': (v) => (body.value = v),
        title: '测试',
        documentType: 'wiki',
        documentId: 1,
      }),
  };
  await mount(Parent, '/wiki.html');
  const textarea = q('textarea');
  textarea.setSelectionRange(1, 1);
  const imageInput = q('[aria-label="选择图片"]');
  const choose = () => {
    Object.defineProperty(imageInput, 'files', {
      configurable: true,
      value: [new File(['synthetic'], 'graph.png', { type: 'image/png' })],
    });
    imageInput.dispatchEvent(new dom.window.Event('change'));
  };
  failUpload = true;
  choose();
  await settle();
  assert.equal(body.value, '前后');
  assert.ok(host.textContent.includes('合成上传错误'));
  failUpload = false;
  await click('重试上传');
  assert.equal(body.value, `前![graph](${asset})后`);
  heldUpload = true;
  choose();
  await settle();
  const call = calls.at(-1);
  app.unmount();
  app = null;
  await settle();
  assert.equal(call.signal.aborted, true);
});

test('reader uses actual article classification, gives members no management entry and preserves content after a failed query', async () => {
  setAuth({ authenticated: true, role: 'member', qq_id: 'member' }, true);
  await mount(null, '/wiki.html?slug=dsu&category=999');
  assert.ok(host.textContent.includes('公开正文'));
  assert.equal(host.textContent.includes('管理 Wiki'), false);
  assert.ok(q('.wiki-categories .active').textContent.includes('知识总览'));
  assert.equal(
    decodeURIComponent(q('.wiki-toc a').getAttribute('href')),
    '/wiki.html?slug=dsu&category=999#路径压缩',
  );
  await router.push('/wiki.html?slug=missing');
  await settle();
  assert.ok(host.textContent.includes('内容或分类不存在'));
  assert.ok(host.textContent.includes('公开正文'));
});

test('reader route replacement ignores late search responses and navigation supports browser history', async () => {
  await mount(null, '/wiki.html?q=旧搜索');
  await router.push('/wiki.html?q=新搜索');
  await settle();
  assert.equal(releases.length, 2);
  releases[1]();
  await settle();
  releases[0]();
  await settle();
  assert.ok(q('.wiki-article-card').textContent.includes('新搜索'));
  await router.push('/wiki.html?category=1');
  await settle();
  await router.push('/wiki.html?category=2');
  await settle();
  assert.ok(q('.wiki-article-card'));
  router.back();
  await settle();
  assert.ok(q('.wiki-subcategory'));
  assert.ok(!q('.wiki-article-card'));
});

test('new article saving serializes edits made during a request and does not deadlock its new route', async () => {
  await mount(null, '/admin.html?section=wiki&tab=pages');
  await input(q('input[maxlength="240"]'), '首次草稿');
  await input(q('textarea[aria-label="Markdown 正文"]'), '初始内容');
  holdCreate = true;
  button('保存草稿').click();
  await settle();
  assert.equal(releases.length, 1);
  // Simulate typing while an automatic save is already in flight.
  q('textarea[aria-label="Markdown 正文"]').value = '请求期间继续输入';
  q('textarea[aria-label="Markdown 正文"]').dispatchEvent(
    new dom.window.Event('input', { bubbles: true }),
  );
  releases[0]();
  await settle();
  assert.equal(savedPage.draft.body, '请求期间继续输入');
  assert.equal(router.currentRoute.value.query.page_id, '1');
  assert.equal(calls.filter((c) => c.url === '/api/admin/wiki/pages' && c.body).length, 1);
  assert.ok(host.textContent.includes('草稿已保存'));
});

test('409 preserves the editor, presents the server version and supports explicit reconciliation', async () => {
  savedPage = {
    id: 1,
    slug: 'dsu',
    category_id: 2,
    version: 2,
    draft_revision_id: 1,
    published_revision_id: 1,
    draft: { ...source },
  };
  await mount(null, '/admin.html?section=wiki&tab=pages&page_id=1');
  await input(q('textarea[aria-label="Markdown 正文"]'), '我的未保存内容');
  conflict = true;
  await click('保存草稿');
  assert.equal(q('textarea[aria-label="Markdown 正文"]').value, '我的未保存内容');
  assert.ok(host.textContent.includes('保存冲突：你的输入已保留'));
  assert.ok(localStorage.getItem('acm-wiki:test-admin:1').includes('我的未保存内容'));
  conflict = false;
  await click('保留输入，基于最新版本继续编辑');
  await click('保存草稿');
  assert.equal(savedPage.draft.body, '我的未保存内容');
});

test('forum still saves a shared-editor draft and protects local recovery before navigation', async () => {
  await mount(null, '/compose.html');
  assert.ok(q('textarea[aria-label="Markdown 正文"]'));
  const title = q('input[maxlength="240"]');
  assert.ok(title);
  await input(title, '论坛测试');
  await input(q('textarea[aria-label="Markdown 正文"]'), '共享编辑器正文');
  await router.push('/elsewhere');
  await settle();
  const draft = calls.find((c) => c.url === '/api/forum/drafts' && c.body);
  assert.ok(draft);
  assert.equal(draft.body.title, '论坛测试');
  assert.equal(draft.body.body, '共享编辑器正文');
});

test('leaving a new Wiki draft saves it without replacing the requested destination', async () => {
  await mount(null, '/admin.html?section=wiki&tab=pages');
  await input(q('input[maxlength="240"]'), '离开前保存');
  await input(q('textarea[aria-label="Markdown 正文"]'), '新草稿正文');
  await router.push('/admin.html?section=wiki&tab=categories');
  await settle();
  assert.equal(savedPage.draft.body, '新草稿正文');
  assert.equal(router.currentRoute.value.query.tab, 'categories');
  assert.equal(router.currentRoute.value.query.page_id, undefined);
});

test('online source validation counts Unicode points and forum recovery retains over-limit input', async () => {
  assert.equal(
    Array.from(sourceFields({ title: '😀'.repeat(120), body: '正文' }).title).length,
    120,
  );
  assert.throws(() => sourceFields({ title: '😀'.repeat(121), body: '正文' }), /120/);
  await mount(null, '/compose.html');
  await input(q('input[maxlength="240"]'), '长度错误恢复');
  const body = '长'.repeat(20001);
  await input(q('textarea[aria-label="Markdown 正文"]'), body);
  const values = Object.values(localStorage);
  assert.ok(values.some((value) => value.includes(body)));
});

test('Wiki login entry retains article query and heading hash', async () => {
  setAuth({ authenticated: false }, true);
  await mount(Header, '/wiki.html?slug=dsu#路径压缩');
  const link = [...host.querySelectorAll('a')].find((a) => a.textContent === '登录社区');
  assert.ok(link);
  assert.equal(
    decodeURIComponent(new URL(link.href).searchParams.get('next')),
    '/wiki.html?slug=dsu#路径压缩',
  );
});
