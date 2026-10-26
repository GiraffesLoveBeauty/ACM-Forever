<script setup>
import { useRoute } from 'vue-router';
import { safeNext } from '../lib/api.js';
const route = useRoute();
</script>
<template>
  <main class="community-main">
    <section class="card">
      <h1>{{ route.meta.retired ? '功能已下线' : route.meta.title }}</h1>
      <p v-if="route.meta.authError" role="alert">
        认证服务暂时不可用或请求超时。请检查网络后重试，目标页面已保留。
      </p>
      <p v-else-if="route.meta.forbidden" role="alert">此页面仅限管理员，当前账号无权访问。</p>
      <p v-else>
        {{ route.meta.retired ? '历史资料保留存档。' : '' }}请从社区或个人中心进入当前功能。
      </p>
      <RouterLink
        v-if="route.meta.authError"
        class="btn primary"
        :to="safeNext(route.query.next, '/home.html')"
        >重试原页面</RouterLink
      >
      <RouterLink class="btn" to="/home.html">返回个人中心</RouterLink>
      <RouterLink class="btn primary" to="/index.html">返回社区</RouterLink>
    </section>
  </main>
</template>
