<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, auth, avatar, logoutSession } from '../lib/api.js';
import { profileName, profileAvatar, setProfile } from '../lib/profile-store.js';
import ProfileQuickEdit from './ProfileQuickEdit.vue';

const route = useRoute();
/* 顶部 ACM 区块：默认外观不变，点击后弹出头像/昵称设置 */
const editingProfile = ref(false);

/* 登录状态就绪后再拉昵称/头像（初始化是异步的，所以用 watch 而不是 onMounted） */
watch(
  () => auth.authenticated,
  async (signedIn) => {
    if (!signedIn) {
      setProfile({ name: '', avatar_url: null });
      return;
    }
    try {
      const data = await api('/me/profile');
      const user = data?.user || {};
      setProfile({ name: user.name, avatar_url: user.avatar_url ?? auth.avatar_url });
    } catch {
      /* 拉取失败就沿用默认文字 */
    }
  },
  { immediate: true },
);
const brandName = computed(() => profileName.value || 'Forever');
const brandAvatar = computed(() => profileAvatar.value || auth.avatar_url || null);

/* 图标：16×16，描边风格，接近 GitHub Octicons 的观感 */
const icons = {
  home: '<path d="M2 7.5 8 2l6 5.5V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5Z"/>',
  issue:
    '<circle cx="8" cy="8" r="6"/><path d="M8 5v3.5M8 11h.01"/>',
  list: '<path d="M3 5h10M3 8h10M3 11h7"/>',
  book: '<path d="M3 3h7a2 2 0 0 1 2 2v8H5a2 2 0 0 1-2-2V3Zm9 2h2a1 1 0 0 1 1 1v7h-3"/>',
  check: '<path d="M3 8.5 6 11.5 13 4.5"/>',
  bolt: '<path d="M9 2 3 9h4l-1 5 7-8H8l1-4Z"/>',
  flag: '<path d="M4 2v12M4 3h7l-1.5 2.5L11 8H4"/>',
  file: '<path d="M4 2h5l3 3v9H4V2Z"/><path d="M9 2v3h3"/>',
  bell: '<path d="M8 2a4 4 0 0 0-4 4v3l-1 2h10l-1-2V6a4 4 0 0 0-4-4Z"/><path d="M6.5 13a1.5 1.5 0 0 0 3 0"/>',
  user: '<circle cx="8" cy="6" r="2.5"/><path d="M3 14c0-2.5 2.2-4 5-4s5 1.5 5 4"/>',
  pencil: '<path d="M3 13l1-3 7-7 2 2-7 7-3 1Z"/>',
  palette:
    '<circle cx="8" cy="8" r="6"/><circle cx="6" cy="6.5" r="1"/><circle cx="10" cy="6.5" r="1"/><circle cx="6.5" cy="10" r="1"/>',
  shield: '<path d="M8 2 13 4v5c0 3-2.5 4.5-5 5-2.5-.5-5-2-5-5V4l5-2Z"/>',
  tag: '<path d="M3 8 8 3h5v5l-5 5-5-5Z"/><circle cx="10.5" cy="5.5" r="1"/>',
  lock: '<rect x="3.5" y="7" width="9" height="6" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
  logout: '<path d="M6 3H3v10h3"/><path d="M9 8h5m0 0-2-2m2 2-2 2"/>',
  code: '<path d="m5.5 6-2.5 2 2.5 2M10.5 6l2.5 2-2.5 2"/>',
};

const icon = (name) => `<svg viewBox="0 0 16 16" aria-hidden="true">${icons[name] || icons.list}</svg>`;

const isAdmin = computed(() => ['admin', 'root'].includes(auth.role));
const path = computed(() => route.path);

const groups = computed(() => [
  {
    title: '',
    items: [
      { label: '论坛首页', to: '/index.html', icon: 'home' },
      { label: '排行榜', to: '/leaderboard.html', icon: 'list' },
      { label: 'Wiki', to: '/wiki.html', icon: 'book' },
    ],
  },
  {
    title: '我的',
    items: [
      { label: '我的题库', to: '/my-problems.html', icon: 'check' },
      { label: '训练任务', to: '/training-tasks.html', icon: 'bolt' },
      { label: '挑战', to: '/challenge.html', icon: 'flag' },
      { label: '比赛复盘', to: '/contest-review.html', icon: 'code' },
      { label: '我的帖子', to: '/my-post.html', icon: 'file' },
      { label: '通知', to: '/notifications.html', icon: 'bell' },
      { label: '个人中心', to: '/home.html', icon: 'user' },
    ],
  },
  {
    title: '创作',
    items: [
      { label: '写新话题', to: '/compose.html', icon: 'pencil' },
      { label: '题目详情', to: '/problem.html', icon: 'issue' },
    ],
  },
  {
    title: '管理',
    adminOnly: true,
    items: [
      { label: '账户与成员', to: '/admin.html', section: 'accounts', icon: 'shield' },
      { label: '训练与题目', to: '/admin.html?section=training', section: 'training', icon: 'bolt' },
      { label: '社区与系统', to: '/admin.html?section=moderation', section: 'moderation', icon: 'list' },
    ],
  },
  {
    title: '账户',
    items: [
      { label: '修改密码', to: '/change-password.html', icon: 'lock' },
    ],
  },
]);

const visibleGroups = computed(() =>
  groups.value.filter((group) => !group.adminOnly || isAdmin.value),
);
const currentSection = computed(() => String(route.query.section || 'accounts'));
const isActive = (item) => {
  if (item.section) return route.path === '/admin.html' && currentSection.value === item.section;
  return path.value === item.to;
};
</script>

<template>
  <aside class="gh-sidebar" aria-label="主导航">
    <button
      type="button"
      class="gh-sidebar-brand"
      :aria-label="auth.authenticated ? '设置头像与昵称' : 'ACM Forever'"
      @click="auth.authenticated && (editingProfile = true)"
    >
      <span class="gh-sidebar-mark" :class="{ 'has-avatar': !!brandAvatar }" aria-hidden="true">
        <img v-if="brandAvatar" :src="avatar(brandAvatar)" alt="" />
        <template v-else>ACM</template>
      </span>
      <span class="gh-sidebar-title">
        <span class="gh-sidebar-name">{{ brandName }}</span>
        <small>Community</small>
      </span>
    </button>

    <nav class="gh-sidebar-nav">
      <div v-for="group in visibleGroups" :key="group.title || 'main'" class="gh-sidebar-group">
        <p v-if="group.title" class="gh-sidebar-group-title">{{ group.title }}</p>
        <RouterLink
          v-for="item in group.items"
          :key="item.to"
          class="gh-sidebar-item"
          :class="{ 'is-active': isActive(item) }"
          :to="item.to"
          :aria-current="isActive(item) ? 'page' : undefined"
        >
          <span class="gh-sidebar-icon" v-html="icon(item.icon)" />
          <span class="gh-sidebar-label">{{ item.label }}</span>
        </RouterLink>
      </div>
    </nav>

    <div v-if="auth.authenticated" class="gh-sidebar-footer">
      <button type="button" class="gh-sidebar-item gh-sidebar-signout" @click="logoutSession()">
        <span class="gh-sidebar-icon" v-html="icon('logout')" />
        <span class="gh-sidebar-label">退出登录</span>
      </button>
    </div>
  </aside>
  <ProfileQuickEdit v-if="editingProfile" @close="editingProfile = false" />
</template>
