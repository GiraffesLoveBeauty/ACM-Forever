<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { api, useRequests, showError, notify, date, external } from '../lib/api.js';
import { cfMemory, adminSessionVersion, useParams } from '../lib/admin.js';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  update = useParams(),
  request = useRequests();
const sessionVersion = adminSessionVersion();
const sameSession = () => sessionVersion === adminSessionVersion();
const options = ref([]),
  statuses = ref([...cfMemory.statuses]),
  excluded = ref([...cfMemory.excluded]),
  scope = ref(null),
  recent = ref(null),
  result = ref(null),
  selected = ref([]),
  job = ref(null),
  evidence = ref(null),
  dialog = ref(),
  copyFallback = ref(''),
  message = ref('');
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
const filters = reactive({
  days: 7,
  date_from: today(),
  date_to: today(),
  rating_min: '',
  rating_max: '',
  tag: '',
  view: 'problems',
  search: '',
  page: 1,
});
const candidate = reactive({
  input: cfMemory.input,
  contest: cfMemory.contest,
  kind: cfMemory.kind,
  mode: cfMemory.mode,
});
const tab = computed(() => (route.query.tab === 'check' ? 'check' : 'recent'));
const overviewBusy = ref(false),
  checkBusy = ref(false),
  syncBusy = ref(Boolean(cfMemory.submission)),
  copyBusy = ref(false);
const busy = computed(
  () => overviewBusy.value || checkBusy.value || syncBusy.value || copyBusy.value,
);
const terminals = new Set(['completed', 'partial', 'failed', 'interrupted']);
const decisions = {
  eligible: '可用',
  excluded_ac: '有人 AC，排除',
  excluded_attempted: '有人提交，排除',
  unknown: '未知，待处理',
  invalid: '输入无效 / 题目不存在',
};
let alive = true,
  overviewVersion = 0,
  checkVersion = 0,
  detailVersion = 0,
  syncVersion = 0,
  initializing = true;
const waits = new Map();
function canceled() {
  return new DOMException('请求已取消', 'AbortError');
}
function pause() {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      waits.delete(timer);
      resolve();
    }, 2500);
    waits.set(timer, reject);
  });
}
function scopeSpec() {
  return { statuses: [...statuses.value], exclude_qq_ids: [...excluded.value] };
}
function invalidate(text = '范围或输入已改变，请重新查重。') {
  checkVersion++;
  result.value = null;
  selected.value = [];
  copyFallback.value = '';
  checkBusy.value = copyBusy.value = false;
  if (sameSession()) cfMemory.recheck = false;
  message.value = text;
}
function recentPayload() {
  const body = {
    view: filters.view,
    page: filters.page,
    page_size: 20,
    tag: filters.tag,
    search: filters.search,
  };
  if (filters.days === 'custom') {
    if (!filters.date_from || !filters.date_to) throw Error('请选择完整日期范围。');
    body.date_from = filters.date_from + 'T00:00:00+08:00';
    body.date_to = filters.date_to + 'T23:59:59+08:00';
  } else body.days = Number(filters.days);
  if (filters.rating_min !== '') body.rating_min = filters.rating_min;
  if (filters.rating_max !== '') body.rating_max = filters.rating_max;
  return body;
}
async function loadOptions() {
  const data = await request('/admin/cf/options');
  options.value = data.statuses;
  const values = new Set(data.statuses.map((row) => row.value));
  statuses.value = statuses.value.filter((value) => values.has(value));
  if (!statuses.value.length && data.statuses.length)
    statuses.value = [values.has('现役') ? '现役' : data.statuses[0].value];
}
async function handleError(error) {
  if (error.name === 'AbortError') return;
  if (error.code === 'scope_changed') {
    invalidate('成员范围或 CF 绑定已变化，请重新核对排除名单。');
    scope.value = null;
    excluded.value = [];
    try {
      initializing = true;
      await loadOptions();
    } catch (e) {
      showError(e);
    } finally {
      initializing = false;
    }
    await overview(true);
  }
  message.value = error.message;
}
async function overview(reset = false) {
  if (reset) filters.page = 1;
  const version = ++overviewVersion;
  overviewBusy.value = true;
  try {
    if (!statuses.value.length) {
      scope.value = null;
      recent.value = null;
      return;
    }
    const data = await request(
      '/admin/cf/overview',
      { method: 'POST', body: { scope: scopeSpec(), ...recentPayload() } },
      'overview',
    );
    if (version !== overviewVersion) return;
    if (scope.value && scope.value.fingerprint !== data.scope.fingerprint) invalidate();
    scope.value = data.scope;
    recent.value = data;
  } catch (e) {
    if (version === overviewVersion) await handleError(e);
  } finally {
    if (version === overviewVersion) overviewBusy.value = false;
  }
}
function payload() {
  if (!scope.value?.member_count) throw Error('请选择至少一名参与成员。');
  return {
    scope: scopeSpec(),
    expected_scope_fingerprint: scope.value.fingerprint,
    mode: candidate.mode,
    ...(candidate.kind === 'contest'
      ? { contest_id: candidate.contest }
      : {
          candidates: candidate.input
            .split(/[\n,;，；]+/)
            .map((s) => s.trim())
            .filter(Boolean),
        }),
  };
}
function selectable(row) {
  return (
    row.eligible &&
    row.decision === 'eligible' &&
    result.value?.scope.fingerprint === scope.value?.fingerprint &&
    !scope.value?.unknown_member_count &&
    scope.value?.member_count > 0
  );
}
async function poll(id, current, kind) {
  if (!sameSession()) throw canceled();
  cfMemory.job = { id, kind };
  while (alive && current() && sameSession()) {
    const value = await request('/admin/cf/jobs/' + encodeURIComponent(id), {}, kind + '-job');
    if (!current() || !sameSession()) throw canceled();
    job.value = value;
    if (terminals.has(value.status)) {
      if (cfMemory.job?.id === id) cfMemory.job = null;
      return value;
    }
    await pause();
  }
  throw canceled();
}
async function checked(body, current) {
  let data = await request('/admin/cf/check', { method: 'POST', body }, 'check');
  if (!current()) throw canceled();
  if (data.status === 'queued') {
    const value = await poll(data.job_id, current, 'check');
    if (!value.result)
      throw Object.assign(Error(value.message || '题目核实未完成'), { code: value.error_code });
    data = value.result;
  }
  return data;
}
async function check() {
  if (busy.value || !scope.value?.member_count) return;
  const version = ++checkVersion;
  checkBusy.value = true;
  result.value = null;
  selected.value = [];
  message.value = '正在使用全部历史查重…';
  try {
    const data = await checked(payload(), () => alive && version === checkVersion);
    if (data.scope.fingerprint !== scope.value?.fingerprint)
      throw Object.assign(Error('成员范围已变化'), { code: 'scope_changed' });
    result.value = data;
    scope.value = data.scope;
    cfMemory.recheck = true;
    message.value = '查重完成。仅“可用”题目允许勾选。';
  } catch (e) {
    if (version === checkVersion) await handleError(e);
  } finally {
    if (version === checkVersion) checkBusy.value = false;
  }
}
function submitSync(body) {
  const operation = { id: null, error: null, ready: null };
  cfMemory.submission = operation;
  operation.ready = api('/admin/cf/sync', { method: 'POST', timeoutMs: 30000, body })
    .then((data) => {
      if (!sameSession() || cfMemory.submission !== operation) return;
      operation.id = data.job_id;
      cfMemory.job = { id: data.job_id, kind: 'sync' };
    })
    .catch((error) => {
      operation.error = error;
    });
  return operation;
}
async function followSync(operation) {
  const version = ++syncVersion;
  const current = () => alive && sameSession() && version === syncVersion;
  syncBusy.value = true;
  message.value = '正在确认同步提交…';
  try {
    await operation.ready;
    if (!current()) throw canceled();
    if (operation.error) {
      if (cfMemory.submission === operation) cfMemory.submission = null;
      throw operation.error;
    }
    const value = await poll(operation.id, current, 'sync');
    if (cfMemory.submission === operation) cfMemory.submission = null;
    await overview();
    if (!current()) throw canceled();
    message.value =
      value.status === 'completed' ? 'CF 历史刷新完成。' : '刷新结束，请查看待处理项。';
    const recheck = cfMemory.recheck;
    syncBusy.value = false;
    if (recheck && scope.value?.member_count) await check();
  } catch (e) {
    if (current()) await handleError(e);
  } finally {
    if (current()) syncBusy.value = false;
  }
}
async function sync() {
  if (!sameSession() || busy.value || cfMemory.submission || !scope.value?.member_count) return;
  const recheck = Boolean(result.value);
  const body = { scope: scopeSpec(), expected_scope_fingerprint: scope.value.fingerprint };
  invalidate('数据更新中，旧查重结果已失效。');
  cfMemory.recheck = recheck;
  await followSync(submitSync(body));
}
async function copy(kind) {
  if (busy.value || !result.value || !selected.value.length) return;
  const rows = result.value.rows.filter(
    (row) => selected.value.includes(row.display_id) && selectable(row),
  );
  if (!rows.length) return;
  const version = checkVersion;
  copyBusy.value = true;
  try {
    const data = await checked(
      {
        scope: scopeSpec(),
        expected_scope_fingerprint: scope.value.fingerprint,
        mode: result.value.mode,
        candidates: rows.map((row) => row.display_id),
      },
      () => alive && version === checkVersion,
    );
    if (
      data.scope.fingerprint !== scope.value?.fingerprint ||
      data.scope.unknown_member_count ||
      data.rows.length !== rows.length ||
      data.rows.some((row) => !row.eligible || row.decision !== 'eligible')
    ) {
      invalidate('所选题目的数据或结论已变化，请重新查重。');
      return;
    }
    const text = rows.map((row) => (kind === 'links' ? row.url : row.display_id)).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      notify(`已复制 ${rows.length} 道题`);
    } catch {
      copyFallback.value = text;
      notify('自动复制失败，可从下方手动复制');
    }
  } catch (e) {
    if (version === checkVersion) await handleError(e);
  } finally {
    if (version === checkVersion) copyBusy.value = false;
  }
}
async function showEvidence(problem_id, period, page = 1) {
  const version = ++detailVersion;
  evidence.value = { problem_id, period, page, rows: [], total: 0, loading: true };
  if (!dialog.value.open) dialog.value.showModal();
  try {
    const data = await request(
      '/admin/cf/problem-members',
      {
        method: 'POST',
        body: {
          ...(period === 'recent' ? recentPayload() : {}),
          scope: scopeSpec(),
          expected_scope_fingerprint: scope.value.fingerprint,
          problem_id,
          period,
          page,
          page_size: 20,
        },
      },
      'evidence',
    );
    if (version !== detailVersion) return;
    evidence.value = { ...evidence.value, ...data, loading: false };
  } catch (e) {
    if (version === detailVersion) {
      evidence.value.loading = false;
      await handleError(e);
    }
  }
}
function toggleExcluded(qq, include) {
  excluded.value = include
    ? excluded.value.filter((value) => value !== qq)
    : [...excluded.value, qq];
}
async function scopeChanged() {
  if (initializing) return;
  syncVersion++;
  syncBusy.value = false;
  scope.value = null;
  invalidate();
  detailVersion++;
  job.value = null;
  dialog.value?.close();
  await overview(true);
  if (alive && cfMemory.submission) await followSync(cfMemory.submission);
}
watch(
  [() => JSON.stringify(statuses.value), () => JSON.stringify(excluded.value)],
  (values, previous) => {
    if (!initializing && values[0] !== previous[0] && excluded.value.length) {
      excluded.value = [];
      return;
    }
    scopeChanged();
  },
);
async function refreshScope() {
  try {
    initializing = true;
    await loadOptions();
    initializing = false;
    await overview(true);
    if (alive && cfMemory.submission) await followSync(cfMemory.submission);
  } catch (error) {
    await handleError(error);
  } finally {
    initializing = false;
  }
}
watch(
  candidate,
  () => {
    if (!initializing) invalidate('候选输入已改变，请重新查重。');
  },
  { deep: true, flush: 'sync' },
);
onMounted(async () => {
  try {
    await loadOptions();
    await overview(true);
    initializing = false;
    if (cfMemory.submission) await followSync(cfMemory.submission);
    else if (cfMemory.job) {
      const saved = cfMemory.job;
      const version = ++checkVersion;
      const value = await poll(saved.id, () => alive && version === checkVersion, saved.kind);
      await overview();
      if ((value.kind === 'check' && value.result) || cfMemory.recheck) await check();
    } else if (cfMemory.recheck && scope.value?.member_count) await check();
  } catch (e) {
    await handleError(e);
  } finally {
    initializing = false;
  }
});
onBeforeUnmount(() => {
  alive = false;
  overviewVersion++;
  checkVersion++;
  syncVersion++;
  detailVersion++;
  for (const [timer, reject] of waits) {
    clearTimeout(timer);
    reject(canceled());
  }
  waits.clear();
  if (sameSession())
    Object.assign(cfMemory, {
      statuses: [...statuses.value],
      excluded: [...excluded.value],
      input: candidate.input,
      contest: candidate.contest,
      kind: candidate.kind,
      mode: candidate.mode,
    });
  dialog.value?.close();
});
</script>
<template>
  <div class="cf-intro">
    <div>
      <span class="cf-eyebrow">CODEFORCES · PRACTICE</span>
      <h2>先了解进度，再确认候选。</h2>
      <p>近期 AC 帮助了解成员进度；候选题使用全部历史查重。</p>
    </div>
    <span class="cf-intro-mark">{ AC }</span>
  </div>
  <p class="cf-message" role="status">{{ message }}</p>
  <section class="card cf-scope">
    <div class="cf-section-heading">
      <div>
        <h2>参与成员</h2>
        <p class="muted">按实际身份选择成员，并排除本次不参赛的人。</p>
      </div>
      <div class="cf-actions">
        <button class="btn" :disabled="busy" @click="refreshScope">刷新概况</button
        ><button
          class="btn primary"
          :disabled="busy || !scope?.member_count || Boolean(cfMemory.submission)"
          @click="sync"
        >
          补齐 / 刷新数据
        </button>
      </div>
    </div>
    <fieldset class="cf-fieldset">
      <legend>成员身份</legend>
      <div class="cf-status-options">
        <label v-for="row in options" :key="row.value" class="cf-status-option"
          ><input v-model="statuses" type="checkbox" :value="row.value" /><span
            >{{ row.label }} · {{ row.member_count }} 人</span
          ></label
        >
      </div>
    </fieldset>
    <template v-if="scope"
      ><div class="cf-metrics">
        <div
          v-for="(label, key) in {
            member_count: '参与成员',
            bound_member_count: 'CF 已绑定',
            ready_member_count: '数据就绪',
            unknown_member_count: '待处理成员',
          }"
          :key="key"
          class="cf-metric"
        >
          <strong>{{ scope[key] }}</strong
          ><span>{{ label }}</span>
        </div>
      </div>
      <p class="muted cf-coverage">
        数据共同覆盖截至：{{ date(scope.coverage_as_of) }}（北京时间）。
      </p>
      <details class="cf-members">
        <summary>查看参与成员与待处理项 · 已排除 {{ scope.exclude_qq_ids.length }} 人</summary>
        <div class="cf-member-list">
          <label v-for="member in scope.members" :key="member.qq_id" class="cf-member-row"
            ><input
              type="checkbox"
              :checked="!member.excluded"
              :aria-label="`${member.name} 参加本次练习赛`"
              @change="toggleExcluded(member.qq_id, $event.target.checked)"
            /><span
              ><b>{{ member.name }} · {{ member.cf_handle || '未绑定 CF' }}</b
              ><small>{{ member.reason_label }} {{ member.error_message }}</small
              ><small>最近成功：{{ date(member.last_success_at) }}</small></span
            ></label
          >
        </div>
      </details></template
    >
  </section>
  <section v-if="job || syncBusy" class="card cf-job">
    <h2>后台任务</h2>
    <p role="status">{{ job?.status || '正在确认同步提交…' }} · {{ job?.message }}</p>
    <progress
      v-if="job"
      :max="Math.max(1, job.members?.length || 1)"
      :value="
        job.members?.filter((m) => terminals.has(m.status)).length ||
        (terminals.has(job.status) ? 1 : 0)
      "
      aria-label="同步进度"
    ></progress>
    <div class="cf-job-members">
      <div v-for="member in job?.members || []" :key="member.qq_id">
        <b>{{ member.handle || member.qq_id }}</b> · {{ member.status }} {{ member.error_message }}
      </div>
    </div>
  </section>
  <div class="cf-tabs" role="tablist" aria-label="选题工具">
    <button
      v-for="(label, key) in { recent: '近期刷题', check: '候选题查重' }"
      :key="key"
      role="tab"
      :aria-selected="tab === key"
      :aria-controls="`panel-${key}`"
      @click="update({ tab: key })"
    >
      {{ label }}
    </button>
  </div>
  <section v-show="tab === 'recent'" id="panel-recent" class="card" role="tabpanel">
    <form class="cf-recent-filters" @submit.prevent="overview(true)">
      <label
        >时间范围<select v-model="filters.days">
          <option :value="7">近 7 天</option>
          <option :value="30">近 30 天</option>
          <option value="custom">自定义日期</option>
        </select></label
      >
      <div v-if="filters.days === 'custom'" class="cf-custom-dates">
        <label>起始日期<input v-model="filters.date_from" type="date" /></label
        ><label>结束日期<input v-model="filters.date_to" type="date" /></label>
      </div>
      <label
        >最低 Rating<input
          v-model="filters.rating_min"
          type="number"
          min="0"
          max="5000"
          step="100"
          placeholder="不限" /></label
      ><label
        >最高 Rating<input
          v-model="filters.rating_max"
          type="number"
          min="0"
          max="5000"
          step="100"
          placeholder="不限" /></label
      ><label
        >标签<select v-model="filters.tag">
          <option value="">全部标签</option>
          <option v-for="tag in recent?.available_tags || []" :key="tag">{{ tag }}</option>
        </select></label
      ><label
        >展示方式<select v-model="filters.view">
          <option value="problems">按题目汇总</option>
          <option value="members">按成员展开</option>
        </select></label
      ><label class="cf-search"
        >搜索<input v-model.trim="filters.search" maxlength="200" placeholder="题号或题名" /></label
      ><button class="btn primary" :disabled="overviewBusy">查询</button>
    </form>
    <div class="cf-result-heading">
      <h2>近期 AC</h2>
      <span class="muted"
        >共 {{ recent?.total || 0 }} 条 ·
        {{ scope?.unknown_member_count ? '统计可能不完整' : '成员数据就绪' }}</span
      >
    </div>
    <ul v-if="recent?.view === 'members'" class="cf-member-results">
      <li v-for="member in recent.rows" :key="member.qq_id">
        <details>
          <summary>
            <b>{{ member.name }}</b> · {{ member.cf_handle }} · 近期 AC
            {{ member.recent_ac_count }} 题
          </summary>
          <div class="cf-member-problems">
            <div v-for="problem in member.problems" :key="problem.display_id">
              <span
                ><a :href="external(problem.url)" target="_blank" rel="noopener"
                  >{{ problem.display_id }} · {{ problem.name }}</a
                >
                · Rating {{ problem.rating ?? '未知' }}<br />{{ date(problem.ac_at) }}</span
              ><span
                ><a
                  v-if="problem.submission_url"
                  :href="external(problem.submission_url)"
                  target="_blank"
                  rel="noopener"
                  >AC 提交 ↗</a
                ><button class="btn" @click="showEvidence(problem.display_id, 'history')">
                  历史证据
                </button></span
              >
            </div>
          </div>
        </details>
      </li>
    </ul>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>题号 / 题名</th>
            <th>Rating / 标签</th>
            <th>近期 AC 人</th>
            <th>历史 AC 人</th>
            <th>最近 AC</th>
            <th>证据</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in recent?.rows || []" :key="row.display_id">
            <td>
              <a :href="external(row.url)" target="_blank" rel="noopener"
                ><b>{{ row.display_id }}</b> · {{ row.name }} ↗</a
              >
            </td>
            <td>
              {{ row.rating ?? '未知' }}<small>{{ row.tags.join(' · ') }}</small>
            </td>
            <td>{{ row.recent_ac_count }} 人</td>
            <td>{{ row.history_ac_count }} 人</td>
            <td>{{ date(row.last_ac_at) }}</td>
            <td>
              <button class="btn" @click="showEvidence(row.display_id, 'recent')">近期成员</button
              ><button class="btn" @click="showEvidence(row.display_id, 'history')">
                历史证据
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!recent?.rows.length" class="empty">当前范围和筛选下暂无近期 AC。</p>
    </div>
    <Pager
      :page="Number(recent?.page || 1)"
      :total="recent?.total || 0"
      :busy="overviewBusy"
      @change="
        (page) => {
          filters.page = page;
          overview();
        }
      "
    />
    <p class="muted cf-footnote">同一成员同一道题只计一次。历史 AC 人数不受近期日期筛选影响。</p>
  </section>
  <section v-show="tab === 'check'" id="panel-check" class="card" role="tabpanel">
    <form @submit.prevent="check">
      <div class="cf-check-controls">
        <label
          >输入方式<select v-model="candidate.kind">
            <option value="problems">批量题号 / CF 链接</option>
            <option value="contest">整场比赛</option>
          </select></label
        ><label
          >查重口径<select v-model="candidate.mode">
            <option value="any_submission">排除所有提交过的题</option>
            <option value="ac_only">仅排除已 AC 的题</option>
          </select></label
        >
      </div>
      <label v-if="candidate.kind === 'problems'" class="cf-input-label"
        >候选题<textarea
          v-model="candidate.input"
          rows="5"
          maxlength="102400"
          placeholder="1843A&#10;https://codeforces.com/contest/1843/problem/B"
        ></textarea></label
      ><label v-else class="cf-input-label"
        >CF 比赛 ID<input v-model="candidate.contest" type="number" min="1" max="9999999"
      /></label>
      <div class="cf-check-submit">
        <p class="muted">每行一个题号或链接，最多 100 条；也可用逗号分隔。查重使用全部历史。</p>
        <button class="btn primary" :disabled="busy || !scope?.member_count">开始查重</button>
      </div>
    </form>
    <div class="cf-result-heading">
      <h2>查重结果</h2>
      <span v-if="result"
        >共 {{ result.total }} 题 · 可用 {{ result.counts.eligible }} · 未知
        {{ result.counts.unknown }}</span
      >
    </div>
    <p v-if="result" class="muted">
      全部历史 · 数据覆盖截至 {{ date(result.coverage_as_of) }} · 查重时间
      {{ date(result.checked_at) }}
    </p>
    <div class="table-wrap">
      <table v-if="result">
        <thead>
          <tr>
            <th>选择</th>
            <th>题号 / 题名</th>
            <th>Rating</th>
            <th>AC 人数</th>
            <th>提交人数</th>
            <th>判定 / 原因</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in result.rows" :key="row.display_id">
            <td>
              <input
                v-model="selected"
                type="checkbox"
                :value="row.display_id"
                :disabled="busy || !selectable(row)"
                :aria-label="`选择 ${row.display_id}`"
              />
            </td>
            <td>
              <a v-if="row.url" :href="external(row.url)" target="_blank" rel="noopener"
                ><b>{{ row.display_id }}</b> ↗</a
              ><b v-else>{{ row.display_id }}</b
              ><small>{{ row.name }}</small>
            </td>
            <td>{{ row.rating ?? '未知' }}</td>
            <td>{{ row.ac_count }}</td>
            <td>{{ row.attempt_count }}</td>
            <td>
              <span class="cf-state" :class="`cf-state-${row.decision}`">{{
                decisions[row.decision]
              }}</span
              ><small>{{ row.reason }}</small>
            </td>
            <td>
              <button v-if="row.url" class="btn" @click="showEvidence(row.display_id, 'history')">
                涉及成员
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty">输入候选题后开始查重。</p>
    </div>
    <div class="cf-copy-bar">
      <span>已选 {{ selected.length }} 题</span>
      <div class="cf-actions">
        <button class="btn" :disabled="busy || !selected.length" @click="copy('ids')">
          复制题号</button
        ><button class="btn primary" :disabled="busy || !selected.length" @click="copy('links')">
          复制 CF 链接
        </button>
      </div>
    </div>
    <label v-if="copyFallback" class="cf-input-label"
      >复制内容<textarea :value="copyFallback" rows="4" readonly></textarea>
    </label>
    <p class="muted cf-footnote">
      结论仅截至数据覆盖时间，无法识别只看过题但未提交的情况。候选清单不会创建练习赛。
    </p>
  </section>
  <dialog
    ref="dialog"
    class="cf-dialog"
    aria-labelledby="evidence-heading"
    @close="detailVersion++"
  >
    <div class="cf-section-heading">
      <h2 id="evidence-heading">{{ evidence?.problem_id }} · 成员证据</h2>
      <button class="btn" @click="dialog.close()">关闭</button>
    </div>
    <p>
      {{
        evidence?.period === 'recent'
          ? '当前日期范围内的 AC'
          : '全部历史提交与 AC，不受近期筛选影响'
      }}（北京时间）
    </p>
    <p v-if="evidence?.loading">正在查询证据…</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>成员 / CF handle</th>
            <th>证据</th>
            <th>最近 AC</th>
            <th>最近提交</th>
            <th>提交链接</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in evidence?.rows || []" :key="row.qq_id">
            <td>{{ row.name }}<br />{{ row.cf_handle }}</td>
            <td>{{ row.has_ac ? '有 AC 证据' : '仅有提交证据' }}</td>
            <td>{{ date(row.ac_at) }}</td>
            <td>{{ date(row.last_attempt_at) }}</td>
            <td>
              <a
                v-if="row.ac_submission_url"
                :href="external(row.ac_submission_url)"
                target="_blank"
                rel="noopener"
                >AC 提交 ↗</a
              ><br /><a
                v-if="row.attempt_submission_url"
                :href="external(row.attempt_submission_url)"
                target="_blank"
                rel="noopener"
                >最近提交 ↗</a
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Pager
      :page="Number(evidence?.page || 1)"
      :total="evidence?.total || 0"
      :busy="evidence?.loading"
      @change="(page) => showEvidence(evidence.problem_id, evidence.period, page)"
    />
  </dialog>
</template>
