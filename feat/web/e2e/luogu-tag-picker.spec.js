import { test, expect } from '@playwright/test';

const ids = Array.from({ length: 20 }, (_, index) => String(index + 1));
const taxonomy = {
  difficulties: [],
  tag_types: [{ id: 2, name: '算法', order: 1 }],
  tags: Array.from({ length: 40 }, (_, index) => ({
    id: index + 1,
    name: '算法标签 ' + (index + 1),
    type: 2,
    parent: index === 0 ? null : 1,
  })),
};

async function openPage(page, owner, selected) {
  const prefix = owner === 'member' ? '' : 'bank_';
  const query = new URLSearchParams({
    ...(owner === 'admin' ? { section: 'problems' } : {}),
    [prefix + 'platform']: 'luogu',
    [prefix + 'native_tags']: selected.join(','),
  });
  await page.goto((owner === 'member' ? '/problem-bank.html?' : '/admin.html?') + query);
  await expect(pickerTrigger(page, owner)).toBeVisible();
}

function pickerTrigger(page, owner) {
  return page.getByRole('button', { name: owner === 'member' ? /按标签筛选/ : /按算法筛选/ });
}

async function openPicker(page, owner) {
  await pickerTrigger(page, owner).click();
  const dialog = page.getByRole('dialog', { name: '选择标签' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: '算法标签 1', exact: true })).toBeVisible();
  return dialog;
}

test('Codeforces picker shows all groups and submits Chinese choices', async ({ page }) => {
  const login = await page.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
  });
  expect(login.status()).toBe(200);
  await page.route('**/api/me/problems/tags?*', (route) =>
    route.fulfill({ json: { tags: ['implementation', 'math', 'interactive'] } }),
  );
  await page.goto('/problem-bank.html?platform=codeforces&problem_tag=Implementation');
  await expect(page.locator('#problem-list article').first()).toContainText('模拟');
  await page.getByRole('button', { name: /按标签筛选/ }).click();
  const dialog = page.getByRole('dialog', { name: '选择标签' });
  await expect(dialog.getByRole('tablist')).toHaveCount(0);
  await expect(dialog.getByRole('tab')).toHaveCount(0);
  const tags = dialog.locator('.luogu-picker-body');
  await expect(tags.getByRole('button', { name: '模拟', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(tags.getByRole('button', { name: '数学', exact: true })).toBeVisible();
  await expect(tags.getByRole('button', { name: '交互题', exact: true })).toBeVisible();
  const search = dialog.getByRole('searchbox', { name: '搜索全部标签' });
  await search.fill('math');
  await expect(tags.getByRole('button', { name: '交互题', exact: true })).toHaveCount(0);
  await tags.getByRole('button', { name: '数学', exact: true }).click();
  await expect(page).toHaveURL((url) => url.searchParams.get('problem_tag') === 'Implementation');
  const response = page.waitForResponse((item) => {
    const url = new URL(item.url());
    return (
      url.pathname === '/api/me/problems' &&
      url.searchParams.get('problem_tags') === 'Implementation,math'
    );
  });
  await dialog.getByRole('button', { name: '确认筛选' }).click();
  expect((await response).status()).toBe(200);
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('没有匹配题目，请调整筛选。')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#problem-list article').first()).toContainText('模拟');
});

for (const owner of ['member', 'admin']) {
  test.describe(owner + ' Luogu picker', () => {
    test.beforeEach(async ({ page }) => {
      const response = await page.request.post('/api/auth/login', {
        data: {
          qq_id: owner === 'member' ? '10000001' : '10000003',
          password: 'Browser-fixture-only!2026',
        },
      });
      expect(response.status()).toBe(200);
      // Keep dictionary data deterministic; list queries still use the fixture API.
      await page.route('**/api/**/problems/taxonomy?*', (route) =>
        route.fulfill({ json: taxonomy }),
      );
      await page.route('**/api/problems/taxonomy?*', (route) => route.fulfill({ json: taxonomy }));
    });

    test('composition Enter preserves drafts and requests until ordinary Enter confirms', async ({
      page,
    }) => {
      const requests = [];
      page.on('request', (request) => {
        if (/\/api\/(?:me\/problems|admin\/database\/problems)\?/.test(request.url()))
          requests.push(request.url());
      });
      await openPage(page, owner, ['1']);
      const dialog = await openPicker(page, owner);
      await dialog.getByRole('button', { name: '算法标签 2', exact: true }).click();
      const input = dialog.getByRole('searchbox', { name: '搜索全部标签' });
      const url = page.url();
      const count = requests.length;
      const defaultAllowed = await input.evaluate((element) => {
        element.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
        element.value = 'suan';
        element.dispatchEvent(
          new InputEvent('input', {
            data: 'suan',
            inputType: 'insertCompositionText',
            isComposing: true,
            bubbles: true,
          }),
        );
        return element.dispatchEvent(
          new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            isComposing: true,
            bubbles: true,
            cancelable: true,
          }),
        );
      });
      expect(defaultAllowed).toBe(true);
      await expect(dialog).toBeVisible();
      expect(page.url()).toBe(url);
      expect(requests.length).toBe(count);
      await expect(dialog.getByRole('button', { name: '算法标签 2', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true',
      );

      await input.dispatchEvent('compositionend', { data: '算法' });
      await input.fill('算法标签 2');
      await expect(dialog.getByRole('status')).toContainText('全部分类中找到');
      const response = page.waitForResponse((item) => {
        const url = new URL(item.url());
        return (
          /\/api\/(?:me\/problems|admin\/database\/problems)$/.test(url.pathname) &&
          url.searchParams.get('native_tags') === '1,2'
        );
      });
      await input.press('Enter');
      expect((await response).status()).toBe(200);
      await expect(dialog).toHaveCount(0);
      expect(requests.length).toBe(count + 1);
    });

    test('low-height landscape keeps tags reachable and footer controls visible', async ({
      page,
    }, info) => {
      const activate = (locator) =>
        info.project.name === 'mobile' ? locator.tap() : locator.click();
      for (const theme of ['light', 'dark']) {
        for (const [width, height] of [
          [568, 320],
          [667, 320],
          [640, 360],
        ]) {
          await page.setViewportSize({ width, height });
          await openPage(page, owner, ids);
          await page.evaluate((value) => (document.body.dataset.theme = value), theme);
          const dialog = await openPicker(page, owner);
          const confirm = dialog.getByRole('button', { name: '确认筛选', exact: true });
          const cancel = dialog.getByRole('button', { name: '取消', exact: true });
          const bounds = await dialog.boundingBox();
          for (const control of [confirm, cancel]) {
            const box = await control.boundingBox();
            expect(box.y).toBeGreaterThanOrEqual(bounds.y);
            expect(box.y + box.height).toBeLessThanOrEqual(bounds.y + bounds.height + 1);
            await expect(control).toBeInViewport({ ratio: 1 });
          }
          await activate(dialog.getByRole('button', { name: '移除标签：算法标签 1', exact: true }));
          const added = dialog.getByRole('button', { name: '算法标签 21', exact: true });
          await activate(added);
          await expect(added).toHaveAttribute('aria-pressed', 'true');
          await expect(added).toBeInViewport({ ratio: 1 });
          await expect(confirm).toBeInViewport({ ratio: 1 });
          await activate(confirm);
          await expect(dialog).toHaveCount(0);
          const key = owner === 'member' ? 'native_tags' : 'bank_native_tags';
          await expect(page).toHaveURL(
            (url) => url.searchParams.get(key) === [...ids.slice(1), '21'].join(','),
          );

          const applied = page.url();
          const reopened = await openPicker(page, owner);
          await activate(
            reopened.getByRole('button', { name: '移除标签：算法标签 2', exact: true }),
          );
          await activate(reopened.getByRole('button', { name: '取消', exact: true }));
          await expect(reopened).toHaveCount(0);
          expect(page.url()).toBe(applied);
        }
      }
    });
  });
}
