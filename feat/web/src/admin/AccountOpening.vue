<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue';
import { api, auth, useRequests, notify, showError, date } from '../lib/api.js';
import { adminSessionVersion, useLeaveGuard } from '../lib/admin.js';
import Pager from '../components/Pager.vue';
const request = useRequests(),
  candidates = ref({ items: [], total: 0, page: 1, page_size: 20 }),
  selected = ref(new Set()),
  credentials = ref([]),
  skipped = ref([]),
  filter = reactive({ search: '', include_issued: false }),
  busy = ref(false),
  fallback = ref(''),
  invalidated = ref(false);
const form = reactive({
  qq_id: '',
  name: '',
  initial_password: '',
  status: '',
  school: '',
  role: 'member',
});
const names = new Map();
const owner = [auth.authenticated, auth.qq_id, auth.account_epoch, auth.role];
const sessionVersion = adminSessionVersion();
let disposed = false;
const sameSession = () => !disposed && sessionVersion === adminSessionVersion();
async function loadCandidates(page = 1) {
  if (!sameSession()) return;
  try {
    const data = await request(
      '/admin/web-account-candidates?' +
        new URLSearchParams({
          search: filter.search,
          page,
          page_size: 20,
          ...(filter.include_issued ? { include_issued: 1 } : {}),
        }),
      {},
      'candidates',
    );
    if (!sameSession()) return;
    candidates.value = data;
    for (const row of candidates.value.items) names.set(row.qq_id, row.name);
  } catch (e) {
    if (sameSession()) showError(e);
  }
}
function select(qq, active) {
  const next = new Set(selected.value);
  if (active) {
    if (next.size < 20) next.add(qq);
  } else next.delete(qq);
  selected.value = next;
}
function selectPage(event) {
  if (busy.value) return;
  for (const row of candidates.value.items.filter((r) => !r.has_web_account))
    select(row.qq_id, event.target.checked);
}
function remember(result) {
  credentials.value = (result.created || []).map((row) => ({
    ...row,
    name: row.name || names.get(row.qq_id) || '未命名',
  }));
  skipped.value = result.skipped || [];
}
async function issue() {
  if (busy.value || !sameSession() || !selected.value.size) return;
  const ids = [...selected.value];
  if (
    !confirm(
      `将为以下成员发放临时密码：\n${ids.map((id) => `${names.get(id) || id}（${id}）`).join('\n')}\n确认继续？`,
    )
  )
    return;
  busy.value = true;
  try {
    const result = await api('/admin/web-accounts/batch', {
      method: 'POST',
      timeoutMs: 30000,
      body: { qq_ids: ids },
    });
    if (!sameSession()) return;
    remember(result);
    selected.value = new Set();
    await loadCandidates(candidates.value.page);
  } catch (e) {
    if (sameSession()) showError(e);
  } finally {
    busy.value = false;
  }
}
async function create() {
  if (busy.value || !sameSession()) return;
  busy.value = true;
  try {
    await request('/admin/web-accounts', { method: 'POST', body: { ...form } });
    if (!sameSession()) return;
    form.initial_password = '';
    notify('账号已创建');
    await loadCandidates();
  } catch (e) {
    if (sameSession()) showError(e);
  } finally {
    busy.value = false;
  }
}
function credentialRows() {
  return credentials.value.map((row) => [
    row.qq_id,
    row.name,
    row.temporary_password,
    date(row.expires_at),
  ]);
}
async function copy() {
  if (!sameSession() || !credentials.value.length) return;
  const text = credentialRows()
    .map((row) => row.join('\t'))
    .join('\n');
  try {
    await navigator.clipboard.writeText(text);
    if (sameSession()) notify('已复制账密');
  } catch {
    if (!sameSession()) return;
    fallback.value = text;
    notify('自动复制失败，请从文本框手动复制');
  }
}
function download() {
  if (!sameSession() || !credentials.value.length) return;
  const cell = (value) => {
    let s = String(value ?? '');
    if (/^[=+@\-]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  const data = [['QQ', '昵称', '临时密码', '过期时间'], ...credentialRows()]
    .map((row) => row.map(cell).join(','))
    .join('\r\n');
  const url = URL.createObjectURL(new Blob(['\ufeff' + data], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'web-member-accounts.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function leave() {
  return (
    !(credentials.value.length || busy.value) ||
    confirm(
      '离开后临时密码会清除，无法再次查看。请先复制或下载；正在发放的结果也可能无法领取。继续离开？',
    )
  );
}
function unload(event) {
  if (credentials.value.length || busy.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
function clear() {
  credentials.value = [];
  fallback.value = '';
  form.initial_password = '';
  selected.value = new Set();
  names.clear();
  skipped.value = [];
}
function invalidate() {
  disposed = true;
  invalidated.value = true;
  busy.value = false;
  clear();
}
function reloadPage() {
  location.reload();
}
function pageshow(event) {
  if (event.persisted) location.reload();
}
watch(
  () => [auth.authenticated, auth.qq_id, auth.account_epoch, auth.role],
  (current) => {
    if (
      current.some((value, index) => value !== owner[index]) ||
      sessionVersion !== adminSessionVersion()
    ) {
      invalidate();
    }
  },
  { flush: 'pre' },
);
useLeaveGuard(leave);
onMounted(() => {
  window.addEventListener('beforeunload', unload);
  window.addEventListener('pagehide', invalidate);
  window.addEventListener('pageshow', pageshow);
  loadCandidates();
});
onBeforeUnmount(() => {
  disposed = true;
  clear();
  window.removeEventListener('beforeunload', unload);
  window.removeEventListener('pagehide', invalidate);
  window.removeEventListener('pageshow', pageshow);
});
</script>
<template>
  <div class="admin-content">
    <p v-if="invalidated" role="alert">
      登录会话已变化，请重新加载页面。<button class="btn" @click="reloadPage">重新加载页面</button>
    </p>
    <template v-else>
      <section class="admin-section">
        <div class="admin-section-heading">
          <div>
            <h2>给已有成员开通账号</h2>
            <p>搜索成员并批量发放 Web 登录账号。</p>
          </div>
          <span class="admin-limit">每批最多 20 人</span>
        </div>
        <section class="admin-panel">
          <form class="admin-filter-row" @submit.prevent="loadCandidates()">
            <label class="admin-search"
              ><input
                v-model.trim="filter.search"
                type="search"
                aria-label="搜索昵称、QQ 或学校"
                placeholder="搜索昵称、QQ 或学校" /></label
            ><label class="admin-toggle"
              ><input
                v-model="filter.include_issued"
                type="checkbox"
                @change="loadCandidates()"
              />包括已有账号</label
            ><button class="btn primary">搜索成员</button>
          </form>
          <div class="admin-table-meta">
            <span>共 {{ candidates.total }} 位成员</span><span>已选 {{ selected.size }} / 20</span>
          </div>
          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="选择本页未发号成员"
                      :disabled="busy"
                      :checked="
                        candidates.items.filter((r) => !r.has_web_account).length > 0 &&
                        candidates.items
                          .filter((r) => !r.has_web_account)
                          .every((r) => selected.has(r.qq_id))
                      "
                      @change="selectPage"
                    />
                  </th>
                  <th>QQ</th>
                  <th>昵称</th>
                  <th>学校</th>
                  <th>身份</th>
                  <th>账号状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in candidates.items" :key="row.qq_id">
                  <td>
                    <input
                      type="checkbox"
                      :aria-label="`选择 ${row.name}`"
                      :checked="selected.has(row.qq_id)"
                      :disabled="
                        busy ||
                        row.has_web_account ||
                        (!selected.has(row.qq_id) && selected.size >= 20)
                      "
                      @change="select(row.qq_id, $event.target.checked)"
                    />
                  </td>
                  <td>{{ row.qq_id }}</td>
                  <td>{{ row.name }}</td>
                  <td>{{ row.school || '—' }}</td>
                  <td>{{ row.status || '—' }}</td>
                  <td>
                    {{
                      row.has_web_account
                        ? `${row.role} · ${row.is_active ? '启用' : '停用'}`
                        : '未发放'
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="admin-table-footer">
            <Pager
              :page="candidates.page"
              :total="candidates.total"
              :busy="busy"
              @change="loadCandidates"
            /><button class="btn primary" :disabled="busy || !selected.size" @click="issue">
              为已选成员生成账号
            </button>
          </div>
          <p class="admin-security-note">
            临时密码有效期默认 72 小时。结果只显示一次，请及时复制或下载并通过安全渠道交给成员。
          </p>
        </section>
        <section v-if="credentials.length || skipped.length" class="admin-panel admin-results">
          <div class="admin-section-heading">
            <h2>本次发放结果</h2>
            <div class="admin-result-actions">
              <button class="btn" @click="copy">复制账密</button
              ><button class="btn" @click="download">下载 CSV</button>
            </div>
          </div>
          <p>
            成功 {{ credentials.length }} 个，跳过 {{ skipped.length }} 个。离开后临时密码无法恢复。
          </p>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>QQ</th>
                  <th>昵称</th>
                  <th>临时密码</th>
                  <th>过期时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in credentials" :key="row.qq_id">
                  <td>{{ row.qq_id }}</td>
                  <td>{{ row.name }}</td>
                  <td>
                    <code>{{ row.temporary_password }}</code>
                  </td>
                  <td>{{ date(row.expires_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-for="(row, i) in skipped" :key="i">{{ row.qq_id }} · {{ row.reason }}</p>
          <textarea v-if="fallback" :value="fallback" readonly aria-label="手动复制账密"></textarea>
        </section>
      </section>
      <section class="admin-section">
        <h2>单个成员开通</h2>
        <details class="admin-create" open>
          <summary>单个创建账号</summary>
          <p class="muted">
            已注销的 QQ 可在这里创建全新账号，须填写新昵称和密码；旧资料、私有数据及权限不会继承。
          </p>
          <form class="admin-create-body" @submit.prevent="create">
            <div class="admin-create-grid">
              <label
                v-for="(label, key) in {
                  qq_id: '成员 QQ',
                  name: '昵称',
                  initial_password: '初始密码',
                  status: '身份 / 年级',
                  school: '学校',
                }"
                :key="key"
                >{{ label
                }}<input
                  v-model="form[key]"
                  :type="key === 'initial_password' ? 'password' : 'text'"
                  :autocomplete="key === 'initial_password' ? 'new-password' : undefined"
                  :required="['qq_id', 'initial_password'].includes(key)" /></label
              ><label
                >账号角色<select v-model="form.role">
                  <option value="member">成员</option>
                  <option value="admin">管理员</option>
                  <option v-if="auth.role === 'root'" value="root">Root</option>
                </select></label
              >
            </div>
            <button class="btn primary" :disabled="busy">创建账号</button>
          </form>
        </details>
      </section>
    </template>
  </div>
</template>
