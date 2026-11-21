<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { date, showError, syncFailureMessage, useRequests } from '../lib/api.js';

const request = useRequests();
const loading = ref(false);
const sending = reactive({});
const memberStatuses = ref([]);
const expanded = reactive(new Set());
const feedback = ref('');
const error = ref('');
const snapshot = ref({
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  summary: {},
  platforms: [],
  global: { luogu: {} },
});
const filters = reactive({ search: '', member_status: '', platform: '', status: '', page: 1 });
let timer;
let disposed = false;

const platformList = computed(() => snapshot.value.platforms || []);
const totalPages = computed(() => Math.max(1, Math.ceil((snapshot.value.total || 0) / snapshot.value.page_size)));
const gate = computed(() => snapshot.value.global?.luogu || {});
const stats = computed(() => [
  { key: 'success', label: '正常', hint: '所有已绑定平台均可用', tone: 'good' },
  { key: 'running', label: '同步中', hint: '已有任务排队或执行', tone: 'running' },
  { key: 'waiting', label: '等待重试', hint: '受冷却或退避影响', tone: 'waiting' },
  { key: 'failed', label: '失败', hint: '需要管理员关注', tone: 'failed' },
  { key: 'disabled', label: '已停用', hint: '洛谷账号访问受限，等待管理员开启', tone: 'disabled' },
  { key: 'paused', label: '暂停', hint: '平台同步开关已关闭', tone: 'paused' },
  { key: 'never', label: '未同步', hint: '已绑定但尚无成功记录', tone: 'neutral' },
]);

function statusLabel(status) {
  return {
    success: '正常',
    running: '同步中',
    waiting: '等待重试',
    failed: '失败',
    disabled: '已停用',
    paused: '已暂停',
    never: '未同步',
    cancelled: '已取消',
    unbound: '未绑定',
  }[status] || status;
}
function statusTone(status) {
  return `sync-status-${status || 'never'}`;
}
function shortError(platform) {
  if (!platform?.last_error_message) return '';
  return syncFailureMessage({
    message: platform.last_error_message,
    next_retry_at: platform.next_retry_at,
    consecutive_failures: platform.consecutive_failures,
  });
}
function rowKey(row) {
  return String(row.qq_id);
}
function isExpanded(row) {
  return expanded.has(rowKey(row));
}
function toggleRow(row) {
  const key = rowKey(row);
  if (expanded.has(key)) expanded.delete(key);
  else expanded.add(key);
}
function buildQuery() {
  const query = new URLSearchParams({
    page: String(filters.page),
    page_size: String(snapshot.value.page_size || 20),
  });
  if (filters.search.trim()) query.set('search', filters.search.trim());
  if (filters.member_status) query.set('member_status', filters.member_status);
  if (filters.platform) query.set('platform', filters.platform);
  if (filters.status) query.set('status', filters.status);
  return query.toString();
}
async function loadMemberOptions() {
  try {
    const data = await request('/admin/members/options', {}, 'sync-member-options');
    memberStatuses.value = Array.isArray(data?.statuses) ? data.statuses : [];
  } catch (cause) {
    if (cause.name !== 'AbortError') memberStatuses.value = [];
  }
}

async function load({ quiet = false } = {}) {
  if (!quiet) loading.value = true;
  error.value = '';
  try {
    const data = await request(`/admin/sync/members?${buildQuery()}`, {}, 'sync-center');
    snapshot.value = data;
  } catch (cause) {
    if (cause.name !== 'AbortError') {
      error.value = cause.message || '同步状态暂时无法读取。';
      showError(cause);
    }
  } finally {
    loading.value = false;
  }
}
function resetPage() {
  filters.page = 1;
  load();
}
function previousPage() {
  if (filters.page > 1) {
    filters.page -= 1;
    load();
  }
}
function nextPage() {
  if (filters.page < totalPages.value) {
    filters.page += 1;
    load();
  }
}
async function enableLuogu(row) {
  const key = `enable:${row.qq_id}`;
  if (sending[key]) return;
  sending[key] = true;
  try {
    await request(`/admin/luogu-sync/${encodeURIComponent(row.qq_id)}/enable`, { method: 'POST' }, key);
    await load({ quiet: true });
  } catch (cause) {
    if (cause.name !== 'AbortError') showError(cause);
  } finally {
    sending[key] = false;
  }
}

async function startSync(row, platform = '') {
  const key = `${row.qq_id}:${platform || 'all'}`;
  if (sending[key]) return;
  sending[key] = true;
  feedback.value = '';
  try {
    const data = await request(`/admin/sync/members/${encodeURIComponent(row.qq_id)}`, {
      method: 'POST',
      body: { platforms: platform ? [platform] : undefined },
    });
    feedback.value = `${row.name} 的${platform ? ` ${platformLabel(platform)}` : ''}同步已排队（任务 ${data.task_id || '—'}）。`;
    await load({ quiet: true });
  } catch (cause) {
    if (cause.name !== 'AbortError') showError(cause);
  } finally {
    sending[key] = false;
  }
}
async function startAll() {
  const key = `all:${filters.platform || 'all'}`;
  if (sending[key]) return;
  sending[key] = true;
  feedback.value = '';
  try {
    const data = await request('/admin/sync/all', {
      method: 'POST',
      body: { platforms: filters.platform ? [filters.platform] : undefined },
    });
    feedback.value = `${filters.platform ? platformLabel(filters.platform) : '全部平台'}全员同步已排队（任务 ${data.task_id || '—'}）。`;
    await load({ quiet: true });
  } catch (cause) {
    if (cause.name !== 'AbortError') showError(cause);
  } finally {
    sending[key] = false;
  }
}
function platformLabel(key) {
  return platformList.value.find((item) => item.key === key)?.label || key;
}
function retryText(platform) {
  if (!platform?.next_retry_at) return '';
  return platform.next_retry_at > Math.floor(Date.now() / 1000)
    ? `重试：${date(platform.next_retry_at)}`
    : '';
}
function accountLabel(platform) {
  return platform?.account || '未绑定';
}
onMounted(async () => {
  await Promise.all([load(), loadMemberOptions()]);
  const poll = async () => {
    if (disposed) return;
    await load({ quiet: true });
    if (!disposed) timer = setTimeout(poll, 5000);
  };
  timer = setTimeout(poll, 5000);
});
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
</script>

<template>
  <section class="admin-panel sync-center">
    <header class="sync-center-header">
      <div>
        <p class="eyebrow">MEMBER SYNC / OBSERVABILITY</p>
        <h2>成员同步中心</h2>
        <p class="muted">集中查看成员各 OJ 的同步状态、失败原因和下一次重试时间。</p>
      </div>
      <div class="sync-center-actions">
        <button class="btn primary" :disabled="sending[`all:${filters.platform || 'all'}`]" @click="startAll">
          {{ sending[`all:${filters.platform || 'all'}`] ? '正在排队…' : filters.platform ? `同步全部${platformLabel(filters.platform)}` : '同步全部成员' }}
        </button>
        <button class="btn" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新状态' }}</button>
      </div>
    </header>

    <div v-if="feedback" class="sync-feedback" role="status">{{ feedback }}</div>
    <div v-if="error" class="sync-feedback sync-feedback-error" role="alert">{{ error }}</div>

    <div class="sync-stats" aria-label="同步概览">
      <button v-for="stat in stats" :key="stat.key" class="sync-stat" :class="stat.tone" @click="filters.status = stat.key; resetPage()">
        <span class="sync-stat-value">{{ snapshot.summary?.[stat.key] || 0 }}</span>
        <span class="sync-stat-label">{{ stat.label }}</span>
        <small>{{ stat.hint }}</small>
      </button>
    </div>

    <div class="sync-gate" :class="{ blocked: gate.cooldown_seconds > 0 || gate.enabled === false }">
      <div class="sync-gate-icon">↻</div>
      <div>
        <strong>洛谷全局请求门禁</strong>
        <p v-if="gate.enabled === false">洛谷成员同步开关已关闭，已有记录会保留。</p>
        <p v-else-if="gate.cooldown_seconds > 0">当前处于冷却期，{{ gate.cause_http_status ? `触发状态 HTTP ${gate.cause_http_status}，` : '' }}约 {{ gate.cooldown_seconds }} 秒后恢复；连续失败 {{ gate.failures || 0 }} 次。</p>
        <p v-else>当前可请求{{ gate.failures ? `，历史连续失败 ${gate.failures} 次` : '' }}。</p>
      </div>
      <span class="sync-gate-time" v-if="gate.blocked_until">恢复时间：{{ date(gate.blocked_until) }}</span>
    </div>

    <form class="sync-filters" @submit.prevent="resetPage">
      <label class="sync-search">搜索成员<input v-model="filters.search" type="search" placeholder="姓名、QQ、学校或 OJ 账号" /></label>
      <label>成员身份<select v-model="filters.member_status" @change="resetPage"><option value="">全部身份</option><option value="__empty__">未设置身份</option><option v-for="status in memberStatuses" :key="status" :value="status">{{ status }}</option></select></label>
      <label>平台<select v-model="filters.platform" @change="resetPage"><option value="">全部平台</option><option v-for="platform in platformList" :key="platform.key" :value="platform.key">{{ platform.label }}</option></select></label>
      <label>状态<select v-model="filters.status" @change="resetPage"><option value="">全部状态</option><option value="success">正常</option><option value="running">同步中</option><option value="waiting">等待重试</option><option value="failed">失败</option><option value="disabled">已停用</option><option value="paused">已暂停</option><option value="never">未同步</option><option value="unbound">未绑定</option></select></label>
      <button class="btn" type="submit">应用筛选</button>
      <button class="btn ghost" type="button" @click="filters.search = ''; filters.member_status = ''; filters.platform = ''; filters.status = ''; resetPage()">清空</button>
    </form>

    <div class="sync-table-wrap">
      <table class="sync-table">
        <thead>
          <tr><th>成员</th><th v-for="platform in platformList" :key="platform.key">{{ platform.label }}</th><th class="sync-table-actions">操作</th></tr>
        </thead>
        <tbody>
          <template v-for="row in snapshot.items" :key="row.qq_id">
            <tr :class="{ expanded: isExpanded(row) }">
              <td class="sync-member-cell"><button class="sync-expand" type="button" :aria-expanded="isExpanded(row)" @click="toggleRow(row)">{{ isExpanded(row) ? '−' : '+' }}</button><span class="sync-avatar">{{ (row.name || '?').slice(0, 1) }}</span><span><strong>{{ row.name }}</strong><small>{{ row.real_name || row.qq_id }}<span v-if="row.school"> · {{ row.school }}</span></small><small>身份：{{ row.member_status || '未设置' }}</small></span></td>
              <td v-for="platform in platformList" :key="platform.key" class="sync-platform-cell">
                <div class="sync-platform-head"><span class="sync-dot" :class="statusTone(row.platforms[platform.key]?.status)"></span><span>{{ statusLabel(row.platforms[platform.key]?.status) }}</span></div>
                <strong class="sync-account">{{ accountLabel(row.platforms[platform.key]) }}</strong>
                <small v-if="row.platforms[platform.key]?.last_success_at">成功：{{ date(row.platforms[platform.key].last_success_at) }}</small>
                <small v-else-if="row.platforms[platform.key]?.last_attempt_at">尝试：{{ date(row.platforms[platform.key].last_attempt_at) }}</small>
                <small v-if="shortError(row.platforms[platform.key])" class="sync-error-text" :title="shortError(row.platforms[platform.key])">{{ shortError(row.platforms[platform.key]) }}</small>
                <small v-if="retryText(row.platforms[platform.key])" class="sync-retry-text">{{ retryText(row.platforms[platform.key]) }}</small>
              </td>
              <td class="sync-table-actions"><button class="btn compact" :disabled="sending[`${row.qq_id}:all`]" @click="startSync(row)">{{ sending[`${row.qq_id}:all`] ? '排队…' : '同步成员' }}</button></td>
            </tr>
            <tr v-if="isExpanded(row)" class="sync-detail-row"><td :colspan="platformList.length + 2"><div class="sync-detail-grid"><article v-for="platform in platformList" :key="platform.key" class="sync-detail-card"><header><strong>{{ platform.label }}</strong><span><button v-if="platform.key === 'luogu' && row.platforms[platform.key]?.status === 'disabled'" class="btn compact" :disabled="sending[`enable:${row.qq_id}`]" @click="enableLuogu(row)">{{ sending[`enable:${row.qq_id}`] ? '开启中…' : '重新开启' }}</button><button class="btn compact" :disabled="!row.platforms[platform.key]?.bound || sending[`${row.qq_id}:${platform.key}`]" @click="startSync(row, platform.key)">{{ sending[`${row.qq_id}:${platform.key}`] ? '排队…' : '单独同步' }}</button></span></header><dl><div><dt>账号</dt><dd>{{ accountLabel(row.platforms[platform.key]) }}</dd></div><div><dt>上次尝试</dt><dd>{{ date(row.platforms[platform.key]?.last_attempt_at) }}</dd></div><div><dt>上次成功</dt><dd>{{ date(row.platforms[platform.key]?.last_success_at) }}</dd></div><div><dt>连续失败</dt><dd>{{ row.platforms[platform.key]?.consecutive_failures || 0 }}</dd></div><div><dt>完整覆盖</dt><dd>{{ date(row.platforms[platform.key]?.full_history_at) }}</dd></div><div><dt>错误码</dt><dd>{{ row.platforms[platform.key]?.last_error_code || '—' }}</dd></div></dl><p v-if="shortError(row.platforms[platform.key])" class="sync-detail-error">{{ shortError(row.platforms[platform.key]) }}</p></article></div></td></tr>
          </template>
        </tbody>
      </table>
      <p v-if="!loading && !snapshot.items.length" class="empty">没有符合条件的成员。</p>
      <p v-if="loading" class="sync-loading">正在读取同步状态…</p>
    </div>

    <footer class="sync-pagination"><span class="muted">共 {{ snapshot.total || 0 }} 位成员 · 每 5 秒自动刷新</span><div><button class="btn compact" :disabled="filters.page <= 1" @click="previousPage">上一页</button><span>第 {{ snapshot.page || filters.page }} / {{ totalPages }} 页</span><button class="btn compact" :disabled="filters.page >= totalPages" @click="nextPage">下一页</button></div></footer>
  </section>
</template>

<style scoped>
.sync-center { display: grid; gap: 18px; }
.sync-center-header { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }
.sync-center-header h2 { margin: 4px 0 6px; }.sync-center-header .eyebrow { margin: 0; color: var(--brand); font-size: 10px; font-weight: 800; letter-spacing: .16em; }.sync-center-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.sync-feedback { padding: 10px 12px; border: 1px solid color-mix(in srgb, var(--brand) 25%, var(--line)); border-radius: 8px; color: var(--brand-strong); background: color-mix(in srgb, var(--brand) 8%, var(--panel)); font-size: 12px; }.sync-feedback-error { color: var(--danger, #b74242); border-color: color-mix(in srgb, #b74242 25%, var(--line)); background: color-mix(in srgb, #b74242 6%, var(--panel)); }
.sync-stats { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 9px; }.sync-stat { display: grid; gap: 3px; padding: 13px; text-align: left; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--text); cursor: pointer; }.sync-stat:hover { border-color: var(--brand); transform: translateY(-1px); }.sync-stat-value { font-size: 23px; font-weight: 800; }.sync-stat-label { font-size: 12px; font-weight: 700; }.sync-stat small { min-height: 26px; color: var(--muted); font-size: 10px; line-height: 1.35; }.sync-stat.good .sync-stat-value { color: #2e9472; }.sync-stat.running .sync-stat-value { color: #3d76b5; }.sync-stat.waiting .sync-stat-value { color: #b48531; }.sync-stat.failed .sync-stat-value { color: #bd5b5b; }.sync-stat.disabled .sync-stat-value { color: #c17a32; }.sync-stat.paused .sync-stat-value { color: #8b6bb2; }.sync-stat.neutral .sync-stat-value { color: var(--muted); }
.sync-gate { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid color-mix(in srgb, #3b936e 25%, var(--line)); border-radius: 10px; background: color-mix(in srgb, #3b936e 7%, var(--panel)); }.sync-gate.blocked { border-color: color-mix(in srgb, #bd7f37 35%, var(--line)); background: color-mix(in srgb, #bd7f37 8%, var(--panel)); }.sync-gate-icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%; color: var(--panel); background: var(--brand); font-size: 18px; }.sync-gate p { margin: 3px 0 0; color: var(--muted); font-size: 11px; }.sync-gate-time { margin-left: auto; color: var(--muted); font-size: 11px; white-space: nowrap; }
.sync-filters { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--subtle-bg); }.sync-filters label { display: grid; gap: 5px; color: var(--muted); font-size: 11px; }.sync-filters .sync-search { flex: 1 1 250px; }.sync-filters input, .sync-filters select { min-height: 34px; min-width: 150px; }
.sync-table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }.sync-table { width: 100%; min-width: 1040px; border-collapse: collapse; }.sync-table th { padding: 11px 12px; color: var(--muted); background: var(--subtle-bg); font-size: 10px; font-weight: 800; letter-spacing: .06em; text-align: left; white-space: nowrap; }.sync-table td { padding: 11px 12px; border-top: 1px solid var(--line); vertical-align: top; }.sync-table tbody tr:hover { background: color-mix(in srgb, var(--brand) 3%, transparent); }.sync-table tbody tr.expanded { background: color-mix(in srgb, var(--brand) 5%, transparent); }
.sync-member-cell { display: flex; gap: 8px; align-items: center; min-width: 190px; }.sync-member-cell > span:last-child { display: grid; gap: 3px; }.sync-member-cell small, .sync-platform-cell small { display: block; color: var(--muted); font-size: 10px; line-height: 1.35; }.sync-expand { width: 21px; height: 21px; padding: 0; border: 1px solid var(--line); border-radius: 50%; background: transparent; color: var(--muted); cursor: pointer; }.sync-avatar { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px; background: color-mix(in srgb, var(--brand) 18%, var(--panel)); color: var(--brand-strong); font-weight: 800; }
.sync-platform-cell { min-width: 145px; }.sync-platform-head { display: flex; gap: 5px; align-items: center; font-size: 10px; color: var(--muted); }.sync-dot { width: 7px; height: 7px; display: inline-block; border-radius: 50%; background: var(--muted); }.sync-status-success { background: #359a76; }.sync-status-running { background: #4f8bcc; }.sync-status-waiting { background: #c18a34; }.sync-status-failed { background: #c45f5f; }.sync-status-disabled { background: #c17a32; }.sync-status-paused { background: #9472bc; }.sync-status-never, .sync-status-unbound, .sync-status-cancelled { background: #a6a7ac; }.sync-account { display: block; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }.sync-error-text { max-width: 170px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #bd5b5b !important; }.sync-retry-text { color: #b48531 !important; }.sync-table-actions { min-width: 96px; text-align: right !important; }.btn.compact { min-height: 29px; padding: 5px 9px; font-size: 10px; }.btn.ghost { background: transparent; }
.sync-detail-row td { padding: 0 12px 14px 46px; background: color-mix(in srgb, var(--brand) 3%, var(--panel)); }.sync-detail-grid { display: grid; grid-template-columns: repeat(5, minmax(170px, 1fr)); gap: 8px; padding-top: 10px; }.sync-detail-card { padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }.sync-detail-card header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.sync-detail-card dl { display: grid; gap: 5px; margin: 10px 0 0; }.sync-detail-card dl div { display: flex; justify-content: space-between; gap: 8px; font-size: 10px; }.sync-detail-card dt { color: var(--muted); }.sync-detail-card dd { margin: 0; text-align: right; }.sync-detail-error { margin: 9px 0 0; color: #bd5b5b; font-size: 10px; line-height: 1.4; }
.sync-loading, .sync-pagination { padding: 12px; color: var(--muted); font-size: 11px; }.sync-pagination { display: flex; justify-content: space-between; gap: 12px; align-items: center; }.sync-pagination > div { display: flex; gap: 10px; align-items: center; }
@media (max-width: 1100px) { .sync-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }.sync-detail-grid { grid-template-columns: repeat(2, minmax(170px, 1fr)); } }
@media (max-width: 700px) { .sync-center-header, .sync-pagination { flex-direction: column; align-items: stretch; }.sync-center-actions { justify-content: flex-start; }.sync-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }.sync-gate { align-items: flex-start; }.sync-gate-time { margin-left: 0; }.sync-detail-grid { grid-template-columns: 1fr; } }
</style>
