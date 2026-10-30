<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRequests, date } from '../lib/api.js';
import { memberFilters, memberQuery, problemLink } from '../lib/member-problems.js';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive(memberFilters(route.query));
const rows = ref([]),
  total = ref(0),
  busy = ref(false),
  error = ref('');
const current = computed(() => memberFilters(route.query));
let revision = 0;
async function load() {
  const version = ++revision;
  Object.assign(form, current.value);
  rows.value = [];
  error.value = '';
  busy.value = true;
  try {
    const data = await request(
      '/me/problems?' + new URLSearchParams({ ...current.value, page_size: 20 }),
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
  Object.assign(form, memberFilters({ scope: current.value.scope }));
  navigate();
}
watch(() => route.fullPath, load, { immediate: true });
</script>
<template>
  <main class="community-main member-problems">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>题库</h1>
    <p>浏览站内题目，或查看本人已 AC 的题目。打开题面后可回到当前筛选与页码。</p>
    <div class="chips" aria-label="题库范围">
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
      <form class="filters" @submit.prevent="navigate()">
        <label
          >平台<select v-model="form.platform">
            <option value="">全部平台</option>
            <option
              v-for="(label, key) in {
                codeforces: 'Codeforces',
                atcoder: 'AtCoder',
                luogu: '洛谷',
                nowcoder: '牛客',
                cjlu: '校 OJ',
              }"
              :key="key"
              :value="key"
            >
              {{ label }}
            </option>
          </select></label
        >
        <label
          >搜索<input v-model="form.tag" maxlength="100" placeholder="题号、题名或标签"
        /></label>
        <label
          >收藏<select v-model="form.state">
            <option value="">全部</option>
            <option value="favorite">已收藏</option>
          </select></label
        >
        <button class="btn primary" :disabled="busy">查询</button
        ><button type="button" class="btn" @click="clear">清除筛选</button>
      </form>
      <p v-if="busy" role="status">正在加载题目…</p>
      <div v-else-if="error" role="alert">
        <p>题目加载失败：{{ error }}</p>
        <button class="btn" @click="load">重试</button>
      </div>
      <template v-else>
        <p class="muted">
          {{ current.scope === 'solved' ? '本人已 AC' : '全站目录' }} · 共 {{ total }} 道题目
        </p>
        <div id="problem-list">
          <article v-for="row in rows" :key="`${row.platform}-${row.problem_id}`" class="list-item">
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
        <Pager :page="current.page" :total="total" :busy="busy" @change="navigate" />
      </template>
    </section>
  </main>
</template>
