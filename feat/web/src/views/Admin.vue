<script setup>
import { computed, provide, defineAsyncComponent, onMounted } from 'vue';
import { useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import { sections } from '../router.js';
import { api, showError } from '../lib/api.js';
const route = useRoute();
const modules = {
  accounts: defineAsyncComponent(() => import('../admin/Accounts.vue')),
  members: defineAsyncComponent(() => import('../admin/Members.vue')),
  training: defineAsyncComponent(() => import('../admin/Training.vue')),
  problems: defineAsyncComponent(() => import('../admin/Problems.vue')),
  'cf-practice': defineAsyncComponent(() => import('../admin/CfPractice.vue')),
  contests: defineAsyncComponent(() => import('../admin/Contests.vue')),
  'sync-center': defineAsyncComponent(() => import('../admin/SyncWorkspace.vue')),
  moderation: defineAsyncComponent(() => import('../admin/Moderation.vue')),
  settings: defineAsyncComponent(() => import('../admin/Settings.vue')),
  wiki: defineAsyncComponent(() => import('../admin/Wiki.vue')),
};
const section = computed(() =>
  Object.hasOwn(sections, route.query.section) ? route.query.section : 'accounts',
);

/* 管理导航（方案 C）：分区 Tab + 组内横向入口，取代原来的纵向侧栏 */
const ICONS = {
  accounts: '▤',
  members: '◉',
  training: '◎',
  problems: '▦',
  'cf-practice': '⌘',
  contests: '◈',
  'sync-center': '⇄',
  moderation: '☷',
  settings: '⚙',
  wiki: '▧',
};
const GROUP_TITLES = {
  accounts: '账户与成员',
  members: '账户与成员',
  training: '训练与题目',
  problems: '训练与题目',
  'cf-practice': '训练与题目',
  contests: '训练与题目',
  'sync-center': '训练与题目',
  moderation: '社区与系统',
  settings: '社区与系统',
  wiki: '社区与系统',
};
const groups = computed(() => {
  const out = [];
  for (const [key, label] of Object.entries(sections)) {
    const title = GROUP_TITLES[key] || '其他';
    let group = out.find((item) => item.title === title);
    if (!group) {
      group = { title, items: [] };
      out.push(group);
    }
    group.items.push({ key, label, icon: ICONS[key] || '·' });
  }
  const training = out.find((group) => group.title === '训练与题目');
  if (training) {
    training.items.push({
      key: 'tag-management',
      label: '标签管理',
      icon: '▧',
      to: '/tag-management.html',
    });
  }
  return out;
});
const activeGroup = computed(() => GROUP_TITLES[section.value] || '其他');
const currentItems = computed(
  () => groups.value.find((group) => group.title === activeGroup.value)?.items || [],
);
let leaveGuard = () => true;
provide('registerLeaveGuard', (handler) => {
  leaveGuard = handler;
  return () => {
    if (leaveGuard === handler) leaveGuard = () => true;
  };
});
onBeforeRouteLeave((to) => leaveGuard(to));
onBeforeRouteUpdate((to) => {
  if (
    (to.query.section || 'accounts') !== section.value ||
    (section.value === 'training' && to.fullPath !== route.fullPath) ||
    (section.value === 'accounts' &&
      (to.query.tab !== route.query.tab || to.query.import_id !== route.query.import_id))
  )
    return leaveGuard(to);
});
onMounted(async () => {
  try {
    const preferences = await api('/ui/preferences');
    document.documentElement.style.setProperty('--font-scale', preferences.font_scale || 1);
  } catch (e) {
    showError(e);
  }
});
</script>
<template>
  <main class="admin-home-layout" :class="{ 'wiki-workspace': section === 'wiki' }">
    <header class="forum-welcome admin-welcome">
      <div class="industrial-hero-dots" aria-hidden="true"></div>
      <div class="industrial-hero-copy">
        <span class="forum-kicker">ACM FOREVER / 管理工作台</span>
        <h1>{{ sections[section] }}</h1>
        <p>维护成员、训练与社区，让每一项管理工作都清楚、有序。</p>
      </div>
      <div class="industrial-hero-bottom" aria-hidden="true">
        <span>管理工作台</span><span>学习 / 训练 / 社区</span>
      </div>
    </header>
    <div class="admin-nav-row">
      <nav class="admin-subtabs" aria-label="功能模块">
        <RouterLink
          v-for="item in currentItems"
          :key="item.key"
          :to="
            item.to || (item.key === 'accounts' ? '/admin.html' : `/admin.html?section=${item.key}`)
          "
          class="admin-subtab"
          :class="{ active: section === item.key }"
          :aria-current="section === item.key ? 'page' : undefined"
          ><span class="admin-subtab-icon" aria-hidden="true">{{ item.icon }}</span
          >{{ item.label }}</RouterLink
        >
      </nav>
    </div>
    <section class="admin-workspace">
      <div class="admin-module">
        <component :is="modules[section]" :key="section" />
      </div>
    </section>
  </main>
</template>
