<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, auth, date, notify, showError, useRequests } from '../lib/api.js';
import { adminSessionVersion, useLeaveGuard, useParams } from '../lib/admin.js';
import { credentialsWorkbook } from '../lib/account-import-credentials.js';
import Pager from '../components/Pager.vue';

const route = useRoute(),
  update = useParams(),
  request = useRequests();
const accounts = ref([]),
  loading = ref(true),
  loadError = ref('');
const queryValue = (key) => (typeof route.query[key] === 'string' ? route.query[key] : '');
const routeFilters = () => ({
  search: queryValue('account_search'),
  school: queryValue('account_school'),
  status: queryValue('account_status'),
});
const filters = reactive(routeFilters()),
  selected = ref(new Map());
const sessionChanged = ref(false);
const busy = ref(false),
  results = ref([]),
  credentials = ref([]),
  exported = ref(true);
const batchRole = ref('member'),
  roleDrafts = ref({}),
  downloadError = ref('');
const sessionVersion = adminSessionVersion();
const owner = [auth.qq_id, auth.account_epoch, auth.role];
let disposed = false,
  invalidated = false;
const sameSession = () => !disposed && !invalidated && sessionVersion === adminSessionVersion();
const writeBlocked = computed(
  () => busy.value || loading.value || Boolean(loadError.value) || sessionChanged.value,
);
const roles = { member: '成员', admin: '管理员', root: '超级管理员' };
const filterValues = (field) =>
  [
    ...new Set(
      accounts.value
        .map((row) => row[field])
        .filter((value) => typeof value === 'string' && value.trim()),
    ),
  ].sort((a, b) => a.localeCompare(b, 'zh-CN'));
const options = computed(() => ({
  schools: filterValues('school'),
  statuses: filterValues('status'),
}));
const filtered = computed(() => {
  const applied = routeFilters();
  const term = applied.search.trim().toLowerCase();
  return accounts.value.filter(
    (row) =>
      (!applied.school || row.school === applied.school) &&
      (!applied.status || row.status === applied.status) &&
      (!term ||
        [
          row.qq_id,
          row.display_qq_id,
          row.real_name,
          row.name,
          row.school,
          row.status,
          row.role,
          roles[row.role],
        ].some((value) =>
          String(value || '')
            .toLowerCase()
            .includes(term),
        )),
  );
});
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / 20)));
const page = computed(() => {
  const requested = Number(route.query.account_page);
  return Math.min(pages.value, Number.isInteger(requested) && requested > 0 ? requested : 1);
});
const rows = computed(() => filtered.value.slice((page.value - 1) * 20, page.value * 20));
const manageable = (row) =>
  Boolean(row.qq_id) &&
  row.account_state !== 'closed' &&
  (auth.role === 'root' || row.role === 'member');
const resettable = (row) => manageable(row) && row.role === 'member' && Boolean(row.is_active);
const eligible = computed(() => rows.value.filter(manageable));
const allSelected = computed(
  () => eligible.value.length > 0 && eligible.value.every((row) => selected.value.has(row.qq_id)),
);
const someSelected = computed(
  () => !allSelected.value && eligible.value.some((row) => selected.value.has(row.qq_id)),
);
const snapshot = (row) => ({
  expected_account_epoch: row.account_epoch,
  expected_credential_version: row.credential_version,
});
function clearSensitive() {
  credentials.value = [];
  exported.value = true;
  selected.value = new Map();
  results.value = [];
  downloadError.value = '';
}
function invalidate() {
  invalidated = true;
  sessionChanged.value = true;
  busy.value = false;
  loading.value = false;
  loadError.value = '登录会话已变化，请重新加载页面';
  clearSensitive();
  accounts.value = [];
  roleDrafts.value = {};
}
watch(
  () => [auth.authenticated, auth.qq_id, auth.account_epoch, auth.role],
  (current) => {
    if (
      !current[0] ||
      current[1] !== owner[0] ||
      current[2] !== owner[1] ||
      current[3] !== owner[2]
    )
      invalidate();
  },
  { flush: 'pre' },
);
watch(
  () => [
    route.query.account_search,
    route.query.account_school,
    route.query.account_status,
    route.query.account_page,
  ],
  () => {
    Object.assign(filters, routeFilters());
    selected.value = new Map();
  },
);
function applyFilters(reset = false) {
  if (busy.value || sessionChanged.value) return;
  const next = reset
    ? { search: '', school: '', status: '' }
    : { search: filters.search.trim(), school: filters.school, status: filters.status };
  Object.assign(filters, next);
  selected.value = new Map();
  return update({
    account_search: next.search || null,
    account_school: next.school || null,
    account_status: next.status || null,
    account_page: 1,
  });
}
function toggle(row, checked) {
  if (writeBlocked.value || !manageable(row)) return;
  const next = new Map(selected.value);
  if (checked) next.set(row.qq_id, { ...row });
  else next.delete(row.qq_id);
  selected.value = next;
}
function selectPage(checked) {
  for (const row of eligible.value) toggle(row, checked);
}
async function load() {
  if (!sameSession()) return;
  loading.value = true;
  loadError.value = '';
  try {
    const data = await request('/admin/web-accounts', {}, 'accounts');
    if (!sameSession()) return;
    accounts.value = data;
    roleDrafts.value = {};
    const visible = new Map(rows.value.filter(manageable).map((row) => [row.qq_id, row]));
    selected.value = new Map(
      [...selected.value].filter(
        ([id, original]) =>
          visible.get(id)?.account_epoch === original.account_epoch &&
          visible.get(id)?.credential_version === original.credential_version,
      ),
    );
    // A later password/state change must not leave an obsolete password exportable.
    const remaining = credentials.value.filter((receipt) =>
      data.some(
        (row) =>
          row.qq_id === receipt.qq_id &&
          row.account_epoch === receipt.account_epoch &&
          row.credential_version === receipt.credential_version &&
          row.is_active,
      ),
    );
    if (remaining.length !== credentials.value.length) {
      credentials.value = remaining;
      notify('部分账号已变化，已移除对应的旧临时密码，请勿继续使用旧密码表。');
    }
  } catch (error) {
    if (sameSession() && error.name !== 'AbortError') loadError.value = error.message;
  } finally {
    if (sameSession()) loading.value = false;
  }
}
function targetText(row) {
  return `${row.real_name || '未填写姓名'}（QQ ${row.qq_id}）`;
}
function operationLabel(kind) {
  return {
    temporary: '重设临时密码',
    role: '更改权限',
    active: '调整启停状态',
    password: '设置初始密码',
  }[kind];
}
async function run(kind, targets, value) {
  if (writeBlocked.value || !sameSession() || !targets.length) return;
  if (kind === 'role' && auth.role !== 'root') return;
  const ordered = [...targets].sort(
    (a, b) => Number(a.qq_id === auth.qq_id) - Number(b.qq_id === auth.qq_id),
  );
  const effect =
    kind === 'temporary'
      ? '旧密码与旧登录会话将失效，下次登录必须改密。已导出的旧密码也会失效。'
      : kind === 'role'
        ? `目标权限：${roles[value]}。修改将使目标的现有会话失效。`
        : '现有登录会话将失效。';
  if (
    !confirm(
      `${operationLabel(kind)}：共 ${ordered.length} 人\n${ordered.map(targetText).join('\n')}\n${effect}\n确认继续？`,
    )
  )
    return;
  busy.value = true;
  results.value = [];
  for (const row of ordered) {
    if (!sameSession()) break;
    const result = {
      qq_id: row.qq_id,
      real_name: row.real_name || '',
      state: 'pending',
      message: '处理中',
    };
    results.value = [...results.value, result];
    if (kind === 'role' && row.role === value) {
      Object.assign(result, { state: 'skipped', message: '权限未变化，已跳过' });
      const next = new Map(selected.value);
      next.delete(row.qq_id);
      selected.value = next;
      results.value = results.value.map((entry) => ({ ...entry }));
      continue;
    }
    // Every maintenance write changes the credential version. Do not rely on the
    // following refresh to remove an obsolete receipt: that refresh can fail.
    credentials.value = credentials.value.filter((item) => item.qq_id !== row.qq_id);
    try {
      const suffix =
        { temporary: '/reset-temporary-password', password: '/reset-password' }[kind] || '';
      const response = await api(`/admin/web-accounts/${encodeURIComponent(row.qq_id)}${suffix}`, {
        method: suffix ? 'POST' : 'PATCH',
        body: {
          ...snapshot(row),
          ...(kind === 'role'
            ? { role: value }
            : kind === 'active'
              ? { is_active: !row.is_active }
              : kind === 'password'
                ? { initial_password: value }
                : {}),
        },
      });
      if (!sameSession()) break;
      if (kind === 'temporary') {
        if (
          !response.temporary_password ||
          response.qq_id !== row.qq_id ||
          response.account_epoch !== row.account_epoch
        )
          throw Error('未收到完整密码结果，请核对账号状态；不要自动重试。');
        credentials.value = [
          ...credentials.value,
          { ...response, real_name: response.real_name || '' },
        ];
        exported.value = false;
        downloadError.value = '';
      }
      Object.assign(result, { state: 'success', message: '成功' });
      const next = new Map(selected.value);
      next.delete(row.qq_id);
      selected.value = next;
    } catch (error) {
      if (!sameSession()) break;
      const uncertain = !error.status || error.status >= 500;
      Object.assign(result, {
        state: 'failed',
        message: uncertain
          ? '结果未确认，操作可能已生效。请刷新核对，不会自动重试。'
          : error.message,
      });
      if (error.status === 401 || error.status === 403) {
        results.value = results.value.map((entry) => ({ ...entry }));
        for (const pending of ordered.slice(ordered.indexOf(row) + 1))
          results.value.push({
            qq_id: pending.qq_id,
            real_name: pending.real_name || '',
            state: 'failed',
            message: '权限校验失败，后续操作已停止。',
          });
        break;
      }
    }
    results.value = results.value.map((entry) => ({ ...entry }));
  }
  if (sameSession()) {
    await load();
    if (sameSession()) busy.value = false;
  }
}
function changeRole(row) {
  const role = roleDrafts.value[row.qq_id] || row.role;
  if (role !== row.role) return run('role', [row], role);
}
function bulk(kind) {
  return run(kind, [...selected.value.values()], kind === 'role' ? batchRole.value : undefined);
}
function manualPassword(row) {
  const password = prompt('设置新的初始密码（至少 12 位；密码不会被本页保存）');
  if (password) return run('password', [row], password);
}
function download() {
  if (!sameSession() || busy.value || !credentials.value.length) return;
  downloadError.value = '';
  let url;
  try {
    const workbook = credentialsWorkbook(credentials.value, {
      nameLabel: '真实姓名',
      passwordLabel: '临时密码',
      sheetName: '临时密码',
    });
    url = URL.createObjectURL(workbook);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'web-account-temporary-passwords.xlsx';
    document.body.append(link);
    link.click();
    link.remove();
    // Browsers do not confirm a completed download. Keep the unsaved-results warning.
    notify('已发起下载，请确认文件已保存。可重复导出，不会再次重设密码。');
  } catch (error) {
    downloadError.value = '导出未完成，密码结果仍保留在本页。请重新导出，不要重新重设密码。';
  } finally {
    if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
function leave() {
  return (
    !(busy.value || (credentials.value.length && !exported.value)) ||
    confirm(
      '操作仍在进行或临时密码尚未确认保存。离开后密码明文会清除，无法重新查看。请先导出并确认文件已保存。仍要离开？',
    )
  );
}
function unload(event) {
  if (busy.value || (credentials.value.length && !exported.value)) {
    event.preventDefault();
    event.returnValue = '';
  }
}
function reloadPage() {
  location.reload();
}
function pageshow(event) {
  if (event.persisted) location.reload();
}
useLeaveGuard(leave);
onMounted(() => {
  load();
  window.addEventListener('beforeunload', unload);
  window.addEventListener('pagehide', invalidate);
  window.addEventListener('pageshow', pageshow);
});
onBeforeUnmount(() => {
  disposed = true;
  clearSensitive();
  window.removeEventListener('beforeunload', unload);
  window.removeEventListener('pagehide', invalidate);
  window.removeEventListener('pageshow', pageshow);
});
</script>
<template>
  <section class="admin-panel account-management">
    <div class="admin-section-heading">
      <div>
        <h2>账号管理</h2>
        <p class="muted">管理已有账号的权限和密码；新成员请前往「开通账号」。</p>
      </div>
      <button class="btn" :disabled="busy || loading || sessionChanged" @click="load">
        刷新账号
      </button>
    </div>
    <button v-if="sessionChanged" class="btn primary" @click="reloadPage">重新加载页面</button>
    <form class="filters account-filters" @submit.prevent="applyFilters()">
      <label
        >关键词<input
          v-model="filters.search"
          type="search"
          placeholder="QQ、真实姓名、昵称、学校或身份"
          :disabled="busy || sessionChanged"
      /></label>
      <label
        >学校<select v-model="filters.school" aria-label="学校" :disabled="busy || sessionChanged">
          <option value="">全部学校</option>
          <option v-for="school in options.schools" :key="school" :value="school">
            {{ school }}
          </option>
          <option
            v-if="filters.school && !options.schools.includes(filters.school)"
            :value="filters.school"
          >
            {{ filters.school }}
          </option>
        </select></label
      >
      <label
        >身份<select v-model="filters.status" aria-label="身份" :disabled="busy || sessionChanged">
          <option value="">全部身份</option>
          <option v-for="status in options.statuses" :key="status" :value="status">
            {{ status }}
          </option>
          <option
            v-if="filters.status && !options.statuses.includes(filters.status)"
            :value="filters.status"
          >
            {{ filters.status }}
          </option>
        </select></label
      >
      <button class="btn primary" :disabled="busy || sessionChanged">搜索</button>
      <button
        class="btn"
        type="button"
        :disabled="busy || sessionChanged"
        @click="applyFilters(true)"
      >
        重置
      </button>
    </form>
    <div class="account-actions" aria-label="批量账号操作">
      <span>已选 {{ selected.size }} 人（仅当前页，翻页或筛选会清除选择）</span>
      <button class="btn" :disabled="writeBlocked || !selected.size" @click="selected = new Map()">
        取消选择
      </button>
      <button class="btn" :disabled="writeBlocked || !selected.size" @click="bulk('temporary')">
        批量重设临时密码
      </button>
      <template v-if="auth.role === 'root'">
        <label
          >目标权限<select v-model="batchRole" aria-label="目标权限" :disabled="writeBlocked">
            <option v-for="(label, role) in roles" :key="role" :value="role">{{ label }}</option>
          </select></label
        >
        <button class="btn" :disabled="writeBlocked || !selected.size" @click="bulk('role')">
          批量更改权限
        </button>
      </template>
      <span v-else class="muted">仅 root 可更改权限</span>
    </div>
    <p v-if="loading" role="status">正在加载账号…</p>
    <p v-else-if="loadError" role="alert">
      {{ loadError }}。请刷新重试，当前列表可能不是最新状态。
    </p>
    <p v-else class="muted">
      共 {{ filtered.length }} 个账号<span v-if="busy"> · 正在处理，请勿重复提交或离开页面</span>
    </p>
    <p v-if="!loading && !loadError" class="muted account-scroll-hint">
      表格可左右滚动，查看完整信息与操作。
    </p>
    <div
      v-if="!loading && !loadError"
      class="table-wrap account-table-wrap"
      role="region"
      aria-label="账号列表（可左右滚动）"
      tabindex="0"
    >
      <table class="account-table">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label="全选当前页可维护账号"
                :checked="allSelected"
                :indeterminate="someSelected"
                :disabled="writeBlocked || !eligible.length"
                @change="selectPage($event.target.checked)"
              />
            </th>
            <th>QQ 号</th>
            <th>真实姓名</th>
            <th>最近登录时间</th>
            <th>当前权限 / 状态</th>
            <th>重设临时密码</th>
            <th>更改权限</th>
            <th>其他操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.qq_id || row.account_key">
            <td>
              <input
                type="checkbox"
                :aria-label="`选择 QQ ${row.qq_id || row.display_qq_id}`"
                :checked="selected.has(row.qq_id)"
                :disabled="writeBlocked || !manageable(row)"
                @change="toggle(row, $event.target.checked)"
              />
            </td>
            <td>{{ row.qq_id || row.display_qq_id }}</td>
            <td>{{ row.real_name || '—' }}</td>
            <td>{{ row.last_login_at ? date(row.last_login_at) : '从未登录' }}</td>
            <td>
              {{ roles[row.role] || row.role }}<br /><small class="muted"
                >{{ row.account_state === 'closed' ? '已注销' : row.is_active ? '启用' : '停用' }} ·
                {{ row.must_change_password ? '待改密' : '已改密' }}</small
              >
            </td>
            <td>
              <button
                class="btn"
                :disabled="writeBlocked || !resettable(row)"
                @click="run('temporary', [row])"
              >
                重设临时密码</button
              ><small v-if="row.role !== 'member'" class="muted account-hint"
                >管理员账号由 root 设置初始密码</small
              >
            </td>
            <td>
              <template v-if="auth.role === 'root' && manageable(row)">
                <select
                  v-model="roleDrafts[row.qq_id]"
                  :aria-label="`QQ ${row.qq_id} 的目标权限`"
                  :disabled="writeBlocked"
                >
                  <option :value="undefined" disabled>选择权限</option>
                  <option v-for="(label, role) in roles" :key="role" :value="role">
                    {{ label }}
                  </option>
                </select>
                <button
                  class="btn"
                  :disabled="
                    writeBlocked || !roleDrafts[row.qq_id] || roleDrafts[row.qq_id] === row.role
                  "
                  @click="changeRole(row)"
                >
                  更改权限
                </button>
              </template>
              <span v-else class="muted">{{
                row.account_state === 'closed' ? '已注销' : '仅 root 可操作'
              }}</span>
            </td>
            <td class="account-row-actions">
              <button
                class="btn"
                :disabled="writeBlocked || !manageable(row)"
                @click="run('active', [row])"
              >
                {{ row.is_active ? '停用' : '启用' }}
              </button>
              <button
                class="btn"
                :disabled="writeBlocked || !manageable(row)"
                @click="manualPassword(row)"
              >
                设置初始密码
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="8">
              {{
                routeFilters().search || routeFilters().school || routeFilters().status
                  ? '没有匹配的账号。'
                  : '暂无已开通账号，请前往「开通账号」。'
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Pager
      v-if="!loading && !loadError"
      :page="page"
      :total="filtered.length"
      :busy="busy"
      @change="(next) => update({ account_page: next })"
    />
    <section
      v-if="results.length"
      class="account-results"
      aria-label="本次操作结果"
      aria-live="polite"
    >
      <h3>本次操作结果</h3>
      <p>
        成功 {{ results.filter((row) => row.state === 'success').length }} 人，失败/未处理
        {{ results.filter((row) => row.state === 'failed').length }} 人<span v-if="busy"
          >，处理中…</span
        >
      </p>
      <p v-if="results.some((row) => row.state === 'skipped')" class="muted">
        已跳过 {{ results.filter((row) => row.state === 'skipped').length }} 人（无需更改）
      </p>
      <ul>
        <li v-for="row in results" :key="row.qq_id">
          QQ {{ row.qq_id }} · {{ row.real_name || '—' }}：{{ row.message }}
        </li>
      </ul>
      <p class="muted">版本或状态冲突时请刷新核对后重新勾选；不会自动重试，以免重复重设密码。</p>
    </section>
    <section v-if="credentials.length" class="account-results" aria-label="临时密码导出">
      <h3>临时密码表 · {{ credentials.length }} 人</h3>
      <p>
        仅包含当前页面累计领取的成功结果，不含失败账号。导出列为 QQ
        号、真实姓名、账号、临时密码；离开后无法重新查看。
      </p>
      <button class="btn primary" :disabled="busy" @click="download">
        导出本次密码表（Excel）
      </button>
      <button class="btn" :disabled="busy" @click="exported = true">已确认文件保存</button>
      <p v-if="downloadError" role="alert">{{ downloadError }}</p>
      <p class="muted">
        可以重复下载，不会再次重设密码。每个账号仅保留最新已领取的密码；重设后此前导出的旧密码失效。
      </p>
    </section>
  </section>
</template>
<style scoped>
.account-management {
  min-width: 0;
}
.account-filters {
  align-items: flex-end;
  flex-wrap: wrap;
}
.account-filters label:first-child {
  flex: 1;
  min-width: 180px;
}
.account-filters select {
  width: 100%;
  min-width: 130px;
}
.account-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 20px 0;
}
.account-actions label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.account-table-wrap {
  max-width: 100%;
  overflow-x: auto;
}
.account-table {
  min-width: 1120px;
}
.account-table th,
.account-table td {
  vertical-align: middle;
}
.account-table th {
  white-space: nowrap;
}
.account-table input[type='checkbox'] {
  min-width: 18px;
  min-height: 18px;
}
.account-table select {
  max-width: 125px;
}
.account-row-actions .btn {
  margin: 3px;
}
.account-hint {
  display: block;
  max-width: 150px;
  margin-top: 6px;
}
.account-results {
  border-top: 1px solid var(--line);
  margin-top: 22px;
  padding-top: 18px;
}
.account-results ul {
  max-height: 260px;
  overflow-y: auto;
}
.account-results .btn {
  margin: 4px 8px 4px 0;
}
@media (max-width: 640px) {
  .account-filters label {
    flex: 1 1 100%;
    min-width: 0 !important;
  }
  .account-actions {
    align-items: flex-start;
  }
  .account-actions > span {
    flex-basis: 100%;
  }
}
</style>
