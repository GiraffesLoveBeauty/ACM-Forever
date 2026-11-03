import { test, expect } from '@playwright/test';

test('comments and replies preview Markdown, math and copyable code safely', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000002', password: 'Browser-fixture-only!2026' },
  });
  expect(login.status()).toBe(200);
  await page.goto('/post.html?id=29');
  const source =
    '**思路说明**\n\n$a^2+b^2=c^2$\n\n```cpp\nint main() { return 42; }\n```\n\n<script>window.commentXss=1</script>\n<img src=x onerror="window.commentXss=1">';
  await page.getByLabel('评论内容', { exact: true }).fill(source);
  await page.getByRole('button', { name: '预览评论', exact: true }).click();
  const preview = page.getByLabel('评论预览');
  await expect(preview.locator('strong')).toHaveText('思路说明');
  await expect(preview.locator('.katex').first()).toBeVisible();
  await expect(preview.locator('.hljs-keyword').first()).toBeVisible();
  await expect(preview.locator('script,img,[onerror]')).toHaveCount(0);
  await preview.getByRole('button', { name: '复制代码', exact: true }).click();
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(
    'int main() { return 42; }\n',
  );
  const posted = page.waitForResponse(
    (r) => r.url().endsWith('/posts/29/comments') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '发布评论', exact: true }).click();
  expect((await posted).status()).toBe(201);
  const comment = page.locator('.forum-comment').filter({ hasText: '思路说明' }).last();
  await expect(comment.locator('strong')).toHaveText('思路说明');
  await expect(comment.locator('.katex').first()).toBeVisible();
  await comment.getByRole('button', { name: '回复', exact: true }).click();
  await expect(page.getByLabel('评论内容', { exact: true })).toBeFocused();
  await page.getByLabel('评论内容', { exact: true }).fill('```python\nprint(42)\n```');
  await page.getByRole('button', { name: '发布评论', exact: true }).click();
  await expect(comment.locator('.forum-comment-reply .hljs-built_in')).toBeVisible();
  await page.reload();
  await expect(
    page.locator('.forum-comment-reply code').filter({ hasText: 'print(42)' }).last(),
  ).toBeVisible();
  expect(await page.evaluate(() => window.commentXss)).toBeUndefined();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
});

test('a failed comment preserves the source for retry', async ({ page, context }) => {
  await context.request.post('/api/auth/login', {
    data: { qq_id: '10000002', password: 'Browser-fixture-only!2026' },
  });
  await page.goto('/post.html?id=28');
  await page.getByLabel('评论内容', { exact: true }).fill('**需要保留的回复**');
  await page.route('**/api/forum/posts/28/comments', (route) =>
    route.fulfill({ status: 503, json: { message: '合成网络故障' } }),
  );
  await page.getByRole('button', { name: '发布评论', exact: true }).click();
  await expect(page.getByLabel('评论内容', { exact: true })).toHaveValue('**需要保留的回复**');
  await page.unroute('**/api/forum/posts/28/comments');
  await page.getByRole('button', { name: '发布评论', exact: true }).click();
  await expect(
    page.locator('.forum-comment strong').filter({ hasText: '需要保留的回复' }).last(),
  ).toBeVisible();
});
