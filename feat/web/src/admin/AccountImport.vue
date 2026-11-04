<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, auth, date, useRequests } from '../lib/api.js';
import { useLeaveGuard, useParams } from '../lib/admin.js';
import ImportPreviewTable from '../components/account-import/ImportPreviewTable.vue';
import ImportResults from '../components/account-import/ImportResults.vue';
const route = useRoute(),
  params = useParams(),
  request = useRequests();
const capabilities = ref(null),
  batch = ref(null),
  rows = ref([]),
  selected = ref(new Set());
const file = ref(null),
  input = ref(null),
  error = ref(''),
  busy = ref(false),
  loading = ref(false);
const credentials = ref([]),
  acknowledge = ref(false),
  running = ref(false),
  uncertain = ref(false);
let disposed = false,
  generation = 0,
  lifetime = 0,
  pollTimer,
  writeController,
  recoveryTarget;
const prefix = '/admin/account-imports';
const chosen = computed(() => rows.value.filter((row) => selected.value.has(row.row_id)));
const canContinue = computed(
  () =>
    batch.value &&
    !batch.value.read_only &&
    capabilities.value?.enabled &&
    batch.value.status === 'paused' &&
    batch.value.summary.remaining > 0 &&
    batch.value.next_chunk_token,
);
const dirty = computed(() => credentials.value.length > 0 || busy.value || running.value);
const missingCredentials = computed(() =>
  Math.max(0, (batch.value?.summary.created || 0) - credentials.value.length),
);
const statusText = computed(
  () =>
    ({
      preview_ready: '待确认',
      committing: '当前段正在处理',
      paused: '已暂停，可明确继续',
      completed: '已完成',
      completed_with_errors: '已完成，部分行冲突',
      cancelled: '已停止后续创建',
      expired: '已过期，请重新上传',
    })[batch.value?.status] || '准备上传',
);
function showError(e) {
  if (!disposed && e.name !== 'AbortError') error.value = e.message || '操作失败，请重试。';
}
function schedule() {
  clearTimeout(pollTimer);
  if (!disposed && !running.value && batch.value?.active_chunk)
    pollTimer = setTimeout(() => refresh().catch(showError), 2500);
}
async function refresh(id = batch.value?.id) {
  if (!id || disposed) return;
  const revision = ++generation;
  loading.value = true;
  try {
    const data = await request(`${prefix}/${encodeURIComponent(id)}`, {}, 'batch');
    const all = [];
    for (let page = 1; ; page++) {
      const result = await request(
        `${prefix}/${encodeURIComponent(id)}/rows?page=${page}&page_size=100`,
        {},
        'rows',
      );
      all.push(...result.items);
      if (all.length >= result.total) break;
    }
    if (disposed || revision !== generation) return;
    batch.value = data;
    rows.value = all;
    if (data.selection_digest)
      selected.value = new Set(all.filter((row) => row.selected).map((row) => row.row_id));
    else
      selected.value = new Set(
        [...selected.value].filter((id) => all.some((row) => row.row_id === id && row.can_submit)),
      );
    uncertain.value = Boolean(data.active_chunk);
    schedule();
  } finally {
    if (revision === generation) loading.value = false;
  }
}
function chooseFile(event) {
  file.value = event.target.files?.[0] || null;
  error.value = '';
}
async function upload() {
  if (busy.value || !file.value) return;
  if (dirty.value && !leave()) return;
  const lifetimeAtStart = lifetime;
  const chosenFile = file.value;
  if (!/\.xlsx$/i.test(chosenFile.name)) {
    error.value = '请选择.xlsx模板。';
    return;
  }
  if (chosenFile.size > capabilities.value.max_file_bytes) {
    error.value = '文件超过5MiB，请拆分后上传。';
    return;
  }
  busy.value = true;
  error.value = '';
  clearTimeout(pollTimer);
  credentials.value = [];
  rows.value = [];
  batch.value = null;
  selected.value = new Set();
  acknowledge.value = false;
  const form = new FormData();
  form.append('file', chosenFile);
  writeController = new AbortController();
  try {
    const data = await api(`${prefix}/preview`, {
      method: 'POST',
      body: form,
      timeoutMs: 30000,
      signal: writeController.signal,
    });
    if (disposed || lifetimeAtStart !== lifetime) return;
    batch.value = data;
    recoveryTarget = data.id;
    try {
      await params({ section: 'accounts', tab: 'import', import_id: data.id }, true);
    } finally {
      recoveryTarget = null;
    }
    await refresh(data.id);
    file.value = null;
    if (input.value) input.value.value = '';
  } catch (e) {
    showError(e);
  } finally {
    if (lifetimeAtStart === lifetime) busy.value = false;
  }
}
function selectRows(ids, active) {
  const value = new Set(selected.value);
  for (const id of ids) active ? value.add(id) : value.delete(id);
  selected.value = value;
}
function initialRequest() {
  return {
    preview_version: batch.value.preview_version,
    selected_row_ids: [...selected.value],
    acknowledge_admin_binding: acknowledge.value,
    idempotency_key: crypto.randomUUID(),
  };
}
function nextRequest() {
  return {
    preview_version: batch.value.preview_version,
    selection_digest: batch.value.selection_digest,
    continuation_token: batch.value.next_chunk_token,
    idempotency_key: crypto.randomUUID(),
  };
}
async function execute() {
  if (busy.value || uncertain.value || !batch.value || batch.value.read_only) return;
  const first = !batch.value.selection_digest;
  if (first && !chosen.value.length) return;
  const scope = first
    ? chosen.value
    : rows.value.filter((row) => row.selected && ['ready', 'retryable'].includes(row.status));
  if (
    !confirm(
      `将${first ? '创建' : '继续创建'}以下 ${scope.length} 位成员的普通账号：\n${scope.map((row) => `${row.name}（${row.qq_id}），${row.action === 'create_web_account_only' ? '仅补开户，忽略表内其他资料' : '新建并开户'}`).join('\n')}\n初始密码有效 ${batch.value.temporary_password_ttl_hours} 小时，首次登录必须改密。确认继续？`,
    )
  )
    return;
  running.value = true;
  busy.value = true;
  error.value = '';
  clearTimeout(pollTimer);
  const lifetimeAtStart = lifetime;
  let body = first ? initialRequest() : nextRequest();
  try {
    while (!disposed && running.value) {
      writeController = new AbortController();
      const data = await api(`${prefix}/${encodeURIComponent(batch.value.id)}/commit`, {
        method: 'POST',
        body,
        timeoutMs: 30000,
        signal: writeController.signal,
      });
      if (disposed || lifetimeAtStart !== lifetime) return;
      batch.value = data;
      const existing = new Set(credentials.value.map((row) => row.row_id));
      credentials.value.push(
        ...(data.credentials || []).filter((row) => !existing.has(row.row_id)),
      );
      if (data.active_chunk) {
        uncertain.value = true;
        running.value = false;
      }
      if (data.chunk_status === 'interrupted') {
        running.value = false;
        error.value = '当前段已暂停。请核对已创建结果，再明确继续未处理成员。';
      }
      if (!data.next_chunk_token || !data.summary.remaining) break;
      if (running.value) body = nextRequest();
    }
    if (!disposed && lifetimeAtStart === lifetime) await refresh();
  } catch (e) {
    if (!disposed && lifetimeAtStart === lifetime) {
      running.value = false;
      uncertain.value = true;
      error.value = '本次请求结果尚未确认，请先查询进度；已创建账号不会重复创建，也不会重放密码。';
      try {
        await refresh();
      } catch (queryError) {
        showError(queryError);
      }
      if (e.status && e.status < 500) showError(e);
    }
  } finally {
    if (lifetimeAtStart === lifetime) {
      running.value = false;
      busy.value = false;
      schedule();
    }
  }
}
async function cancelBatch() {
  if (busy.value || !batch.value || !confirm('停止此批次后续创建？已成功创建的账号会保留。'))
    return;
  busy.value = true;
  error.value = '';
  try {
    await request(`${prefix}/${encodeURIComponent(batch.value.id)}/cancel`, {
      method: 'POST',
      body: {},
    });
    await refresh();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function download(kind) {
  error.value = '';
  try {
    const path =
      kind === 'template'
        ? `${prefix}/template`
        : `${prefix}/${encodeURIComponent(batch.value.id)}/report`;
    const blob = await request(path, { responseType: 'blob', timeoutMs: 30000 }, 'download');
    if (disposed) return;
    const url = URL.createObjectURL(blob),
      link = document.createElement('a');
    link.href = url;
    link.download = kind === 'template' ? 'account-import-v1.xlsx' : 'account-import-results.xlsx';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    showError(e);
  }
}
function leave(to) {
  if (
    recoveryTarget &&
    to?.query?.import_id === recoveryTarget &&
    to.query.tab === 'import' &&
    (to.query.section || 'accounts') === 'accounts'
  )
    return true;
  return (
    !dirty.value ||
    confirm(
      '离开后，本页已领取的初始密码会清除，无法再次查询。请先复制或下载；当前段可能已创建账号，返回后需查询结果。继续离开？',
    )
  );
}
function unload(event) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
function clearSecrets() {
  running.value = false;
  credentials.value = [];
  writeController?.abort();
  clearTimeout(pollTimer);
}
useLeaveGuard(leave);
watch(
  () => route.query.import_id,
  async (id) => {
    if (!capabilities.value || id === batch.value?.id) return;
    if (id && (typeof id !== 'string' || !/^[A-Za-z0-9_-]{24,64}$/.test(id))) {
      error.value = '批次地址无效，已返回上传步骤。';
      await params({ import_id: null }, true);
      return;
    }
    ++lifetime;
    ++generation;
    clearSecrets();
    busy.value = false;
    loading.value = false;
    uncertain.value = false;
    credentials.value = [];
    selected.value = new Set();
    batch.value = null;
    rows.value = [];
    if (id) refresh(id).catch(showError);
  },
);
watch(
  () => [auth.qq_id, auth.role, auth.csrf_token, auth.account_epoch],
  () => {
    ++generation;
    ++lifetime;
    clearSecrets();
    rows.value = [];
    batch.value = null;
  },
);
onMounted(async () => {
  window.addEventListener('beforeunload', unload);
  window.addEventListener('pagehide', clearSecrets);
  try {
    capabilities.value = await request(`${prefix}/capabilities`);
    const id = route.query.import_id;
    if (id && typeof id === 'string' && /^[A-Za-z0-9_-]{24,64}$/.test(id)) await refresh(id);
    else if (id) {
      error.value = '批次地址无效，已返回上传步骤。';
      await params({ import_id: null }, true);
    }
  } catch (e) {
    showError(e);
  }
});
onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  clearSecrets();
  window.removeEventListener('beforeunload', unload);
  window.removeEventListener('pagehide', clearSecrets);
});
</script>
<template>
  <section class="account-import" aria-labelledby="account-import-title">
    <div class="admin-section-heading">
      <div>
        <h2 id="account-import-title">Excel 批量开户</h2>
        <p>先核对每一行，再分段创建普通成员账号。</p>
      </div>
      <span class="admin-limit">{{ capabilities?.max_rows || 200 }} 人 / 文件</span>
    </div>
    <ol class="import-steps" aria-label="导入步骤">
      <li :aria-current="!batch ? 'step' : undefined">01 下载并填写模板</li>
      <li :aria-current="batch?.status === 'preview_ready' ? 'step' : undefined">02 上传与预检</li>
      <li :aria-current="batch && batch.status !== 'preview_ready' ? 'step' : undefined">
        03 确认创建与领取
      </li>
    </ol>
    <p v-if="error" role="alert" class="import-error">{{ error }}</p>
    <p v-if="!capabilities && !error" role="status">正在读取导入配置…</p>
    <p v-if="capabilities && !capabilities.enabled" role="status">
      Excel 导入尚未启用。已有批次仍可查询结果，启用后才能上传或继续创建。
    </p>
    <form v-if="capabilities?.enabled" class="admin-panel import-upload" @submit.prevent="upload">
      <div>
        <h3>使用标准模板</h3>
        <p>QQ 必填，支持五个平台账号标识。已有成员只补开户，保留原资料和绑定。</p>
        <button type="button" class="btn" :disabled="busy" @click="download('template')">
          下载 Excel 模板
        </button>
      </div>
      <div>
        <label for="import-file">选择 .xlsx 文件</label
        ><input
          id="import-file"
          ref="input"
          type="file"
          accept=".xlsx"
          :disabled="busy"
          @change="chooseFile"
        />
        <p class="muted">
          最多 5 MiB / {{ capabilities.max_rows }} 行，不要填写 OJ 密码、公式或外部链接。
        </p>
        <p v-if="file">待上传：{{ file.name }}</p>
        <button class="btn primary" :disabled="busy || !file">
          {{ busy && !batch ? '正在安全解析…' : '上传并校验' }}
        </button>
      </div>
    </form>
    <template v-if="batch">
      <div class="import-status" role="status">
        <strong>{{ statusText }}</strong
        ><span>有效至 {{ date(batch.expires_at) }}</span
        ><span
          >共 {{ batch.summary.total }} 行 · 成功 {{ batch.summary.created }} · 冲突
          {{ batch.summary.conflict }} · 错误 {{ batch.summary.invalid }} · 跳过
          {{ batch.summary.skipped }}</span
        >
      </div>
      <p v-if="batch.read_only" class="muted">当前仅可查看此批次的无密码结果。</p>
      <p v-if="batch.payload_purged" class="muted">资料副本与报告已到期，仅保留最小开户台账。</p>
      <ImportPreviewTable
        :rows="rows"
        :selected="selected"
        :locked="busy || batch.status !== 'preview_ready' || batch.read_only"
        @select="selectRows"
      />
      <div
        v-if="batch.status === 'preview_ready' && !batch.read_only"
        class="admin-panel import-confirm"
      >
        <p>
          已明确选择 {{ chosen.length }} 人：新建
          {{ chosen.filter((r) => r.action === 'create_member_and_account').length }} 人，补开户
          {{ chosen.filter((r) => r.action === 'create_web_account_only').length }} 人。
        </p>
        <details v-if="chosen.length">
          <summary>查看完整所选名单（包括其他页）</summary>
          <ul>
            <li v-for="row in chosen" :key="row.row_id">
              {{ row.name }}（{{ row.qq_id }}）{{
                row.ignored_fields.length ? '；忽略：' + row.ignored_fields.join('、') : ''
              }}
            </li>
          </ul>
        </details>
        <label class="import-check"
          ><input v-model="acknowledge" type="checkbox" :disabled="busy" />我已核对将录入的 OJ
          账号与成员对应关系，理解这不代表本人归属核验。</label
        >
        <p class="muted">
          初始密码逐人随机生成，有效
          {{ batch.temporary_password_ttl_hours }}
          小时；首次登录必须修改。只在创建响应中领取，离开后无法查询明文。
        </p>
        <button
          class="btn primary"
          :disabled="
            busy ||
            loading ||
            uncertain ||
            !chosen.length ||
            !capabilities?.enabled ||
            (chosen.some((r) => Object.keys(r.bindings || {}).length) && !acknowledge)
          "
          @click="execute"
        >
          确认创建所选账号
        </button>
      </div>
      <div class="import-actions">
        <button v-if="busy && running" class="btn" @click="running = false">暂停后续创建</button
        ><button
          v-if="canContinue"
          class="btn primary"
          :disabled="busy || uncertain || loading"
          @click="execute"
        >
          继续未处理成员</button
        ><button class="btn" :disabled="busy || loading" @click="refresh().catch(showError)">
          {{ loading ? '正在查询…' : '查询进度' }}</button
        ><button class="btn" :disabled="busy || batch.payload_purged" @click="download('report')">
          下载无密码报告</button
        ><button
          v-if="
            ['preview_ready', 'paused', 'committing'].includes(batch.status) && !batch.read_only
          "
          class="btn"
          :disabled="busy"
          @click="cancelBatch"
        >
          停止此批次
        </button>
      </div>
      <p v-if="uncertain" role="status">
        当前段结果待确认。正在查询服务端进度，请勿重新上传或重复创建。
      </p>
      <ImportResults :credentials="credentials" :missing="missingCredentials" />
    </template>
  </section>
</template>
<style scoped>
.account-import {
  min-width: 0;
}
.import-steps {
  display: flex;
  gap: 12px;
  list-style: none;
  padding: 0;
  margin: 18px 0;
  flex-wrap: wrap;
}
.import-steps li {
  background: var(--panel);
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 0.88rem;
}
.import-steps li[aria-current] {
  border-bottom: 3px solid var(--accent, #42715a);
  font-weight: 700;
}
.import-upload {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
}
.import-upload h3 {
  margin-top: 0;
}
.import-upload input {
  max-width: 100%;
  display: block;
  margin-top: 10px;
}
.import-status {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px 0;
}
.import-confirm {
  margin-top: 16px;
}
.import-check {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 16px;
}
.import-check input {
  width: auto;
}
.import-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 18px 0;
}
.import-error {
  border-left: 3px solid #bd5b4a;
  padding: 12px;
  background: var(--panel);
  overflow-wrap: anywhere;
}
@media (max-width: 650px) {
  .import-upload {
    grid-template-columns: 1fr;
    gap: 20px;
  }
  .import-steps {
    gap: 6px;
  }
  .import-steps li {
    padding: 8px;
  }
}
</style>
