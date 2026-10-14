<script setup>
import { inject } from 'vue';
import { useRouter, isNavigationFailure, NavigationFailureType } from 'vue-router';
import { auth, logoutSession, avatar, showError } from '../lib/api.js';
const openTheme = inject('openTheme');
const toggleTheme = inject('toggleTheme');
const router = useRouter();
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
      ><RouterLink v-if="auth.authenticated" to="/home.html" active-class="active"
        >◉ 个人中心</RouterLink
      ><RouterLink v-if="['admin', 'root'].includes(auth.role)" to="/admin.html"
        >⚙ 管理后台</RouterLink
      >
    </nav>
    <div class="forum-header-actions">
      <button class="btn" aria-label="切换主题" @click="toggleTheme">◐</button>
      <button class="btn" @click="openTheme">自助调色</button
      ><RouterLink v-if="!auth.authenticated" class="btn primary" to="/login.html"
        >登录后发帖</RouterLink
      ><RouterLink
        v-else
        class="btn account-avatar-button"
        :to="auth.role === 'member' ? '/home.html' : '/admin.html'"
        aria-label="账户中心"
        ><img
          class="header-account-avatar"
          :src="avatar(auth.avatar_url)"
          alt="我的头像" /></RouterLink
      ><button v-if="auth.authenticated" class="btn" @click="logout">退出</button>
    </div>
  </header>
</template>
