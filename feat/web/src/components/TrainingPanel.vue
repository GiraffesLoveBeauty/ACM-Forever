<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { auth, useRequests, date, notify } from '../lib/api.js';
import { adminFilters } from '../lib/admin.js';
import { problemLink } from '../lib/member-problems.js';
const props = defineProps({ personal: { type: Boolean, default: false } });
const route = useRoute(),
  request = useRequests();
const form = reactive(
  (!props.personal && adminFilters.training) || {
    ...(!props.personal ? { owner: route.query.qq_id || auth.qq_id || '' } : {}),
    platform: '',
    tag: '',
    weak_tag: false,
    difficulty: '',
  },
);
if (!props.personal) adminFilters.training = form;
const rows = ref([]),
  zones = ref([null, null, null]),
  busy = ref(false),
  historyBusy = ref(true),
  historyError = ref('');
let historyRevision = 0,
  disposed = false;
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
  const revision = ++historyRevision;
  rows.value = [];
  historyBusy.value = true;
  historyError.value = '';
  try {
    const data = await request(
      props.personal
        ? '/me/training/challenges'
        : '/challenge/list?qq_id=' + encodeURIComponent(form.owner),
      {},
      'history',
    );
    if (!disposed && revision === historyRevision) rows.value = data;
  } catch (e) {
    if (!disposed && revision === historyRevision && e.name !== 'AbortError')
      historyError.value = e.message;
  } finally {
    if (!disposed && revision === historyRevision) historyBusy.value = false;
  }
}
async function generate() {
  if (busy.value) return;
  if (!props.personal && !/^\d{4,12}$/.test(form.owner)) return notify('请填写有效成员 QQ。');
  busy.value = true;
  const config = { ...form },
    values = [...difficulties.value];
  let tag = config.tag,
    generated = 0;
  zones.value = [null, null, null];
  try {
    for (let i = 0; i < 3; i++) {
      zones.value[i] = { loading: true };
      try {
        const row = await request(props.personal ? '/me/challenge/start' : '/challenge/start', {
          method: 'POST',
          body: {
            platform: config.platform,
            tag,
            difficulty: values[i],
            ...(!props.personal ? { owner_qq_id: config.owner } : {}),
            weak_tag: config.weak_tag,
          },
        });
        if (disposed) return;
        if (config.weak_tag && row.weak_tag) tag = row.weak_tag;
        zones.value[i] = row;
        generated++;
      } catch (e) {
        if (e.name === 'AbortError' || disposed) return;
        zones.value[i] = { error: e.message };
      }
    }
    await history();
    if (!disposed)
      notify(generated ? `已生成 ${generated} 道训练题` : '训练未能生成，请查看各训练区提示。');
  } finally {
    if (!disposed) busy.value = false;
  }
}
if (!props.personal) watch(() => form.owner, history);
onMounted(history);
onBeforeUnmount(() => {
  disposed = true;
  historyRevision++;
});
</script>
<template>
  <section :class="props.personal ? 'card training-filter-panel' : 'admin-panel'">
    <form class="filters training-filters" @submit.prevent="generate">
      <label v-if="!props.personal"
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
      ><label class="training-weak-toggle"
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
  <section class="grid three training-zones" aria-label="训练题目">
    <article v-for="(label, i) in ['稳定基础', '主训练', '突破上限']" :key="i" class="card">
      <div class="label">
        {{ ['巩固区', '同段区', '挑战区'][i] }} · {{ difficulties[i] ?? '不限' }}
      </div>
      <h2>{{ label }}</h2>
      <template v-if="zones[i] && !zones[i].loading && !zones[i].error"
        ><b>{{ zones[i].problem_name || zones[i].problem_id }}</b>
        <p>{{ zones[i].platform }} · 难度 {{ zones[i].problem_rating ?? '未知' }}</p>
        <p class="muted">{{ zones[i].recommendation_reason }}</p>
        <RouterLink class="btn primary" :to="problemLink(zones[i], '/home.html')"
          >打开题目 →</RouterLink
        ></template
      >
      <p v-else :role="zones[i]?.error ? 'alert' : 'status'">
        {{ zones[i]?.error || (zones[i]?.loading ? '正在生成…' : '等待生成') }}
      </p>
    </article>
  </section>
  <section :class="props.personal ? 'card training-history' : 'admin-panel'">
    <h2>挑战历史</h2>
    <p v-if="historyBusy" role="status">正在加载挑战历史…</p>
    <div v-else-if="historyError" role="alert">
      <p>挑战历史加载失败：{{ historyError }}</p>
      <button class="btn" @click="history">重试加载历史</button>
    </div>
    <template v-else>
      <article v-for="(row, i) in rows" :key="row.id ?? i" class="list-item training-history-row">
        <span
          ><RouterLink :to="problemLink(row, '/home.html')"
            ><b>{{ row.problem_name || row.problem_id }}</b></RouterLink
          ><br />{{ row.platform }} · {{ row.status }} · {{ row.problem_rating ?? '未知' }}</span
        ><time>{{ date(row.created_at) }}</time>
      </article>
      <p v-if="!rows.length" class="empty">暂无挑战记录。</p>
    </template>
  </section>
</template>
<style scoped>
.training-filter-panel,
.training-zones {
  margin-bottom: 24px;
}
.training-filters {
  align-items: flex-end;
  gap: 20px 24px;
}
.training-filters > label:not(.training-weak-toggle) {
  display: flex;
  flex: 1 1 170px;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.training-filters :is(input, select) {
  min-width: 0;
  max-width: 100%;
}
.training-weak-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
}
.training-weak-toggle input {
  width: auto;
}
.training-zones > article,
.training-history-row > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.training-history-row {
  flex-wrap: wrap;
  gap: 12px;
}
.training-history-row time {
  color: var(--muted);
}
</style>
