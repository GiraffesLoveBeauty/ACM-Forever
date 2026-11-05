import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
const password = 'Browser-fixture-only!2026';
async function open(page, query = '') {
  const response = await page.request.post('/api/auth/login', {
    data: { qq_id: '10000003', password },
  });
  expect(response.status()).toBe(200);
  await page.goto('/admin.html?section=members' + query);
  await expect(page.getByRole('heading', { name: '成员资料', exact: true }).last()).toBeVisible();
  await expect(page.getByText('正在加载成员资料…')).toHaveCount(0);
}
function qq(info, offset) {
  return String(21000000 + offset + (info.project.name === 'mobile' ? 12 : 0));
}
function row(page, id) {
  return page.locator(`[data-member="${id}"]`);
}
async function edit(page) {
  await page.getByRole('button', { name: '进入编辑模式', exact: true }).click();
}
async function screenshot(page, name, info) {
  if (process.env.ACM_PROFILE_ARTIFACTS) {
    await mkdir(process.env.ACM_PROFILE_ARTIFACTS, { recursive: true });
    await page.screenshot({
      path: join(process.env.ACM_PROFILE_ARTIFACTS, `${info.project.name}-${name}.png`),
      fullPage: info.project.name !== 'mobile',
    });
  }
}
async function noOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
}

test('member list filters, separate columns, URL history and detail context', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: info.project.name === 'mobile' ? 360 : 1440, height: 900 });
  await open(page, '&search=' + encodeURIComponent('资料夹具'));
  const id = qq(info, 0),
    entry = row(page, id);
  await expect(entry).toContainText('ProfileCF_');
  await expect(entry).toContainText('ProfileAC_');
  await expect(entry).toContainText('810');
  await expect(entry).toContainText('910');
  await expect(entry).toContainText('未开通');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.locator('tbody tr')).toHaveCount(6);
  await page.goBack();
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await page.getByLabel('学校', { exact: true }).selectOption('测试学校乙');
  await page.getByLabel('身份', { exact: true }).selectOption('测试集训');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await expect(page).toHaveURL(/school=/);
  await expect(page.locator('tbody tr')).toHaveCount(5);
  await page.reload();
  await expect(page.getByLabel('学校', { exact: true })).toHaveValue('测试学校乙');
  await expect(page.locator('tbody tr')).toHaveCount(5);
  // The lightweight list does not load external OJ statistics. Stub only the old detail read.
  await page.route('**/api/member/*', (route) =>
    route.fulfill({
      json: {
        user: { name: '合成详情', qq_id: id, cjlu_username: '保留校OJ' },
        permissions: { role: null },
        platform_counts: {},
        recent_ac: [],
      },
    }),
  );
  await row(page, id).getByRole('button', { name: '查看资料' }).click();
  await expect(page.getByLabel('校 OJ', { exact: true })).toHaveValue('保留校OJ');
  await page.getByRole('button', { name: '← 返回成员列表' }).click();
  await expect(page.getByLabel('学校', { exact: true })).toHaveValue('测试学校乙');
  await expect(page.locator('tbody tr')).toHaveCount(5);
  await noOverflow(page);
  await screenshot(page, 'browse', info);
});

test('member drafts survive refresh, detail, pagination and identity creation with keyboard focus', async ({
  page,
}, info) => {
  const id = qq(info, 1);
  await open(page, '&search=资料夹具');
  await edit(page);
  await page.getByLabel(`${id} 真实姓名`, { exact: true }).fill('草稿合成姓名');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await page.getByRole('button', { name: '上一页', exact: true }).click();
  await expect(page.getByLabel(`${id} 真实姓名`, { exact: true })).toHaveValue('草稿合成姓名');
  await page.getByLabel(`${id} 身份`, { exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '选择成员身份' });
  await expect(dialog.getByRole('button', { name: '测试集训', exact: true })).toBeVisible();
  const options = dialog.locator('.member-status-options button');
  await expect(options.last()).toHaveText('＋ 新建身份');
  await dialog.getByRole('button', { name: '关闭身份选择器' }).focus();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: '取消此次身份输入' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: '关闭身份选择器' })).toBeFocused();
  await screenshot(page, 'identity-drawer', info);
  await dialog.getByRole('button', { name: '＋ 新建身份' }).click();
  await dialog.getByLabel('新身份名称').fill('未确认的合成身份' + id);
  await dialog.getByLabel('新身份名称').press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel(`${id} 身份`, { exact: true })).toBeFocused();
  await page.reload();
  await page.getByRole('button', { name: '恢复草稿', exact: true }).click();
  await expect(page.getByLabel(`${id} 真实姓名`, { exact: true })).toHaveValue('草稿合成姓名');
  await expect(page.getByRole('dialog').getByLabel('新身份名称')).toHaveValue(
    '未确认的合成身份' + id,
  );
  await page.getByRole('dialog').getByRole('button', { name: '创建并应用' }).click();
  await expect(page.getByLabel(`${id} 身份`, { exact: true })).toHaveText('未确认的合成身份' + id);
  const changes = await page.request.get('/api/admin/members/' + id);
  expect((await changes.json()).status).not.toContain('未确认');
  await page.getByRole('button', { name: '退出编辑，保留草稿' }).click();
  await expect(row(page, id)).not.toContainText('草稿合成姓名');
  await page.getByRole('button', { name: '继续编辑', exact: true }).click();
  await noOverflow(page);
  await screenshot(page, 'edit', info);
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '放弃全部草稿', exact: true }).click();
  await expect(page.getByLabel(`${id} 真实姓名`, { exact: true })).not.toHaveValue('草稿合成姓名');
});

test('member profile conflict keeps input and supports explicit field comparison', async ({
  page,
}, info) => {
  const id = qq(info, 2);
  await open(page, '&search=' + id);
  await edit(page);
  await page.getByLabel(`${id} 学校`, { exact: true }).fill('我的草稿学校');
  const auth = await (await page.request.get('/api/auth/me')).json(),
    current = await (await page.request.get('/api/admin/members/' + id)).json();
  const changed = await page.request.patch('/api/admin/members/' + id, {
    headers: { 'X-CSRF-Token': auth.csrf_token },
    data: {
      school: '另一管理员学校',
      expected_account_epoch: current.account_epoch,
      profile_revision: current.profile_revision,
    },
  });
  expect(changed.status()).toBe(200);
  await page.getByRole('button', { name: '保存全部（1）', exact: true }).click();
  await expect(page.getByText('冲突 1 人', { exact: false })).toBeVisible();
  await expect(page.getByLabel(`${id} 学校`, { exact: true })).toHaveValue('我的草稿学校');
  await page.getByRole('button', { name: '核对变化', exact: true }).click();
  const comparison = page.getByRole('region', { name: '资料冲突核对' });
  await expect(comparison).toContainText('另一管理员学校');
  await comparison.getByRole('radio', { name: '我的草稿', exact: true }).check();
  await screenshot(page, 'conflict', info);
  await comparison.getByRole('button', { name: '确认选择，保留为草稿' }).click();
  await page.getByRole('button', { name: '保存全部（1）', exact: true }).click();
  await expect(page.getByText('成功 1 人', { exact: false })).toBeVisible();
  expect((await (await page.request.get('/api/admin/members/' + id)).json()).school).toBe(
    '我的草稿学校',
  );
});

test('OJ cancel does not write, confirmed unbind preserves campus OJ and clears the saved draft', async ({
  page,
}, info) => {
  const id = qq(info, 3);
  await open(page, '&search=' + id);
  const before = await (await page.request.get('/api/admin/members/' + id)).json();
  await edit(page);
  await page.getByLabel(`${id} Codeforces`, { exact: true }).fill('');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '保存全部（1）', exact: true }).click();
  expect((await (await page.request.get('/api/admin/members/' + id)).json()).cf_handle).toBe(
    before.cf_handle,
  );
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '保存全部（1）', exact: true }).click();
  await expect(page.getByText('成功 1 人', { exact: false })).toBeVisible();
  const after = await (await page.request.get('/api/admin/members/' + id)).json();
  expect(after.cf_handle).toBe('');
  expect(after.cjlu_username).toBe(before.cjlu_username);
  expect(after.cjlu_binding_version).toBe(before.cjlu_binding_version);
  await page.reload();
  await expect(page.getByRole('button', { name: '恢复草稿', exact: true })).toHaveCount(0);
  await noOverflow(page);
});

async function holdProfileWrites(page, pauseFourth = false) {
  let release, releaseFourth;
  const first = new Promise((resolve) => (release = resolve));
  const fourth = new Promise((resolve) => (releaseFourth = resolve));
  const sent = [];
  const handler = async (route) => {
    if (route.request().method() === 'PATCH') {
      sent.push({ url: route.request().url(), body: route.request().postDataJSON() });
      if (sent.length <= 3) await first;
      else if (pauseFourth && sent.length === 4) await fourth;
    }
    await route.continue();
  };
  await page.route('**/api/admin/members/*', handler);
  return {
    sent,
    release,
    releaseFourth,
    async close() {
      release();
      releaseFourth();
      await page.unroute('**/api/admin/members/*', handler);
    },
  };
}
async function editQueuedMembers(page, info, start) {
  const ids = Array.from({ length: 4 }, (_, index) => qq(info, start + index));
  await open(
    page,
    '&search=资料夹具' + (start === 8 && info.project.name === 'mobile' ? '&page=2' : ''),
  );
  const before = await Promise.all(
    ids.map(async (id) => (await page.request.get('/api/admin/members/' + id)).json()),
  );
  await edit(page);
  for (const member of before)
    await page.getByLabel(`${member.qq_id} 昵称`, { exact: true }).fill(member.name + '_队列保存');
  return { ids, before };
}

test('queued OJ and drawer input require a new save, preserving server bindings until confirmed', async ({
  page,
}, info) => {
  const { ids, before } = await editQueuedMembers(page, info, 4);
  const id = ids[3],
    batch = await holdProfileWrites(page, true),
    confirmations = [];
  page.on('dialog', async (dialog) => {
    confirmations.push(dialog.message());
    await dialog.accept();
  });
  try {
    await page.getByRole('button', { name: '保存全部（4）', exact: true }).click();
    await expect.poll(() => batch.sent.length).toBe(3);
    const nextCF = `QueueCF_${id}`,
      nextStatus = `${info.project.name}后续身份`;
    await page.getByLabel(`${id} Codeforces`, { exact: true }).fill(nextCF);
    await page.getByLabel(`${id} 身份`, { exact: true }).click();
    const drawer = page.getByRole('dialog', { name: '选择成员身份' });
    await drawer.getByRole('button', { name: '＋ 新建身份', exact: true }).click();
    batch.release();
    await expect.poll(() => batch.sent.length).toBe(4);
    await drawer.getByLabel('新身份名称', { exact: true }).fill(nextStatus);
    expect(batch.sent[3].body).not.toHaveProperty('cf_handle');
    expect(batch.sent[3].body.confirm_bindings).toBe(false);
    expect(confirmations).toHaveLength(0);
    batch.releaseFourth();
    await expect(page.getByText('成功 4 人', { exact: false })).toBeVisible();
    await drawer.getByRole('button', { name: '关闭身份选择器' }).click();
    await expect(page.getByLabel(`${id} 昵称`, { exact: true })).toBeEnabled();
    await expect(page.getByLabel(`${id} Codeforces`, { exact: true })).toHaveValue(nextCF);
    const saved = await (await page.request.get('/api/admin/members/' + id)).json();
    expect(saved.cf_handle).toBe(before[3].cf_handle);
    expect(saved.cf_binding_version).toBe(before[3].cf_binding_version);
    expect(saved.cjlu_binding_version).toBe(before[3].cjlu_binding_version);
    const pending = await page.evaluate(
      (qqId) =>
        Object.keys(localStorage)
          .filter((key) => key.startsWith('acm-member-profile:'))
          .map((key) => JSON.parse(localStorage.getItem(key)))
          .find((record) => record.qq_id === qqId),
      id,
    );
    expect(pending.base.profile_revision).toBe(saved.profile_revision);
    expect(pending.changes).toEqual({ cf_handle: nextCF });
    expect(pending.drawer.text).toBe(nextStatus);
    await page.getByLabel(`${id} 身份`, { exact: true }).click();
    await expect(drawer.getByLabel('新身份名称', { exact: true })).toHaveValue(nextStatus);
    await drawer.getByRole('button', { name: '创建并应用', exact: true }).click();
    await screenshot(page, 'queue-later-input', info);
    await page.getByRole('button', { name: '保存全部（1）', exact: true }).click();
    await expect(page.getByText('成功 1 人', { exact: false })).toBeVisible();
    expect(confirmations).toHaveLength(1);
    expect(confirmations[0]).toContain(`${before[3].cf_handle} → ${nextCF}`);
    expect(batch.sent[4].body.cf_handle).toBe(nextCF);
    expect(batch.sent[4].body.confirm_bindings).toBe(true);
    const final = await (await page.request.get('/api/admin/members/' + id)).json();
    expect(final.cf_handle).toBe(nextCF);
    expect(final.status).toBe(nextStatus);
    expect(final.cf_binding_version).toBe(before[3].cf_binding_version + 1);
    await noOverflow(page);
  } finally {
    await batch.close();
  }
});

test('discarding a queued member prevents its request and leaves no recoverable discarded change', async ({
  page,
}, info) => {
  const { ids, before } = await editQueuedMembers(page, info, 8);
  const id = ids[3],
    batch = await holdProfileWrites(page);
  try {
    await page.getByRole('button', { name: '保存全部（4）', exact: true }).click();
    await expect.poll(() => batch.sent.length).toBe(3);
    await page.getByRole('button', { name: '查看待保存', exact: true }).click();
    const member = page.locator('.profile-pending article').filter({ hasText: id });
    await expect(member).toContainText('排队中');
    page.once('dialog', (dialog) => dialog.accept());
    await member.getByRole('button', { name: '放弃此草稿', exact: true }).click();
    await expect(member).toHaveCount(0);
    batch.release();
    await expect(page.getByText('已取消排队 1 人', { exact: false })).toBeVisible();
    expect(batch.sent).toHaveLength(3);
    const after = await (await page.request.get('/api/admin/members/' + id)).json();
    expect(after.name).toBe(before[3].name);
    expect(after.profile_revision).toBe(before[3].profile_revision);
    await page.reload();
    await expect(page.getByRole('button', { name: '恢复草稿', exact: true })).toHaveCount(0);
  } finally {
    await batch.close();
  }
});
