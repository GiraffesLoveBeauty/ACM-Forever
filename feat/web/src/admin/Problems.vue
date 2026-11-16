<script setup>
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth } from '../lib/api.js';
import ProblemCollection from '../components/ProblemCollection.vue';
import ProblemDatabaseBrowser from '../components/ProblemDatabaseBrowser.vue';

const manager = computed(() => ['admin', 'root'].includes(auth.role));
const route = useRoute(),
  router = useRouter();
const collection = computed(() => route.query.view === 'collection');
function showCollection(value) {
  const query = { ...route.query };
  if (value) query.view = 'collection';
  else delete query.view;
  router.replace({ path: route.path, query });
}
</script>
<template>
  <template v-if="manager">
    <div class="admin-panel processing-intro">
      <div>
        <h2>题库管理</h2>
        <p>
          采集公开题面与样例，按平台原生难度和标签筛选。每日同步和手动采集在“采集与数据库工具”中管理。
        </p>
      </div>
      <div class="chips">
        <button class="btn" :class="{ primary: !collection }" @click="showCollection(false)">
          题库浏览</button
        ><button class="btn" :class="{ primary: collection }" @click="showCollection(true)">
          采集与数据库工具
        </button>
      </div>
    </div>
    <ProblemCollection v-if="collection" />
    <ProblemDatabaseBrowser v-else />
  </template>
</template>
<style scoped>
.processing-intro {
  margin-bottom: 24px;
}
.processing-intro h2 {
  margin-top: 0;
}
.processing-intro p {
  line-height: 1.8;
  color: var(--muted, #697970);
}
</style>
