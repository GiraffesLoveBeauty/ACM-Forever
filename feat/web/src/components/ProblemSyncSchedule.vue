<script setup>
import { onMounted, ref } from 'vue';
import { date, useRequests } from '../lib/api.js';
const request = useRequests();
const schedule = ref(null),
  busy = ref(''),
  error = ref(''),
  message = ref('');
const names = { codeforces: 'Codeforces', atcoder: 'AtCoder', luogu: '洛谷 · 公开 P 题库' };
const states = { completed: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消' };
async function load() {
  busy.value = 'load';
  error.value = '';
  try {
    schedule.value = await request('/admin/problems/schedule', {}, 'problem-schedule');
  } catch (cause) {
    if (cause.name !== 'AbortError') error.value = cause.message;
  } finally {
    busy.value = '';
  }
}
async function change(row, event) {
  const checked = event.target.checked;
  busy.value = row.platform;
  error.value = '';
  message.value = '';
  try {
    schedule.value = await request(
      '/admin/problems/schedule',
      { method: 'PUT', body: { platforms: { [row.platform]: checked } } },
      'problem-schedule',
    );
    message.value = names[row.platform] + (checked ? '每日同步已开启。' : '每日同步已关闭。');
  } catch (cause) {
    if (cause.name !== 'AbortError') error.value = cause.message;
  } finally {
    event.target.checked =
      schedule.value?.platforms.find((item) => item.platform === row.platform)?.enabled ??
      row.enabled;
    busy.value = '';
  }
}
onMounted(load);
</script>
<template>
  <section class="admin-section" aria-labelledby="problem-schedule-heading">
    <div class="admin-section-heading">
      <div>
        <h2 id="problem-schedule-heading">每日题库同步</h2>
        <p>北京时间每天 04:00 检查更新。开关只控制题库采集，成员过题记录独立同步。</p>
      </div>
      <button class="btn" :disabled="Boolean(busy)" @click="load">刷新设置</button>
    </div>
    <div class="admin-panel">
      <p v-if="busy === 'load' && !schedule" role="status">正在读取每日同步设置…</p>
      <p v-if="schedule && !schedule.global_enabled" class="schedule-note">
        服务端总开关已停用。以下设置会保存，但每日任务暂不执行；手动采集仍然可用。
      </p>
      <div class="schedule-grid">
        <article v-for="row in schedule?.platforms || []" :key="row.platform" class="schedule-card">
          <label class="schedule-switch"
            ><span>{{ names[row.platform] }}</span
            ><input
              type="checkbox"
              role="switch"
              :aria-label="names[row.platform] + '每日自动同步'"
              :checked="row.enabled"
              :disabled="Boolean(busy)"
              @change="change(row, $event)"
          /></label>
          <p>
            {{
              row.effective_enabled
                ? '每日同步已启用'
                : row.enabled
                  ? '等待服务端启用调度'
                  : '每日同步已关闭'
            }}
          </p>
          <small>下次检查：{{ row.next_run_at ? date(row.next_run_at) : '—' }}</small>
          <small>最近安排：{{ row.last_scheduled_day || '尚未安排' }}</small>
          <small v-if="row.last_result"
            >最近结果：{{ states[row.last_result.status] || row.last_result.status }} ·
            {{ date(row.last_result.finished_at)
            }}<template v-if="row.last_result.remaining_count">
              · 剩余 {{ row.last_result.remaining_count }} 题</template
            ></small
          >
        </article>
      </div>
      <p class="schedule-note">
        关闭后不再安排新的每日任务；已经开始的任务可在下方或成员同步中心的任务队列中查看、取消。设置保存在服务端。
      </p>
      <p v-if="message" role="status">{{ message }}</p>
      <p v-if="error" role="alert">
        {{ error }} <button class="btn" @click="load" :disabled="Boolean(busy)">重试</button>
      </p>
    </div>
  </section>
</template>
<style scoped>
.schedule-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 16px;
}
.schedule-card {
  border: 1px solid var(--border, #d9e1dc);
  border-radius: 12px;
  padding: 16px;
  min-width: 0;
}
.schedule-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  font-weight: 700;
}
.schedule-switch input {
  width: 22px;
  height: 22px;
  flex: none;
}
.schedule-card p {
  font-size: 13px;
}
.schedule-card small {
  display: block;
  line-height: 1.9;
  overflow-wrap: anywhere;
  color: var(--muted, #697970);
}
.schedule-note {
  font-size: 12px;
  line-height: 1.8;
  color: var(--muted, #697970);
}
[role='alert'] {
  color: var(--danger, #ad3f40);
}
</style>
