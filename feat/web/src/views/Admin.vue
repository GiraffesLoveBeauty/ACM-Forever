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
  tasks: defineAsyncComponent(() => import('../admin/Tasks.vue')),
  moderation: defineAsyncComponent(() => import('../admin/Moderation.vue')),
  settings: defineAsyncComponent(() => import('../admin/Settings.vue')),
  wiki: defineAsyncComponent(() => import('../admin/Wiki.vue')),
};
const section = computed(() =>
  Object.hasOwn(sections, route.query.section) ? route.query.section : 'accounts',
);
let leaveGuard = () => true;
provide('registerLeaveGuard', (handler) => {
  leaveGuard = handler;
  return () => {
    if (leaveGuard === handler) leaveGuard = () => true;
  };
});
onBeforeRouteLeave(() => leaveGuard());
onBeforeRouteUpdate((to) => {
  if ((to.query.section || 'accounts') !== section.value) return leaveGuard();
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
    <aside class="admin-module-sidebar" aria-label="管理后台导航">
      <div class="forum-rail-card admin-module-card">
        <p class="admin-module-title">管理功能</p>
        <nav class="admin-module-nav" aria-label="功能模块">
          <template v-for="(label, key) in sections" :key="key">
            <div
              v-if="['accounts', 'training', 'moderation'].includes(key)"
              class="admin-module-group"
            >
              {{
                { accounts: '账户与成员', training: '训练与题目', moderation: '社区与系统' }[key]
              }}
            </div>
            <RouterLink
              :to="key === 'accounts' ? '/admin.html' : `/admin.html?section=${key}`"
              :class="{ active: section === key }"
              ><span class="admin-module-nav-icon">{{
                {
                  accounts: '▤',
                  members: '◉',
                  training: '◎',
                  problems: '▦',
                  'cf-practice': '⌘',
                  contests: '◈',
                  tasks: '↻',
                  moderation: '☷',
                  settings: '⚙',
                  wiki: '▧',
                }[key]
              }}</span
              >{{ label }}</RouterLink
            >
          </template>
        </nav>
        <p class="admin-module-note"><span aria-hidden="true">●</span> 管理操作即时生效</p>
      </div>
    </aside>
    <section class="admin-workspace">
      <div class="admin-module">
        <component :is="modules[section]" :key="section" />
      </div>
    </section>
  </main>
</template>
