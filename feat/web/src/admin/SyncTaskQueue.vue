<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRequests, date, showError, syncFailureMessage } from '../lib/api.js';
import ProblemTaskProgress from '../components/ProblemTaskProgress.vue';

const request = useRequests();
const rows = ref([]);
const memberStatuses = ref([]);
const memberStatus = ref('');
let timer;
let disposed = false;

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
      : {
          '-1': '成员不存在或抓取失败',
          '-2': '未绑定账号',
          '-3': '抓取失败',
          '-5': '已暂停，保留已有记录',
          '-6': '洛谷访问受限，已停用，等待管理员重新开启',
        }[value] || '同步失败';
  return String(value);
}

function matchesStatus(status) {
  return memberStatus.value === '__empty__'
    ? !String(status || '').trim()
    : status === memberStatus.value;
}

function taskMatches(task) {
  if (!memberStatus.value) return true;
  if (task.member) return matchesStatus(task.member.status);
  if (task.member_statuses && typeof task.member_statuses === 'object')
    return Object.values(task.member_statuses).some(matchesStatus);
  return false;
}

function visibleResult(task) {
  if (
    !memberStatus.value ||
    task.qq_id !== '*' ||
    !task.member_statuses ||
    !task.result ||
    typeof task.result !== 'object'
  )
    return task.result;
  const visible = Object.fromEntries(
    Object.entries(task.result).filter(
      ([qq, value]) => qq === 'error' || matchesStatus(task.member_statuses[qq]),
    ),
  );
  return Object.keys(visible).length ? visible : null;
}

const visibleRows = computed(() => rows.value.filter(taskMatches));
async function loadMemberOptions() {
  try {
    const options = await request('/admin/members/options', {}, 'task-member-options');
    memberStatuses.value = Array.isArray(options?.statuses) ? options.statuses : [];
  } catch (e) {
    if (e.name !== 'AbortError') memberStatuses.value = [];
  }
}

async function load() {
  try {
    const tasks = await request('/tasks', {}, 'tasks');
    rows.value = (Array.isArray(tasks) ? tasks : []).slice().reverse();
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

onMounted(() => {
  loadMemberOptions();
  poll();
});
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
</script>
<template>
  <section class="admin-panel" aria-labelledby="sync-queue-heading">
    <h2 id="sync-queue-heading">任务队列</h2>
    <p class="muted">查看成员同步和题库采集的进度、执行结果，或取消运行中的任务。</p>
    <form class="filters" @submit.prevent="load">
      <label
        >成员身份<select v-model="memberStatus" aria-label="成员身份">
          <option value="">全部身份</option>
          <option value="__empty__">未设置身份</option>
          <option v-for="status in memberStatuses" :key="status" :value="status">
            {{ status }}
          </option>
        </select></label
      ><button class="btn primary">刷新任务</button
      ><RouterLink class="btn" to="/admin.html?section=problems&view=collection"
        >拉取题目</RouterLink
      ><span class="muted">离开此模块停止刷新，后台任务继续执行。</span>
    </form>

    <article v-for="task in visibleRows" :key="task.id" class="list-item">
      <span>
        <b>{{ task.kind }} · #{{ task.id }}</b>
        <ProblemTaskProgress v-if="task.kind === '题目采集'" :task="task" />
        <template v-else
          ><br />成员 {{ task.qq_id || '全部'
          }}<span v-if="task.member?.name"> · {{ task.member.name }}</span> · 平台
          {{ task.platform || '全部' }} · {{ task.status === 'waiting' ? '等待重试' : task.status
          }}<br />
          <small v-if="task.member?.status || memberStatus"
            >成员身份：{{
              task.member?.status || (memberStatus === '__empty__' ? '未设置' : memberStatus)
            }}<br
          /></small>
          <small v-if="task.progress"
            >已处理 {{ task.progress.done }} / {{ task.progress.total }} 位成员<br /></small
          ><small>{{ describe(visibleResult(task), task.errors) }}</small></template
        >
        <br /><small>{{ date(task.finished_at || task.started_at) }}</small></span
      ><button
        v-if="['queued', 'running'].includes(task.status)"
        class="btn"
        @click="cancel(task.id)"
      >
        取消任务
      </button>
    </article>
    <p v-if="!visibleRows.length" class="empty">
      {{ memberStatus ? '没有符合该成员身份的任务。' : '暂无后台任务。' }}
    </p>
  </section>
</template>
