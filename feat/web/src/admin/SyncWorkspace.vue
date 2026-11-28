<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import MemberSyncOverview from './SyncCenter.vue';
import SyncTaskQueue from './SyncTaskQueue.vue';

const route = useRoute();
const queue = computed(() => route.query.tab === 'queue');
const overviewLink = '/admin.html?section=sync-center';
const queueLink = overviewLink + '&tab=queue';
</script>

<template>
  <nav class="sync-center-views" aria-label="同步中心视图">
    <RouterLink
      :to="overviewLink"
      class="btn"
      :class="{ primary: !queue }"
      :aria-current-value="queue ? 'false' : 'page'"
      >成员同步</RouterLink
    >
    <RouterLink
      :to="queueLink"
      class="btn"
      :class="{ primary: queue }"
      :aria-current-value="queue ? 'page' : 'false'"
      >任务队列</RouterLink
    >
  </nav>
  <SyncTaskQueue v-if="queue" />
  <MemberSyncOverview v-else />
</template>

<style scoped>
.sync-center-views {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
</style>
