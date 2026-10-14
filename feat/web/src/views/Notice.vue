<script setup>
import { useRoute } from 'vue-router';
const route = useRoute();
</script>
<template>
  <main class="community-main">
    <section class="card">
      <h1>{{ route.meta.retired ? '功能已下线' : route.meta.title }}</h1>
      <p>{{ route.meta.retired ? '历史资料保留存档。' : '' }}请从社区或个人中心进入当前功能。</p>
      <RouterLink class="btn primary" to="/index.html">返回社区</RouterLink>
    </section>
  </main>
</template>
