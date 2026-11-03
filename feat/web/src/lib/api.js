import { reactive, ref, onBeforeUnmount } from 'vue';
import { adminSessionVersion, resetAdminSession } from './admin.js';

const anonymousAuth = () => ({
  authenticated: false,
  role: null,
  qq_id: null,
  account_epoch: null,
  csrf_token: '',
  avatar_url: null,
  must_change_password: false,
  account_closure_enabled: false,
});
export const auth = reactive(anonymousAuth());
export function setAuth(data, newSession = false) {
  if (
    newSession ||
    Boolean(data.authenticated) !== auth.authenticated ||
    (data.qq_id ?? null) !== auth.qq_id ||
    (data.account_epoch ?? null) !== auth.account_epoch
  )
    resetAdminSession();
  for (const key of Object.keys(auth)) delete auth[key];
  Object.assign(auth, anonymousAuth(), data);
}
export async function logoutSession() {
  try {
    await api('/auth/logout', { method: 'POST' });
  } catch (error) {
    if (error.status !== 401) throw error;
  }
  setAuth(anonymousAuth(), true);
}
export const notification = ref('');
export const pageLoadError = ref(null);
let noticeTimer;
export function notify(message) {
  notification.value = String(message || '');
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => {
    notification.value = '';
  }, 5000);
}
export function safeNext(value, fallback = '/index.html', exclude = []) {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\x00-\x1f\x7f]/.test(value)
  )
    return fallback;
  try {
    const url = new URL(value, 'https://acm.invalid');
    const path = decodeURIComponent(url.pathname).toLowerCase();
    if (
      path.startsWith('//') ||
      /[\\\x00-\x1f\x7f]/.test(path) ||
      ['/login.html', '/auth-unavailable.html', '/forbidden.html', ...exclude].includes(path)
    )
      return fallback;
    return value;
  } catch {
    return fallback;
  }
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
  const sessionVersion = adminSessionVersion();
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
  const closureRequest =
    path === '/me/account-closure' || /^\/account-closures\/[a-f0-9]{32}$/.test(path);
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
    if (sessionVersion !== adminSessionVersion())
      throw new DOMException('登录会话已改变', 'AbortError');
    if (
      response.status === 401 &&
      (!path.startsWith('/auth/') || ['/auth/me', '/auth/logout'].includes(path))
    ) {
      setAuth(anonymousAuth(), true);
      if (!closureRequest && !path.startsWith('/auth/'))
        location.assign(
          '/login.html?next=' +
            encodeURIComponent(location.pathname + location.search + (location.hash || '')),
        );
    }
    if (response.status === 428 && location.pathname !== '/change-password.html')
      location.assign(
        '/change-password.html?next=' +
          encodeURIComponent(location.pathname + location.search + (location.hash || '')),
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
      setAuth(data);
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

// Only an invalidation signal is shared. Receipt capabilities stay in this tab.
export function finishAccountClosure() {
  setAuth(anonymousAuth(), true);
  initialization = null;
  try {
    localStorage.setItem('acm-account-closed', String(Date.now()) + ':' + Math.random());
  } catch {
    /* Server-side epoch checks still revoke every old session. */
  }
}
if (typeof window !== 'undefined') {
  window.addEventListener('storage', async (event) => {
    if (event.key !== 'acm-account-closed' || !event.newValue) return;
    initialization = null;
    try {
      // Another tab may already have logged into a fresh account generation.
      // Revalidate the shared cookie before discarding that new login.
      const current = await api('/auth/me');
      setAuth(current);
      if (current.authenticated) return;
    } catch {
      setAuth(anonymousAuth(), true);
    }
    location.replace('/index.html');
  });
}
