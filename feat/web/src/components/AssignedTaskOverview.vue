<script setup>
import { onMounted, ref } from 'vue';
import { date, useRequests } from '../lib/api.js';
import { fraction, phases } from '../lib/training-tasks.js';
const request = useRequests(),
  task = ref(null),
  loading = ref(true),
  error = ref('');
async function load() {
  loading.value = true;
  error.value = '';
  try {
    let data = await request('/me/training-tasks?tab=active&page_size=1', {}, 'overview');
    if (!data.items.length)
      data = await request('/me/training-tasks?tab=upcoming&page_size=1', {}, 'overview');
    task.value = data.items[0] || null;
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="community-panel training-tasks">
    <div class="tt-between">
      <h2>我的训练安排</h2>
      <RouterLink to="/training-tasks.html">查看全部 →</RouterLink>
    </div>
    <p v-if="loading" class="tt-caption" role="status">正在加载任务安排…</p>
    <div v-else-if="error" class="tt-error" role="alert">
      任务安排加载失败：{{ error }} <button class="btn" @click="load">重试任务安排</button>
    </div>
    <template v-else-if="task"
      ><div class="tt-between">
        <div>
          <p class="tt-caption">{{ task.phase === 'active' ? '最近截止' : '即将开始' }}</p>
          <h3>{{ task.title }}</h3>
          <p class="tt-caption">
            {{ date(task.due_at) }} 前完成 · {{ task.recipient.completed_problems }} /
            {{ task.recipient.problem_count }} 题
          </p>
        </div>
        <span class="tt-tag" :class="task.phase">{{ phases[task.phase] }}</span>
      </div>
      <div class="tt-progress">
        <span
          :style="{
            width: fraction(task.recipient.completed_problems, task.recipient.problem_count) + '%',
          }"
        ></span>
      </div>
      <div>
        <RouterLink
          class="btn primary"
          :to="{ path: '/training-tasks.html', query: { task_id: task.id } }"
          >继续训练 →</RouterLink
        >
      </div></template
    >
    <p v-else class="tt-muted">当前没有进行中或即将开始的任务，可查看历史安排。</p>
  </section>
</template>
