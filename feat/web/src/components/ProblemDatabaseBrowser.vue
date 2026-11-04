<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { date, useRequests } from '../lib/api.js';
import Pager from './Pager.vue';
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
const filters = reactive({ q: '', platform: '', status: 'all' });
const rows = ref([]),
  total = ref(0),
  page = ref(1),
  busy = ref(false),
  error = ref('');
const pageSize = 20;

function platformName(value) {
  return { codeforces: 'Codeforces', atcoder: 'AtCoder' }[value] || value;
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
function tagsText(tags) {
  return Array.isArray(tags) && tags.length ? tags.join(' · ') : '—';
}
async function load(nextPage = 1) {
  page.value = nextPage;
  busy.value = true;
  error.value = '';
  const params = new URLSearchParams({
    q: filters.q.trim(),
    platform: filters.platform,
    status: filters.status,
    page: String(page.value),
    page_size: String(pageSize),
    labels: selectedTags.value.join(','),
    match: matchMode.value,
  });
  try {
    const data = await request(`/admin/database/problems?${params}`, {}, 'database-problems');
    rows.value = data.items || [];
    facets.value = data.tag_facets || [];
    total.value = data.total || 0;
    page.value = data.page || 1;
  } catch (cause) {
    if (cause.name !== 'AbortError') error.value = cause.message || '读取题库记录失败。';
  } finally {
    busy.value = false;
  }
}
function reset() {
  filters.q = '';
  filters.platform = '';
  filters.status = 'all';
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
onMounted(() => {
  load();
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
        <p>
          直接对接爬虫保存的题面、公式与样例；在同一题目中查看 AI
          任务与人工标签。当前环境只允许离线预检。
        </p>
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
          ><select v-model="filters.platform">
            <option value="">全部平台</option>
            <option value="codeforces">Codeforces</option>
            <option value="atcoder">AtCoder</option>
          </select></label
        ><label
          ><span>题面状态</span
          ><select v-model="filters.status">
            <option value="all">全部</option>
            <option value="collected">已采集题面</option>
            <option value="pending">尚未采集</option>
            <option value="failed">最近采集失败</option>
          </select></label
        >
        <div class="problem-database-filter-actions">
          <button class="btn primary" type="submit" :disabled="busy">筛选</button>
          <button class="btn" type="button" :disabled="busy" @click="reset">重置</button>
        </div>
      </form>
      <div v-if="facets.length" class="admin-label-filter">
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
              <th>更新时间</th>
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
                <small
                  >比赛 {{ row.contest_id || '—' }} · 题序 {{ row.problem_index || '—' }}</small
                >
              </td>
              <td>{{ row.problem_rating ?? '—' }}</td>
              <td class="problem-database-tags">
                <span>{{ tagsText(row.tags) }}</span
                ><small>{{
                  row.has_secondary
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
                <small>{{ row.sample_count }} 组样例</small>
                <small v-if="row.translation_status === 'auto'" class="translation-ready">已翻译 · 未人工确认</small>
                <small v-else-if="row.translation_status === 'needs_review'">翻译待复核</small>
                <small v-else-if="row.translation_status">待翻译</small>
              </td>
              <td>{{ date(row.updated_at) }}</td>
              <td>
                <div class="problem-processing-actions">
                  <button class="btn" @click="openProcessing(row, 'translation')">AI 翻译</button>
                  <button class="btn" @click="openProcessing(row, 'annotation')">AI 标签</button>
                  <button class="btn" @click="openProcessing(row, 'manual')">人工标签</button>
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
