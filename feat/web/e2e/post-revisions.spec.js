import { test, expect } from '@playwright/test';

test('author revises, reviewer rejects and author resubmits the same post', async ({
  page,
  context,
  browser,
}, info) => {
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
  });
  const { csrf_token } = await login.json();
  const created = await context.request.post('/api/forum/posts', {
    headers: { 'X-CSRF-Token': csrf_token },
    data: { title: '需要完善的算法说明', body: '这是原始算法说明。', category_id: 2 },
  });
  const { id } = await created.json();
  const reviewer = await browser.newContext({
    baseURL: new URL(page.url() === 'about:blank' ? info.project.use.baseURL : page.url()).origin,
  });
  try {
    await reviewer.request.post('/api/auth/login', {
      data: { qq_id: '10000003', password: 'Browser-fixture-only!2026' },
    });
    const admin = await reviewer.newPage();
    await admin.goto('/admin.html?section=moderation');
    const card = admin.locator('.forum-moderation-card').filter({ hasText: '需要完善的算法说明' });
    await card.locator('textarea').fill('请补充复杂度说明');
    await card.getByRole('button', { name: '退回', exact: true }).click();
    await page.goto('/my-post.html?id=' + id);
    await expect(page.getByText('退回原因：请补充复杂度说明', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '修改后重新投稿', exact: true }).click();
    await expect(page.getByRole('heading', { name: '修改帖子', exact: true })).toBeVisible();
    await page.getByLabel('话题标题').fill('已经补充的算法说明');
    await page.getByLabel('Markdown 正文').fill('## 复杂度\n\n时间复杂度 O(n log n)。');
    await page.getByRole('button', { name: '提交审核', exact: true }).click();
    await expect(page).toHaveURL(new RegExp('my-post.html\\?id=' + id + '$'));
    await expect(page.getByText('等待审核', { exact: true })).toBeVisible();
    await page.getByText(/第 1 版/).click();
    await expect(page.getByText('这是原始算法说明。', { exact: true })).toBeVisible();
    await admin.reload();
    await admin
      .locator('.forum-moderation-card')
      .filter({ hasText: '已经补充的算法说明' })
      .getByRole('button', { name: '通过并发布', exact: true })
      .click();
    await page.getByRole('button', { name: '刷新状态', exact: true }).click();
    await page.getByRole('link', { name: '查看已发布话题' }).click();
    await expect(
      page.getByRole('heading', { name: '已经补充的算法说明', exact: true }),
    ).toBeVisible();
  } finally {
    await reviewer.close();
  }
});
