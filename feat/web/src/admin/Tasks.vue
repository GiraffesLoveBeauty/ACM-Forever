<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRequests, date, showError, syncFailureMessage } from '../lib/api.js';
import ProblemTaskProgress from '../components/ProblemTaskProgress.vue';
const request = useRequests(),
  rows = ref([]);
let timer,
  disposed = false;
function describe(value, errors) {
  if (errors?.message) return syncFailureMessage(errors);
  if (value == null) return '';
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([key, v]) => `${key}：${describe(v, errors?.[key])}`)
      .join('；');
  if (typeof value === 'number')
    return value >= 0
      ? `新增 ${value} 条`
      : { '-1': '同步失败', '-2': '未绑定账号', '-3': '抓取失败', '-5': '已暂停，保留已有记录' }[
          value
        ] || '同步失败';
  return String(value);
}
const taskRows = computed(() =>
  rows.value.map((task) => {
    if (task.kind === '题目采集') return { task };
    if (!task.luogu_members) return { task, details: describe(task.result, task.errors) };

    const failed = { label: '洛谷实际请求失败', members: [], open: true };
    const waiting = {
      label: '洛谷等待重试',
      suffix: '（本次未发送请求）',
      members: [],
      open: true,
    };
    const success = { label: '洛谷同步成功', members: [], open: false };
    const other = { label: '其他洛谷结果', members: [], open: true };
    const remaining = { ...task.result };
    for (const [qqId, member] of Object.entries(task.luogu_members)) {
      const count = task.result?.[qqId]?.luogu;
      if (typeof count !== 'number') continue;
      const error = task.errors?.[qqId]?.luogu;
      let group = other;
      if (count >= 0) group = success;
      else if (error?.deferred) group = waiting;
      else if (error?.request_attempted === true) group = failed;
      group.members.push({
        qqId,
        name: member.name,
        uid: member.uid,
        failures: error?.consecutive_failures,
        message:
          { '-4': '绑定已变更，已跳过', '-3': '同步未完成，请重试' }[count] ||
          describe(count, error),
      });
      const platforms = { ...remaining[qqId] };
      delete platforms.luogu;
      if (Object.keys(platforms).length) remaining[qqId] = platforms;
      else delete remaining[qqId];
    }
    return {
      task,
      groups: [failed, waiting, success, other].filter((group) => group.members.length),
      details: describe(remaining, task.errors),
    };
  }),
);
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
      ><RouterLink class="btn" to="/admin.html?section=problems">拉取题目</RouterLink
      ><span class="muted">离开此模块停止刷新，后台任务继续执行。</span>
    </div>
    <article v-for="{ task, groups, details } in taskRows" :key="task.id" class="list-item">
      <div class="task-details">
        <b>{{ task.kind }} · #{{ task.id }}</b>
        <ProblemTaskProgress v-if="task.kind === '题目采集'" :task="task" />
        <template v-else>
          <br />成员 {{ task.qq_id === '*' ? '全部' : task.qq_id || '全部' }} · 平台
          {{ task.platform === 'all' ? '全部' : task.platform || '全部' }} ·
          {{ task.status === 'waiting' ? '等待重试' : task.status }}<br />
          <small v-if="task.progress">
            已处理 {{ task.progress.done }} / {{ task.progress.total }} 位成员<br />
          </small>
          <details v-for="group in groups" :key="group.label" :open="group.open">
            <summary>{{ group.label }} {{ group.members.length }} 人{{ group.suffix }}</summary>
            <ul>
              <li v-for="member in group.members" :key="member.qqId">
                <small>
                  <template v-if="member.name && member.name !== member.qqId">
                    {{ member.name }} ·
                  </template>
                  QQ {{ member.qqId }} · 洛谷 UID {{ member.uid }} · {{ member.message }}
                  <template v-if="Number.isInteger(member.failures)">
                    · 连续失败 {{ member.failures }} 次</template
                  >
                </small>
              </li>
            </ul>
          </details>
          <small v-if="details">{{ details }}<br /></small>
        </template>
        <small>{{ date(task.finished_at || task.started_at) }}</small>
      </div>
      <button
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

<style scoped>
.task-details {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
