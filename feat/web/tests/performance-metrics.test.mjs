import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  origin,
  percentile,
  summarize,
  phases,
  resourceKind,
} from '../tools/performance-metrics.mjs';
test('failed and absent samples cannot be reported as fast successes', () => {
  assert.deepEqual(
    summarize(
      [{ readable: 100 }, { readable: 200 }, { error: 'timeout', readable: 0 }, {}],
      'readable',
    ),
    { samples: 4, success: 2, median: 150, p95: 200 },
  );
  assert.equal(percentile([], 0.95), null);
});
test('nearest rank p95 retains a slow tail rather than averaging it away', () => {
  assert.equal(percentile([5, 10, 900], 0.95), 900);
});
test('only explicit HTTP origins without secrets are accepted', () => {
  assert.equal(origin('https://example.org/'), 'https://example.org');
  for (const value of [
    'file:///x',
    'https://user:secret@example.org',
    'https://example.org/path',
    'https://example.org/?token=secret',
  ])
    assert.throws(() => origin(value));
});
test('phase boundaries account for reused connections and API classification', () => {
  assert.deepEqual(
    phases({
      startTime: 0,
      domainLookupStart: 0,
      domainLookupEnd: 0,
      connectStart: 0,
      connectEnd: 0,
      secureConnectionStart: 0,
      requestStart: 1,
      responseStart: 20,
      responseEnd: 25,
    }),
    { dns: 0, connect: 0, tls: 0, ttfb: 19, download: 5, total: 25 },
  );
  assert.equal(resourceKind('/api/wiki/navigation'), 'api');
  assert.equal(resourceKind('/assets/site.js'), 'static');
});
