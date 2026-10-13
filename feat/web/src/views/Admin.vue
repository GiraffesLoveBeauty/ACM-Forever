<script setup>
import { computed, provide, inject, defineAsyncComponent, onMounted } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import { sections } from '../router.js';
import { api, auth, showError } from '../lib/api.js';
const route = useRoute(),
  router = useRouter(),
  openTheme = inject('openTheme');
const toggleTheme = inject('toggleTheme');
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
async function logout() {
  if (!(await leaveGuard())) return;
  try {
    await api('/auth/logout', { method: 'POST' });
    Object.assign(auth, { authenticated: false, role: null, csrf_token: '' });
    leaveGuard = () => true;
    await router.push('/index.html');
  } catch (e) {
    showError(e);
  }
}
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
  <div class="admin-shell">
    <aside class="admin-rail" aria-label="管理后台导航">
      <RouterLink class="admin-brand" to="/admin.html"
        ><span class="admin-brand-mark">A<span>C</span></span
        ><span><b>ACM Forever</b><small>管理后台</small></span></RouterLink
      >
      <nav class="admin-nav" aria-label="功能模块">
        <template v-for="(label, key) in sections" :key="key"
          ><div
            v-if="['accounts', 'training', 'moderation'].includes(key)"
            class="admin-rail-label"
          >
            {{ { accounts: '账户与成员', training: '训练与题目', moderation: '社区与系统' }[key] }}
          </div>
          <RouterLink
            :to="key === 'accounts' ? '/admin.html' : `/admin.html?section=${key}`"
            :class="{ active: section === key }"
            ><span class="admin-nav-icon">{{
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
              }[key]
            }}</span
            >{{ label }}</RouterLink
          ></template
        >
      </nav>
      <div class="admin-rail-foot">
        <RouterLink class="admin-return" to="/index.html">← 返回社区</RouterLink
        ><span class="admin-rail-status"
          ><span class="admin-status-dot"></span> 管理操作即时生效</span
        >
      </div>
    </aside>
    <main class="admin-main">
      <header class="admin-topbar">
        <div>
          <p class="admin-page-path">管理后台 <span>/</span> {{ sections[section] }}</p>
          <h1>{{ sections[section] }}</h1>
          <p class="admin-lede">维护成员、训练和社区。</p>
        </div>
        <div class="admin-actions">
          <RouterLink class="admin-action-link" to="/change-password.html?next=/admin.html"
            >修改密码</RouterLink
          ><button class="admin-icon-button" aria-label="切换主题" @click="toggleTheme">◐</button>
          <button class="btn" @click="openTheme">自助调色</button
          ><button class="admin-logout" @click="logout">退出</button>
        </div>
      </header>
      <div class="admin-workspace"><component :is="modules[section]" :key="section" /></div>
    </main>
  </div>
</template>
