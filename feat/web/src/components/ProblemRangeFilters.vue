<script setup>
import { computed } from 'vue';
import { localTime, timeValue } from '../lib/problem-filters.js';
const props = defineProps({ filters: { type: Object, required: true }, collection: Boolean });
const emit = defineEmits(['change']);
const numeric = computed(
  () => !props.collection && ['codeforces', 'atcoder'].includes(props.filters.platform),
);
const basis = computed(
  () =>
    props.filters.time_basis ||
    (props.filters.platform === 'luogu' ? 'first_seen' : props.collection ? 'contest' : 'auto'),
);
function setTime(key, value) {
  emit('change', { [key]: timeValue(value) });
}
</script>
<template>
  <div class="problem-range-filters">
    <template v-if="numeric">
      <label
        ><span>{{ filters.platform === 'codeforces' ? 'CF rating 下限' : 'AtCoder 难度下限' }}</span
        ><input
          type="number"
          min="0"
          max="100000"
          step="1"
          :value="filters.rating_min"
          @input="emit('change', { rating_min: $event.target.value })"
          placeholder="不限"
      /></label>
      <label
        ><span>{{ filters.platform === 'codeforces' ? 'CF rating 上限' : 'AtCoder 难度上限' }}</span
        ><input
          type="number"
          min="0"
          max="100000"
          step="1"
          :value="filters.rating_max"
          @input="emit('change', { rating_max: $event.target.value })"
          placeholder="不限"
      /></label>
    </template>
    <label
      ><span>时间依据</span
      ><select :value="basis" @change="emit('change', { time_basis: $event.target.value })">
        <option v-if="!collection" value="auto">题目时间（比赛 / 首次收录）</option>
        <option v-if="filters.platform !== 'luogu'" value="contest">比赛时间</option>
        <option value="first_seen">本站首次收录时间</option>
      </select></label
    >
    <label
      ><span>开始时间（北京时间）</span
      ><input
        type="datetime-local"
        :value="localTime(filters.start_at)"
        @change="setTime('start_at', $event.target.value)"
    /></label>
    <label
      ><span>结束时间（不含，北京时间）</span
      ><input
        type="datetime-local"
        :value="localTime(filters.end_at)"
        @change="setTime('end_at', $event.target.value)"
    /></label>
    <p v-if="filters.platform === 'luogu'">
      洛谷仅公开 P 题；缺少可靠发布时间，按本站首次收录时间筛选。首次建库请选择全部。
    </p>
    <p v-else-if="filters.platform === 'atcoder'">
      数值为 AtCoder Problems 估计难度，包含区间两端；没有估计难度的题目不计入数值区间。
    </p>
    <p v-else-if="numeric">
      使用 Codeforces 原始 rating，包含区间两端；无 rating 的题目不计入数值区间。
    </p>
  </div>
</template>
<style scoped>
.problem-range-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  flex: 1 1 100%;
  min-width: 0;
  align-items: flex-end;
}
label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1 1 160px;
  min-width: 0;
}
input,
select {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 44px;
  box-sizing: border-box;
}
p {
  flex-basis: 100%;
  margin: 0;
  color: var(--muted, #697970);
  font-size: 12px;
  line-height: 1.8;
}
</style>
