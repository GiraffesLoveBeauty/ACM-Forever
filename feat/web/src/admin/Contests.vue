<script setup>
import { ref, reactive, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { auth, useRequests, showError, notify } from '../lib/api.js';
import { adminFilters } from '../lib/admin.js';
const route = useRoute(),
  request = useRequests(),
  rows = ref([]),
  busy = ref(false);
const form = reactive(
  adminFilters.contests || {
    owner_qq_id: route.query.qq_id || auth.qq_id || '',
    contest_id: route.query.contest_id || '',
  },
);
adminFilters.contests = form;
let loaded = {};
const states = {
  todo: '待处理',
  unsolved: '未通过',
  queued: '待补题',
  solved: '已解决',
  reviewed: '已复盘',
  ignored: '忽略',
};
async function load() {
  if (!form.contest_id || !form.owner_qq_id) return;
  try {
    const params = { ...form };
    rows.value = await request('/contest/reviews?' + new URLSearchParams(params), {}, 'contests');
    loaded = params;
  } catch (e) {
    showError(e);
  }
}
async function save(row, value) {
  busy.value = true;
  try {
    await request('/contest/reviews', {
      method: 'PUT',
      body: { ...loaded, problem_id: row.problem_id, status: value },
    });
    row.status = value;
    notify('逐题状态已保存');
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="admin-panel">
    <form class="filters" @submit.prevent="load">
      <label v-if="auth.role !== 'member'"
        >成员 QQ<input v-model.trim="form.owner_qq_id" inputmode="numeric" /></label
      ><label>比赛 ID<input v-model.trim="form.contest_id" /></label
      ><button class="btn primary">查询比赛题目</button>
    </form>
    <article v-for="row in rows" :key="row.problem_id" class="list-item">
      <span
        ><b>{{ row.problem_id }}</b
        ><br />{{ row.verdict || '未记录结果' }} · 难度 {{ row.rating ?? '未知' }}</span
      ><label
        >逐题状态<select
          :value="row.status"
          :disabled="busy"
          @change="save(row, $event.target.value)"
        >
          <option v-for="(label, key) in states" :key="key" :value="key">{{ label }}</option>
        </select></label
      >
    </article>
    <p v-if="!rows.length" class="empty">请输入比赛 ID 查询。无题目记录时请先同步提交数据。</p>
  </section>
</template>
