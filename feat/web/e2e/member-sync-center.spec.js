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
  expect(await response.json()).toMatchObject({ success: true, task_id: expect.any(String) });
  await expect(page.getByRole('status').filter({ hasText: memberName })).toContainText(
    '同步任务已排队',
  );
  await expect(row).toHaveCount(0);
  await expect(other.getByRole('button', action)).toBeVisible();

  await status.selectOption('');
  await expect(row).toBeVisible();
  await expect(row.getByRole('button', action)).toHaveCount(0);
  await expect(row.getByText('已停用', { exact: true })).toHaveCount(0);
});
