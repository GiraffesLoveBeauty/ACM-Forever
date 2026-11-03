import { createRouter, createWebHistory } from 'vue-router';
import { initializeAuth, auth, safeNext, notify, pageLoadError } from './lib/api.js';
const legacy = {
  '/member.html': 'members',
  '/challenge.html': 'training',
  '/problem-bank.html': 'problems',
  '/contest-review.html': 'contests',
  '/tasks.html': 'tasks',
  '/settings.html': 'settings',
  '/forum-moderation.html': 'moderation',
  '/cf-practice.html': 'cf-practice',
};
export const sections = {
  accounts: '成员账号',
  members: '成员资料',
  training: '训练管理',
  problems: '题库管理',
  'cf-practice': 'CF 练习赛选题',
  contests: '赛事复盘',
  tasks: '同步任务',
  moderation: '内容审核',
  settings: '全局设置',
  wiki: 'Wiki 知识手册',
};
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      alias: '/index.html',
      component: () => import('./views/Forum.vue'),
      meta: { public: true, title: '论坛', body: 'forum-home' },
    },
    {
      path: '/post.html',
      component: () => import('./views/Post.vue'),
      meta: { public: true, title: '话题' },
    },
    {
      path: '/compose.html',
      component: () => import('./views/Compose.vue'),
      meta: { title: '发布话题' },
    },
    {
      path: '/notifications.html',
      component: () => import('./views/Notifications.vue'),
      meta: { title: '我的通知' },
    },
    {
      path: '/my-post.html',
      component: () => import('./views/MyPost.vue'),
      meta: { title: '投稿进度' },
    },
    {
      path: '/auth-unavailable.html',
      component: () => import('./views/Notice.vue'),
      meta: { public: true, title: '暂时无法确认登录状态', authError: true },
    },
    {
      path: '/forbidden.html',
      component: () => import('./views/Notice.vue'),
      meta: { public: true, title: '无权访问', forbidden: true },
    },
    {
      path: '/wiki.html',
      component: () => import('./views/Wiki.vue'),
      meta: { public: true, title: 'Wiki 知识手册', body: 'wiki-page' },
    },
    {
      path: '/home.html',
      component: () => import('./views/Home.vue'),
      meta: { title: '个人中心', body: 'personal-page' },
    },
    {
      path: '/leaderboard.html',
      component: () => import('./views/Leaderboard.vue'),
      meta: { public: true, title: '排行榜', body: 'leaderboard-page' },
    },
    {
      path: '/login.html',
      component: () => import('./views/Auth.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/change-password.html',
      component: () => import('./views/Auth.vue'),
      meta: { title: '修改密码' },
    },
    {
      path: '/admin.html',
      component: () => import('./views/Admin.vue'),
      meta: { admin: true, title: '管理后台' },
    },
    {
      path: '/my-problems.html',
      component: () => import('./views/MemberProblems.vue'),
      meta: { title: '题库' },
    },
    {
      path: '/problem.html',
      component: () => import('./views/Problem.vue'),
      meta: { title: '题目详情' },
    },
    ...Object.entries(legacy).map(([path, section]) => ({
      path,
      component:
        section === 'problems'
          ? () => import('./views/MemberProblems.vue')
          : () => import('./views/MemberTool.vue'),
      meta: {
        section,
        admin: !['training', 'problems', 'contests'].includes(section),
        title: section === 'problems' ? '题库' : sections[section],
      },
    })),
    ...['reviews', 'submissions', 'workspace'].map((page) => ({
      path: `/${page}.html`,
      component: () => import('./views/Notice.vue'),
      meta: { public: true, retired: true, title: '功能已调整' },
    })),
    {
      path: '/:pathMatch(.*)*',
      component: () => import('./views/Notice.vue'),
      meta: { public: true, title: '页面不存在' },
    },
  ],
  scrollBehavior(to, from, saved) {
    if (to.hash) {
      try {
        const el = document.getElementById(decodeURIComponent(to.hash.slice(1)));
        if (el) return { el, top: 110 };
      } catch {}
    }
    return saved || (to.path === from.path ? false : { top: 0 });
  },
});
router.beforeEach(async (to) => {
  // Recovery must mount immediately; only an explicit retry starts authentication again.
  if (to.meta.authError) return;
  // Public reading and the login form remain available while authentication is slow.
  if (to.meta.public && !auth.authenticated) {
    initializeAuth()
      .then(async () => {
        await router.isReady();
        if (router.currentRoute.value.fullPath !== to.fullPath || !auth.authenticated) return;
        const next = to.path === '/login.html' ? safeNext(to.query.next) : to.fullPath;
        if (auth.must_change_password && !to.meta.retired)
          return router.replace({ path: '/change-password.html', query: { next } });
        if (to.path === '/login.html') return router.replace(next);
      })
      .catch(() => {});
    return;
  }
  try {
    await initializeAuth();
  } catch {
    if (!to.meta.public) return { path: '/auth-unavailable.html', query: { next: to.fullPath } };
  }
  const target = to.path === '/login.html' ? safeNext(to.query.next) : to.fullPath;
  if (
    !to.meta.retired &&
    auth.authenticated &&
    auth.must_change_password &&
    to.path !== '/change-password.html'
  )
    return { path: '/change-password.html', query: { next: target } };
  if (!to.meta.public && !auth.authenticated)
    return { path: '/login.html', query: { next: target } };
  if (to.path === '/login.html' && auth.authenticated) {
    const next = safeNext(to.query.next);
    return next;
  }
  if (to.meta.admin && !['admin', 'root'].includes(auth.role)) return { path: '/forbidden.html' };
  if (to.meta.section && ['admin', 'root'].includes(auth.role))
    return { path: '/admin.html', query: { ...to.query, section: to.meta.section }, hash: to.hash };
  if (to.path === '/admin.html') {
    const query = { ...to.query };
    let changed = false;
    if (query.section && !Object.hasOwn(sections, query.section)) {
      delete query.section;
      delete query.tab;
      delete query.qq_id;
      changed = true;
      notify('未知模块，已返回成员账号。');
    }
    if (query.qq_id && !/^\d{4,12}$/.test(query.qq_id)) {
      delete query.qq_id;
      changed = true;
      notify('无效成员 QQ，已清除。');
    }
    if (
      query.tab &&
      !(
        {
          'cf-practice': ['recent', 'check'],
          moderation: ['posts', 'reports'],
          wiki: ['categories', 'pages'],
        }[query.section] || []
      ).includes(query.tab)
    ) {
      delete query.tab;
      changed = true;
    }
    if (changed) return { path: to.path, query, hash: to.hash, replace: true };
  }
});
router.afterEach((to, from, failure) => {
  if (failure) return;
  pageLoadError.value = null;
  document.title = `${to.meta.title} · ACM Forever`;
  document.body.className =
    to.meta.admin && to.path === '/admin.html'
      ? 'forum-page endfield-design admin-console'
      : `forum-page endfield-design ${to.meta.body || ''}`;
});
router.onError((_error, to) => {
  pageLoadError.value = { target: to.fullPath };
});
export default router;
