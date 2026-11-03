<script setup>
import { computed, defineAsyncComponent } from 'vue';
import { useRoute } from 'vue-router';
const route = useRoute();
const importing = computed(() => route.query.tab === 'import');
const AccountList = defineAsyncComponent(() => import('./AccountsList.vue'));
const AccountImport = defineAsyncComponent(() => import('./AccountImport.vue'));
</script>
<template>
  <div class="admin-content">
    <nav class="account-tabs" aria-label="成员账号功能">
      <RouterLink
        :to="{ path: '/admin.html', query: { section: 'accounts' } }"
        :aria-current="!importing ? 'page' : undefined"
        >账号管理</RouterLink
      >
      <RouterLink
        :to="{ path: '/admin.html', query: { section: 'accounts', tab: 'import' } }"
        :aria-current="importing ? 'page' : undefined"
        >Excel 导入</RouterLink
      >
    </nav>
    <component :is="importing ? AccountImport : AccountList" />
  </div>
</template>
<style scoped>
.account-tabs {
  display: flex;
  gap: 8px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 20px;
}
.account-tabs a {
  padding: 10px 18px;
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}
.account-tabs a[aria-current] {
  background: var(--hover-bg, var(--panel));
  font-weight: 700;
}
</style>
