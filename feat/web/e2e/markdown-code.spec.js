import { test, expect } from '@playwright/test';

const cpp = '#include <iostream>\nint main() { std::cout << "你好 <AC>"; return 0; }\n';
const python = 'def solve(n):\n    # 保留缩进\n    return "AC" * n\n';
const java =
  'public class Main {\n    public static void main(String[] args) { System.out.println(42); }\n}\n';

// Windows native clipboards normalize LF to CRLF; retain all other whitespace.
const normalized = (text) => text.replace(/\r\n/g, '\n');

test('post code highlights, copies exact source and keeps a black monospace layout in every theme', async ({
  page,
  context,
}, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/post.html?id=30');
  const blocks = page.locator('.forum-article-body pre.markdown-code-block');
  await expect(blocks).toHaveCount(3);
  for (const [index, source] of [cpp, python, java].entries()) {
    const block = blocks.nth(index);
    await expect(block.locator('.hljs-keyword').first()).toBeVisible();
    await block.getByRole('button', { name: '复制代码', exact: true }).click();
    await expect(block.getByRole('status')).toHaveText('代码已复制。');
    expect(normalized(await page.evaluate(() => navigator.clipboard.readText()))).toBe(source);
  }
  for (const [template, theme] of [
    ['original', 'light'],
    ['original', 'dark'],
    ['minecraft', 'dark'],
  ]) {
    await page.evaluate(
      ([template, theme]) => {
        document.documentElement.dataset.customTheme = 'true';
        document.documentElement.dataset.designTemplate = template;
        document.documentElement.dataset.theme = theme;
        document.body.dataset.theme = theme;
      },
      [template, theme],
    );
    await expect(blocks.first()).toHaveCSS('background-color', 'rgb(0, 0, 0)');
    const code = blocks.first().locator('code');
    await expect(code).toHaveCSS('font-family', /Cascadia Code/);
    await expect(code.locator('.hljs-keyword').first()).not.toHaveCSS(
      'color',
      'rgb(230, 237, 243)',
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
  }
  await page.evaluate(() => {
    document.documentElement.dataset.designTemplate = 'original';
    document.documentElement.dataset.theme = 'dark';
    document.body.dataset.theme = 'dark';
    window.scrollTo(0, 0);
  });
  await page.screenshot({ path: info.outputPath('markdown-code.png'), fullPage: true });
});

test('native copy works when the Clipboard API is unavailable', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/post.html?id=30');
  const block = page.locator('.forum-article-body pre.markdown-code-block').first();
  await expect(block).toBeVisible();
  await page.evaluate(() => {
    const clipboard = navigator.clipboard;
    window.readTestClipboard = () => clipboard.readText();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
  });
  await block.getByRole('button', { name: '复制代码', exact: true }).click();
  await expect(block.getByRole('status')).toHaveText('代码已复制。');
  expect(normalized(await page.evaluate(() => window.readTestClipboard()))).toBe(cpp);
});

test('editor preview follows edits and long code scrolls without moving its copy button', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
  });
  expect(login.status()).toBe(200);
  await page.goto('/compose.html');
  const input = page.getByLabel('Markdown 正文');
  await input.fill('```cpp\n' + cpp + '```');
  await page.getByRole('button', { name: '预览', exact: true }).click();
  const blocks = page.locator('.compose-preview pre.markdown-code-block');
  await expect(blocks).toHaveCount(1);
  await expect(blocks.first().locator('.hljs-keyword').first()).toBeVisible();
  await blocks.first().getByRole('button', { name: '复制代码', exact: true }).click();
  await expect(blocks.first().getByRole('status')).toHaveText('代码已复制。');
  expect(normalized(await page.evaluate(() => navigator.clipboard.readText()))).toBe(cpp);
  await page.getByRole('button', { name: '编辑', exact: true }).click();
  const longCode = 'print("' + 'algorithm_'.repeat(50) + '")\n';
  await input.fill('```python\n' + longCode + '```');
  await page.getByRole('button', { name: '预览', exact: true }).click();
  await expect(blocks).toHaveCount(1);
  const code = blocks.first().locator('code');
  expect(await code.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  await code.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
  });
  const copy = blocks.first().getByRole('button', { name: '复制代码', exact: true });
  await expect(copy).toBeVisible();
  await copy.click();
  await expect(blocks.first().getByRole('status')).toHaveText('代码已复制。');
  expect(normalized(await page.evaluate(() => navigator.clipboard.readText()))).toBe(longCode);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
});
