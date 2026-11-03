// Only successful public navigation is shared; pending requests belong to each view.
const TTL = 30_000;
let cached, expiresAt = 0, generation = 0;
export function invalidateWikiNavigation() {
  generation++;
  cached = undefined;
  expiresAt = 0;
}
export function peekWikiNavigation() {
  return Date.now() < expiresAt ? cached : undefined;
}
export function createWikiNavigationLoader(request) {
  let pending, pendingGeneration, disposed = false;
  return {
    load(force = false) {
      if (disposed) return Promise.reject(new DOMException('页面已离开', 'AbortError'));
      const value = peekWikiNavigation();
      if (!force && value) return Promise.resolve(value);
      if (pending && pendingGeneration === generation) return pending;
      const current = generation;
      pendingGeneration = current;
      const operation = request('/wiki/navigation', {}, 'wiki-navigation').then(data => {
        if (disposed) throw new DOMException('页面已离开', 'AbortError');
        if (current !== generation)
          throw Object.assign(new DOMException('目录已更新', 'AbortError'), {
            codeName: 'wiki_navigation_invalidated',
          });
        cached = data;
        expiresAt = Date.now() + TTL;
        return data;
      }).finally(() => {
        if (pending === operation) pending = undefined;
      });
      pending = operation;
      return operation;
    },
    dispose() { disposed = true; },
  };
}

export function affectsPublicWiki(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  if (method === 'GET') return false;
  path = path.split('?')[0];
  return (
    (path.startsWith('/categories') && !path.endsWith('/delete-preview')) ||
    path === '/settings' ||
    /^\/category-operations\/\d+\/restore$/.test(path) ||
    (method === 'PATCH' && /^\/pages\/\d+$/.test(path) &&
      Object.hasOwn(options.body || {}, 'category_id')) ||
    /^\/revisions\/\d+\/publish$/.test(path) ||
    (method === 'PATCH' && /^\/revisions\/\d+$/.test(path))
  );
}
