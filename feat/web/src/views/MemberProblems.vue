<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth, useRequests, date } from '../lib/api.js';
import { memberFilters, memberQuery, problemLink } from '../lib/member-problems.js';
import Pager from '../components/Pager.vue';
import ProblemTracker from '../components/ProblemTracker.vue';
import { filterTaxonomy, reviewLabels, sourceLabels } from '../lib/tag-management.js';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive(memberFilters(route.query));
const rows = ref([]),
  total = ref(0),
  busy = ref(false),
  error = ref('');
const facets = ref([]),
  tagSearch = ref(''),
  expandedTags = ref(false);
const canManage = computed(() => ['admin', 'root'].includes(auth.role));
const selectedLabels = computed(() => (form.labels ? form.labels.split(',') : []));
const selectedNames = computed(() =>
  selectedLabels.value.map((id) => ({
    id,
    name_zh: facets.value.find((t) => t.id === id)?.name_zh || id,
  })),
);
const visibleTags = computed(() => {
  const filtered = filterTaxonomy(facets.value, tagSearch.value).filter(
    (t) => tagSearch.value || expandedTags.value || t.count || selectedLabels.value.includes(t.id),
  );
  return tagSearch.value || expandedTags.value ? filtered : filtered.slice(0, 14);
});
const tags = ref([]),
  tagsBusy = ref(false),
  tagsError = ref('');
const availableTags = computed(() => [
  ...new Set([form.problem_tag, ...tags.value].filter(Boolean)),
]);
const current = computed(() => memberFilters(route.query));
const isTracker = computed(() => current.value.view === 'tracker');
const platforms = computed(() => ({
  ...(!isTracker.value ? { all: '全部平台' } : {}),
  codeforces: 'Codeforces',
  atcoder: 'AtCoder',
  ...(!isTracker.value ? { luogu: '洛谷', nowcoder: '牛客', cjlu: '校 OJ' } : {}),
}));
let revision = 0;
let tagsRevision = 0;
async function loadTags(platform = form.platform) {
  const version = ++tagsRevision;
  tags.value = [];
  tagsError.value = '';
  tagsBusy.value = true;
  try {
    const data = await request(
      '/me/problems/tags?' + new URLSearchParams({ platform: platform === 'all' ? '' : platform }),
      {},
      'member-problem-tags',
    );
    if (version !== tagsRevision) return;
    tags.value = data.tags;
  } catch (e) {
    if (version === tagsRevision && e.name !== 'AbortError') tagsError.value = e.message;
  } finally {
    if (version === tagsRevision) tagsBusy.value = false;
  }
}
async function load() {
  const version = ++revision;
  Object.assign(form, current.value);
  rows.value = [];
  error.value = '';
  busy.value = true;
  try {
    const { view, ...filters } = current.value;
    if (view === 'tracker') {
      delete filters.labels;
      delete filters.match;
    }
    const data = await request(
      (view === 'tracker' ? '/me/problems/tracker?' : '/me/problems?') +
        new URLSearchParams({ ...filters, page_size: 20 }),
      {},
      'member-problems',
    );
    if (version !== revision) return;
    rows.value = data.items;
    total.value = data.total;
    facets.value = data.tag_facets || [];
  } catch (e) {
    if (version === revision && e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (version === revision) busy.value = false;
  }
}
function navigate(page = 1) {
  router.push({ path: route.path, query: memberQuery({ ...form, page }) });
}
function scope(value) {
  Object.assign(form, current.value, { scope: value });
  navigate();
}
function changeView(view) {
  const next = memberFilters({ ...current.value, view, page: 1 });
  if (next.platform !== current.value.platform) next.problem_tag = '';
  Object.assign(form, next);
  navigate();
}
async function favorite(row) {
  try {
    await request(
      `/me/problems/${encodeURIComponent(row.platform)}/${encodeURIComponent(row.problem_id)}/state`,
      { method: 'PUT', body: { is_favorite: !row.is_favorite } },
    );
    await load();
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  }
}
function tagsText(value) {
  let tags = value;
  if (typeof tags === 'string' && tags.trimStart().startsWith('[')) {
    try {
      tags = JSON.parse(tags);
    } catch {
      /* Legacy text remains readable when it is not a JSON array. */
    }
  }
  return Array.isArray(tags)
    ? tags.filter((tag) => typeof tag === 'string').join(', ') || '无标签'
    : tags || '无标签';
}
function clear() {
  Object.assign(form, memberFilters({ scope: current.value.scope, view: current.value.view }));
  navigate();
}
function toggleLabel(id) {
  form.labels = (
    selectedLabels.value.includes(id)
      ? selectedLabels.value.filter((t) => t !== id)
      : [...selectedLabels.value, id]
  )
    .sort()
    .join(',');
  navigate();
}
function clearLabels() {
  form.labels = '';
  navigate();
}
watch(() => route.fullPath, load, { immediate: true });
watch(
  () => form.platform,
  (platform, previous) => {
    if (previous !== undefined && platform !== current.value.platform) form.problem_tag = '';
    loadTags(platform);
  },
  { immediate: true },
);
</script>
<template>
  <main class="community-main member-problems" :class="{ 'member-problems-tracker': isTracker }">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>题库</h1>
    <p>按算法标签寻找练习题，或查看本人已 AC 的题目。人工修正后的有效标签会立即用于筛选。</p>
    <div class="chips member-problem-views" aria-label="题库视图">
      <button
        class="btn"
        :class="{ primary: !isTracker }"
        :aria-pressed="!isTracker"
        @click="changeView('list')"
      >
        题目列表
      </button>
      <button
        class="btn"
        :class="{ primary: isTracker }"
        :aria-pressed="isTracker"
        @click="changeView('tracker')"
      >
        比赛进度
      </button>
    </div>
    <div class="chips member-problem-scopes" aria-label="题库范围">
      <button
        class="btn"
        :class="{ primary: current.scope === 'all' }"
        :aria-pressed="current.scope === 'all'"
        @click="scope('all')"
      >
        全部题目
      </button>
      <button
        class="btn"
        :class="{ primary: current.scope === 'solved' }"
        :aria-pressed="current.scope === 'solved'"
        @click="scope('solved')"
      >
        我已 AC
      </button>
    </div>
    <section class="card">
      <form class="filters member-problem-filters" @submit.prevent="navigate()">
        <label
          ><span>平台</span
          ><select v-model="form.platform">
            <option v-for="(label, key) in platforms" :key="key" :value="key">
              {{ label }}
            </option>
          </select></label
        >
        <label class="member-problem-search"
          ><span>搜索</span
          ><input
            v-model="form.tag"
            maxlength="100"
            :placeholder="isTracker ? '比赛 ID、题号、题名或标签' : '题号、题名或标签'"
        /></label>
        <label
          ><span>标签</span
          ><select v-model="form.problem_tag" :disabled="tagsBusy">
            <option value="">{{ tagsBusy ? '正在加载标签…' : '全部标签' }}</option>
            <option v-for="tag in availableTags" :key="tag" :value="tag">{{ tag }}</option>
          </select></label
        >
        <label
          ><span>收藏</span
          ><select v-model="form.state">
            <option value="">全部</option>
            <option value="favorite">已收藏</option>
          </select></label
        >
        <div class="member-problem-filter-actions">
          <button class="btn primary" :disabled="busy">查询</button>
          <button type="button" class="btn" @click="clear">清除筛选</button>
        </div>
      </form>
      <section v-if="!isTracker" class="bank-label-filter" aria-label="算法标签筛选">
        <div class="bank-label-heading">
          <div>
            <h2>按算法标签筛选</h2>
            <p>使用最终有效标签，包含人工修正。多个标签可以组合查询。</p>
          </div>
          <label class="bank-match-label"
            >匹配方式<select v-model="form.match" aria-label="标签匹配方式" @change="navigate()">
              <option value="all">同时包含全部标签</option>
              <option value="any">包含任意一个标签</option>
            </select></label
          >
        </div>
        <label class="bank-tag-search"
          >查找标签<input
            v-model="tagSearch"
            type="search"
            aria-label="查找算法标签"
            placeholder="中文名称或英文 ID，例如：差分 / dp"
        /></label>
        <div class="bank-tag-options">
          <button
            v-for="tag in visibleTags"
            :key="tag.id"
            type="button"
            class="bank-tag-option"
            :class="{ active: selectedLabels.includes(tag.id) }"
            :aria-pressed="selectedLabels.includes(tag.id)"
            :title="tag.id"
            :data-tag-id="tag.id"
            @click="toggleLabel(tag.id)"
          >
            {{ selectedLabels.includes(tag.id) ? '✓ ' : '' }}{{ tag.name_zh }}
            <small>{{ tag.count }}</small></button
          ><span v-if="!visibleTags.length" class="muted">{{
            tagSearch ? '没有匹配的标准标签' : '当前范围暂无可筛选的算法标签'
          }}</span>
        </div>
        <button
          v-if="facets.length && !tagSearch"
          type="button"
          class="bank-label-more"
          @click="expandedTags = !expandedTags"
        >
          {{ expandedTags ? '收起词表' : `浏览全部 ${facets.length} 个标签` }}
        </button>
        <div v-if="selectedLabels.length" class="bank-active-labels" aria-label="已选算法标签">
          <span>已选：</span
          ><button
            v-for="tag in selectedNames"
            :key="tag.id"
            class="bank-selected-label"
            type="button"
            :aria-label="'取消标签筛选：' + tag.name_zh"
            @click="toggleLabel(tag.id)"
          >
            {{ tag.name_zh }} ×</button
          ><button class="bank-label-more" type="button" @click="clearLabels">清空标签</button>
        </div>
      </section>
      <p v-if="tagsError" class="member-problem-tags-error" role="alert">
        标签加载失败：{{ tagsError }}
        <button type="button" class="btn" @click="loadTags()">重试标签</button>
      </p>
      <p v-if="isTracker" class="muted tracker-description">
        按比赛查看 Codeforces / AtCoder 的站内目录。搜索、标签、收藏与“我已
        AC”筛选匹配的比赛，保留该场全部已收录题目。
      </p>
      <p v-if="busy" role="status">{{ isTracker ? '正在加载比赛进度…' : '正在加载题目…' }}</p>
      <div v-else-if="error" role="alert">
        <p>{{ isTracker ? '比赛进度加载失败' : '题目加载失败' }}：{{ error }}</p>
        <button class="btn" @click="load">重试</button>
      </div>
      <template v-else>
        <template v-if="isTracker">
          <p class="muted">
            {{ current.scope === 'solved' ? '包含本人已 AC 的比赛' : '站内比赛目录' }} · 共
            {{ total }} 场比赛 · 按开始时间从新到旧 · 每页 20 场
          </p>
          <ProblemTracker
            v-if="rows.length"
            :contests="rows"
            :page="current.page"
            :page-size="20"
            :from="route.fullPath"
          />
          <p v-else class="empty">
            没有匹配的比赛。请调整筛选，并检查个人中心的 OJ 绑定与同步状态。
          </p>
        </template>
        <template v-else>
          <p class="muted">
            {{ current.scope === 'solved' ? '本人已 AC' : '全站目录' }} · 共 {{ total }} 道题目
          </p>
          <div id="problem-list">
            <article
              v-for="row in rows"
              :key="`${row.platform}-${row.problem_id}`"
              class="list-item"
            >
              <div class="bank-problem-info">
                <b>{{ row.platform }} · {{ row.problem_id }}</b
                ><br />{{ row.problem_name || '未命名题目' }}<br /><small
                  >难度 {{ row.problem_rating ?? '未知'
                  }}<template v-if="row.ac_at"> · AC {{ date(row.ac_at) }}</template></small
                >
                <div v-if="row.has_secondary" class="bank-result-tags">
                  <button
                    v-for="tag in row.effective_tags"
                    :key="tag.id"
                    type="button"
                    class="bank-result-tag"
                    :title="`${tag.id} · ${sourceLabels[tag.source] || tag.source} · 点击筛选`"
                    @click="toggleLabel(tag.id)"
                  >
                    {{ tag.name_zh }}<small v-if="tag.source === 'manual_add'">人工</small></button
                  ><span v-if="!row.effective_tags.length" class="muted">空标签</span
                  ><small class="bank-review-state">{{
                    reviewLabels[row.review_status] || row.review_status
                  }}</small>
                </div>
                <small v-else class="muted"
                  >原站标签：{{ tagsText(row.tags) }}
                  · 算法标签待接入</small
                >
              </div>
              <span class="chips"
                ><RouterLink
                  v-if="canManage && row.has_secondary"
                  class="btn bank-edit-tags"
                  :to="{
                    path: '/admin.html',
                    query: {
                      section: 'problems',
                      platform: row.platform,
                      problem_id: row.problem_id,
                      action: 'manual',
                    },
                  }"
                >
                  后台管理</RouterLink
                ><button class="btn" @click="favorite(row)">
                  {{ row.is_favorite ? '取消收藏' : '收藏' }}</button
                ><RouterLink class="btn" :to="problemLink(row, route.fullPath)"
                  >查看题面</RouterLink
                ></span
              >
            </article>
          </div>
          <p v-if="!rows.length" class="empty">
            {{
              current.scope === 'solved'
                ? '暂未同步到匹配的已 AC 题目。请检查筛选与个人中心的绑定、同步状态。'
                : '没有匹配题目，请调整筛选。'
            }}
          </p>
        </template>
        <Pager :page="current.page" :total="total" :busy="busy" @change="navigate" />
      </template>
    </section>
  </main>
</template>

<style scoped>
.bank-label-filter {
  padding: 20px;
  background: #176c6005;
  border: 1px solid #176c6026;
  border-radius: 10px;
  margin-bottom: 24px;
}
.bank-label-heading {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
}
.bank-label-heading h2 {
  font-size: 16px;
  margin: 0 0 6px;
}
.bank-label-heading p {
  font-size: 12px;
  margin: 0;
  color: #6b7d76;
}
.bank-match-label {
  display: grid;
  gap: 5px;
  font-size: 11px;
  min-width: 180px;
}
.bank-match-label select {
  min-height: 38px;
}
.bank-tag-search {
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 12px;
  margin: 16px 0 12px;
}
.bank-tag-search input {
  width: min(440px, 100%);
  min-width: 0;
  min-height: 38px;
}
.bank-tag-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 210px;
  overflow: auto;
  padding: 2px;
}
.bank-tag-option,
.bank-selected-label,
.bank-result-tag {
  border: 1px solid #b7cfc4;
  background: var(--card-bg, #fff);
  color: inherit;
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
}
.bank-tag-option small {
  font: 10px system-ui;
  color: #6b7d76;
  margin-left: 5px;
}
.bank-tag-option.active,
.bank-selected-label {
  background: #176c60;
  color: #fff;
  border-color: #176c60;
}
.bank-tag-option.active small {
  color: #ffffffa8;
}
.bank-label-more {
  border: 0;
  background: transparent;
  color: #176c60;
  font-size: 12px;
  padding: 8px 0;
  cursor: pointer;
}
.bank-active-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  border-top: 1px solid #176c6025;
  padding-top: 12px;
  margin-top: 10px;
  font-size: 12px;
}
.bank-problem-info {
  min-width: 0;
}
.bank-result-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 10px;
}
.bank-result-tag {
  font-size: 11px;
  padding: 5px 8px;
  color: #245b48;
  background: #176c6008;
}
.bank-result-tag small {
  font-size: 9px;
  margin-left: 5px;
  color: #a17235;
}
.bank-review-state {
  font-size: 10px;
  color: #6b7d76;
  margin-left: 4px;
}
.bank-edit-tags {
  border-color: #93b3a3;
  color: #176c60;
}
.member-problems .list-item {
  gap: 16px;
}
.member-problems .list-item > .chips {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.bank-tag-option:focus-visible,
.bank-result-tag:focus-visible,
.bank-selected-label:focus-visible {
  outline: 2px solid #176c60;
  outline-offset: 3px;
}
@media (max-width: 640px) {
  .bank-label-heading {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }
  .bank-tag-search {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
  .bank-tag-search input {
    width: 100%;
  }
  .member-problems .list-item {
    align-items: flex-start;
    flex-direction: column;
  }
  .member-problems .list-item > .chips {
    justify-content: flex-start;
  }
  .bank-label-filter {
    padding: 15px;
  }
}
.community-main.member-problems-tracker {
  width: min(1920px, calc(100% - 32px));
  padding-inline: 16px;
}
.member-problems-tracker > .card {
  min-width: 0;
  padding: 16px;
}
.member-problem-scopes {
  gap: 12px;
  margin: 24px 0;
}
.member-problem-views {
  gap: 12px;
  margin: 24px 0 12px;
}
.tracker-description {
  line-height: 1.7;
  margin-bottom: 20px;
}
form.member-problem-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 20px 24px;
  margin: 0 0 24px;
}
.member-problem-filters > label {
  display: flex;
  flex: 1 1 180px;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.member-problem-filters > .member-problem-search {
  flex: 2 1 280px;
}
.member-problem-filters label > span {
  line-height: 1.5;
  white-space: nowrap;
}
.member-problem-filters :is(input, select) {
  width: 100%;
  min-width: 0;
  min-height: 44px;
}
.member-problem-filter-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}
.member-problem-filter-actions > .btn {
  min-height: 44px;
  white-space: nowrap;
}
.member-problem-tags-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
@media (max-width: 640px) {
  .community-main.member-problems-tracker {
    width: calc(100% - 24px);
    padding-inline: 8px;
  }
  .member-problems-tracker > .card {
    padding: 12px;
  }
  .member-problem-filters > label,
  .member-problem-filters > .member-problem-search {
    flex-basis: 100%;
  }
  .member-problem-filter-actions {
    width: 100%;
  }
  .member-problem-filter-actions > .btn {
    flex: 1;
  }
}
</style>
