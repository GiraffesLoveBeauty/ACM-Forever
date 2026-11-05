export const reviewLabels = {
  auto: '自动标注',
  corrected: '人工修正',
  verified: '人工确认',
  needs_review: '需要复核',
};
export const sourceLabels = {
  ai: 'AI 自动',
  cf_rule_mapping: 'CF 映射',
  manual_add: '人工添加',
  legacy_human: '历史人工确认',
};
export function tagDiff(original = [], chosen = []) {
  const before = new Set(original),
    after = new Set(chosen);
  return {
    added: [...after].filter((id) => !before.has(id)),
    removed: [...before].filter((id) => !after.has(id)),
  };
}
function normalizeSearch(text) {
  return String(text ?? '')
    .trim()
    .toLowerCase()
    .replace(/动态规划|动态/g, 'dp');
}
export function filterProblems(items, text, status = 'all') {
  const query = normalizeSearch(text);
  return items.filter(
    (p) =>
      (status === 'all' || p.review_status === status) &&
      (!query ||
        [p.title, p.problem_key, ...p.effective_tags.flatMap((t) => [t.id, t.name_zh])].some((v) =>
          normalizeSearch(v).includes(query),
        )),
  );
}
export function filterTaxonomy(tags, text, kind = 'all') {
  const query = normalizeSearch(text);
  return tags.filter(
    (t) =>
      (kind === 'all' || t.tag_kind === kind) &&
      (!query ||
        normalizeSearch(t.name_zh).includes(query) ||
        normalizeSearch(t.id).includes(query)),
  );
}
