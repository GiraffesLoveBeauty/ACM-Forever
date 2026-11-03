import { test, expect } from '@playwright/test';
import { audit } from '../tools/performance-audit.mjs';
test('performance audit separates API and static resources in a disposable local site', async ({
  page,
}, info) => {
  test.setTimeout(90000);
  await page.goto('/index.html');
  const report = await audit({
    sites: [new URL(page.url()).origin],
    samples: 1,
    output: info.outputPath('performance.json'),
    executablePath: process.env.ACM_E2E_BROWSER,
    scenarios: [{ path: '/index.html', ready: '.forum-post-card' }],
  });
  expect(report.pages.length).toBeGreaterThanOrEqual(4);
  expect(report.pages.every((row) => !row.error && row.readable > 0)).toBe(true);
  expect(report.pages[0].resources.some((row) => row.kind === 'api')).toBe(true);
  expect(report.pages[0].resources.some((row) => row.kind === 'static')).toBe(true);
  expect(report.probes).toHaveLength(4);
  expect(report.summary.every((row) => row.readable.success === 1)).toBe(true);
});
