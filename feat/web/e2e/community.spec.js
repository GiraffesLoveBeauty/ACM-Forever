import { test, expect } from '@playwright/test';

const password = 'Browser-fixture-only!2026';
async function login(page, qq = '10000001', next = '/index.html') {
  await page.goto('/login.html?next=' + encodeURIComponent(next));
  await page.getByLabel('用户名 / QQ').fill(qq);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(next.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
}
async function noHorizontalOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
}

test('public entry, responsive feed and protected editor login return', async ({ page }) => {
  await page.goto('/index.html');
  await expect(page.locator('.forum-post-card').first()).toBeVisible();
  await noHorizontalOverflow(page);
  await page.goto('/compose.html');
  await expect(page).toHaveURL(/login\.html\?next=/);
  await page.getByLabel('用户名 / QQ').fill('10000001');
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '发布新话题' })).toBeVisible();
  await expect(page.getByRole('link', { name: /管理后台/ })).toHaveCount(0);
  expect((await page.request.get('/api/forum/moderation/posts')).status()).toBe(403);
  expect((await page.request.get('/admin.html')).status()).toBe(403);
  await noHorizontalOverflow(page);
});

test('Markdown reimport replaces title and a saved draft survives reload', async ({ page }) => {
  page.on('dialog', (dialog) => dialog.accept());
  await login(page, '10000002', '/compose.html');
  await page.getByLabel('选择版块').selectOption('2');
  const file = (name) => ({
    name: name + '.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# ' + name + '\n\n导入测试正文。'),
  });
  await page.getByLabel('选择 Markdown 文件').setInputFiles(file('第一份标题'));
  await expect(page.getByLabel('话题标题')).toHaveValue('第一份标题');
  await page.getByLabel('选择 Markdown 文件').setInputFiles(file('第二份标题'));
  await expect(page.getByLabel('话题标题')).toHaveValue('第二份标题');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await expect(page).toHaveURL(/draft_id=\d+/);
  await expect(page.locator('.compose-save-state')).toContainText('保存');
  await page.reload();
  await expect(page.getByLabel('话题标题')).toHaveValue('第二份标题');
  await expect(page.getByLabel('Markdown 正文')).toHaveValue(/导入测试正文。/);
  await page.getByRole('button', { name: '删除草稿', exact: true }).click();
  await expect(page.getByLabel('话题标题')).toBeEmpty();
});

test('submit, moderate, comment, reply and author deletion use the real API', async ({
  page,
  browser,
}, info) => {
  const title = '端到端投稿 ' + info.project.name + ' attempt ' + info.retry;
  await login(page, '10000001', '/compose.html');
  await page.getByLabel('选择版块').selectOption('2');
  await page.getByLabel('话题标题').fill(title);
  await page.getByLabel('Markdown 正文').fill('## 测试思路\n\n这是经过审核后公开的测试内容。');
  const submitted = page.waitForResponse(
    (r) => /\/drafts\/\d+\/submit$/.test(r.url()) && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '提交审核', exact: true }).click();
  const result = await submitted;
  expect(result.status()).toBe(201);
  const { id } = await result.json();
  // A successful submission can finish at the forum or its own review-progress page.
  await expect(page).toHaveURL(
    (url) =>
      url.pathname === '/index.html' ||
      (url.pathname === '/my-post.html' && url.searchParams.get('id') === String(id)),
  );
  const admin = await browser.newContext({
    baseURL: info.project.use.baseURL || new URL(page.url()).origin,
  });
  try {
    const reviewer = await admin.newPage();
    await login(reviewer, '10000003', '/admin.html?section=moderation');
    const card = reviewer.locator('.forum-moderation-card').filter({ hasText: title });
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: '通过并发布' }).click();
    await expect(card).toHaveCount(0);
    await page.goto('/post.html?id=' + id);
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await noHorizontalOverflow(page);
    await page.locator('.forum-comment-form textarea').fill('成员的测试评论');
    await page.getByRole('button', { name: '发布评论' }).click();
    await expect(page.locator('.plain-comment', { hasText: '成员的测试评论' })).toBeVisible();
    await reviewer.goto('/post.html?id=' + id);
    await reviewer
      .locator('.forum-comment')
      .filter({ hasText: '成员的测试评论' })
      .getByRole('button', { name: '回复', exact: true })
      .click();
    await reviewer.locator('.forum-comment-form textarea').fill('审核员的测试回复');
    await reviewer.getByRole('button', { name: '发布评论' }).click();
    await expect(
      reviewer.locator('.forum-comment-reply', { hasText: '审核员的测试回复' }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.locator('.forum-comment-reply', { hasText: '审核员的测试回复' }),
    ).toBeVisible();
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '删除帖子' }).click();
    await expect(page).toHaveURL(/index\.html$/);
    expect((await admin.request.get('/api/forum/posts/' + id)).status()).toBe(404);
  } finally {
    await admin.close();
  }
});
