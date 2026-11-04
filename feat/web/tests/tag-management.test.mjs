import assert from 'node:assert/strict';
import { test } from 'node:test';
import { tagDiff, filterProblems, filterTaxonomy } from '../src/lib/tag-management.js';

test('Chinese dynamic programming search finds existing DP IDs without creating new labels', () => {
  const tags = [{ id: 'linear_dp', name_zh: '线性 DP', tag_kind: 'specific' }];
  assert.equal(filterTaxonomy(tags, '动态').length, 1);
  assert.equal(filterTaxonomy(tags, '动态规划').length, 1);
});

test('draft diff reports additions and deletions independently', () => {
  assert.deepEqual(tagDiff(['dp', 'math'], ['dp', 'greedy']), {
    added: ['greedy'],
    removed: ['math'],
  });
});
test('clearing all labels is supported', () =>
  assert.deepEqual(tagDiff(['dp'], []), { added: [], removed: ['dp'] }));
test('unchanged sets ignore ordering', () =>
  assert.deepEqual(tagDiff(['a', 'b'], ['b', 'a']), { added: [], removed: [] }));
test('problem search supports names identities and Chinese effective labels', () => {
  const items = [
    {
      title: 'Train',
      problem_key: 'atcoder:abc:abc_a',
      review_status: 'auto',
      effective_tags: [{ id: 'dp', name_zh: '动态规划' }],
    },
  ];
  for (const text of ['train', 'abc_a', '动态', 'dp'])
    assert.equal(filterProblems(items, text).length, 1);
});
test('status filter and empty search combine', () => {
  const items = [{ title: 'A', problem_key: 'a', review_status: 'corrected', effective_tags: [] }];
  assert.equal(filterProblems(items, '  ', 'corrected').length, 1);
  assert.equal(filterProblems(items, '', 'auto').length, 0);
});
test('taxonomy filters kinds and standard IDs', () => {
  const tags = [
    { id: 'dp', name_zh: '动态规划', tag_kind: 'specific' },
    { id: 'temp_dp', name_zh: '临时动态规划', tag_kind: 'provisional' },
  ];
  assert.equal(filterTaxonomy(tags, '动态', 'specific').length, 1);
  assert.equal(filterTaxonomy(tags, 'TEMP_DP', 'all').length, 1);
  assert.equal(filterTaxonomy(tags, 'unknown', 'all').length, 0);
});
