<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth, useRequests, date } from '../lib/api.js';
import { memberFilters, memberQuery, problemLink } from '../lib/member-problems.js';
import Pager from '../components/Pager.vue';
import LuoguBadges from '../components/LuoguBadges.vue';
import LuoguFilters from '../components/LuoguFilters.vue';
import LuoguTagPicker from '../components/LuoguTagPicker.vue';
import ProblemRangeFilters from '../components/ProblemRangeFilters.vue';
import { ratingFilters } from '../lib/problem-filters.js';
import { nativeFilters } from '../lib/luogu-problems.js';
import { nativeParams } from '../lib/luogu-problems.js';
import ProblemTracker from '../components/ProblemTracker.vue';
import ProblemDifficulty from '../components/ProblemDifficulty.vue';
import AlgorithmTag from '../components/AlgorithmTag.vue';
import ProblemTags from '../components/ProblemTags.vue';
import { reviewLabels, sourceLabels } from '../lib/tag-management.js';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive(memberFilters(route.query));
const rows = ref([]),
  total = ref(0),
  busy = ref(false),
  error = ref('');
const canManage = computed(() => ['admin', 'root'].includes(auth.role));
const tags = ref([]),
  tagsBusy = ref(false),
  tagsError = ref('');
const selectedProblemTags = computed(() => {
  if (form.platform !== 'codeforces') {
    return form.problem_tag ? [form.problem_tag] : [];
  }
  return (form.problem_tags || form.problem_tag)
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
});
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
const tagCache = new Map();
const pageCursors = new Map();
let cursorQuery = '';
let tagsAfterPending = null;
async function loadTags(platform = form.platform, expectedVersion = '') {
  const version = ++tagsRevision;
  tagsAfterPending = null;
  tags.value = [];
  tagsError.value = '';
  const cached = tagCache.get(platform);
  if (
    cached &&
    (expectedVersion ? cached.version === expectedVersion : Date.now() < cached.expires)
  ) {
    tags.value = cached.tags;
    tagsBusy.value = false;
    return;
  }
  tagsBusy.value = true;
  try {
    const data = await request(
      '/me/problems/tags?' + new URLSearchParams({ platform: platform === 'all' ? '' : platform }),
      {},
      'member-problem-tags',
    );
    if (version !== tagsRevision) return;
    tags.value = data.tags;
    tagCache.set(platform, {
      tags: data.tags,
      version: data.tags_version,
      expires: Date.now() + 60000,
    });
  } catch (e) {
    if (version === tagsRevision && e.name !== 'AbortError') tagsError.value = e.message;
  } finally {
    if (version === tagsRevision) {
      tagsBusy.value = false;
      const pending = tagsAfterPending;
      tagsAfterPending = null;
      if (pending && tagCache.get(pending.platform)?.version !== pending.version)
        loadTags(pending.platform, pending.version);
    }
  }
}
async function load() {
  const version = ++revision;
  Object.assign(form, current.value);
  rows.value = [];
  error.value = '';
  busy.value = true;
  try {
    const { view, rating_min, rating_max, ...filters } = current.value;
    for (const key of Object.keys(filters)) if (key.startsWith('native_')) delete filters[key];
    Object.assign(filters, nativeParams(current.value));
    if (rating_min) filters.rating_min = rating_min;
    if (rating_max) filters.rating_max = rating_max;
    if (!filters.problem_tags) delete filters.problem_tags;
    // The backend treats every nonempty platform as a literal platform name.
    if (filters.platform === 'all') delete filters.platform;
    const pageQuery = { ...filters, page_size: 20 };
    const { page, ...withoutPage } = pageQuery;
    const queryKey = new URLSearchParams(withoutPage).toString();
    if (queryKey !== cursorQuery) {
      pageCursors.clear();
      cursorQuery = queryKey;
    }
    if (view !== 'tracker' && pageCursors.has(Number(page)))
      pageQuery.cursor = pageCursors.get(Number(page));
    const data = await request(
      (view === 'tracker' ? '/me/problems/tracker?' : '/me/problems?') +
        new URLSearchParams(pageQuery),
      {},
      'member-problems',
    );
    if (version !== revision) return;
    if (view !== 'tracker') {
      for (const key of pageCursors.keys()) if (key > Number(data.page)) pageCursors.delete(key);
      if (data.next_cursor) pageCursors.set(Number(data.page) + 1, data.next_cursor);
      const platform = current.value.platform;
      if (
        platform !== 'luogu' &&
        data.tags_version &&
        tagCache.get(platform)?.version !== data.tags_version
      ) {
        if (tagsBusy.value) tagsAfterPending = { platform, version: data.tags_version };
        else loadTags(platform, data.tags_version);
      }
    }
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    if (version === revision && e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (version === revision) busy.value = false;
  }
}
function navigate(page = 1) {
  router.push({ path: route.path, query: memberQuery({ ...form, page }) });
}
function changePlatform() {
  form.problem_tag = '';
  form.problem_tags = '';
  navigate();
}
function applyProblemTags(selected) {
  const multiTag = form.platform === 'codeforces';
  form.problem_tag = multiTag ? '' : selected[0] || '';
  form.problem_tags = multiTag ? selected.join(',') : '';
  navigate();
}
function scope(value) {
  Object.assign(form, current.value, { scope: value });
  navigate();
}
function changeView(view) {
  const next = memberFilters({ ...current.value, view, page: 1 });
  if (next.platform !== current.value.platform) {
    next.problem_tag = '';
    next.problem_tags = '';
  }
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
function clear() {
  Object.assign(form, memberFilters({ scope: current.value.scope, view: current.value.view }));
  navigate();
}
watch(() => route.fullPath, load, { immediate: true });
watch(
  () => form.platform,
  (platform, previous) => {
    if (previous !== undefined && platform !== current.value.platform) {
      form.problem_tag = '';
      form.problem_tags = '';
      Object.assign(form, nativeFilters({ platform }), ratingFilters({ platform }));
    }
    if (platform !== 'luogu') loadTags(platform);
    else {
      ++tagsRevision;
      tags.value = [];
      tagsError.value = '';
      tagsBusy.value = false;
    }
  },
  { immediate: true, flush: 'sync' },
);
</script>
<template>
  <main class="community-main member-problems" :class="{ 'member-problems-tracker': isTracker }">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>题库</h1>
    <p>按题目标签寻找练习题，或查看本人已 AC 的题目。</p>
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
          ><select v-model="form.platform" @change="changePlatform">
            <option v-for="(label, key) in platforms" :key="key" :value="key">
              {{ label }}
            </option>
          </select></label
        >
        <label
          ><span>搜索</span
          ><input
            v-model="form.tag"
            maxlength="100"
            :placeholder="isTracker ? '比赛 ID、题号、题名或标签' : '题号、题名或标签'"
        /></label>
        <LuoguFilters
          v-if="form.platform === 'luogu' && !isTracker"
          v-model:difficulty="form.native_difficulty"
          v-model:tag="form.native_tag"
          v-model:difficulty-min="form.native_difficulty_min"
          v-model:difficulty-max="form.native_difficulty_max"
          v-model:tags="form.native_tags"
          bank-layout
          @apply="navigate()"
        >
          <template #after-picker>
            <label class="member-problem-favorite">
              <span>收藏</span>
              <select v-model="form.state">
                <option value="">全部</option>
                <option value="favorite">已收藏</option>
              </select>
            </label>
          </template>
        </LuoguFilters>
        <template v-else>
          <LuoguTagPicker
            :key="form.platform"
            class="member-problem-tag-slot"
            :platform="form.platform"
            :tags="tags"
            :model-value="selectedProblemTags"
            :loading="tagsBusy"
            :error="tagsError"
            @update:model-value="applyProblemTags"
            @retry="loadTags()"
          />
          <label class="member-problem-favorite">
            <span>收藏</span>
            <select v-model="form.state">
              <option value="">全部</option>
              <option value="favorite">已收藏</option>
            </select>
          </label>
        </template>
        <ProblemRangeFilters
          class="member-problem-difficulty"
          v-if="!isTracker && ['codeforces', 'atcoder'].includes(form.platform)"
          :filters="form"
          difficulty-only
          @change="Object.assign(form, $event)"
        />
        <div class="member-problem-filter-actions">
          <button class="btn primary">查询</button>
          <button type="button" class="btn" @click="clear">清除筛选</button>
        </div>
      </form>
      <p
        v-if="tagsError && form.platform !== 'codeforces'"
        class="member-problem-tags-error"
        role="alert"
      >
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
                ><br />{{ row.problem_name || '未命名题目' }}<br />
                <ProblemDifficulty :problem="row" class="bank-problem-difficulty" />
                <small v-if="row.time_basis === 'contest' && row.problem_time">
                  · 比赛时间 {{ date(row.problem_time) }}
                </small>
                <small v-if="row.ac_at"> · AC {{ date(row.ac_at) }}</small>
                <small v-else-if="current.scope === 'solved'"> · 已 AC，时间未知</small>
                <div v-if="row.platform === 'luogu'" class="bank-result-tags">
                  <LuoguBadges :problem="row" :difficulty="false" />
                </div>
                <div v-else-if="row.has_secondary" class="bank-result-tags">
                  <AlgorithmTag
                    v-for="tag in row.effective_tags"
                    :key="tag.id"
                    :tag="tag"
                    class="bank-result-tag"
                    :title="`${tag.id} · ${sourceLabels[tag.source] || tag.source}`"
                  >
                    {{ tag.name_zh
                    }}<small v-if="tag.source === 'manual_add'">人工</small></AlgorithmTag
                  ><span v-if="!row.effective_tags.length" class="muted">空标签</span
                  ><small class="bank-review-state">{{
                    reviewLabels[row.review_status] || row.review_status
                  }}</small>
                </div>
                <div v-else class="bank-result-tags">
                  <small class="muted">原站标签：</small
                  ><ProblemTags :tags="row.tags" :platform="row.platform" />
                  <small class="muted">算法标签待接入</small>
                </div>
              </div>
              <span class="chips bank-problem-actions"
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
              current.scope === 'solved' && current.platform === 'luogu'
                ? '暂无匹配的已保存洛谷 AC 记录。题库目录与成员记录分别同步。'
                : current.scope === 'solved'
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
.bank-problem-difficulty {
  margin-top: 9px;
}
.bank-problem-info {
  min-width: 0;
  overflow-wrap: anywhere;
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
}
.bank-result-tag small {
  font-size: 9px;
  margin-left: 5px;
  color: inherit;
}
.bank-review-state {
  font-size: 10px;
  color: var(--muted);
  margin-left: 4px;
}
.bank-edit-tags {
  border-color: #93b3a3;
  color: #176c60;
}
.member-problems #problem-list > .list-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
}
.bank-problem-actions {
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
}
@media (max-width: 640px) {
  .member-problems #problem-list > .list-item {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }
  .bank-problem-actions {
    flex-wrap: wrap;
    justify-content: flex-start;
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
  --filter-label-gap: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.65fr) minmax(168px, 18%);
  align-items: start;
  gap: 20px 24px;
  margin: 0 0 24px;
}
.member-problem-filters > label,
.member-problem-favorite {
  display: flex;
  flex-direction: column;
  gap: var(--filter-label-gap);
  min-width: 0;
}
.member-problem-filters :deep(.member-problem-tag-slot) {
  padding-block-start: calc(1.5em + var(--filter-label-gap));
}
.member-problem-favorite,
.member-problem-filters :deep(.member-problem-difficulty),
.member-problem-filter-actions {
  grid-column: 1 / -1;
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
  form.member-problem-filters {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 16px;
  }
  .member-problem-filters :deep(.member-problem-tag-slot) {
    padding-block-start: 0;
  }
  .member-problem-filters :deep(.problem-range-filters > label) {
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
