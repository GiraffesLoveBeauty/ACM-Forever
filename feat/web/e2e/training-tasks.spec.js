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
  const table = page.getByRole('table', { name: '成员完成情况' });
  const member = table.getByRole('row').filter({ hasText: '训练测试姓名甲' });
  await expect(member).toContainText('1 / 2 题');
  const bar = member.getByRole('progressbar', { name: '训练测试姓名甲的做题进度' });
  await expect(bar).toHaveAttribute('aria-valuenow', '1');
  await expect(bar).toHaveAttribute('aria-valuemax', '2');
  expect(
    await bar
      .locator('span')
      .evaluate(
        (fill) =>
          fill.getBoundingClientRect().width / fill.parentElement.getBoundingClientRect().width,
      ),
  ).toBeCloseTo(0.5, 2);
  await expect(table).not.toContainText('10000118');
  await expect(table).not.toContainText('任务状态');
  await expect(table).not.toContainText('核验与账号');
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
  await page.getByRole('button', { name: '切换主题', exact: true }).click();
  await expect(page.locator('body')).toHaveAttribute('data-theme', 'dark');
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

async function createBoundaryTask(context, csrf, title) {
  const now = Math.floor(Date.now() / 1000);
  const response = await context.request.post('/api/admin/training-tasks', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      title,
      statuses: ['训练任务测试组'],
      starts_at: now - 86400,
      due_at: now + 86400,
      rule: 'period_ac',
      problems: [{ platform: 'codeforces', problem_id: '1A' }],
    },
  });
  expect(response.status()).toBe(201);
  return await response.json();
}

async function setBoundaryBinding(context, csrf, account) {
  const current = await (await context.request.get('/api/admin/members/10000119')).json();
  if ((current.cf_handle || '') === account) return;
  const response = await context.request.patch('/api/admin/members/10000119', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      cf_handle: account,
      expected_account_epoch: current.account_epoch,
      profile_revision: current.profile_revision,
      confirm_bindings: true,
      expected_bindings: {
        cf_handle: current.cf_handle,
        atcoder_handle: current.atcoder_handle,
        luogu_id: current.luogu_id,
        nowcoder_id: current.nowcoder_id,
      },
      binding_versions: current.binding_versions,
    },
  });
  expect([200, 202]).toContain(response.status());
}

test('saving keeps text entered after submission and preserves the unsaved leave guard', async ({
  page,
  context,
}, testInfo) => {
  const csrf = await login(context, '10000003');
  const task = await createBoundaryTask(context, csrf, '保存响应边界 ' + testInfo.project.name);
  await page.goto('/admin.html?section=training&task_id=' + task.id + '&tab=edit');
  const title = page.getByLabel('任务标题', { exact: true });
  await expect(title).toHaveValue(task.title);
  await title.fill('Submitted title');
  let release,
    submitted,
    held = false;
  const gate = new Promise((resolve) => (release = resolve));
  await page.route('**/api/admin/training-tasks/' + task.id, async (route) => {
    if (route.request().method() !== 'PATCH' || held) return route.continue();
    held = true;
    submitted = route.request().postDataJSON();
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  try {
    await expect.poll(() => Boolean(submitted)).toBe(true);
    await title.fill('Text entered during saving');
    await page.getByLabel('训练说明', { exact: true }).fill('Description entered during saving');
  } finally {
    release();
  }
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeEnabled();
  await expect(title).toHaveValue('Text entered during saving');
  await expect(page.getByLabel('训练说明', { exact: true })).toHaveValue(
    'Description entered during saving',
  );
  const server = await (await context.request.get('/api/admin/training-tasks/' + task.id)).json();
  expect(server.title).toBe('Submitted title');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '返回列表', exact: true }).click();
  await expect(title).toHaveValue('Text entered during saving');
  await page.screenshot({
    path: testInfo.outputPath('saving-retains-later-input.png'),
    fullPage: true,
  });
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await context.request.get('/api/admin/training-tasks/' + task.id)).json()).title,
    )
    .toBe('Text entered during saving');
});

test('first binding permits task refresh before a successful sync', async ({
  page,
  context,
}, testInfo) => {
  const csrf = await login(context, '10000003');
  await setBoundaryBinding(context, csrf, '');
  const task = await createBoundaryTask(context, csrf, '首次绑定边界 ' + testInfo.project.name);
  const headers = { 'X-CSRF-Token': csrf };
  const preview = await (
    await context.request.post('/api/admin/training-tasks/' + task.id + '/audience-preview', {
      headers,
      data: { version: task.version },
    })
  ).json();
  const published = await context.request.post(
    '/api/admin/training-tasks/' + task.id + '/publish',
    {
      headers: {
        ...headers,
        'Idempotency-Key': 'first-binding-' + testInfo.project.name + '-' + task.id,
      },
      data: {
        version: task.version,
        preview_token: preview.preview_token,
        confirm_exclusions: true,
      },
    },
  );
  expect(published.status()).toBe(200);
  await setBoundaryBinding(context, csrf, 'WaitingBindingFixture');
  await login(context, '10000119');
  const detail = await (await context.request.get('/api/me/training-tasks/' + task.id)).json();
  expect(detail.problems[0].verification).not.toBe('unbound');
  expect(detail.recipient.pending).toBe(true);
  await page.goto('/training-tasks.html?task_id=' + task.id);
  const refresh = page.getByRole('button', { name: '刷新进度', exact: true });
  await expect(refresh).toBeEnabled();
  let refreshRequests = 0;
  await page.route('**/api/me/training-tasks/' + task.id + '/refresh', (route) => {
    refreshRequests++;
    return route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ message: '合成同步暂不可用，已有进度保留。' }),
    });
  });
  await refresh.click();
  await expect.poll(() => refreshRequests).toBe(1);
  await expect(page.getByRole('alert')).toContainText('已有进度保留');
  await page.screenshot({
    path: testInfo.outputPath('first-binding-refresh-enabled.png'),
    fullPage: true,
  });
});

test('completion real names, search and long progress bars remain usable across widths and themes', async ({
  page,
  context,
}, testInfo) => {
  const csrf = await login(context, '10000003');
  const task = await createBoundaryTask(context, csrf, '进度布局验收 ' + testInfo.project.name);
  const base = '/api/admin/training-tasks/' + task.id;
  const preview = await (
    await context.request.post(base + '/audience-preview', {
      headers: { 'X-CSRF-Token': csrf },
      data: { version: task.version },
    })
  ).json();
  const published = await context.request.post(base + '/publish', {
    headers: {
      'X-CSRF-Token': csrf,
      'Idempotency-Key': 'completion-layout-' + testInfo.project.name + '-' + Date.now(),
    },
    data: { version: task.version, preview_token: preview.preview_token, confirm_exclusions: true },
  });
  expect(published.status()).toBe(200);
  await page.goto('/admin.html?section=training&task_id=' + task.id + '&tab=progress');
  const table = page.getByRole('table', { name: '成员完成情况' });
  const complete = table.getByRole('progressbar', { name: '训练测试姓名甲的做题进度' });
  const empty = table.getByRole('progressbar', { name: '未填写姓名的做题进度' });
  await expect(complete).toHaveAttribute('aria-valuetext', '已完成 1 / 1 题');
  await expect(empty).toHaveAttribute('aria-valuetext', '已完成 0 / 1 题');
  expect(await table.getByRole('columnheader').allTextContents()).toEqual([
    '成员 / 身份快照',
    '完成进度',
    '操作',
  ]);
  for (const theme of ['light', 'dark']) {
    if ((await page.locator('body').getAttribute('data-theme')) !== theme)
      await page.getByRole('button', { name: '切换主题', exact: true }).click();
    await expect(page.locator('body')).toHaveAttribute('data-theme', theme);
    await expect(complete.locator('span')).toHaveCSS(
      'background-color',
      theme === 'dark' ? 'rgb(169, 130, 255)' : 'rgb(130, 80, 223)',
    );
    for (const width of [1440, 768, 414, 360]) {
      await page.setViewportSize({ width, height: 960 });
      await expect(complete).toBeVisible();
      const track = await complete.boundingBox();
      expect(track.width).toBeGreaterThan(90);
      expect(
        await complete
          .locator('span')
          .evaluate(
            (fill) =>
              fill.getBoundingClientRect().width / fill.parentElement.getBoundingClientRect().width,
          ),
      ).toBeCloseTo(1, 2);
      expect(
        await empty.locator('span').evaluate((fill) => fill.getBoundingClientRect().width),
      ).toBe(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      expect(await table.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath('completion-' + theme + '-' + width + '.png'),
        fullPage: true,
      });
      if (width === 1440)
        await table.screenshot({ path: testInfo.outputPath('completion-table-' + theme + '.png') });
    }
  }
  await page.getByPlaceholder('真实姓名、昵称或 QQ').fill('训练测试姓名甲');
  await page.getByRole('button', { name: '筛选成员', exact: true }).click();
  await expect(table.getByRole('progressbar')).toHaveCount(1);
  await expect(complete).toBeVisible();
  await page.reload();
  await expect(complete).toBeVisible();
  await expect(page.getByPlaceholder('真实姓名、昵称或 QQ')).toHaveValue('训练测试姓名甲');
  await page.getByPlaceholder('真实姓名、昵称或 QQ').fill('不存在的合成姓名');
  await page.getByRole('button', { name: '筛选成员', exact: true }).click();
  await expect(table).toContainText('没有符合筛选条件的成员。');
  await expect(table.getByRole('progressbar')).toHaveCount(0);
});
