import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/compose.html',
  runScripts: 'outside-only',
});
for (const name of [
  'window',
  'document',
  'Node',
  'Element',
  'HTMLElement',
  'SVGElement',
  'navigator',
  'location',
])
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });

const { createApp, h, nextTick, ref } = await import('vue');
const { markdown } = await import('../src/lib/markdown.js');
const { codeBlocks } = await import('../src/lib/code-blocks.js');
const { loadSfc, cleanupCompiled } = await import('./helpers/vue-harness.mjs');
const Editor = (await import(await loadSfc('src/components/MarkdownEditor.vue'))).default;
const View = (await import(await loadSfc('src/components/MarkdownView.vue'))).default;
const legacyRenderer = await readFile(
  new URL('../../api/acm_api/public/assets/forum-markdown.js', import.meta.url),
  'utf8',
);
const fence = (language, code) => '```' + language + '\n' + code + '```';
const cpp = '#include <iostream>\nint main() { std::cout << "你好 <AC>"; return 0; }\n';
const python = 'def solve(n):\n    # 保留缩进\n    return "AC" * n\n';
const java =
  'public class Main {\n    public static void main(String[] args) { System.out.println(42); }\n}\n';
let app, host, copied;
async function settle() {
  for (let i = 0; i < 4; i++) {
    await new Promise((resolve) => setImmediate(resolve));
    await nextTick();
  }
}
function open(source) {
  host.innerHTML = markdown(source);
  codeBlocks.mounted(host);
  return host;
}
function mount(component, props) {
  app = createApp(component, props);
  app.directive('forum-math', {});
  app.mount(host);
}
beforeEach(() => {
  copied = [];
  delete window.renderForumMarkdown;
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: async (text) => copied.push(text) },
  });
  delete document.execCommand;
  host = document.createElement('div');
  document.body.append(host);
});
afterEach(() => {
  app?.unmount();
  app = null;
  codeBlocks.beforeUnmount(host);
  host.remove();
});
after(async () => {
  await cleanupCompiled();
  dom.window.close();
});

for (const sharedRenderer of [false, true]) {
  test(`C++, Python and Java highlight safely with ${sharedRenderer ? 'shared math' : 'fallback'} rendering`, async () => {
    if (sharedRenderer) {
      window.marked = (await import('marked')).marked;
      window.DOMPurify = (await import('dompurify')).default;
      window.eval(legacyRenderer);
    }
    open([fence('cpp', cpp), fence('python', python), fence('java', java)].join('\n\n'));
    const codes = [...host.querySelectorAll('pre > code')];
    assert.deepEqual(
      codes.map((code) => code.textContent),
      [cpp, python, java],
    );
    assert.equal(host.querySelectorAll('code.hljs').length, 3);
    codes.forEach((code) => assert.ok(code.querySelector('.hljs-keyword')));
    assert.deepEqual(
      [...host.querySelectorAll('.markdown-code-language')].map((node) => node.textContent),
      ['C++', 'Python', 'Java'],
    );
    for (const button of host.querySelectorAll('.code-copy')) button.click();
    await settle();
    assert.deepEqual(copied, [cpp, python, java]);
    assert.equal(host.querySelectorAll('.code-copy-status').length, 3);
  });
}

test('language aliases highlight without guessing unknown or unlabelled code', () => {
  open(
    ['c++', 'cc', 'cxx', 'py', 'python3', 'PY3', 'JAVA']
      .map((language) => fence(language, 'return 1;\n'))
      .join('\n\n'),
  );
  assert.equal(host.querySelectorAll('code.hljs').length, 7);
  open(
    fence('constructor', '<unknown>& text\n') +
      '\n\n' +
      fence('', 'int main() {}\n') +
      '\n\n`return 1;`',
  );
  assert.equal(host.querySelectorAll('code.hljs').length, 0);
  assert.equal(host.querySelectorAll('.code-copy').length, 2);
  assert.equal(host.querySelector('pre code').textContent, '<unknown>& text\n');
  assert.equal(host.querySelector('p code span'), null);
});

test('code containing HTML and script text stays literal and is copied unchanged', async () => {
  const source =
    '<script>alert("x")</script>\n<img src=x onerror=alert(1)>\n</code><button data-copy>伪按钮</button>\n';
  open(fence('python', source));
  assert.equal(host.querySelector('script,img,[onerror],[data-copy]'), null);
  assert.equal(host.querySelector('code').textContent, source);
  assert.equal(host.querySelectorAll('button').length, 1);
  host.querySelector('.code-copy').click();
  await settle();
  assert.deepEqual(copied, [source]);
});

for (const denied of [false, true]) {
  test(`native copy fallback works when Clipboard API is ${denied ? 'denied' : 'absent'}`, async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: denied
        ? {
            writeText: async () => {
              throw Error('Denied');
            },
          }
        : undefined,
    });
    open(fence('cpp', cpp));
    const button = host.querySelector('.code-copy');
    button.focus();
    document.execCommand = (command) => {
      assert.equal(command, 'copy');
      copied.push(document.activeElement.value);
      return true;
    };
    button.click();
    await settle();
    assert.deepEqual(copied, [cpp]);
    assert.equal(document.activeElement, button);
    assert.equal(document.querySelector('textarea'), null);
    assert.equal(button.textContent, '已复制');
  });
}

test('copy failure gives actionable feedback and permits a successful retry', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
  document.execCommand = () => false;
  open(fence('python', python));
  const button = host.querySelector('.code-copy');
  button.click();
  await settle();
  assert.match(host.querySelector('[role=status]').textContent, /复制失败.*手动复制/);
  assert.equal(button.disabled, false);
  document.execCommand = () => true;
  button.click();
  await settle();
  assert.equal(button.textContent, '已复制');
});

test('rerendering replaces controls once and a late copy cannot change the new block', async () => {
  let release;
  navigator.clipboard.writeText = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  open(fence('python', python));
  codeBlocks.updated(host);
  assert.equal(host.querySelectorAll('.code-copy').length, 1);
  host.querySelector('.code-copy').click();
  host.innerHTML = markdown(fence('java', java));
  codeBlocks.updated(host);
  release();
  await settle();
  assert.equal(host.querySelectorAll('.code-copy').length, 1);
  assert.equal(host.querySelector('.code-copy').textContent, '复制代码');
  assert.equal(host.querySelector('code').textContent, java);
});

test('real editor preview highlights, copies and follows subsequent edits', async () => {
  const source = ref(fence('cpp', cpp));
  mount({ render: () => h(Editor, { modelValue: source.value, mode: 'split' }) });
  await settle();
  assert.ok(host.querySelector('.compose-preview .hljs-keyword'));
  host.querySelector('.code-copy').click();
  await settle();
  assert.deepEqual(copied, [cpp]);
  source.value = fence('python', python);
  await settle();
  assert.equal(host.querySelectorAll('.code-copy').length, 1);
  assert.equal(host.querySelector('code').textContent, python);
  host.querySelector('.code-copy').click();
  await settle();
  assert.deepEqual(copied, [cpp, python]);
});

test('Wiki language tabs retain one copy control per block after source updates', async () => {
  const source = ref(fence('cpp', cpp) + '\n\n' + fence('python', python));
  mount({ render: () => h(View, { source: source.value }) });
  await settle();
  assert.equal(host.querySelectorAll('.code-copy').length, 2);
  assert.equal(host.querySelectorAll('pre:not([hidden])').length, 1);
  host.querySelector('.code-languages button[data-index="1"]').click();
  const shown = host.querySelector('pre:not([hidden])');
  assert.equal(shown.querySelector('code').textContent, python);
  shown.querySelector('.code-copy').click();
  await settle();
  assert.deepEqual(copied, [python]);
  source.value = fence('java', java);
  await settle();
  assert.equal(host.querySelectorAll('.code-copy').length, 1);
  assert.equal(host.querySelector('.code-languages'), null);
});
