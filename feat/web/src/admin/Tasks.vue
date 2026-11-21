<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRequests, date, showError } from '../lib/api.js';
import ProblemTaskProgress from '../components/ProblemTaskProgress.vue';

const request = useRequests();
const rows = ref([]);
const memberStatuses = ref([]);
const memberStatus = ref('');
const restrictedLuogu = ref([]);
const enabling = ref(new Set());
let timer;
let disposed = false;

function describe(value) {
  if (value == null) return '';
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([key, v]) => `${key}：${describe(v)}`)
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
  return memberStatus.value === '__empty__' ? !String(status || '').trim() : status === memberStatus.value;
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
const visibleRestrictedLuogu = computed(() =>
  restrictedLuogu.value.filter((member) => !memberStatus.value || matchesStatus(member.status)),
);

async function loadMemberOptions() {
  try {
    const options = await request('/admin/members/options', {}, 'task-member-options');
    memberStatuses.value = Array.isArray(options?.statuses) ? options.statuses : [];
  } catch (e) {
    if (e.name !== 'AbortError') memberStatuses.value = [];
  }
}

async function loadRestrictedLuogu() {
  try {
    const items = await request('/admin/luogu-sync', {}, 'luogu-restricted');
    restrictedLuogu.value = Array.isArray(items) ? items : [];
  } catch (e) {
    if (e.name !== 'AbortError') restrictedLuogu.value = [];
  }
}

async function load() {
  try {
    const tasks = await request('/tasks', {}, 'tasks');
    rows.value = (Array.isArray(tasks) ? tasks : []).slice().reverse();
  } catch (e) {
    showError(e);
    return;
  }
  await Promise.all([loadMemberOptions(), loadRestrictedLuogu()]);
}

async function enableLuogu(qqId) {
  const next = new Set(enabling.value);
  next.add(qqId);
  enabling.value = next;
  try {
    await request(`/admin/luogu-sync/${encodeURIComponent(qqId)}/enable`, { method: 'POST' }, `enable-luogu-${qqId}`);
    await load();
  } catch (e) {
    showError(e);
  } finally {
    const current = new Set(enabling.value);
    current.delete(qqId);
    enabling.value = current;
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
      ><RouterLink class="btn" to="/admin.html?section=problems">拉取题目</RouterLink
      ><span class="muted">离开此模块停止刷新，后台任务继续执行。</span>
    </form>

    <article v-if="visibleRestrictedLuogu.length" class="list-item">
      <span>
        <b>洛谷访问受限 · {{ visibleRestrictedLuogu.length }} 位成员</b><br />
        <small class="muted">这些账号返回 HTTP 403，已从默认同步中跳过；确认成员解除访问限制后，可由管理员重新开启。</small>
        <br />
        <small v-for="member in visibleRestrictedLuogu" :key="member.qq_id" class="task-member-line">
          {{ member.name }} · QQ {{ member.qq_id }} · 身份 {{ member.status || '未设置' }} · UID {{ member.luogu_id }}
          <button
            class="btn"
            :disabled="enabling.has(member.qq_id)"
            @click="enableLuogu(member.qq_id)"
          >
            {{ enabling.has(member.qq_id) ? '开启中…' : '重新开启' }}
          </button>
          <br />
        </small>
      </span>
    </article>

    <article v-for="task in visibleRows" :key="task.id" class="list-item">
      <span>
        <b>{{ task.kind }} · #{{ task.id }}</b>
        <ProblemTaskProgress v-if="task.kind === '题目采集'" :task="task" />
        <template v-else
          ><br />成员 {{ task.qq_id || '全部' }}<span v-if="task.member?.name"> · {{ task.member.name }}</span>
          · 平台 {{ task.platform || '全部' }} · {{ task.status }}<br />
          <small v-if="task.member?.status || memberStatus"
            >成员身份：{{ task.member?.status || (memberStatus === '__empty__' ? '未设置' : memberStatus) }}<br
          /></small>
          <small v-if="task.progress"
            >已处理 {{ task.progress.done }} / {{ task.progress.total }} 位成员<br /></small
          ><small>{{ describe(visibleResult(task)) }}</small></template
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
      {{ memberStatus ? '没有符合该成员身份的同步任务。' : '暂无同步任务。' }}
    </p>
  </section>
</template>
