<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { date, useRequests } from '../lib/api.js';
import { useLeaveGuard } from '../lib/admin.js';
import {
  filterProblems,
  filterTaxonomy,
  reviewLabels,
  sourceLabels,
  tagDiff,
} from '../lib/tag-management.js';

const props = defineProps({ embedded: Boolean, platform: String, problemId: String });
const emit = defineEmits(['saved', 'close']);

const request = useRequests(),
  route = useRoute(),
  router = useRouter();
const rows = ref([]),
  taxonomy = ref([]),
  selected = ref(null),
  detail = ref(null);
const loading = ref(true),
  opening = ref(false),
  saving = ref(false),
  error = ref(''),
  notice = ref('');
const query = ref(''),
  status = ref('all'),
  tagQuery = ref(''),
  kind = ref('specific');
const chosen = ref([]),
  reason = ref(''),
  confirmation = ref(''),
  historyOpen = ref(false),
  conflict = ref(false);
const pendingRequest = ref(null),
  searchInput = ref(null);
const filtered = computed(() => filterProblems(rows.value, query.value, status.value));
const available = computed(() => filterTaxonomy(taxonomy.value, tagQuery.value, kind.value));
const byId = computed(() => Object.fromEntries(taxonomy.value.map((t) => [t.id, t])));
const currentIds = computed(() => detail.value?.effective_tags.map((t) => t.id) || []);
const diff = computed(() => tagDiff(currentIds.value, chosen.value));
const dirty = computed(() => !!(diff.value.added.length || diff.value.removed.length));
const correctedCount = computed(
  () => rows.value.filter((p) => p.review_status === 'corrected').length,
);
const reviewedCount = computed(
  () => rows.value.filter((p) => p.review_status === 'verified').length,
);
const needsReviewCount = computed(
  () => rows.value.filter((p) => p.review_status === 'needs_review').length,
);
const canSave = computed(
  () => dirty.value && reason.value.trim().length >= 2 && !saving.value && !conflict.value,
);
const name = (id) => byId.value[id]?.name_zh || id;
const endpoint = (p) =>
  `/secondary/tag-management/${encodeURIComponent(p.platform)}/${encodeURIComponent(p.problem_id)}`;
let generation = 0;
function discardAllowed() {
  return !dirty.value || window.confirm('当前标签草稿尚未保存。确定放弃草稿并离开吗？');
}
function beforeUnload(e) {
  if (dirty.value || saving.value) {
    e.preventDefault();
    e.returnValue = '';
  }
}
onBeforeRouteLeave(() => !saving.value && discardAllowed());
useLeaveGuard(() => !saving.value && discardAllowed());
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload);
  try {
    const data = await request('/secondary/tag-management');
    rows.value = data.items;
    taxonomy.value = data.taxonomy;
    const first =
      rows.value.find(
        (p) =>
          p.problem_id === (props.problemId || route.query.problem_id) &&
          p.platform === (props.platform || route.query.platform),
      ) || (!props.embedded ? rows.value[0] : null);
    if (first) await open(first);
    else if (props.embedded) error.value = '该题尚未接入可修正的标签记录。';
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    loading.value = false;
  }
});
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
async function open(p, force = false) {
  if (saving.value || (!force && !discardAllowed())) return;
  const version = ++generation;
  selected.value = p;
  detail.value = null;
  chosen.value = [];
  opening.value = true;
  error.value = '';
  notice.value = '';
  confirmation.value = '';
  conflict.value = false;
  pendingRequest.value = null;
  historyOpen.value = false;
  tagQuery.value = '';
  reason.value = '';
  try {
    const data = await request(endpoint(p), {}, 'tag_detail');
    if (version !== generation) return;
    detail.value = data;
    chosen.value = data.effective_tags.map((t) => t.id);
    // A refresh or shared URL must return to this problem, not the first row.
    if (!props.embedded)
      await router.replace({
        path: route.path,
        query: { ...route.query, platform: p.platform, problem_id: p.problem_id },
      });
  } catch (e) {
    if (version === generation && e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (version === generation) opening.value = false;
  }
}
function toggle(id) {
  if (saving.value || conflict.value) return;
  chosen.value = chosen.value.includes(id)
    ? chosen.value.filter((t) => t !== id)
    : [...chosen.value, id];
  pendingRequest.value = null;
  confirmation.value = '';
  notice.value = '';
}
function discard() {
  chosen.value = [...currentIds.value];
  reason.value = '';
  pendingRequest.value = null;
  confirmation.value = '';
}
async function mutate(operation) {
  if (saving.value || conflict.value || !detail.value) return;
  if (reason.value.trim().length < 2) {
    error.value = '请先填写至少 2 字的操作原因。';
    return;
  }
  if (operation === 'save' && !dirty.value) return;
  // Retrying after a lost response sends the same operation ID, never another event.
  const draft = {
    operation,
    tag_ids: operation === 'save' ? [...chosen.value] : [],
    reason: reason.value.trim(),
    revision: detail.value.revision,
  };
  const serialized = JSON.stringify(draft);
  if (pendingRequest.value?.serialized !== serialized)
    pendingRequest.value = { serialized, body: { ...draft, request_id: crypto.randomUUID() } };
  saving.value = true;
  error.value = '';
  notice.value = '';
  confirmation.value = '';
  try {
    const data = await request(
      endpoint(selected.value),
      { method: 'POST', body: pendingRequest.value.body },
      'tag_write',
    );
    detail.value = data.detail;
    chosen.value = data.detail.effective_tags.map((t) => t.id);
    reason.value = '';
    pendingRequest.value = null;
    notice.value = data.message;
    emit('saved', { platform: selected.value.platform, problem_id: selected.value.problem_id });
    // Update list without discarding editor state; server remains authoritative.
    try {
      const list = await request('/secondary/tag-management');
      rows.value = list.items;
    } catch (e) {
      if (e.name !== 'AbortError') notice.value += '；目录刷新失败，可重新加载查看。';
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      conflict.value = e.status === 409;
      error.value = conflict.value
        ? '其他窗口已更新这道题。草稿已保留，请对照后重新加载。'
        : e.message + ' 若响应丢失，可再次保存；同一操作不会重复记账。';
    }
  } finally {
    saving.value = false;
  }
}
function prepareAction(operation) {
  if (!saving.value) {
    confirmation.value = operation;
    nextTick(() => document.getElementById('confirm-tag-operation')?.focus());
  }
}
const confirmLabels = {
  undo: '撤销最近一次人工操作',
  reset: '清除全部人工覆盖，恢复当前自动标签',
  verify: '确认已完整核对当前全部标签',
};
function requestClose() {
  if (!saving.value && discardAllowed()) emit('close');
}
defineExpose({ requestClose });
</script>

<template>
  <main class="tag-workspace" :class="{ 'tm-embedded': embedded }">
    <header v-if="!embedded" class="tm-page-head">
      <div>
        <p class="tm-eyebrow">ACM FOREVER / 题库工作台</p>
        <h1>标签管理 <span class="tm-local">本地隔离</span></h1>
        <p class="tm-subtitle">自动标注提供起点，人工修正保留判断。每次修改都能追溯与撤销。</p>
      </div>
      <div class="tm-head-actions">
        <a class="tm-back" href="/api/secondary/tag-management/export" download>导出人工记录 ↓</a
        ><RouterLink class="tm-back" to="/processing-demo.html">返回验收总览 ↗</RouterLink>
      </div>
    </header>
    <div v-if="!embedded" class="tm-stats" aria-label="标签统计">
      <div>
        <strong>{{ rows.length }}</strong
        ><span>已接入题目</span>
      </div>
      <div>
        <strong>{{ correctedCount }}</strong
        ><span>人工修正</span>
      </div>
      <div>
        <strong>{{ reviewedCount }}</strong
        ><span>人工确认</span>
      </div>
      <div>
        <strong>{{ needsReviewCount }}</strong
        ><span>需要复核</span>
      </div>
      <p>
        <span class="tm-dot"></span>仅保存到本地人工记录<br /><small
          >原始预测不变 · AI 调用为 0</small
        >
      </p>
    </div>
    <p v-if="loading" class="tm-message" role="status">正在读取题目和 V0.3 标签词表…</p>
    <p v-if="error" class="tm-message tm-error" role="alert">
      {{ error }}
      <button v-if="conflict" class="tm-button" :disabled="saving" @click="open(selected, false)">
        放弃草稿并重新加载
      </button>
    </p>
    <p v-if="notice" class="tm-message tm-success" role="status">✓ {{ notice }}</p>
    <div v-if="!loading" class="tm-layout">
      <aside v-if="!embedded" class="tm-sidebar" aria-label="题目选择">
        <div class="tm-sidebar-head">
          <h2>
            题目目录 <small>{{ filtered.length }}</small>
          </h2>
          <label class="tm-sr" for="problem-search">搜索题目或标签</label>
          <input
            id="problem-search"
            v-model="query"
            type="search"
            placeholder="搜索题名、题号或标签…"
          />
          <label class="tm-sr" for="status-filter">人工状态</label>
          <select id="status-filter" v-model="status">
            <option value="all">全部状态</option>
            <option v-for="(label, key) in reviewLabels" :key="key" :value="key">
              {{ label }}
            </option>
          </select>
        </div>
        <div class="tm-problem-list">
          <button
            v-for="p in filtered"
            :key="p.problem_key"
            class="tm-problem"
            :class="{ selected: selected?.problem_key === p.problem_key }"
            :aria-current="selected?.problem_key === p.problem_key ? 'true' : undefined"
            :disabled="saving"
            @click="open(p)"
          >
            <span class="tm-problem-meta"
              >{{ p.platform === 'atcoder' ? 'AtCoder' : p.platform }} · {{ p.problem_id }}
              <i :class="p.review_status"></i
            ></span>
            <strong>{{ p.title }}</strong
            ><span class="tm-problem-tags">{{
              p.effective_tags.map((t) => t.name_zh).join(' · ') || '暂无标签'
            }}</span>
            <small
              >{{ reviewLabels[p.review_status]
              }}<span v-if="p.manual_history_count">
                · {{ p.manual_history_count }} 条历史</span
              ></small
            >
          </button>
          <p v-if="!filtered.length" class="tm-empty">没有匹配的题目，试试其他关键词。</p>
        </div>
      </aside>
      <div class="tm-editor">
        <p v-if="opening" class="tm-empty" role="status">正在读取最新标签和历史…</p>
        <template v-else-if="detail && selected">
          <section class="tm-card tm-title-card">
            <div>
              <span class="tm-eyebrow">{{ selected.problem_key }}</span>
              <h2>{{ selected.title }}</h2>
              <span class="tm-state" :class="detail.review_status">{{
                reviewLabels[detail.review_status]
              }}</span>
              <span v-if="dirty" class="tm-draft">有未保存修改</span>
            </div>
            <RouterLink
              class="tm-back"
              :to="{
                path: '/problem.html',
                query: { platform: selected.platform, problem_id: selected.problem_id },
              }"
              >查看完整题面 ↗</RouterLink
            >
            <p v-if="detail.needs_review_reasons.length" class="tm-warning">
              待复核：{{ detail.needs_review_reasons.join('、') }}
            </p>
          </section>
          <section class="tm-card" aria-label="当前标签编辑">
            <div class="tm-section-head">
              <h3>
                最终有效标签 <small>{{ chosen.length }}</small>
              </h3>
              <span class="tm-hint">点击 × 移除；在下方词表中添加</span>
            </div>
            <div class="tm-selected-tags">
              <button
                v-for="id in chosen"
                :key="id"
                class="tm-tag selected"
                :class="{ added: diff.added.includes(id) }"
                :disabled="saving || conflict"
                :aria-label="'移除' + name(id)"
                @click="toggle(id)"
              >
                {{ name(id) }}
                <small>{{
                  diff.added.includes(id)
                    ? '待新增'
                    : sourceLabels[detail.effective_tags.find((t) => t.id === id)?.source] || '已有'
                }}</small
                ><b aria-hidden="true">×</b>
              </button>
              <p v-if="!chosen.length" class="tm-empty-inline">
                当前为空标签。允许保存，不会自动补充或调用 AI。
              </p>
            </div>
            <div class="tm-baseline">
              <span>原始自动标签</span
              ><span
                v-for="tag in detail.auto_tags.tags"
                :key="tag.id"
                class="tm-auto"
                :class="{ removed: !chosen.includes(tag.id) }"
                >{{ tag.name_zh
                }}<small>{{ !chosen.includes(tag.id) ? '已移除' : '保留' }}</small></span
              ><span v-if="!detail.auto_tags.tags.length">无</span>
            </div>
            <p class="tm-hint">
              人工删除的标签不会被后续 AI 自动恢复。CF 精确映射也允许明确纠错，记录原因后保存。
            </p>
          </section>
          <section class="tm-card" aria-label="标签词表">
            <div class="tm-section-head">
              <h3>添加算法标签</h3>
              <span class="tm-hint">V0.3 · {{ taxonomy.length }} 个标准标签</span>
            </div>
            <div class="tm-library-tools">
              <label class="tm-search"
                ><span aria-hidden="true">⌕</span
                ><input
                  ref="searchInput"
                  v-model="tagQuery"
                  type="search"
                  aria-label="搜索标签中文名或英文ID"
                  placeholder="搜索中文名或英文 ID，例如：动态规划 / dp"
              /></label>
              <div class="tm-segments" aria-label="标签类型">
                <button
                  v-for="[value, label] in [
                    ['specific', '具体算法'],
                    ['provisional', '临时大类'],
                    ['all', '全部'],
                  ]"
                  :key="value"
                  :aria-pressed="kind === value"
                  :class="{ active: kind === value }"
                  @click="kind = value"
                >
                  {{ label }}
                </button>
              </div>
            </div>
            <div class="tm-taxonomy">
              <button
                v-for="tag in available"
                :key="tag.id"
                class="tm-option"
                :class="{
                  active: chosen.includes(tag.id),
                  provisional: tag.tag_kind === 'provisional',
                }"
                :disabled="saving || conflict"
                :aria-pressed="chosen.includes(tag.id)"
                :title="tag.id"
                @click="toggle(tag.id)"
              >
                <span>{{ chosen.includes(tag.id) ? '✓' : '+' }}</span
                >{{ tag.name_zh }}<small>{{ tag.id }}</small>
              </button>
            </div>
            <p v-if="!available.length" class="tm-empty">
              没有找到标准标签，不能自行创建词表之外的标签。
            </p>
          </section>
          <section class="tm-card tm-save-panel" aria-label="修改预览和保存">
            <div class="tm-section-head">
              <h3>修改预览</h3>
              <button class="tm-text-button" :disabled="!dirty || saving" @click="discard">
                放弃草稿
              </button>
            </div>
            <div v-if="dirty" class="tm-diff">
              <span v-for="id in diff.added" :key="'a' + id" class="tm-diff-add"
                >＋ {{ name(id) }}</span
              ><span v-for="id in diff.removed" :key="'r' + id" class="tm-diff-remove"
                >－ {{ name(id) }}</span
              >
            </div>
            <p v-else class="tm-hint">尚未修改标签。普通保存不会将自动标签标记为人工完整确认。</p>
            <label for="edit-reason" class="tm-reason-label"
              >操作原因 <small>必填，2–300 字</small></label
            >
            <textarea
              id="edit-reason"
              v-model="reason"
              maxlength="300"
              rows="2"
              :disabled="saving"
              placeholder="例如：题解采用差分维护颜色计数，移除缺少依据的标签。"
            />
            <div class="tm-save-actions">
              <span class="tm-hint">{{ reason.length }}/300 · 保存时再次校验最新版本</span
              ><button
                class="tm-button tm-primary"
                data-testid="save-tags"
                :disabled="!canSave"
                @click="mutate('save')"
              >
                {{ saving ? '正在保存…' : '保存人工修正' }}
              </button>
            </div>
          </section>
          <section class="tm-card" aria-label="历史与撤销">
            <div class="tm-section-head">
              <h3>
                操作历史 <small>{{ detail.history.length }}</small>
              </h3>
              <button
                class="tm-text-button"
                :aria-expanded="historyOpen"
                @click="historyOpen = !historyOpen"
              >
                {{ historyOpen ? '收起历史' : '展开历史' }}
              </button>
            </div>
            <div class="tm-history-actions">
              <button
                class="tm-button"
                :disabled="saving || dirty || conflict || !detail.history.length"
                @click="prepareAction('undo')"
              >
                撤销上一次</button
              ><button
                class="tm-button"
                :disabled="
                  saving ||
                  dirty ||
                  conflict ||
                  !(
                    detail.manual_overrides.added_tag_ids.length ||
                    detail.manual_overrides.removed_tag_ids.length ||
                    detail.fully_human_verified
                  )
                "
                @click="prepareAction('reset')"
              >
                恢复自动标签</button
              ><button
                class="tm-button"
                :disabled="
                  saving ||
                  dirty ||
                  conflict ||
                  detail.fully_human_verified ||
                  !!detail.needs_review_reasons.length
                "
                @click="prepareAction('verify')"
              >
                完整人工确认
              </button>
            </div>
            <p class="tm-hint">
              撤销会追加历史记录；恢复自动标签会清除本题全部覆盖。两者都保留原有操作历史。
            </p>
            <section
              v-if="confirmation"
              class="tm-confirm"
              role="alertdialog"
              aria-labelledby="confirm-title"
            >
              <h4 id="confirm-title">{{ confirmLabels[confirmation] }}？</h4>
              <p>
                {{
                  confirmation === 'verify'
                    ? '仅在你确实已核对全部标签和题面后确认。这会记录你的管理员身份。'
                    : '这是一条新的人工操作，不删除历史；请在上方填写本次操作原因。'
                }}
              </p>
              <button
                id="confirm-tag-operation"
                class="tm-button tm-primary"
                :disabled="reason.trim().length < 2 || saving"
                @click="mutate(confirmation)"
              >
                确认操作</button
              ><button class="tm-button" @click="confirmation = ''">取消</button>
            </section>
            <ol v-if="historyOpen" class="tm-history">
              <li v-for="event in detail.history" :key="event.event_id">
                <div>
                  <strong>{{
                    {
                      save: '保存标签',
                      undo: '撤销操作',
                      reset: '恢复自动标签',
                      verify: '完整人工确认',
                    }[event.details.action || event.operation] || '人工修正'
                  }}</strong
                  ><time>{{ date(event.created_at) }}</time>
                </div>
                <p>{{ event.reason }}</p>
                <small>{{ event.actor }} · {{ event.event_id.slice(0, 8) }}</small>
                <p class="tm-hint">
                  人工新增 {{ event.after.added_tag_ids.map(name).join('、') || '无' }}；人工删除
                  {{ event.after.removed_tag_ids.map(name).join('、') || '无' }}
                </p>
              </li>
              <li v-if="!detail.history.length" class="tm-empty">
                尚无人工操作，当前保留自动来源。
              </li>
            </ol>
          </section>
        </template>
        <p v-else-if="!opening" class="tm-empty">从左侧选择一道题目开始。</p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.tag-workspace {
  --tm-accent: #176c60;
  --tm-line: #dce4e2;
  --tm-text: #20362f;
  --tm-muted: #6b7d76;
  max-width: 1380px;
  margin: 0 auto;
  padding: 38px 32px 80px;
  color: var(--text, var(--tm-text));
}
.tag-workspace.tm-embedded {
  padding: 18px 20px 35px;
  max-width: none;
}
.tm-embedded .tm-layout {
  grid-template-columns: minmax(0, 1fr);
}
.tm-embedded .tm-title-card .tm-back {
  font-size: 12px;
}
.tm-page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}
.tm-eyebrow {
  font: 600 11px/1.5 system-ui;
  letter-spacing: 1.4px;
  color: var(--tm-muted);
  margin: 0 0 10px;
}
.tm-page-head h1 {
  font-size: 34px;
  letter-spacing: -1px;
  margin: 0;
}
.tm-local {
  display: inline-block;
  font-size: 11px;
  letter-spacing: 0;
  vertical-align: middle;
  background: #e3ede8;
  color: #356b55;
  border: 1px solid #bcd0c4;
  padding: 4px 9px;
  border-radius: 5px;
  margin-left: 10px;
}
.tm-subtitle {
  color: var(--tm-muted);
  font-size: 14px;
  margin-top: 12px;
}
.tm-back {
  font-size: 13px;
  color: var(--tm-accent);
  text-decoration: none;
  white-space: nowrap;
}
.tm-head-actions {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.tm-stats {
  display: flex;
  gap: 0;
  background: var(--card-bg, #fff);
  border: 1px solid var(--tm-line);
  border-radius: 12px;
  margin: 24px 0;
  overflow: hidden;
}
.tm-stats > div {
  padding: 18px 30px;
  display: flex;
  gap: 12px;
  align-items: center;
  border-right: 1px solid var(--tm-line);
}
.tm-stats strong {
  font: 600 26px system-ui;
  color: var(--tm-accent);
}
.tm-stats span {
  font-size: 12px;
  color: var(--tm-muted);
}
.tm-stats > p {
  margin: 0 0 0 auto;
  padding: 18px 22px;
  font-size: 12px;
  line-height: 1.8;
}
.tm-stats small {
  color: var(--tm-muted);
}
.tm-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #398b6b;
  border-radius: 50%;
  margin-right: 6px;
}
.tm-layout {
  display: grid;
  grid-template-columns: 288px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}
.tm-sidebar,
.tm-card {
  border: 1px solid var(--tm-line);
  border-radius: 12px;
  background: var(--card-bg, #fff);
}
.tm-sidebar {
  position: sticky;
  top: 88px;
  overflow: hidden;
}
.tm-sidebar-head {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--tm-line);
}
.tm-sidebar h2 {
  font-size: 14px;
  margin: 0 0 14px;
}
.tm-sidebar h2 small,
.tm-section-head h3 small {
  font: 500 11px system-ui;
  color: var(--tm-muted);
  margin-left: 6px;
  background: #edf1ef;
  padding: 3px 6px;
  border-radius: 4px;
}
.tag-workspace input,
.tag-workspace select,
.tag-workspace textarea {
  box-sizing: border-box;
  width: 100%;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  color: inherit;
  background: transparent;
  border: 1px solid var(--tm-line);
  border-radius: 7px;
  padding: 9px 11px;
}
.tag-workspace input:focus,
.tag-workspace textarea:focus,
.tag-workspace select:focus {
  outline: 2px solid #176c6060;
  outline-offset: 2px;
}
.tm-sidebar select {
  margin-top: 9px;
}
.tm-problem-list {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  padding: 6px;
}
.tm-problem {
  display: flex;
  flex-direction: column;
  width: 100%;
  background: transparent;
  color: inherit;
  text-align: left;
  padding: 14px 12px;
  border: 1px solid transparent;
  border-radius: 7px;
  cursor: pointer;
  margin: 2px 0;
  gap: 7px;
}
.tm-problem.selected {
  border-color: #176c6033;
  background: #ecf4f0;
  box-shadow: inset 3px 0 #176c60;
}
.tm-problem:hover {
  background: #176c6009;
}
.tm-problem strong {
  font: 600 14px/1.4 system-ui;
}
.tm-problem-meta {
  font: 10px system-ui;
  color: var(--tm-muted);
  display: flex;
  align-items: center;
  gap: 7px;
}
.tm-problem-meta i {
  width: 5px;
  height: 5px;
  background: #94a69b;
  border-radius: 50%;
  margin-left: auto;
}
.tm-problem-meta i.corrected {
  background: #bd873d;
}
.tm-problem-meta i.verified {
  background: #278866;
}
.tm-problem-meta i.needs_review {
  background: #c3624c;
}
.tm-problem-tags {
  font-size: 11px;
  color: var(--tm-muted);
}
.tm-problem small {
  font-size: 10px;
  color: var(--tm-muted);
}
.tm-editor {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.tm-card {
  padding: 22px;
}
.tm-title-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.tm-title-card h2 {
  font-size: 24px;
  margin: 6px 0 12px;
  font-family: system-ui;
}
.tm-state,
.tm-draft {
  font-size: 11px;
  padding: 4px 7px;
  border-radius: 4px;
  background: #edf1ef;
  color: #657c6e;
}
.tm-state.corrected,
.tm-draft {
  background: #faf0dd;
  color: #976824;
}
.tm-state.verified {
  background: #e5f4e8;
  color: #39704b;
}
.tm-state.needs_review {
  background: #fbe8e1;
  color: #a55339;
}
.tm-draft {
  margin-left: 8px;
}
.tm-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.tm-section-head h3 {
  font-size: 14px;
  margin: 0;
}
.tm-hint {
  font-size: 11px;
  line-height: 1.8;
  color: var(--tm-muted);
}
.tm-selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 42px;
}
.tm-tag {
  border: 1px solid #b6cfc5;
  border-radius: 7px;
  background: #f0f7f3;
  padding: 10px 12px;
  font-size: 13px;
  color: #245b48;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.tm-tag small {
  font-size: 9px;
  opacity: 0.7;
}
.tm-tag b {
  font: 17px/1 system-ui;
  color: #6a8b7c;
}
.tm-tag.added {
  border-style: dashed;
  background: #e6f4ec;
}
.tm-baseline {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  font-size: 11px;
  color: var(--tm-muted);
  border-top: 1px dashed var(--tm-line);
  margin-top: 18px;
  padding-top: 16px;
}
.tm-auto {
  border: 1px solid var(--tm-line);
  padding: 3px 7px;
  border-radius: 4px;
}
.tm-auto small {
  font-size: 9px;
  margin-left: 6px;
  opacity: 0.7;
}
.tm-auto.removed {
  text-decoration: line-through;
  background: #faf0ec;
}
.tm-library-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.tm-search {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 200px;
}
.tm-search span {
  font: 24px system-ui;
  color: var(--tm-muted);
}
.tm-segments {
  display: flex;
  border: 1px solid var(--tm-line);
  border-radius: 6px;
  padding: 3px;
}
.tm-segments button {
  border: 0;
  background: transparent;
  color: var(--tm-muted);
  padding: 6px 9px;
  font-size: 11px;
  cursor: pointer;
  border-radius: 4px;
}
.tm-segments button.active {
  background: #176c60;
  color: #fff;
}
.tm-taxonomy {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
  gap: 7px;
  max-height: 270px;
  overflow: auto;
  margin-top: 16px;
  padding: 2px;
}
.tm-option {
  border: 1px solid #e3e9e5;
  background: transparent;
  border-radius: 6px;
  text-align: left;
  padding: 9px 10px;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 3px;
}
.tm-option small {
  grid-column: 2;
  font: 9px system-ui;
  color: var(--tm-muted);
  overflow-wrap: anywhere;
}
.tm-option span {
  color: #8c9d92;
}
.tm-option.active {
  background: #edf5ef;
  border-color: #75a38c;
  color: #266048;
}
.tm-option.provisional {
  border-style: dashed;
}
.tm-option:hover {
  border-color: var(--tm-accent);
}
.tm-diff {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 8px 0 18px;
}
.tm-diff-add,
.tm-diff-remove {
  font-size: 12px;
  padding: 5px 9px;
  border-radius: 4px;
}
.tm-diff-add {
  background: #e6f4e9;
  color: #36744c;
}
.tm-diff-remove {
  background: #faeae3;
  color: #aa5a3e;
}
.tm-reason-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 8px;
}
.tm-reason-label small {
  font-size: 10px;
  color: var(--tm-muted);
}
.tm-save-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.tm-button {
  border: 1px solid var(--tm-line);
  background: var(--card-bg, #fff);
  color: inherit;
  border-radius: 6px;
  padding: 9px 13px;
  font-size: 12px;
  cursor: pointer;
}
.tm-primary {
  background: #176c60;
  color: #fff;
  border-color: #176c60;
  font-weight: 600;
}
.tag-workspace button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tag-workspace button:focus-visible,
.tm-back:focus-visible {
  outline: 2px solid #176c60;
  outline-offset: 3px;
}
.tm-text-button {
  border: 0;
  background: transparent;
  color: var(--tm-accent);
  font-size: 12px;
  cursor: pointer;
}
.tm-history-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tm-history {
  padding: 0;
  list-style: none;
  margin: 20px 0 0;
}
.tm-history li {
  padding: 15px 0;
  border-top: 1px solid var(--tm-line);
  font-size: 12px;
}
.tm-history li > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.tm-history time,
.tm-history small {
  font-size: 10px;
  color: var(--tm-muted);
}
.tm-history p {
  margin: 8px 0;
}
.tm-confirm {
  background: #f8f2e6;
  border: 1px solid #e8d7b9;
  padding: 16px;
  border-radius: 6px;
  margin-top: 15px;
}
.tm-confirm h4 {
  font-size: 13px;
  margin: 0 0 8px;
}
.tm-confirm p {
  font-size: 12px;
}
.tm-confirm button {
  margin-right: 8px;
}
.tm-message {
  padding: 15px 18px;
  border-radius: 8px;
  font-size: 13px;
}
.tm-error {
  background: #fcece6;
  color: #994a32;
}
.tm-success {
  background: #e8f5ed;
  color: #2b6948;
}
.tm-warning {
  width: 100%;
  font-size: 12px;
  color: #a15b32;
}
.tm-empty {
  padding: 28px 15px;
  font-size: 12px;
  text-align: center;
  color: var(--tm-muted);
}
.tm-empty-inline {
  font-size: 12px;
  color: var(--tm-muted);
}
.tm-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
@media (max-width: 1000px) {
  .tm-stats > div {
    padding: 16px;
  }
  .tm-stats > p {
    display: none;
  }
  .tm-layout {
    grid-template-columns: 240px minmax(0, 1fr);
  }
  .tag-workspace {
    padding: 26px 18px 60px;
  }
  .tm-section-head {
    flex-wrap: wrap;
  }
}
@media (max-width: 700px) {
  .tm-page-head {
    align-items: flex-start;
  }
  .tm-page-head h1 {
    font-size: 26px;
  }
  .tm-subtitle {
    font-size: 12px;
  }
  .tm-stats > div {
    padding: 12px 9px;
    flex: 1;
    gap: 6px;
    flex-direction: column;
  }
  .tm-stats strong {
    font-size: 22px;
  }
  .tm-stats span {
    font-size: 10px;
  }
  .tm-layout {
    grid-template-columns: 1fr;
  }
  .tm-sidebar {
    position: static;
  }
  .tm-problem-list {
    max-height: 200px;
  }
  .tm-card {
    padding: 17px;
  }
  .tm-title-card h2 {
    font-size: 21px;
  }
  .tm-save-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .tm-taxonomy {
    max-height: 240px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .tm-page-head > .tm-back {
    font-size: 11px;
  }
  .tm-history li > div {
    flex-wrap: wrap;
  }
}
</style>
