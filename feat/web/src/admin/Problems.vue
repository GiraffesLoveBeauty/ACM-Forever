<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { auth, useRequests, external, showError, notify } from '../lib/api.js';
import { adminFilters } from '../lib/admin.js';
import Pager from '../components/Pager.vue';
import ProblemCollection from '../components/ProblemCollection.vue';
const route = useRoute(),
  request = useRequests(),
  rows = ref([]),
  total = ref(0),
  page = ref(1),
  busy = ref(false);
const manager = computed(() => ['admin', 'root'].includes(auth.role));
const form = reactive(
  adminFilters.problems || {
    owner_qq_id: route.query.qq_id || auth.qq_id || '',
    platform: '',
    tag: '',
    state: '',
  },
);
adminFilters.problems = form;
let loadedOwner = '';
async function load(value = 1) {
  page.value = value;
  busy.value = true;
  const owner = form.owner_qq_id;
  try {
    const data = await request(
      '/problems?' + new URLSearchParams({ ...form, page: value, page_size: 20 }),
      {},
      'problems',
    );
    rows.value = Array.isArray(data) ? data : data.items;
    total.value = data.total ?? rows.value.length;
    loadedOwner = owner;
    busy.value = false;
  } catch (e) {
    if (e.name !== 'AbortError') {
      busy.value = false;
      showError(e);
    }
  }
}
async function favorite(row) {
  if (!/^\d{4,12}$/.test(loadedOwner)) return notify('请填写成员 QQ 后查询并保存收藏。');
  try {
    await request(
      `/problems/${encodeURIComponent(row.platform)}/${encodeURIComponent(row.problem_id)}/state`,
      { method: 'PUT', body: { owner_qq_id: loadedOwner, is_favorite: !row.is_favorite } },
    );
    await load(page.value);
  } catch (e) {
    showError(e);
  }
}
onMounted(() => load());
</script>
<template>
  <ProblemCollection v-if="manager" @published="load(page)" />
  <section class="admin-panel">
    <form class="filters" @submit.prevent="load()">
      <label v-if="auth.role !== 'member'"
        >成员 QQ<input v-model.trim="form.owner_qq_id" inputmode="numeric" /></label
      ><label
        >平台<select v-model="form.platform">
          <option value="">全部平台</option>
          <option v-for="p in ['codeforces', 'luogu', 'atcoder', 'nowcoder']" :key="p">
            {{ p }}
          </option>
        </select></label
      ><label>搜索<input v-model="form.tag" placeholder="题号、题名或标签" /></label
      ><label
        >收藏<select v-model="form.state">
          <option value="">全部题目</option>
          <option value="favorite">已收藏</option>
        </select></label
      ><button class="btn primary">筛选题目</button>
    </form>
    <p class="muted">共 {{ total }} 道题目 · 数据来自本地同步库</p>
    <article v-for="row in rows" :key="`${row.platform}-${row.problem_id}`" class="list-item">
      <span
        ><b>{{ row.platform }} · {{ row.problem_id }}</b
        ><br />{{ row.problem_name || '未命名题目' }}<br /><small
          >难度 {{ row.problem_rating ?? '未知' }} · {{ row.tags || '无标签' }}</small
        ></span
      ><span class="chips"
        ><button class="btn" :disabled="busy" @click="favorite(row)">
          {{ row.is_favorite ? '取消收藏' : '收藏' }}</button
        ><a class="btn" :href="external(row.problem_url)" target="_blank" rel="noopener"
          >打开题目</a
        ></span
      >
    </article>
    <p v-if="!rows.length" class="empty">没有匹配题目，请调整筛选或同步数据。</p>
    <Pager :page="page" :total="total" :busy="busy" @change="load" />
  </section>
</template>
