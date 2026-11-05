const platforms = ['codeforces', 'luogu', 'atcoder', 'nowcoder', 'cjlu'];
export function memberFilters(query = {}) {
  const number = Number(query.page);
  const view = query.view === 'tracker' ? 'tracker' : 'list';
  const allowedPlatforms = view === 'tracker' ? ['codeforces', 'atcoder'] : ['all', ...platforms];
  return {
    view,
    scope: query.scope === 'solved' ? 'solved' : 'all',
    platform: allowedPlatforms.includes(query.platform)
      ? query.platform
      : view === 'tracker'
        ? 'codeforces'
        : 'all',
    tag: typeof query.tag === 'string' ? query.tag.slice(0, 100) : '',
    problem_tag:
      typeof query.problem_tag === 'string' ? query.problem_tag.trim().slice(0, 100) : '',
    state: query.state === 'favorite' ? 'favorite' : '',
    labels:
      view === 'tracker'
        ? ''
        : [
            ...new Set(
              (typeof query.labels === 'string' ? query.labels : '')
                .split(',')
                .filter((t) => /^[a-z][a-z0-9_]{0,80}$/.test(t)),
            ),
          ]
            .sort()
            .slice(0, 115)
            .join(','),
    match: query.match === 'any' && view !== 'tracker' ? 'any' : 'all',
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
        !(key === 'match' && value === 'all') &&
        !(key === 'page' && value === 1),
    ),
  );
}
export function problemReturn(value, manager = false) {
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
