<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { date, useRequests } from '../lib/api.js';
import Pager from './Pager.vue';
import LuoguBadges from './LuoguBadges.vue';
import ProblemDifficulty from './ProblemDifficulty.vue';
import ProblemTags from './ProblemTags.vue';
import LuoguFilters from './LuoguFilters.vue';
import { nativeParams, nativeFilters } from '../lib/luogu-problems.js';
import { rangeFilters, rangeParams, timeLabel } from '../lib/problem-filters.js';
import ProblemRangeFilters from './ProblemRangeFilters.vue';
import AdminProblemProcessing from './AdminProblemProcessing.vue';

const request = useRequests();
const route = useRoute(),
  router = useRouter();
const active = ref(null),
  drawer = ref(null),
  facets = ref([]),
  selectedTags = ref([]),
  matchMode = ref('all'),
  labelSearch = ref('');
const visibleFacets = computed(() =>
  facets.value.filter(
    (t) =>
      (t.count || selectedTags.value.includes(t.id)) &&
      `${t.name_zh} ${t.id}`.toLowerCase().includes(labelSearch.value.toLowerCase()),
  ),
);
const filters = reactive({
  q: '',
  platform: '',
  status: 'all',
  native_difficulty: '',
  native_tag: '',
  ...nativeFilters(),
  ...rangeFilters(),
});
let restoringFilters = false;
watch(
  () => filters.platform,
  (platform) => {
    if (restoringFilters) return;
    if (platform === 'luogu') {
      selectedTags.value = [];
      matchMode.value = 'all';
      labelSearch.value = '';
    }
    Object.assign(filters, nativeFilters({ platform }), rangeFilters({ platform }));
  },
  { flush: 'sync' },
);
let revision = 0;
let pendingLoad = null;
const rows = ref([]),
  total = ref(0),
  page = ref(1),
  busy = ref(false),
  error = ref('');
const pageSize = 20;

function platformName(value) {
  return { codeforces: 'Codeforces', atcoder: 'AtCoder', luogu: '洛谷' }[value] || value;
}
function statusName(row) {
  if (row.last_fetch_status === 'failed')
    return row.content_available ? '已有题面，最近更新失败' : '采集失败';
  return row.content_available ? '题面已采集' : '目录已收录';
}
function statusClass(row) {
  if (row.last_fetch_status === 'failed') return 'failed';
  return row.content_available ? 'ready' : 'pending';
}
async function load(nextPage = 1, fromRoute = false) {
  if (!fromRoute) {
    const query = { ...route.query };
    for (const key of Object.keys(query)) if (key.startsWith('bank_')) delete query[key];
    const state = {
      q: filters.q.trim(),
      platform: filters.platform,
      status: filters.status,
      page: String(nextPage),
      ...nativeParams(filters),
      ...rangeParams(filters),
    };
    for (const [key, value] of Object.entries(state))
      if (
        value !== '' &&
        !(key === 'status' && value === 'all') &&
        !(key === 'page' && value === '1')
      )
        query['bank_' + key] = value;
    if (router.resolve({ path: route.path, query }).fullPath !== route.fullPath) {
      await router.push({ path: route.path, query });
      return;
    }
  }
  const params = new URLSearchParams({
    q: filters.q.trim(),
    platform: filters.platform,
    status: filters.status,
    page: String(nextPage),
    page_size: String(pageSize),
    labels: selectedTags.value.join(','),
    match: matchMode.value,
    ...nativeParams(filters),
    ...rangeParams(filters),
  });
  const query = params.toString();
  if (pendingLoad?.query === query) return pendingLoad.promise;
  const version = ++revision;
  page.value = nextPage;
  rows.value = [];
  facets.value = [];
  total.value = 0;
  busy.value = true;
  error.value = '';
  const promise = (async () => {
    try {
      const data = await request(`/admin/database/problems?${query}`, {}, 'database-problems');
      if (version !== revision) return;
      rows.value = data.items || [];
      facets.value = data.tag_facets || [];
      total.value = data.total || 0;
      page.value = data.page || 1;
    } catch (cause) {
      if (version === revision && cause.name !== 'AbortError')
        error.value = cause.message || '读取题库记录失败。';
    } finally {
      // A replaced request must not clear the latest request's loading state.
      if (version === revision) {
        busy.value = false;
        pendingLoad = null;
      }
    }
  })();
  pendingLoad = { query, promise };
  return promise;
}
function reset() {
  filters.q = '';
  filters.platform = '';
  filters.status = 'all';
  Object.assign(filters, nativeFilters(), rangeFilters());
  selectedTags.value = [];
  matchMode.value = 'all';
  labelSearch.value = '';
  load(1);
}
function toggleTag(id) {
  selectedTags.value = selectedTags.value.includes(id)
    ? selectedTags.value.filter((t) => t !== id)
    : [...selectedTags.value, id];
  load(1);
}
function openProcessing(row, action) {
  if (row.platform === 'luogu') return;
  active.value = { ...row, action };
}
function closeProcessing() {
  active.value = null;
  if (route.query.action) {
    const query = { ...route.query };
    delete query.action;
    delete query.platform;
    delete query.problem_id;
    router.replace({ path: route.path, query });
  }
}

defineExpose({ refresh: () => load(page.value) });
watch(
  () => route.fullPath,
  () => {
    const raw = Object.fromEntries(
      Object.entries(route.query)
        .filter(([key]) => key.startsWith('bank_'))
        .map(([key, value]) => [key.slice(5), value]),
    );
    const platform = ['atcoder', 'codeforces', 'luogu'].includes(raw.platform) ? raw.platform : '';
    restoringFilters = true;
    Object.assign(
      filters,
      {
        q: typeof raw.q === 'string' ? raw.q.slice(0, 160) : '',
        platform,
        status: ['all', 'collected', 'pending', 'failed'].includes(raw.status) ? raw.status : 'all',
      },
      nativeFilters({ ...raw, platform }),
      rangeFilters({ ...raw, platform }),
    );
    restoringFilters = false;
    const nextPage = /^[1-9][0-9]{0,6}$/.test(String(raw.page)) ? Number(raw.page) : 1;
    load(nextPage, true);
  },
  { immediate: true },
);
onMounted(() => {
  if (
    route.query.platform &&
    route.query.problem_id &&
    ['annotation', 'translation', 'manual'].includes(route.query.action)
  )
    openProcessing(
      { platform: String(route.query.platform), problem_id: String(route.query.problem_id) },
      route.query.action,
    );
});
</script>

<template>
  <section class="admin-section" aria-labelledby="problem-database-browser-heading">
    <div class="admin-section-heading">
      <div>
        <h2 id="problem-database-browser-heading">题库记录</h2>
        <p>浏览采集保存的题面与样例，使用各平台原生难度和标签筛选。默认按题目时间从新到旧排列。</p>
      </div>
      <button class="btn" type="button" :disabled="busy" @click="load(page)">
        {{ busy ? '正在读取…' : '刷新记录' }}
      </button>
    </div>
    <div class="admin-panel">
      <form class="admin-filter-row problem-database-filters" @submit.prevent="load(1)">
        <label class="problem-database-search"
          ><span>搜索题目</span
          ><input v-model="filters.q" type="search" placeholder="题号、题名或比赛 ID" /> </label
        ><label
          ><span>平台</span
          ><select v-model="filters.platform" @change="load(1)">
            <option value="">全部平台</option>
            <option value="codeforces">Codeforces</option>
            <option value="atcoder">AtCoder</option>
            <option value="luogu">洛谷</option>
          </select></label
        ><label
          ><span>题面状态</span
          ><select v-model="filters.status" @change="load(1)">
            <option value="all">全部</option>
            <option value="collected">已采集题面</option>
            <option value="pending">尚未采集</option>
            <option value="failed">最近采集失败</option>
          </select></label
        >
        <LuoguFilters
          v-if="filters.platform === 'luogu'"
          v-model:difficulty="filters.native_difficulty"
          v-model:tag="filters.native_tag"
          v-model:difficulty-min="filters.native_difficulty_min"
          v-model:difficulty-max="filters.native_difficulty_max"
          v-model:tags="filters.native_tags"
          @apply="load(1)"
        />
        <ProblemRangeFilters :filters="filters" @change="Object.assign(filters, $event)" />
        <div class="problem-database-filter-actions">
          <button class="btn primary" type="submit">筛选</button>
          <button class="btn" type="button" @click="reset">重置</button>
        </div>
      </form>
      <div v-if="filters.platform !== 'luogu' && facets.length" class="admin-label-filter">
        <label
          >按最终算法标签筛选
          <input
            v-model="labelSearch"
            type="search"
            placeholder="中文标签或英文 ID"
            aria-label="搜索后台标签"
        /></label>
        <label
          >组合方式
          <select v-model="matchMode" @change="load(1)">
            <option value="all">同时包含所选标签</option>
            <option value="any">包含任一所选标签</option>
          </select></label
        >
        <div class="chips">
          <button
            v-for="t in visibleFacets"
            :key="t.id"
            :data-admin-tag="t.id"
            class="btn"
            :class="{ primary: selectedTags.includes(t.id) }"
            :aria-pressed="selectedTags.includes(t.id)"
            @click="toggleTag(t.id)"
          >
            {{ t.name_zh }} · {{ t.count }}
          </button>
        </div>
        <p v-if="!visibleFacets.length" class="muted">没有匹配的有效标签。</p>
      </div>
      <div class="admin-table-meta">
        <span>共 {{ total }} 条数据库记录</span>
        <span>每页 {{ pageSize }} 条</span>
      </div>
      <p v-if="error" class="admin-message" role="alert">读取失败：{{ error }}</p>
      <p v-else-if="busy && !rows.length" class="admin-message" role="status">正在读取题库记录…</p>
      <p v-else-if="!rows.length" class="admin-message">没有匹配的题库记录。</p>
      <div v-if="rows.length" class="admin-table-wrap">
        <table class="admin-table problem-database-table">
          <thead>
            <tr>
              <th>平台</th>
              <th>题号</th>
              <th>题目</th>
              <th>难度</th>
              <th>标签</th>
              <th>题面与样例</th>
              <th>题目时间</th>
              <th>题面与处理</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="`${row.platform}-${row.problem_id}`">
              <td>{{ platformName(row.platform) }}</td>
              <td>
                <code>{{ row.problem_id }}</code>
              </td>
              <td class="problem-database-title">
                <b>{{ row.problem_name || '未命名题目' }}</b>
                <small v-if="row.platform === 'luogu'">公开 P 题库 · 独立题目</small>
                <small v-else
                  >比赛 {{ row.contest_id || '—' }} · 题序 {{ row.problem_index || '—' }}</small
                >
              </td>
              <td>
                <ProblemDifficulty :problem="row" />
              </td>
              <td class="problem-database-tags">
                <LuoguBadges v-if="row.platform === 'luogu'" :problem="row" :difficulty="false" />
                <ProblemTags v-else :tags="row.tags" :platform="row.platform" />
                <small>{{
                  row.platform === 'luogu'
                    ? '洛谷原生标签 · 随源站同步'
                    : row.has_secondary
                      ? row.manual_history_count
                        ? '含人工历史 · 最终有效标签'
                        : '自动标签 · 未人工确认'
                      : '爬虫原始标签 · 尚未二次处理'
                }}</small>
              </td>
              <td>
                <span class="problem-database-status" :class="statusClass(row)">
                  {{ statusName(row) }}
                </span>
                <small>{{
                  row.content_available && !row.sample_count
                    ? '源题未提供样例'
                    : row.sample_count + ' 组样例'
                }}</small>
                <small v-if="row.translation_status === 'auto'" class="translation-ready"
                  >已翻译 · 未人工确认</small
                >
                <small v-else-if="row.translation_status === 'needs_review'">翻译待复核</small>
                <small v-else-if="row.translation_status">待翻译</small>
              </td>
              <td>
                <span>{{ date(row.problem_time) }}</span
                ><small>{{ timeLabel(row) }}</small
                ><small>最近同步 {{ date(row.updated_at) }}</small>
              </td>
              <td>
                <div class="problem-processing-actions">
                  <button
                    v-if="row.platform !== 'luogu'"
                    class="btn"
                    @click="openProcessing(row, 'translation')"
                  >
                    AI 翻译
                  </button>
                  <button
                    v-if="row.platform !== 'luogu'"
                    class="btn"
                    @click="openProcessing(row, 'annotation')"
                  >
                    AI 标签
                  </button>
                  <button
                    v-if="row.platform !== 'luogu'"
                    class="btn"
                    @click="openProcessing(row, 'manual')"
                  >
                    人工标签
                  </button>
                  <RouterLink
                    class="btn"
                    :to="{
                      path: '/problem.html',
                      query: { platform: row.platform, problem_id: row.problem_id },
                    }"
                    target="_blank"
                    rel="noopener"
                    >{{ row.content_available ? '查看题面' : '查看记录' }}</RouterLink
                  >
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager :page="page" :total="total" :size="pageSize" :busy="busy" @change="load" />
    </div>
    <AdminProblemProcessing
      v-if="active"
      ref="drawer"
      :key="`${active.platform}:${active.problem_id}`"
      :platform="active.platform"
      :problem-id="active.problem_id"
      :action="active.action"
      @close="closeProcessing"
      @saved="load(page)"
    />
  </section>
</template>

<style scoped>
.admin-label-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin: 10px 0 24px;
  padding: 18px;
  background: #176c6007;
  border: 1px solid #176c6026;
  border-radius: 8px;
}
.admin-label-filter > label {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.admin-label-filter > .chips {
  width: 100%;
  gap: 8px;
}
.problem-processing-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 180px;
}
.problem-processing-actions > .btn {
  font-size: 12px;
  padding: 8px 10px;
}
.problem-database-tags small {
  display: block;
  margin-top: 6px;
  color: var(--muted, #697970);
}
.problem-database-filters {
  align-items: flex-end;
  gap: 20px 24px;
  margin-bottom: 24px;
}
.problem-database-filters > label {
  display: flex;
  flex: 1 1 180px;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.problem-database-filters > .problem-database-search {
  flex: 2 1 280px;
}
.problem-database-filters label > span {
  line-height: 1.5;
  white-space: nowrap;
}
.problem-database-filters :is(input, select) {
  width: 100%;
  min-width: 0;
  min-height: 44px;
}
.problem-database-filter-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}
@media (max-width: 640px) {
  .problem-database-filters > label,
  .problem-database-filters > .problem-database-search {
    flex-basis: 100%;
  }
  .problem-database-filter-actions {
    width: 100%;
  }
  .problem-database-filter-actions > .btn {
    flex: 1;
  }
}
</style>
