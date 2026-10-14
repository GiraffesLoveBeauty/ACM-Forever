<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { auth, useRequests, external, showError, notify } from '../lib/api.js';
import { adminFilters } from '../lib/admin.js';
const route = useRoute(),
  request = useRequests();
const form = reactive(
  adminFilters.training || {
    owner: route.query.qq_id || auth.qq_id || '',
    platform: '',
    tag: '',
    weak_tag: false,
    difficulty: '',
  },
);
adminFilters.training = form;
const rows = ref([]),
  zones = ref([null, null, null]),
  busy = ref(false);
const specs = {
  codeforces: { min: 800, max: 3500, value: 1000 },
  atcoder: { min: 0, max: 4000, value: 800 },
  luogu: {
    values: [
      '未评定',
      '入门',
      '普及-',
      '普及/提高-',
      '普及+/提高',
      '提高+/省选-',
      '省选/NOI-',
      'NOI/NOI+/CTSC',
    ],
    value: '普及-',
  },
  nowcoder: { values: ['1星', '2星', '3星', '4星', '5星'], value: '2星' },
};
const spec = computed(() => specs[form.platform]);
const difficulties = computed(() => {
  if (!spec.value) return [null, null, null];
  if (spec.value.values) {
    const values = spec.value.values,
      i = values.indexOf(form.difficulty);
    return [
      values[Math.max(0, i - 1)],
      form.difficulty,
      values[Math.min(values.length - 1, i + 1)],
    ];
  }
  const s = spec.value,
    value = Math.max(s.min, Math.min(s.max, Number(form.difficulty) || s.value));
  return [Math.max(s.min, value - 150), value, Math.min(s.max, value + 150)];
});
watch(
  () => form.platform,
  () => {
    form.difficulty = spec.value?.value || '';
  },
);
async function history() {
  try {
    rows.value = await request(
      '/challenge/list?qq_id=' + encodeURIComponent(form.owner),
      {},
      'history',
    );
  } catch (e) {
    showError(e);
  }
}
async function generate() {
  if (busy.value) return;
  if (!/^\d{4,12}$/.test(form.owner)) return notify('请填写有效成员 QQ。');
  busy.value = true;
  const config = { ...form },
    values = [...difficulties.value];
  let tag = config.tag;
  try {
    for (let i = 0; i < 3; i++) {
      zones.value[i] = { loading: true };
      try {
        const row = await request('/challenge/start', {
          method: 'POST',
          body: {
            platform: config.platform,
            tag,
            difficulty: values[i],
            owner_qq_id: config.owner,
            weak_tag: config.weak_tag,
          },
        });
        if (config.weak_tag && row.weak_tag) tag = row.weak_tag;
        zones.value[i] = row;
      } catch (e) {
        if (e.name === 'AbortError') return;
        zones.value[i] = { error: e.message };
      }
    }
    await history();
    notify('训练已生成');
  } finally {
    busy.value = false;
  }
}
watch(() => form.owner, history);
onMounted(history);
</script>
<template>
  <section class="admin-panel">
    <form class="filters" @submit.prevent="generate">
      <label v-if="auth.role !== 'member'"
        >成员 QQ<input v-model.trim="form.owner" :disabled="busy" inputmode="numeric" /></label
      ><label
        >平台<select v-model="form.platform" :disabled="busy">
          <option value="">全部平台</option>
          <option
            v-for="(label, key) in {
              codeforces: 'Codeforces',
              luogu: '洛谷',
              atcoder: 'AtCoder',
              nowcoder: '牛客',
            }"
            :key="key"
            :value="key"
          >
            {{ label }}
          </option>
        </select></label
      ><label>算法标签 / 题名 / 题号<input v-model="form.tag" :disabled="busy" /></label
      ><label class="chip"
        ><input v-model="form.weak_tag" type="checkbox" :disabled="busy" />按弱项训练</label
      ><label
        >难度<select v-if="spec?.values" v-model="form.difficulty" :disabled="busy">
          <option v-for="value in spec.values" :key="value">{{ value }}</option></select
        ><input
          v-else-if="spec"
          v-model="form.difficulty"
          type="number"
          :min="spec.min"
          :max="spec.max"
          step="100"
          :disabled="busy" /><input v-else value="不限难度" disabled /></label
      ><button class="btn primary" :disabled="busy">
        {{ busy ? '生成中…' : '重新生成今日训练' }}
      </button>
    </form>
    <p class="muted">三个训练区使用相邻难度，数字难度按目标值 ±150 分档。</p>
  </section>
  <section class="grid three">
    <article v-for="(label, i) in ['稳定基础', '主训练', '突破上限']" :key="i" class="card">
      <div class="label">
        {{ ['巩固区', '同段区', '挑战区'][i] }} · {{ difficulties[i] ?? '不限' }}
      </div>
      <h2>{{ label }}</h2>
      <template v-if="zones[i] && !zones[i].loading && !zones[i].error"
        ><b>{{ zones[i].problem_name || zones[i].problem_id }}</b>
        <p>{{ zones[i].platform }} · 难度 {{ zones[i].problem_rating ?? '未知' }}</p>
        <p class="muted">{{ zones[i].recommendation_reason }}</p>
        <a class="btn primary" :href="external(zones[i].problem_url)" target="_blank" rel="noopener"
          >打开题目 →</a
        ></template
      >
      <p v-else>{{ zones[i]?.error || (zones[i]?.loading ? '正在生成…' : '等待生成') }}</p>
    </article>
  </section>
  <section class="admin-panel">
    <h2>挑战历史</h2>
    <article v-for="(row, i) in rows" :key="i" class="list-item">
      <span
        ><b>{{ row.problem_name || row.problem_id }}</b
        ><br />{{ row.platform }} · {{ row.status }} · {{ row.problem_rating ?? '未知' }}</span
      ><span>{{ row.created_at }}</span>
    </article>
    <p v-if="!rows.length" class="empty">暂无挑战记录。</p>
  </section>
</template>
