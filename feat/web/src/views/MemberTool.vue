<script setup>
import { computed, defineAsyncComponent } from 'vue';
import { useRoute } from 'vue-router';
const route = useRoute();
const modules = {
  training: defineAsyncComponent(() => import('../admin/Training.vue')),
  problems: defineAsyncComponent(() => import('../admin/Problems.vue')),
  contests: defineAsyncComponent(() => import('../admin/Contests.vue')),
};
const component = computed(() => modules[route.meta.section]);
</script>
<template>
  <main class="community-main">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>{{ route.meta.title }}</h1>
    <component :is="component" v-if="component" />
  </main>
</template>
