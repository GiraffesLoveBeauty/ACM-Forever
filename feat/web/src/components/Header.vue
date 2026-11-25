<script setup>
import { computed } from 'vue';
import { useRouter, isNavigationFailure, NavigationFailureType } from 'vue-router';
import { auth, logoutSession, showError, safeNext } from '../lib/api.js';
import ThemeSwitcher from './ThemeSwitcher.vue';
import NotificationBell from './NotificationBell.vue';
const router = useRouter();
const loginTarget = computed(() => ({
  path: '/login.html',
  query: { next: safeNext(router.currentRoute.value.fullPath) },
}));
const canManage = computed(() => auth.authenticated && ['admin', 'root'].includes(auth.role));
async function logout() {
  try {
    const failure = await router.push('/index.html');
    if (
      isNavigationFailure(failure) &&
      !isNavigationFailure(failure, NavigationFailureType.duplicated)
    )
      return;
    await logoutSession();
    await router.push('/index.html');
  } catch (e) {
    showError(e);
  }
}
</script>
<template>
  <header class="forum-header">
    <RouterLink class="forum-brand" to="/index.html"
      ><img class="icpc-brand-logo" src="/assets/icpc-logo.png" alt="ICPC 官方标志" /><span
        >ACM <b>Forever</b><small>计量 ACMer 学习社区</small></span
      ></RouterLink
    >
    <nav class="nav primary-nav" aria-label="主导航">
      <RouterLink to="/index.html" active-class="active">⌂ 论坛</RouterLink
      ><RouterLink to="/leaderboard.html" active-class="active">♛ 排行榜</RouterLink
      ><RouterLink to="/wiki.html" active-class="active">▧ Wiki</RouterLink
      ><RouterLink v-if="auth.authenticated" to="/my-problems.html" active-class="active"
        >▦ 题库</RouterLink
      ><RouterLink v-if="auth.authenticated" to="/home.html" active-class="active"
        >◉ 个人中心</RouterLink
      ><RouterLink v-if="canManage" to="/admin.html" active-class="active">⚙ 管理后台</RouterLink>
    </nav>
    <div class="forum-header-actions">
      <NotificationBell />
      <ThemeSwitcher />
      <RouterLink v-if="!auth.authenticated" class="btn primary" :to="loginTarget"
        >登录社区</RouterLink
      ><button v-if="auth.authenticated" class="btn" @click="logout">退出</button>
    </div>
  </header>
</template>
