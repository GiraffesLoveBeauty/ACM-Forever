<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRequests, date } from '../lib/api.js';
import { memberFilters, memberQuery, problemLink } from '../lib/member-problems.js';
import Pager from '../components/Pager.vue';
import ProblemTracker from '../components/ProblemTracker.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive(memberFilters(route.query));
const rows = ref([]),
  total = ref(0),
  busy = ref(false),
  error = ref('');
const current = computed(() => memberFilters(route.query));
const isTracker = computed(() => current.value.view === 'tracker');
const platforms = computed(() => ({
  codeforces: 'Codeforces',
  atcoder: 'AtCoder',
  ...(!isTracker.value ? { luogu: '洛谷', nowcoder: '牛客', cjlu: '校 OJ' } : {}),
}));
let revision = 0;
async function load() {
  const version = ++revision;
  Object.assign(form, current.value);
  rows.value = [];
  error.value = '';
  busy.value = true;
  try {
    const { view, ...filters } = current.value;
    const data = await request(
      (view === 'tracker' ? '/me/problems/tracker?' : '/me/problems?') +
        new URLSearchParams({ ...filters, page_size: 20 }),
      {},
      'member-problems',
    );
    if (version !== revision) return;
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
function scope(value) {
  Object.assign(form, current.value, { scope: value });
  navigate();
}
function changeView(view) {
  Object.assign(form, memberFilters({ ...current.value, view, page: 1 }));
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
</script>
<template>
  <main class="community-main member-problems">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>题库</h1>
    <p>浏览站内题目，或查看本人已 AC 的题目。打开题面后可回到当前筛选与页码。</p>
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
      <p v-if="isTracker" class="muted tracker-description">
        按比赛查看 Codeforces / AtCoder 的站内目录。搜索、收藏与“我已
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
              <span
                ><b>{{ row.platform }} · {{ row.problem_id }}</b
                ><br />{{ row.problem_name || '未命名题目' }}<br /><small
                  >难度 {{ row.problem_rating ?? '未知' }} · {{ row.tags || '无标签'
                  }}<template v-if="row.ac_at"> · AC {{ date(row.ac_at) }}</template></small
                ></span
              >
              <span class="chips"
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
@media (max-width: 640px) {
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
