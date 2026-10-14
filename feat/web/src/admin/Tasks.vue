<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useRequests, date, showError } from '../lib/api.js';
const request = useRequests(),
  rows = ref([]);
let timer,
  disposed = false;
function describe(value) {
  if (value == null) return '';
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([key, v]) => `${key}：${describe(v)}`)
      .join('；');
  if (typeof value === 'number')
    return value >= 0
      ? `新增 ${value} 条`
      : { '-1': '成员不存在', '-2': '未绑定账号', '-3': '抓取失败' }[value] || '同步失败';
  return String(value);
}
async function load() {
  try {
    rows.value = (await request('/tasks', {}, 'tasks')).slice().reverse();
  } catch (e) {
    showError(e);
  }
}
async function cancel(id) {
  try {
    await request('/tasks/' + encodeURIComponent(id) + '/cancel', { method: 'POST' });
    await load();
  } catch (e) {
    showError(e);
  }
}
async function poll() {
  await load();
  if (!disposed) timer = setTimeout(poll, 5000);
}
onMounted(poll);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
</script>
<template>
  <section class="admin-panel">
    <div class="filters">
      <button class="btn primary" @click="load">刷新任务</button
      ><span class="muted">离开此模块停止刷新，后台任务继续执行。</span>
    </div>
    <article v-for="task in rows" :key="task.id" class="list-item">
      <span
        ><b>{{ task.kind }} · #{{ task.id }}</b
        ><br />成员 {{ task.qq_id || '全部' }} · 平台 {{ task.platform || '全部' }} ·
        {{ task.status }}<br /><small
          >{{ describe(task.result) }} · {{ date(task.finished_at || task.started_at) }}</small
        ></span
      ><button
        v-if="['queued', 'running'].includes(task.status)"
        class="btn"
        @click="cancel(task.id)"
      >
        取消任务
      </button>
    </article>
    <p v-if="!rows.length" class="empty">暂无同步任务。</p>
  </section>
</template>
