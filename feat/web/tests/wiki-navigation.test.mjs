import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import {
  createWikiNavigationLoader,
  invalidateWikiNavigation,
  peekWikiNavigation,
} from '../src/lib/wiki-navigation.js';
import { adminWikiApi } from '../src/lib/wiki.js';
const realNow = Date.now;
beforeEach(invalidateWikiNavigation);
afterEach(() => {
  Date.now = realNow;
});
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
};

test('one owner merges pending navigation; only completed success is shared for thirty seconds', async () => {
  let now = 100,
    calls = 0;
  Date.now = () => now;
  const task = deferred();
  const first = createWikiNavigationLoader(() => {
    calls++;
    return task.promise;
  });
  const pending = first.load();
  assert.equal(first.load(), pending);
  assert.equal(peekWikiNavigation(), undefined);
  task.resolve({ categories: [] });
  const value = await pending;
  const other = createWikiNavigationLoader(async () => {
    calls++;
    return { categories: ['new'] };
  });
  assert.equal(await other.load(), value);
  assert.equal(calls, 1);
  now += 30_000;
  assert.equal(peekWikiNavigation(), undefined);
  assert.deepEqual(await other.load(), { categories: ['new'] });
  assert.equal(calls, 2);
});

test('different owners do not share a pending request or let a disposed response poison the cache', async () => {
  const a = deferred(),
    b = deferred();
  const first = createWikiNavigationLoader(() => a.promise);
  const second = createWikiNavigationLoader(() => b.promise);
  const old = first.load(),
    current = second.load();
  first.dispose();
  b.resolve({ categories: ['current'] });
  await current;
  a.resolve({ categories: ['obsolete'] });
  await assert.rejects(old, { name: 'AbortError' });
  assert.deepEqual(peekWikiNavigation(), { categories: ['current'] });
  await assert.rejects(first.load(), { name: 'AbortError' });
});

test('invalidation rejects an in-flight old generation and failures remain retryable', async () => {
  const task = deferred();
  let calls = 0;
  const loader = createWikiNavigationLoader(() =>
    ++calls === 1 ? task.promise : Promise.resolve({ categories: ['new'] }),
  );
  const old = loader.load();
  invalidateWikiNavigation();
  assert.deepEqual(await loader.load(), { categories: ['new'] });
  task.resolve({ categories: ['old'] });
  await assert.rejects(old, { codeName: 'wiki_navigation_invalidated' });
  assert.deepEqual(peekWikiNavigation(), { categories: ['new'] });
  invalidateWikiNavigation();
  let fail = true;
  const retry = createWikiNavigationLoader(async () => {
    if (fail) throw Error('offline');
    return { categories: [] };
  });
  await assert.rejects(retry.load(), /offline/);
  assert.equal(peekWikiNavigation(), undefined);
  fail = false;
  assert.deepEqual(await retry.load(), { categories: [] });
});

test('successful public mutations invalidate navigation while private maintenance does not', async () => {
  const loader = createWikiNavigationLoader(async () => ({ categories: [] }));
  for (const [path, method, body] of [
    ['/categories', 'POST', {}],
    ['/categories/2', 'PATCH', {}],
    ['/categories/order', 'PUT', {}],
    ['/categories/2/delete', 'POST', {}],
    ['/category-operations/3/restore', 'POST', {}],
    ['/settings', 'PUT', {}],
    ['/revisions/4/publish', 'POST', {}],
    ['/revisions/4', 'PATCH', { hidden: true }],
    ['/pages/1', 'PATCH', { category_id: 3 }],
  ]) {
    await loader.load();
    await adminWikiApi(path, { method, body }, async () => ({}));
    assert.equal(peekWikiNavigation(), undefined, path);
  }
  for (const [path, method] of [
    ['/pages', 'POST'],
    ['/pages/1/revisions', 'POST'],
    ['/categories/2/delete-preview', 'POST'],
    ['/revisions/1/markdown', 'GET'],
    ['/categories', 'GET'],
  ]) {
    const before = await loader.load();
    await adminWikiApi(path, { method }, async () => ({}));
    assert.equal(peekWikiNavigation(), before, path);
  }
  const before = await loader.load();
  await assert.rejects(
    adminWikiApi('/categories/1', { method: 'PATCH' }, async () => {
      throw Error('conflict');
    }),
    /conflict/,
  );
  assert.equal(peekWikiNavigation(), before);
});
