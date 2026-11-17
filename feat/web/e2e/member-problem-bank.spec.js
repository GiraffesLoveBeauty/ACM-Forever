import { test, expect } from '@playwright/test';

const names = [
  '动态规划 DP',
  '二分',
  '单调队列',
  'O2优化',
  '树形 DP',
  '树的直径',
  '树链剖分',
  '虚树',
  'ST 表',
  '2026',
  'CSP-S 提高级',
  '单调栈',
];
const taxonomy = {
  difficulties: [{ id: 7, name: 'NOI/NOI+/CTSC', color: 'lapis-3' }],
  tag_types: [{ id: 2, name: '算法', order: 1 }],
  tags: names.map((name, index) => ({ id: index + 1, name, type: 2, parent: null })),
};
const problems = [
  {
    platform: 'luogu',
    problem_id: 'P17834',
    problem_name: '[CSP-S 2026] 研发基地 / hub（布局回归）',
    native_difficulty: taxonomy.difficulties[0],
    native_tags: taxonomy.tags.map((tag) => ({
      ...tag,
      category: { name: '算法', color: 'lapis-3' },
    })),
  },
  {
    platform: 'luogu',
    problem_id: 'P17835',
    problem_name: '短标签题目（布局回归）',
    native_difficulty: { id: 3, name: '普及−', color: 'orange-3' },
    native_tags: [{ id: 21, name: '字符串', category: { name: '算法', color: 'cyan-3' } }],
  },
  {
    platform: 'codeforces',
    problem_id: 'cf_100A',
    problem_name: '通用题目（布局回归）',
    problem_rating: '1000',
    tags: ['implementation'],
    has_secondary: false,
  },
].map((row) => ({
  ...row,
  problem_time: 1794834815,
  time_basis: 'first_seen',
  is_favorite: false,
}));

test.beforeEach(async ({ page }) => {
  const login = await page.request.post('/api/auth/login', {
    data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
  });
  expect(login.status()).toBe(200);
  const favorites = new Set();
  await page.route('**/api/me/problems?*', (route) => {
    const query = new URL(route.request().url()).searchParams;
    const items = problems
      .filter((row) => !query.get('platform') || row.platform === query.get('platform'))
      .map((row) => ({ ...row, is_favorite: favorites.has(row.problem_id) }));
    return route.fulfill({ json: { items, total: items.length, tag_facets: [] } });
  });
  await page.route('**/api/me/problems/tags?*', (route) => route.fulfill({ json: { tags: [] } }));
  await page.route('**/api/problems/taxonomy?*', (route) => route.fulfill({ json: taxonomy }));
  await page.route('**/api/me/problems/taxonomy?*', (route) => route.fulfill({ json: taxonomy }));
  await page.route('**/api/me/problems/*/*/state', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2);
    if (route.request().postDataJSON().is_favorite) favorites.add(id);
    else favorites.delete(id);
    return route.fulfill({ json: { success: true } });
  });
});

test('default entry, platform selector and native filters agree across navigation', async ({
  page,
}, info) => {
  const requests = [];
  page.on('request', (request) => {
    if (/\/api\/me\/problems\?/.test(request.url())) requests.push(request.url());
  });
  for (const path of ['/my-problems.html', '/problem-bank.html']) {
    requests.length = 0;
    await page.goto(path);
    const platform = page.getByRole('combobox', { name: /^平台/ });
    await expect(platform).toHaveValue('luogu');
    await expect(page.getByRole('heading', { name: '洛谷题库', exact: true })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /^洛谷难度下限/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /按算法筛选/ })).toBeVisible();
    await expect(page.getByLabel('算法标签筛选', { exact: true })).toHaveCount(0);
    await expect(page.locator('#problem-list article')).toHaveCount(2);
    expect(requests).toHaveLength(1);
    expect(new URL(requests[0]).searchParams.get('platform')).toBe('luogu');
    await expect(page.getByText(/人工修正后的有效标签/)).toHaveCount(0);
    if (path === '/my-problems.html')
      await page.screenshot({ path: info.outputPath('default-luogu.png'), fullPage: true });
    await platform.selectOption('all');
    await expect(page.getByLabel('算法标签筛选', { exact: true })).toBeVisible();
    await expect(page.locator('#problem-list article')).toHaveCount(3);
    await expect(page.getByRole('heading', { name: '洛谷题库', exact: true })).toHaveCount(0);
    await page.reload();
    await expect(platform).toHaveValue('all');
    await expect(page.locator('#problem-list article')).toHaveCount(3);
    await page.goBack();
    await expect(platform).toHaveValue('luogu');
    await expect(page.getByRole('combobox', { name: /^洛谷难度下限/ })).toBeVisible();
  }
});

test('long native tags wrap within the information column and all actions stay aligned', async ({
  page,
}, info) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const theme of ['light', 'dark']) {
    for (const [width, scale] of [
      [1440, 1],
      [1405, 1.5],
      [1024, 1],
      [768, 1],
      [640, 1.5],
      [390, 1],
      [360, 1.5],
    ]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto('/my-problems.html?platform=all');
      const rows = page.locator('#problem-list article');
      await expect(rows).toHaveCount(3);
      if ((await page.locator('html').getAttribute('data-theme')) !== theme)
        await page.getByRole('button', { name: '切换主题', exact: true }).click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.evaluate(
        (value) => document.documentElement.style.setProperty('--font-scale', String(value)),
        scale,
      );
      const layout = await rows.evaluateAll((items) =>
        items.map((row) => {
          const bounds = (el) => {
            const box = el.getBoundingClientRect();
            return { left: box.left, right: box.right, top: box.top, bottom: box.bottom };
          };
          const tags = [...row.querySelectorAll('.luogu-tag')].map(bounds);
          return {
            info: bounds(row.querySelector('.bank-problem-info')),
            actions: bounds(row.querySelector('.chips')),
            tags,
            row: bounds(row),
          };
        }),
      );
      expect(Math.abs(layout[0].actions.left - layout[1].actions.left)).toBeLessThanOrEqual(1);
      expect(Math.abs(layout[0].actions.right - layout[2].actions.right)).toBeLessThanOrEqual(1);
      if (width > 640) {
        for (const row of layout) expect(row.actions.left).toBeGreaterThanOrEqual(row.info.right);
        if (width === 1440)
          expect(
            new Set(layout[0].tags.map((tag) => Math.round(tag.top))).size,
          ).toBeGreaterThanOrEqual(2);
      } else {
        for (const row of layout) expect(row.actions.top).toBeGreaterThanOrEqual(row.info.bottom);
      }
      for (const tag of layout[0].tags) {
        expect(tag.left).toBeGreaterThanOrEqual(layout[0].info.left - 1);
        expect(tag.right).toBeLessThanOrEqual(layout[0].info.right + 1);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      if ([1440, 1405, 390].includes(width)) {
        await page.screenshot({
          path: info.outputPath(`bank-${width}-${theme}.png`),
          fullPage: true,
        });
        await page.locator('#problem-list').screenshot({
          path: info.outputPath(`rows-${width}-${theme}.png`),
        });
      }
    }
  }
  const long = page.locator('#problem-list article').filter({ hasText: 'P17834' });
  const favorite = long.getByRole('button', { name: '收藏', exact: true });
  await favorite.click();
  await expect(long.getByRole('button', { name: '取消收藏', exact: true })).toBeVisible();
  const link = long.getByRole('link', { name: '查看题面', exact: true });
  const target = new URL(await link.getAttribute('href'), page.url());
  expect(target.pathname).toBe('/problem.html');
  expect(target.searchParams.get('platform')).toBe('luogu');
  expect(target.searchParams.get('problem_id')).toBe('P17834');
  expect(target.searchParams.get('from')).toBe('/my-problems.html?platform=all');
  expect(errors).toEqual([]);
});
