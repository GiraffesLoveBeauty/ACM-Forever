import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  collectionTime,
  localTime,
  timeValue,
  rangeParams,
  timeLabel,
} from '../src/lib/problem-filters.js';
import { nativeParams } from '../src/lib/luogu-problems.js';
import { memberQuery, problemReturn } from '../src/lib/member-problems.js';
test('manual all drops stale boundaries while time ranges are explicit and exclusive', () => {
  const form = { platform: 'codeforces', scope: 'platform', start_at: '100', end_at: '200' };
  assert.deepEqual(collectionTime({ ...form, range_mode: 'all' }), {});
  assert.deepEqual(collectionTime({ ...form, range_mode: 'time' }), {
    start_at: 100,
    end_at: 200,
    time_basis: 'contest',
  });
  assert.equal(
    collectionTime({ ...form, platform: 'luogu', range_mode: 'time' }).time_basis,
    'first_seen',
  );
  assert.throws(() => collectionTime({ ...form, start_at: '200', range_mode: 'time' }));
  assert.throws(() => collectionTime({ ...form, start_at: '', end_at: '', range_mode: 'time' }));
});
test('Beijing date controls preserve absolute time in any browser timezone', () => {
  assert.equal(timeValue('2026-11-01T08:00'), '1793491200');
  assert.equal(localTime('1793491200'), '2026-11-01T08:00');
  assert.equal(localTime(''), '');
  assert.equal(timeValue(''), '');
});
test('member detail returns preserve Luogu native filters and drop retired dates', () => {
  const query = memberQuery({
    platform: 'luogu',
    native_difficulty_min: '3',
    native_difficulty_max: '4',
    native_tags: '1,-2,1',
    start_at: '100',
    end_at: '200',
    time_basis: 'first_seen',
  });
  assert.equal(query.native_tags, '1,-2');
  assert.equal(query.time_basis, undefined);
  assert.equal(query.start_at, undefined);
  assert.equal(query.end_at, undefined);
  const returned = problemReturn(
    '/problem-bank.html?platform=luogu&native_difficulty_min=3&native_difficulty_max=4&native_tags=1,-2&time_basis=first_seen&start_at=100&end_at=200',
  );
  const params = new URL(returned, 'https://example.invalid').searchParams;
  assert.equal(params.get('native_difficulty_min'), '3');
  assert.equal(params.get('native_difficulty_max'), '4');
  assert.equal(params.get('native_tags'), '1,-2');
  assert.equal(params.get('time_basis'), null);
  assert.equal(params.get('start_at'), null);
  assert.equal(params.get('end_at'), null);
  assert.deepEqual(nativeParams({ ...query, platform: 'codeforces' }), {});
});
test('numeric ranges use only CF or AtCoder scales and cannot leak to tracker', () => {
  assert.deepEqual(
    rangeParams({ platform: 'codeforces', rating_min: '1200', rating_max: '1800' }),
    { rating_min: '1200', rating_max: '1800' },
  );
  assert.deepEqual(rangeParams({ platform: 'luogu', rating_min: '1200', rating_max: '1800' }), {});
  assert.deepEqual(rangeParams({ platform: 'atcoder', view: 'tracker', rating_min: '1200' }), {});
  assert.equal(timeLabel({ time_basis: 'first_seen' }), '首次收录');
});

test('member list links omit retired dates and keep difficulty bounds', () => {
  const options = { platform: 'codeforces', rating_min: '1200', start_at: '100', end_at: '200' };
  for (const basis of [undefined, 'first_seen', 'auto', 'contest', 'unknown'])
    assert.deepEqual(memberQuery({ ...options, time_basis: basis }), {
      platform: 'codeforces',
      rating_min: '1200',
    });
});

test('shared range filters support unknown source time and clear incompatible date bounds', () => {
  assert.deepEqual(
    rangeParams({ platform: 'codeforces', time_basis: 'unknown', start_at: '100', end_at: '200' }),
    { time_basis: 'unknown' },
  );
});
