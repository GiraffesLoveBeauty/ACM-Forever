import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { origin, phases, resourceKind, summarize } from './performance-metrics.mjs';

export async function audit({
  sites,
  samples = 3,
  output,
  executablePath,
  scenarios,
  timeout = 30000,
}) {
  const browser = await chromium.launch({ executablePath });
  const report = {
    schema: 1,
    measuredAt: new Date().toISOString(),
    browser: browser.version(),
    viewport: { width: 1440, height: 900 },
    samples,
    method:
      'Anonymous fresh browser context (cold) followed by reload in the same context (warm). No CPU/network throttling. Each API probe is an independent request; its timings are not browser TTFB.',
    pages: [],
    probes: [],
  };
  try {
    for (const site of sites.map(origin)) {
      const selectedScenarios = [...scenarios];
      const discovery = await browser.newContext();
      try {
        for (const [path, list, field, target, ready] of [
          ['/api/forum/posts?page_size=5', 'rows', 'id', '/post.html?id=', '.forum-article-body'],
          [
            '/api/wiki/pages?page_size=1',
            'items',
            'slug',
            '/wiki.html?slug=',
            '.wiki-reader-layout',
          ],
        ]) {
          const result = await discovery.request
            .get(site + path, { timeout, maxRedirects: 0 })
            .catch(() => null);
          const data = result?.ok() ? await result.json().catch(() => null) : null;
          const value = data?.[list]?.[0]?.[field];
          if (value != null)
            selectedScenarios.push({ path: target + encodeURIComponent(value), ready });
        }
      } finally {
        await discovery.close();
      }
      for (let sample = 1; sample <= samples; sample++) {
        for (const scenario of selectedScenarios) {
          const context = await browser.newContext({
            viewport: { width: 1440, height: 900 },
            serviceWorkers: 'block',
          });
          try {
            const page = await context.newPage();
            await page.addInitScript(() => {
              window.auditLcp = null;
              new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) window.auditLcp = entry.startTime;
              }).observe({ type: 'largest-contentful-paint', buffered: true });
            });
            for (const mode of ['cold', 'warm']) {
              const row = { site, path: scenario.path, sample, mode, resources: [], errors: [] };
              const failed = (request) =>
                row.errors.push({
                  origin: new URL(request.url()).origin,
                  path: new URL(request.url()).pathname,
                  kind: 'requestfailed',
                });
              page.on('requestfailed', failed);
              const httpError = (response) => {
                if (response.status() >= 400)
                  row.errors.push({
                    origin: new URL(response.url()).origin,
                    path: new URL(response.url()).pathname,
                    kind: 'http',
                    status: response.status(),
                  });
              };
              page.on('response', httpError);
              try {
                const started = performance.now();
                const response =
                  mode === 'cold'
                    ? await page.goto(site + scenario.path, {
                        waitUntil: 'domcontentloaded',
                        timeout,
                      })
                    : await page.reload({ waitUntil: 'domcontentloaded', timeout });
                row.status = response.status();
                if (!response.ok() || new URL(page.url()).origin !== site)
                  throw Error('Navigation failed or left the requested origin');
                await page.locator(scenario.ready).first().waitFor({ state: 'visible', timeout });
                row.readable = Math.round(performance.now() - started);
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
                const data = await page.evaluate(() => ({
                  navigation: performance.getEntriesByType('navigation')[0]?.toJSON(),
                  paint:
                    performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
                  lcp: window.auditLcp,
                  resources: performance.getEntriesByType('resource').map((entry) => ({
                    ...entry.toJSON(),
                    serverTiming: entry.serverTiming.map((t) => ({
                      name: t.name,
                      duration: t.duration,
                      description: t.description,
                    })),
                  })),
                  overflow: document.documentElement.scrollWidth > innerWidth + 1,
                }));
                row.navigation = phases(data.navigation);
                row.fcp = data.paint;
                row.lcp = data.lcp;
                row.overflow = data.overflow;
                row.resources = data.resources
                  .filter((resource) => new URL(resource.name).origin === site)
                  .map((resource) => ({
                    path: new URL(resource.name).pathname,
                    kind: resourceKind(new URL(resource.name).pathname),
                    ...phases(resource),
                    transferBytes: resource.transferSize,
                    bodyBytes: resource.encodedBodySize,
                    serverTiming: resource.serverTiming,
                  }));
                row.apiCount = row.resources.filter((resource) => resource.kind === 'api').length;
                row.staticBytes = row.resources
                  .filter((resource) => resource.kind === 'static')
                  .reduce((sum, resource) => sum + resource.transferBytes, 0);
              } catch (error) {
                row.error = error.message;
              } finally {
                page.off('requestfailed', failed);
                page.off('response', httpError);
                report.pages.push(row);
                console.log(
                  `${site} ${scenario.path} ${mode} ${sample}: ${row.error || row.readable + 'ms'}`,
                );
              }
            }
          } finally {
            await context.close();
          }
        }
        for (const path of [
          '/health',
          '/api/forum/categories',
          '/api/forum/posts?page_size=5',
          '/api/wiki/navigation',
        ]) {
          const row = { site, path, sample };
          const context = await browser.newContext();
          try {
            const started = performance.now();
            const response = await context.request.get(site + path, { timeout, maxRedirects: 0 });
            await response.body();
            row.total = Math.round(performance.now() - started);
            row.status = response.status();
            row.serverTiming = response.headers()['server-timing'] || null;
            if (!response.ok()) row.error = `HTTP ${response.status()}`;
          } catch (error) {
            row.error = error.message;
          } finally {
            report.probes.push(row);
            await context.close();
          }
        }
      }
    }
  } finally {
    await browser.close();
  }
  report.completedAt = new Date().toISOString();
  report.summary = [
    ...new Set(report.pages.map((row) => JSON.stringify([row.site, row.path, row.mode]))),
  ].map((key) => {
    const [site, path, mode] = JSON.parse(key),
      rows = report.pages.filter(
        (row) => row.site === site && row.path === path && row.mode === mode,
      );
    return {
      site,
      path,
      mode,
      readable: summarize(rows, 'readable'),
      fcp: summarize(rows, 'fcp'),
      lcp: summarize(rows, 'lcp'),
    };
  });
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, JSON.stringify(report, null, 2) + '\n');
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values } = parseArgs({
    options: {
      site: { type: 'string', multiple: true },
      samples: { type: 'string', default: '3' },
      output: { type: 'string' },
      browser: { type: 'string' },
      help: { type: 'boolean' },
    },
  });
  if (values.help)
    console.log(
      'node tools/performance-audit.mjs --site https://site.example [--site https://second.example] --output /path/report.json [--samples 3] [--browser /path/chrome]',
    );
  else {
    const samples = Number(values.samples);
    if (
      !values.site?.length ||
      !values.output ||
      !Number.isInteger(samples) ||
      samples < 1 ||
      samples > 10
    )
      throw Error('Provide --site, --output and 1–10 samples.');
    const report = await audit({
      sites: values.site,
      samples,
      output: resolve(values.output),
      executablePath: values.browser,
      scenarios: [
        { path: '/index.html', ready: '.forum-post-card, .forum-empty' },
        {
          path: '/wiki.html',
          ready: '.wiki-hero, .wiki-page-heading, .wiki-reader-layout, .wiki-empty',
        },
        { path: '/leaderboard.html', ready: '.community-table-wrap[aria-busy="false"] tbody tr' },
      ],
    });
    if (report.pages.some((row) => row.error) || report.probes.some((row) => row.error))
      process.exitCode = 1;
  }
}
