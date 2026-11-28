import { test, expect } from '@playwright/test';

test('an admin can re-enable only the selected Luogu account from the collapsed table', async ({
  page,
  context,
}, testInfo) => {
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000003', password: 'Browser-fixture-only!2026' },
  });
  expect(login.ok()).toBe(true);

  const index = testInfo.project.name === 'mobile' ? 2 : 1;
  const memberName = `同步中心测试成员${index}`;
  const memberId = `1000021${index}`;
  const row = page.getByRole('row').filter({ hasText: memberName });
  const other = page.getByRole('row').filter({ hasText: '同步中心测试成员3' });
  const action = { name: '重新开启洛谷同步', exact: true };

  await page.goto('/admin.html?section=sync-center');
  await page
    .getByRole('combobox', { name: '成员身份', exact: true })
    .selectOption('同步中心测试组');
  const status = page.getByRole('combobox', { name: '状态', exact: true });
  await status.selectOption('disabled');
  await expect(row.getByText('已停用', { exact: true })).toBeVisible();
  await expect(row.getByRole('button', { name: '+', exact: true })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await expect(row.getByRole('button', { name: '同步成员', exact: true })).toBeVisible();

  const resumed = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === `/api/admin/luogu-sync/${memberId}/enable`,
  );
  await row.getByRole('button', action).click();
  const response = await resumed;
  expect(response.status()).toBe(202);
  const task = await response.json();
  expect(task).toMatchObject({ success: true, task_id: expect.any(String) });
  await expect(page.getByRole('status').filter({ hasText: memberName })).toContainText(
    '同步任务已排队',
  );
  await expect(row).toHaveCount(0);
  await expect(other.getByRole('button', action)).toBeVisible();

  await status.selectOption('');
  await expect(row).toBeVisible();
  await expect(row.getByRole('button', action)).toHaveCount(0);
  await expect(row.getByText('已停用', { exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: '任务队列', exact: true }).click();
  await expect(page.getByText(`账号全量同步 · #${task.task_id}`)).toBeVisible();
});

test('the separate sync tasks entry is removed and its links still reach the queue', async ({
  page,
  context,
}) => {
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000003', password: 'Browser-fixture-only!2026' },
  });
  expect(login.ok()).toBe(true);

  const overview = '/admin.html?section=sync-center';
  const queue = overview + '&tab=queue';
  const queueHeading = page.getByRole('heading', { name: '任务队列', exact: true });
  for (const oldLink of ['/tasks.html', '/admin.html?section=tasks']) {
    await page.goto(oldLink);
    await expect(page).toHaveURL(queue);
    await expect(queueHeading).toBeVisible();
  }
  const sidebar = page.getByRole('navigation', { name: '功能模块' });
  await expect(sidebar.getByRole('link', { name: /成员同步中心/ })).toBeVisible();
  await expect(sidebar.getByRole('link', { name: /同步任务/ })).toHaveCount(0);

  await page.getByRole('link', { name: '成员同步', exact: true }).click();
  await expect(page).toHaveURL(overview);
  await expect(page.getByRole('button', { name: '同步全部成员', exact: true })).toBeVisible();

  await page.goto('/admin.html?section=problems&view=collection');
  await page.getByRole('link', { name: /查看任务队列/ }).click();
  await expect(page).toHaveURL(queue);
  await expect(queueHeading).toBeVisible();
  await page.getByRole('link', { name: '拉取题目', exact: true }).click();
  await expect(page).toHaveURL('/admin.html?section=problems&view=collection');
});
