<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { auth, useRequests, notify } from '../lib/api.js';
import { adminFilters } from '../lib/admin.js';
const props = defineProps({ personal: { type: Boolean, default: false } });
const route = useRoute(),
  request = useRequests(),
  rows = ref([]),
  loading = ref(false),
  saving = ref(false),
  error = ref(''),
  saveError = ref(''),
  loaded = ref(null);
const form = reactive(
  (!props.personal && adminFilters.contests) || {
    ...(!props.personal ? { owner_qq_id: route.query.qq_id || auth.qq_id || '' } : {}),
    contest_id: typeof route.query.contest_id === 'string' ? route.query.contest_id : '',
  },
);
if (!props.personal) adminFilters.contests = form;
let revision = 0,
  disposed = false;
const states = {
  todo: '待处理',
  unsolved: '未通过',
  queued: '待补题',
  solved: '已解决',
  reviewed: '已复盘',
  ignored: '忽略',
};
async function load() {
  if (saving.value) return;
  const current = ++revision;
  rows.value = [];
  loaded.value = null;
  error.value = saveError.value = '';
  const params = {
    contest_id: form.contest_id.trim(),
    ...(!props.personal ? { owner_qq_id: form.owner_qq_id.trim() } : {}),
  };
  if (!params.contest_id) {
    loading.value = false;
    return;
  }
  if (!props.personal && !/^\d{4,12}$/.test(params.owner_qq_id)) {
    error.value = '请填写有效成员 QQ。';
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const data = await request(
      (props.personal ? '/me/contest/reviews?' : '/contest/reviews?') + new URLSearchParams(params),
      {},
      'contests',
    );
    if (!disposed && revision === current) {
      rows.value = data;
      loaded.value = params;
    }
  } catch (e) {
    if (!disposed && revision === current && e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (!disposed && revision === current) loading.value = false;
  }
}
async function save(row, event) {
  if (saving.value || loading.value || !loaded.value) {
    event.target.value = row.status;
    return;
  }
  const value = event.target.value,
    current = revision,
    params = { ...loaded.value, problem_id: row.problem_id, status: value };
  saving.value = true;
  saveError.value = '';
  try {
    await request(props.personal ? '/me/contest/reviews' : '/contest/reviews', {
      method: 'PUT',
      body: params,
    });
    if (!disposed && current === revision) {
      row.status = value;
      notify('逐题状态已保存');
    }
  } catch (e) {
    if (!disposed && e.name !== 'AbortError') saveError.value = e.message;
  } finally {
    if (!disposed) {
      event.target.value = row.status;
      saving.value = false;
    }
  }
}
onMounted(load);
onBeforeUnmount(() => {
  disposed = true;
  revision++;
});
</script>
<template>
  <section :class="props.personal ? 'card contest-review-panel' : 'admin-panel'">
    <form class="filters contest-review-filters" @submit.prevent="load">
      <label v-if="!props.personal"
        >成员 QQ<input
          v-model.trim="form.owner_qq_id"
          :disabled="saving"
          inputmode="numeric" /></label
      ><label
        >比赛 ID<input v-model.trim="form.contest_id" :disabled="saving" maxlength="80" /></label
      ><button class="btn primary" :disabled="saving">
        {{ loading ? '正在查询…' : '查询比赛题目' }}
      </button>
    </form>
    <p v-if="loading" role="status">正在加载比赛题目…</p>
    <div v-else-if="error" role="alert">
      <p>赛事复盘加载失败：{{ error }}</p>
      <button class="btn" @click="load">重试查询</button>
    </div>
    <template v-else-if="loaded">
      <p class="muted">正在查看比赛 {{ loaded.contest_id }} 的逐题复盘。</p>
      <p v-if="saveError" role="alert">状态保存失败：{{ saveError }}。请重新选择状态重试。</p>
      <article v-for="row in rows" :key="row.problem_id" class="list-item contest-review-row">
        <span
          ><b>{{ row.problem_id }}</b
          ><br />{{ row.verdict || '未记录结果' }} · 难度 {{ row.rating ?? '未知' }}</span
        ><label
          >逐题状态<select :value="row.status" :disabled="saving" @change="save(row, $event)">
            <option v-for="(label, key) in states" :key="key" :value="key">{{ label }}</option>
          </select></label
        >
      </article>
      <p v-if="!rows.length" class="empty">此比赛暂无题目记录，请先在个人中心同步提交数据。</p>
    </template>
    <p v-else class="empty">请输入比赛 ID 查询本人的逐题复盘。</p>
  </section>
</template>
<style scoped>
.contest-review-filters {
  align-items: flex-end;
  gap: 20px 24px;
  margin-bottom: 24px;
}
.contest-review-filters > label,
.contest-review-row > label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.contest-review-filters > label {
  flex: 1 1 220px;
  max-width: 460px;
}
.contest-review-filters input {
  width: 100%;
  min-width: 0;
}
.contest-review-row {
  align-items: center;
  flex-wrap: wrap;
  gap: 16px 24px;
}
.contest-review-row > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
