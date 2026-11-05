import { test, expect } from '@playwright/test';

test('Excel import is enabled by default and the shared switch survives refresh', async ({
  page,
  context,
}, testInfo) => {
  const response = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000003', password: 'Browser-fixture-only!2026' },
  });
  expect(response.status()).toBe(200);
  const { csrf_token: csrf } = await response.json();
  const initialAccounts = await (await context.request.get('/api/admin/web-accounts')).json();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/admin.html?section=accounts&tab=import');
  const toggle = page.getByRole('switch', { name: 'Excel 导入开关' });
  await expect(toggle).toBeChecked();
  await expect(page.getByRole('button', { name: '下载 Excel 模板' })).toBeVisible();
  await toggle.focus();
  await expect(toggle).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath('excel-import-enabled.png'), fullPage: true });

  page.once('dialog', (dialog) => dialog.accept());
  await toggle.press('Space');
  await expect(toggle).not.toBeChecked();
  await expect(page.getByRole('button', { name: '下载 Excel 模板' })).toHaveCount(0);
  expect((await context.request.get('/api/admin/account-imports/template')).status()).toBe(503);
  await page.reload();
  await expect(toggle).not.toBeChecked();
  await page.screenshot({ path: testInfo.outputPath('excel-import-disabled.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  await toggle.click();
  await expect(toggle).toBeChecked();
  await page.reload();
  await expect(toggle).toBeChecked();
  expect((await context.request.get('/api/admin/account-imports/template')).status()).toBe(200);
  const capabilities = await (
    await context.request.get('/api/admin/account-imports/capabilities')
  ).json();
  expect(capabilities.enabled).toBe(true);
  const accounts = await (await context.request.get('/api/admin/web-accounts')).json();
  expect(accounts).toHaveLength(initialAccounts.length);
  expect(errors).toEqual([]);

  const member = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
    headers: { 'X-CSRF-Token': csrf },
  });
  expect(member.status()).toBe(200);
  const memberCsrf = (await member.json()).csrf_token;
  const forbidden = await context.request.patch('/api/admin/account-imports/settings', {
    data: { enabled: false },
    headers: { 'X-CSRF-Token': memberCsrf },
  });
  expect(forbidden.status()).toBe(403);
});
