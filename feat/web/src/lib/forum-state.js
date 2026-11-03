const text = (value) => (typeof value === 'string' ? value : '');
export function forumState(query = {}, savedView = 'list') {
  const page = /^\d+$/.test(text(query.page)) ? Number(query.page) : 1;
  return {
    sort: ['latest', 'hot', 'unanswered'].includes(query.sort) ? query.sort : 'latest',
    category: /^[a-z0-9-]{1,48}$/.test(text(query.category)) ? query.category : '',
    q: text(query.q).trim().slice(0, 100),
    page: Math.min(1000000, Math.max(1, page || 1)),
    view: ['list', 'grid'].includes(query.view)
      ? query.view
      : savedView === 'grid'
        ? 'grid'
        : 'list',
  };
}
export function forumQuery(state) {
  return {
    ...(state.sort !== 'latest' ? { sort: state.sort } : {}),
    ...(state.category ? { category: state.category } : {}),
    ...(state.q ? { q: state.q } : {}),
    ...(state.page > 1 ? { page: String(state.page) } : {}),
    view: state.view,
  };
}
export function forumReturn(value) {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\x00-\x20]/.test(value)
  )
    return '/index.html';
  try {
    const url = new URL(value, 'https://acm.invalid');
    if (!['/', '/index.html'].includes(url.pathname)) return '/index.html';
    return (
      url.pathname +
      '?' +
      new URLSearchParams(forumQuery(forumState(Object.fromEntries(url.searchParams))))
    );
  } catch {
    return '/index.html';
  }
}
