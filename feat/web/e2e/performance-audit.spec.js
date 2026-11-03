import { test, expect } from '@playwright/test';
import { execFile } from 'node:child_process';
import { createServer, request as proxyRequest } from 'node:http';
import { readFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import { audit, defaultScenarios } from '../tools/performance-audit.mjs';

async function withProxy(baseURL, intercept, run) {
  const server = createServer((request, response) => {
    if (intercept(request, response)) return;
    const url = new URL(request.url, baseURL);
    const upstream = proxyRequest(
      url,
      { method: request.method, headers: { ...request.headers, host: url.host } },
      (result) => {
        response.writeHead(result.statusCode, result.headers);
        result.pipe(response);
      },
    );
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502);
      response.end();
    });
    response.on('close', () => upstream.destroy());
    request.pipe(upstream);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    return await run(`http://127.0.0.1:${server.address().port}`);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
}

function json(response, body, status = 200) {
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(body));
}
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
  expect(report.failed).toBe(false);
  expect(report.discovery.map((row) => row.outcome)).toEqual(['selected', 'empty']);
});

test('business API errors cannot pass the CLI when documents and independent probes succeed', async ({
  baseURL,
}, info) => {
  test.setTimeout(90000);
  await withProxy(
    baseURL,
    (request, response) => {
      const path = new URL(request.url, baseURL).pathname;
      if (['/api/forum/posts', '/api/community/leaderboard'].includes(path)) {
        const browser = Boolean(request.headers['sec-fetch-mode']);
        json(
          response,
          browser ? { message: 'synthetic unavailable' } : { rows: [], total: 0 },
          browser ? 503 : 200,
        );
        return true;
      }
      return false;
    },
    async (site) => {
      const output = info.outputPath('failed-business.json');
      const result = await promisify(execFile)(process.execPath, [
        'tools/performance-audit.mjs',
        '--site',
        site,
        '--samples',
        '1',
        '--output',
        output,
        ...(process.env.ACM_E2E_BROWSER ? ['--browser', process.env.ACM_E2E_BROWSER] : []),
      ]).catch((error) => error);
      expect(result.code).toBe(1);
      const report = JSON.parse(await readFile(output, 'utf8'));
      const failures = report.pages.filter((row) =>
        ['/index.html', '/leaderboard.html'].includes(row.path),
      );
      expect(failures).toHaveLength(4);
      expect(failures.every((row) => row.error && row.readable == null)).toBe(true);
      expect(
        report.summary
          .filter((row) => ['/index.html', '/leaderboard.html'].includes(row.path))
          .every((row) => row.readable.success === 0),
      ).toBe(true);
      expect(report.probes.every((row) => !row.error)).toBe(true);
      expect(report.discovery.every((row) => !row.error)).toBe(true);
      expect(report.failed).toBe(true);
    },
  );
});

test('valid empty forum and leaderboard content still passes', async ({ baseURL }, info) => {
  test.setTimeout(90000);
  await withProxy(
    baseURL,
    (request, response) => {
      const path = new URL(request.url, baseURL).pathname;
      if (['/api/forum/posts', '/api/community/leaderboard'].includes(path)) {
        json(response, { rows: [], total: 0, page: 1, page_size: 20 });
        return true;
      }
      return false;
    },
    async (site) => {
      const report = await audit({
        sites: [site],
        samples: 1,
        output: info.outputPath('empty-content.json'),
        executablePath: process.env.ACM_E2E_BROWSER,
      });
      expect(report.pages).toHaveLength(6);
      expect(report.pages.every((row) => !row.error && row.readable > 0)).toBe(true);
      expect(report.discovery.every((row) => row.outcome === 'empty')).toBe(true);
      expect(report.failed).toBe(false);
    },
  );
});

for (const failure of ['http', 'json', 'shape', 'missing-id', 'timeout']) {
  test(`discovery ${failure} is recorded without failing later healthy pages or probes`, async ({
    baseURL,
  }, info) => {
    test.setTimeout(90000);
    let first = true;
    await withProxy(
      baseURL,
      (request, response) => {
        if (first && request.url === '/api/forum/posts?page_size=5') {
          first = false;
          if (failure === 'http') json(response, { message: 'synthetic unavailable' }, 503);
          else if (failure === 'json') response.end('{invalid');
          else if (failure === 'shape') json(response, { message: 'not a list' });
          else if (failure === 'missing-id') json(response, { rows: [{}] });
          // Keep the first discovery request pending to exercise the actual request timeout.
          return true;
        }
        return false;
      },
      async (site) => {
        const report = await audit({
          sites: [site],
          samples: 1,
          scenarios: [defaultScenarios[0]],
          timeout: 3000,
          output: info.outputPath('failed-discovery.json'),
          executablePath: process.env.ACM_E2E_BROWSER,
        });
        expect(report.discovery[0].outcome).toBe('failed');
        expect(report.discovery[0].error).toBeTruthy();
        expect(report.pages).toHaveLength(2);
        expect(report.pages.every((row) => !row.error && row.readable > 0)).toBe(true);
        expect(report.probes.every((row) => !row.error)).toBe(true);
        expect(report.failed).toBe(true);
      },
    );
  });
}
