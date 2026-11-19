import { trainingReturn } from './training-tasks.js';
import { ratingFilters } from './problem-filters.js';
import { nativeFilters } from './luogu-problems.js';
const platforms = ['codeforces', 'luogu', 'atcoder', 'nowcoder', 'cjlu'];
export function memberFilters(query = {}) {
  const number = Number(query.page);
  const view = query.view === 'tracker' ? 'tracker' : 'list';
  const allowedPlatforms = view === 'tracker' ? ['codeforces', 'atcoder'] : ['all', ...platforms];
  // Keep existing all-OJ AC views and generic-filter bookmarks intact.
  const genericFilters = ['problem_tag', 'rating_min', 'rating_max'].some(
    (key) => typeof query[key] === 'string' && query[key].trim(),
  );
  const listDefault =
    query.scope === 'solved' || genericFilters || (query.platform != null && query.platform !== '')
      ? 'all'
      : 'luogu';
  const platform = allowedPlatforms.includes(query.platform)
    ? query.platform
    : view === 'tracker'
      ? 'codeforces'
      : listDefault;
  const native = platform === 'luogu' && view !== 'tracker';
  const problemTags =
    platform === 'codeforces' && typeof query.problem_tags === 'string'
      ? query.problem_tags.trim()
      : '';
  const normalized = { ...query, platform, view };
  return {
    ...nativeFilters(normalized),
    ...ratingFilters(normalized),
    view,
    scope: query.scope === 'solved' ? 'solved' : 'all',
    platform,
    tag: typeof query.tag === 'string' ? query.tag.slice(0, 100) : '',
    problem_tag:
      !native && !problemTags && typeof query.problem_tag === 'string'
        ? query.problem_tag.trim().slice(0, 100)
        : '',
    problem_tags: problemTags,
    state: query.state === 'favorite' ? 'favorite' : '',
    page: Number.isSafeInteger(number) && number > 0 && number <= 1000000 ? number : 1,
  };
}
export function memberQuery(filters) {
  return Object.fromEntries(
    Object.entries(memberFilters(filters)).filter(
      ([key, value]) =>
        value &&
        !(key === 'view' && value === 'list') &&
        !(key === 'scope' && value === 'all') &&
        !(key === 'page' && value === 1),
    ),
  );
}
export function problemReturn(value, manager = false) {
  const training = trainingReturn(value);
  if (training && (manager || !training.startsWith('/admin.html'))) return training;
  if (value === '/home.html') return value;
  if (typeof value === 'string' && !/[\\\x00-\x1f]/.test(value)) {
    try {
      const url = new URL(value, 'https://acm.invalid');
      if (
        value.startsWith('/') &&
        !value.startsWith('//') &&
        url.origin === 'https://acm.invalid' &&
        ['/problem-bank.html', '/my-problems.html'].includes(url.pathname)
      ) {
        const query = new URLSearchParams(memberQuery(Object.fromEntries(url.searchParams)));
        return url.pathname + (query.size ? '?' + query : '');
      }
    } catch {
      /* Fall back to a known entry. */
    }
  }
  return manager ? '/admin.html?section=problems' : '/problem-bank.html';
}
export function problemLink(row, from) {
  return {
    path: '/problem.html',
    query: { platform: row.platform, problem_id: row.problem_id, from },
  };
}
