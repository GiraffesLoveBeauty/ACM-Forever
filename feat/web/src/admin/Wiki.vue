<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import WikiCategories from '../components/WikiCategories.vue';
import WikiPages from '../components/WikiPages.vue';
const route = useRoute(),
  tab = computed(() => route.query.tab || 'categories');
</script>
<template>
  <div class="wiki-admin">
    <nav class="chips wiki-admin-tabs" aria-label="Wiki 管理分区">
      <RouterLink
        class="btn"
        :class="{ primary: tab === 'categories' }"
        to="/admin.html?section=wiki&tab=categories"
        >分类管理</RouterLink
      ><RouterLink
        class="btn"
        :class="{ primary: tab === 'pages' }"
        to="/admin.html?section=wiki&tab=pages"
        >文章管理</RouterLink
      ><RouterLink class="btn" to="/wiki.html">阅读 Wiki ↗</RouterLink>
    </nav>
    <WikiCategories v-if="tab === 'categories'" /><WikiPages v-else />
  </div>
</template>
