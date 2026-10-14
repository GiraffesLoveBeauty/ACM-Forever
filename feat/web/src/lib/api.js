import { reactive, ref, onBeforeUnmount } from 'vue';

export const auth = reactive({
  authenticated: false,
  role: null,
  qq_id: null,
  csrf_token: '',
  avatar_url: null,
});
export const notification = ref('');
let noticeTimer;
export function notify(message) {
  notification.value = String(message || '');
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => {
    notification.value = '';
  }, 5000);
}
export function safeNext(value, fallback = '/index.html') {
  return typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//') &&
    !/[\\\x00-\x1f]/.test(value)
    ? value
    : fallback;
}
export function avatar(value) {
  return /^\/uploads\/avatars\/[a-f0-9]{32}\.(png|jpg|webp)$/.test(value || '')
    ? value
    : '/assets/default-avatar.png';
}
export function external(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : '#';
  } catch {
    return '#';
  }
}
export function date(value) {
  if (!value) return '—';
  const d = new Date(typeof value === 'number' ? value * 1000 : value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
}
export async function api(path, options = {}) {
  let body = options.body;
  if (auth.authenticated && auth.role === 'member') {
    const [pathname, query = ''] = path.split('?');
    const params = new URLSearchParams(query);
    params.delete('owner_qq_id');
    params.delete('qq_id');
    const routes = {
      '/challenge/list': '/me/training/challenges',
      '/challenge/start': '/me/challenge/start',
      '/challenge/rating': '/me/challenge/rating',
      '/problems': '/me/problems',
      '/training/weak-tags': '/me/reviews/weak-tags',
      '/training/summary': '/me/training/summary',
      '/contest/reviews': '/me/contest/reviews',
    };
    const from = Object.keys(routes).find(
      (key) => pathname === key || pathname.startsWith(key + '/'),
    );
    path =
      (from ? routes[from] + pathname.slice(from.length) : pathname) +
      (params.size ? '?' + params : '');
    if (body && !(body instanceof FormData)) {
      body = { ...body };
      delete body.qq_id;
      delete body.owner_qq_id;
    }
  }
  const { timeoutMs = 15000, signal, ...rest } = options;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    abort();
  }, timeoutMs);
  try {
    const response = await fetch('/api' + path, {
      credentials: 'same-origin',
      ...rest,
      signal: controller.signal,
      body: body == null ? undefined : body instanceof FormData ? body : JSON.stringify(body),
      headers: {
        ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        'X-CSRF-Token': auth.csrf_token || '',
        ...rest.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith('/auth/'))
      location.assign(
        '/login.html?next=' + encodeURIComponent(location.pathname + location.search),
      );
    if (response.status === 428 && location.pathname !== '/change-password.html')
      location.assign(
        '/change-password.html?next=' + encodeURIComponent(location.pathname + location.search),
      );
    if (!response.ok)
      throw Object.assign(Error(data.message || data.error || `HTTP ${response.status}`), {
        status: response.status,
        code: data.code || data.error_code,
        details: data,
      });
    return data;
  } catch (error) {
    if (timedOut && !signal?.aborted)
      throw Object.assign(Error('请求超时，请重试。'), { code: 'request_timeout' });
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
let initialization;
export function initializeAuth() {
  return (initialization ||= api('/auth/me')
    .then(async (data) => {
      Object.assign(auth, data);
      if (['admin', 'root'].includes(auth.role) && !auth.must_change_password) {
        try {
          const preferences = await api('/ui/preferences');
          document.documentElement.style.setProperty('--font-scale', preferences.font_scale || 1);
        } catch {
          /* Preferences must not prevent signing in. */
        }
      }
      return auth;
    })
    .catch((error) => {
      initialization = null;
      throw error;
    }));
}
// Every view owns its request lifetime. Replacement queries abort older requests.
export function useRequests() {
  const pending = new Map();
  let disposed = false;
  onBeforeUnmount(() => {
    disposed = true;
    for (const controller of pending.values()) controller.abort();
  });
  return async (path, options = {}, key = path) => {
    if (disposed) throw new DOMException('请求已取消', 'AbortError');
    pending.get(key)?.abort();
    const controller = new AbortController();
    pending.set(key, controller);
    try {
      const value = await api(path, { ...options, signal: controller.signal });
      if (disposed || controller.signal.aborted) throw new DOMException('请求已取消', 'AbortError');
      return value;
    } finally {
      if (pending.get(key) === controller) pending.delete(key);
    }
  };
}
export function showError(error) {
  if (error.name !== 'AbortError') notify(error.message);
}
