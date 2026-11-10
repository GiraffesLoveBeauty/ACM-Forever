<script setup>
import { computed, defineAsyncComponent } from 'vue';
import { useRoute } from 'vue-router';
import { auth } from '../lib/api.js';
const route = useRoute();
const importing = computed(() => route.query.tab === 'import');
const opening = computed(() => importing.value || route.query.tab === 'open');
const AccountList = defineAsyncComponent(() => import('./AccountsList.vue'));
const AccountOpening = defineAsyncComponent(() => import('./AccountOpening.vue'));
const AccountImport = defineAsyncComponent(() => import('./AccountImport.vue'));
const accountLink = (tab) => ({
  path: '/admin.html',
  query: { section: 'accounts', ...(tab ? { tab } : {}) },
});
</script>
<template>
  <div class="admin-content">
    <nav class="account-tabs" aria-label="成员账号功能">
      <RouterLink :to="accountLink()" :aria-current="!opening ? 'page' : undefined">
        账号管理
      </RouterLink>
      <RouterLink :to="accountLink('open')" :aria-current="opening ? 'page' : undefined">
        开通账号
      </RouterLink>
    </nav>
    <nav v-if="opening" class="account-tabs account-methods" aria-label="开通账号方式">
      <RouterLink :to="accountLink('open')" :aria-current="!importing ? 'page' : undefined">
        单个成员开通
      </RouterLink>
      <RouterLink :to="accountLink('import')" :aria-current="importing ? 'page' : undefined">
        Excel 导入
      </RouterLink>
    </nav>
    <component
      :is="importing ? AccountImport : opening ? AccountOpening : AccountList"
      :key="`${route.query.tab || 'manage'}:${auth.qq_id}:${auth.account_epoch}:${auth.role}`"
    />
  </div>
</template>
<style scoped>
.account-tabs {
  display: flex;
  flex-wrap: wrap;
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
.account-methods {
  padding-bottom: 12px;
}
</style>
