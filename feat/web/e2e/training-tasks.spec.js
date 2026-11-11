import { test, expect } from '@playwright/test';
const password = 'Browser-fixture-only!2026';
const local = (stamp) => new Date(stamp + 8 * 3600000).toISOString().slice(0, 16);
async function login(context, qq) {
  const response = await context.request.post('/api/auth/login', { data: { qq_id: qq, password } });
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token;
}

test('assigned task publish, frozen progress, member entry and statement round trip', async ({
  page,
  context,
}, testInfo) => {
  await login(context, '10000003');
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/admin.html?section=training');
  await page.getByRole('button', { name: '＋ 新建训练任务', exact: true }).click();
  const title = '端到端题单 ' + testInfo.project.name + ' ' + Date.now();
  await page.getByLabel('任务标题', { exact: true }).fill(title);
  await page.getByLabel('训练说明', { exact: true }).fill('合成数据验收：所有题均为必做题。');
  await page.getByLabel('标准题号', { exact: true }).fill('1A 2A 1A');
  await page.getByRole('button', { name: '校验并添加题号', exact: true }).click();
  await expect(page.getByText('合成训练题一', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '下一步', exact: true }).click();
  await page.getByLabel('训练任务测试组', { exact: true }).check();
  await page.getByLabel('开始时间', { exact: true }).fill(local(Date.now() - 2 * 86400000));
  await page.getByRole('button', { name: '保存并预览发放', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: '训练任务未开户成员' })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认发布任务', exact: true })).toBeDisabled();
  await page.getByLabel('我已确认以上排除原因，仍向有效成员发放。', { exact: true }).check();
  await page.screenshot({ path: testInfo.outputPath('publish-preview.png'), fullPage: true });
  await page.getByRole('button', { name: '确认发布任务', exact: true }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  const taskId = new URL(page.url()).searchParams.get('task_id');
  await page.getByRole('button', { name: '完成情况', exact: true }).click();
  const member = page.getByRole('row').filter({ hasText: '训练任务成员A' });
  await expect(member).toContainText('1 / 2 题');
  await member.getByRole('button', { name: '逐题证据', exact: true }).click();
  await expect(page.getByText(/提交 #801/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('admin-progress.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await login(context, '10000118');
  await page.goto('/home.html');
  const shortcuts = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: '训练与题目', exact: true }) })
    .first();
  expect(await shortcuts.getByRole('link').allTextContents()).toEqual([
    '今日训练',
    '训练任务',
    '题库',
    '赛事复盘',
    '修改密码',
  ]);
  await shortcuts.getByRole('link', { name: '训练任务', exact: true }).click();
  const card = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) });
  await card.getByRole('link', { name: '查看任务 ↗', exact: true }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  await expect(page.getByText(/提交 #801/)).toBeVisible();
  await page.route('**/api/me/training-tasks/*/refresh', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ message: '合成同步服务暂不可用，已有进度保留。' }),
    }),
  );
  await page.getByRole('button', { name: '刷新进度', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('已有进度保留');
  await expect(page.getByText('1 / 2 题', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('member-detail-light.png'), fullPage: true });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: testInfo.outputPath('member-detail-dark.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('link', { name: '查看题目', exact: true }).first().click();
  await page.getByRole('link', { name: '← 返回训练任务', exact: true }).click();
  await expect(page).toHaveURL(new RegExp('training-tasks.html.*task_id=' + taskId));
  expect((await context.request.get('/api/admin/training-tasks')).status()).toBe(403);
  expect(errors).toEqual([]);
});

test('unsaved internal task navigation keeps editor and query history stable', async ({
  page,
  context,
}) => {
  await login(context, '10000003');
  await page.goto('/admin.html?section=training&task_id=new&tab=edit&step=1');
  await page.getByLabel('任务标题', { exact: true }).fill('尚未保存的草稿');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '返回列表', exact: true }).click();
  await expect(page.getByLabel('任务标题', { exact: true })).toHaveValue('尚未保存的草稿');
  expect(new URL(page.url()).searchParams.get('task_id')).toBe('new');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '返回列表', exact: true }).click();
  await expect(page.getByRole('button', { name: '＋ 新建训练任务', exact: true })).toBeVisible();
});

test('anonymous direct links preserve the full task destination', async ({ page }) => {
  await page.goto('/training-tasks.html?task_id=17&tab=history');
  await expect(page.getByRole('heading', { name: '欢迎回来', exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.get('next')).toBe(
    '/training-tasks.html?task_id=17&tab=history',
  );
});
