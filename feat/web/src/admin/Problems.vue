<script setup>
import { computed, ref } from 'vue';
import { auth } from '../lib/api.js';
import ProblemCollection from '../components/ProblemCollection.vue';
import ProblemDatabaseBrowser from '../components/ProblemDatabaseBrowser.vue';

const manager = computed(() => ['admin', 'root'].includes(auth.role));
const collection = ref(false);
</script>
<template>
  <template v-if="manager">
    <div class="admin-panel processing-intro">
      <div>
        <h2>题库与二次处理</h2>
        <p>
          从已采集题目直接查看 AI 标签、中文翻译和人工修正。筛选使用最终有效标签，保留爬虫原始标签。
        </p>
      </div>
      <div class="chips">
        <button class="btn" :class="{ primary: !collection }" @click="collection = false">
          题库与 AI 管理</button
        ><button class="btn" :class="{ primary: collection }" @click="collection = true">
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
