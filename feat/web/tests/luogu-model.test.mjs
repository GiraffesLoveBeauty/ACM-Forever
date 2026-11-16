import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  nativeColor,
  nativeFilters,
  nativeParams,
  luoguCollection,
} from '../src/lib/luogu-problems.js';
import { memberQuery, problemReturn } from '../src/lib/member-problems.js';
test('native ID zero and signed tags survive query and safe return links', () => {
  const query = memberQuery({
    platform: 'luogu',
    native_difficulty: '0',
    native_tag: '-2',
    page: 3,
  });
  assert.equal(query.native_difficulty, '0');
  assert.equal(query.native_tag, '-2');
  const result = new URL(
    problemReturn('/problem-bank.html?' + new URLSearchParams(query)),
    'https://example.invalid',
  );
  assert.equal(result.searchParams.get('native_difficulty'), '0');
  assert.equal(result.searchParams.get('native_tag'), '-2');
  assert.equal(result.searchParams.get('page'), '3');
});
test('native filters cannot leak into other platforms or contest tracker', () => {
  for (const query of [
    { platform: 'codeforces' },
    { platform: 'all' },
    { platform: 'luogu', view: 'tracker' },
  ]) {
    assert.deepEqual(nativeParams({ ...query, native_difficulty: '0', native_tag: '-2' }), {});
  }
});
test('invalid and repeated query values are removed while unknown valid IDs remain usable', () => {
  for (const value of [['1', '2'], '1.2', '1e2', 'javascript:1', '9999999999'])
    assert.equal(nativeFilters({ platform: 'luogu', native_tag: value }).native_tag, '');
  assert.equal(nativeFilters({ platform: 'luogu', native_difficulty: '-2' }).native_difficulty, '');
  assert.deepEqual(
    nativeParams({ platform: 'luogu', native_tag: '-999', native_difficulty: '99' }),
    { native_difficulty: '99', native_tag: '-999' },
  );
});
test('collection normalizes P IDs and full collection has no total cap', () => {
  const payload = luoguCollection({
    scope: 'problems',
    problem_ids: 'p1001，P1002 P1001',
    contest_id: 'bad',
  });
  assert.deepEqual(payload, {
    platform: 'luogu',
    scope: 'problems',
    language: 'zh-CN',
    refresh: false,
    problem_ids: ['P1001', 'P1002'],
  });
  const full = luoguCollection({ scope: 'platform', limit: 100, batch_size: 50 });
  assert.equal('limit' in full, false);
  assert.equal(full.batch_size, 50);
  assert.equal('problem_ids' in full, false);
  assert.equal('contest_id' in full, false);
  assert.equal('limit' in luoguCollection({ scope: 'catalog', batch_size: 50 }), false);
});
test('collection refuses invalid IDs, scopes and size boundaries', () => {
  for (const id of ['', 'B1001', 'P01', 'P0', 'https://www.luogu.com.cn/problem/P1001'])
    assert.throws(() => luoguCollection({ scope: 'problems', problem_ids: id }));
  assert.throws(() =>
    luoguCollection({
      scope: 'problems',
      problem_ids: Array.from({ length: 101 }, (_, i) => 'P' + (i + 1)).join(','),
    }),
  );
  for (const batch_size of [0, 101, 1.5])
    assert.throws(() => luoguCollection({ scope: 'platform', batch_size }));
  assert.throws(() => luoguCollection({ scope: 'catalog', batch_size: 0 }));
  assert.throws(() => luoguCollection({ scope: 'contest' }));
});
test('native colors use a fixed palette and untrusted tokens fall back safely', () => {
  assert.equal(nativeColor('pink-3'), '#fe4c61');
  assert.equal(nativeColor('gold-3'), '#ffc116');
  assert.equal(nativeColor('lapis-4'), '#0e1d69');
  assert.equal(nativeColor('grey-5'), '#262626');
  assert.equal(nativeColor('url(javascript:alert(1))'), '#85928d');
});

test('Luogu removes hidden secondary filters from old links and returns', () => {
  const query = memberQuery({
    platform: 'luogu',
    labels: 'dp,math',
    match: 'any',
    problem_tag: 'math',
    native_tag: '-2',
  });
  assert.equal(query.labels, undefined);
  assert.equal(query.match, undefined);
  assert.equal(query.problem_tag, undefined);
  assert.equal(query.native_tag, '-2');
});

test('over-limit tag URLs preserve all conditions for API validation instead of truncating', () => {
  const tags = Array.from({ length: 21 }, (_, i) => String(i + 1)).join(',');
  const query = { platform: 'luogu', native_tags: tags };
  assert.equal(nativeFilters(query).native_tags, tags);
  assert.equal(nativeParams(query).native_tags, tags);
  const returned = new URL(
    problemReturn('/problem-bank.html?' + new URLSearchParams(memberQuery(query))),
    'https://example.invalid',
  );
  assert.equal(returned.searchParams.get('native_tags'), tags);
});
