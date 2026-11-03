import { test, expect } from '@playwright/test';

test('an untouched old tab cannot submit another tabs updated new-post draft', async ({
  page,
  context,
}) => {
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
  });
  const { csrf_token } = await login.json();
  const created = await context.request.post('/api/forum/drafts', {
    headers: { 'X-CSRF-Token': csrf_token },
    data: { title: '最初确认的普通新帖', body: '第一个标签页读取的正文。', category_id: 2 },
  });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  await page.goto('/compose.html?draft_id=' + id);
  await expect(page.getByLabel('Markdown 正文')).toHaveValue('第一个标签页读取的正文。');
  const second = await context.newPage();
  try {
    await second.goto('/compose.html?draft_id=' + id);
    await second.getByLabel('Markdown 正文').fill('另一个标签页已经保存的新正文。');
    const saved = second.waitForResponse(
      (response) =>
        response.url().endsWith('/api/forum/drafts/' + id) && response.request().method() === 'PUT',
    );
    await second.getByRole('button', { name: '保存草稿', exact: true }).click();
    expect((await saved).status()).toBe(200);
    const submitted = page.waitForResponse((response) =>
      response.url().endsWith(`/api/forum/drafts/${id}/submit`),
    );
    await page.getByRole('button', { name: '提交审核', exact: true }).click();
    expect((await submitted).status()).toBe(409);
    await expect(page).toHaveURL(new RegExp('compose.html\\?draft_id=' + id + '$'));
    await expect(page.getByLabel('Markdown 正文')).toHaveValue('第一个标签页读取的正文。');
    const current = await context.request.get('/api/forum/drafts/' + id);
    expect(current.status()).toBe(200);
    expect((await current.json()).body).toBe('另一个标签页已经保存的新正文。');
  } finally {
    await second.close();
    await context.request.delete('/api/forum/drafts/' + id, {
      headers: { 'X-CSRF-Token': csrf_token },
    });
  }
});

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
