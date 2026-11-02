import { test, expect } from '@playwright/test';

for (const authFirst of [false, true]) {
  for (const [target, endpoint, content] of [
    ['/index.html', '/api/forum/posts', '.forum-post-card'],
    ['/post.html?id=1', '/api/forum/posts/1', '.forum-article-header h1'],
    ['/leaderboard.html', '/api/community/leaderboard', '.leaderboard-summary'],
  ]) {
    test(`${target} loads when ${authFirst ? 'authentication' : 'public data'} finishes first`, async ({
      page,
      context,
    }) => {
      const login = await context.request.post('/api/auth/login', {
        data: { qq_id: '10000001', password: 'Browser-fixture-only!2026' },
      });
      expect(login.status()).toBe(200);
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      let releaseAuth,
        releaseData,
        requests = 0;
      const authGate = new Promise((resolve) => {
        releaseAuth = resolve;
      });
      const dataGate = new Promise((resolve) => {
        releaseData = resolve;
      });
      await page.route('**/api/auth/me', async (route) => {
        const response = await route.fetch();
        await authGate;
        await route.fulfill({ response });
      });
      await page.route(
        (url) =>
          url.pathname === endpoint &&
          (endpoint !== '/api/forum/posts' || url.searchParams.get('sort') === 'latest'),
        async (route) => {
          requests++;
          if (requests > 1) return route.continue();
          const response = await route.fetch();
          if (authFirst) await dataGate;
          // Identity confirmation disposes the initial App view, aborting this request.
          await route.fulfill({ response }).catch(() => {});
        },
      );
      try {
        await page.goto(target);
        await expect.poll(() => requests).toBe(1);
        if (!authFirst) await expect(page.locator(content).first()).toBeVisible();
        releaseAuth();
        await expect(page.getByRole('link', { name: '账户中心', exact: true })).toBeVisible();
        await expect.poll(() => requests).toBe(2);
        releaseData();
        await expect(page.locator(content).first()).toBeVisible();
        if (target === '/index.html')
          await expect(page.locator('#forum-feed')).not.toHaveAttribute('aria-busy', 'true');
        if (target === '/leaderboard.html')
          await expect(page.locator('.leaderboard-summary')).not.toContainText('正在加载');
        expect(errors).toEqual([]);
      } finally {
        releaseAuth();
        releaseData();
      }
    });
  }
}
