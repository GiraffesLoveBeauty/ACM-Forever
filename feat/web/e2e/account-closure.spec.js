import { test, expect } from '@playwright/test';
const password = 'Browser-fixture-only!2026';
async function login(page, qq) {
  const response = await page.request.post('/api/auth/login', { data: { qq_id: qq, password } });
  expect(response.status()).toBe(200);
  await page.goto('/account-closure.html');
  await expect(page.getByRole('heading', { name: '注销账号', exact: true })).toBeVisible();
}
async function fill(page) {
  await expect(page.getByRole('button', { name: '永久注销账号' })).toBeDisabled();
  await page.getByLabel('当前密码', { exact: true }).fill(password);
  const checkbox = page.getByRole('checkbox');
  const bounds = await checkbox.boundingBox();
  expect(bounds.width).toBeLessThanOrEqual(24);
  await checkbox.check();
  await page.getByLabel('请输入“注销账号”确认').fill('注销账号');
  await expect(page.getByRole('button', { name: '永久注销账号' })).toBeEnabled();
}
async function noOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
}

test('closure confirms completion, clears secrets and invalidates other tabs', async ({
  page,
  context,
}, info) => {
  await page.setViewportSize({ width: info.project.name === 'mobile' ? 360 : 1440, height: 900 });
  const qq = info.project.name === 'mobile' ? '10000005' : '10000004';
  await login(page, qq);
  const other = await context.newPage();
  await other.goto('/home.html');
  await expect(other.getByRole('link', { name: '了解并申请注销账号' })).toBeVisible();
  await fill(page);
  await noOverflow(page);
  await page.getByRole('button', { name: '永久注销账号' }).click();
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toBeVisible();
  await expect(other).toHaveURL(/\/index.html$/);
  expect((await (await page.request.get('/api/auth/me')).json()).authenticated).toBe(false);
  expect(
    (await page.request.post('/api/auth/login', { data: { qq_id: qq, password } })).status(),
  ).toBe(401);
  const storage = await page.evaluate(() => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
  }));
  expect(JSON.stringify(storage)).not.toContain(password);
  expect(JSON.stringify(storage)).not.toContain(qq);
  expect(JSON.stringify(storage.local)).not.toContain('receipt_token');
  await page.reload();
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toBeVisible();
  await noOverflow(page);
});

test('a lost response stays uncertain until the secret receipt proves completion', async ({
  page,
}, info) => {
  const qq = info.project.name === 'mobile' ? '10000007' : '10000006';
  await login(page, qq);
  await page.route('**/api/me/account-closure', async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort('failed');
  });
  await fill(page);
  await page.getByRole('button', { name: '永久注销账号' }).click();
  await expect(page.getByRole('heading', { name: '结果待确认', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '用回执查询结果' }).click();
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toBeVisible();
  await noOverflow(page);
});

test('administrators must hand over their role before self-service closure', async ({ page }) => {
  await login(page, '10000003');
  await expect(
    page.getByText('请先完成管理职责交接，由另一位有效 Web root 将你降为普通成员，再由本人注销。'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: '永久注销账号' })).toHaveCount(0);
  await noOverflow(page);
});

test('a closed QQ can receive a fresh account and its old receipt keeps the new login', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: info.project.name === 'mobile' ? 360 : 1440, height: 900 });
  const qq = info.project.name === 'mobile' ? '10000009' : '10000008';
  await login(page, qq);
  await fill(page);
  await page.getByRole('button', { name: '永久注销账号' }).click();
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toBeVisible();
  expect(
    (
      await page.request.post('/api/auth/login', { data: { qq_id: '10000003', password } })
    ).status(),
  ).toBe(200);
  await page.goto('/admin.html');
  await page.getByText('单个创建账号', { exact: true }).click();
  await expect(page.getByText('已注销的 QQ 可在这里创建全新账号', { exact: false })).toBeVisible();
  await page.getByLabel('成员 QQ', { exact: true }).fill(qq);
  await page.getByLabel('昵称', { exact: true }).fill('重新开户的测试成员');
  const freshPassword = 'New-browser-fixture!83';
  await page.getByLabel('初始密码', { exact: true }).fill(freshPassword);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/admin/web-accounts') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '创建账号', exact: true }).click();
  expect((await created).status()).toBe(201);
  await noOverflow(page);
  const freshLogin = await page.request.post('/api/auth/login', {
    data: { qq_id: qq, password: freshPassword },
  });
  expect(freshLogin.status()).toBe(200);
  const fresh = await freshLogin.json();
  expect(fresh.must_change_password).toBe(true);
  expect(
    (
      await page.request.post('/api/auth/change-password', {
        data: { old_password: freshPassword, new_password: password },
        headers: { 'X-CSRF-Token': fresh.csrf_token },
      })
    ).status(),
  ).toBe(200);
  // The original secret receipt is still in this tab. Reopening it must show
  // the old closure result without clearing the new account's shared cookie.
  await page.goto('/account-closure.html');
  await expect(page.getByRole('heading', { name: '账号已注销', exact: true })).toBeVisible();
  const current = await (await page.request.get('/api/auth/me')).json();
  expect(current.authenticated).toBe(true);
  expect(current.account_epoch).toBe(3);
  expect((await page.request.get('/api/me/profile')).status()).toBe(200);
  await noOverflow(page);
});
