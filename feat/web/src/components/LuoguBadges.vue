<script setup>
import { computed } from 'vue';
import { nativeColor } from '../lib/luogu-problems.js';
const props = defineProps({
  problem: { type: Object, required: true },
  difficulty: { type: Boolean, default: true },
  tags: { type: Boolean, default: true },
});
const level = computed(() => props.problem.native_difficulty || {});
const labels = computed(() =>
  Array.isArray(props.problem.native_tags) ? props.problem.native_tags : [],
);
const difficultyName = computed(
  () => level.value.name || (level.value.id == null ? '难度待收录' : '难度 #' + level.value.id),
);
</script>
<template>
  <span class="luogu-badges">
    <span
      v-if="difficulty"
      class="luogu-difficulty"
      :style="{ '--native-color': nativeColor(level.color) }"
      :title="level.id == null ? '尚无洛谷原生难度信息' : '洛谷原生难度 · ID ' + level.id"
    >
      <i aria-hidden="true"></i>{{ difficultyName }}
    </span>
    <template v-if="tags">
      <span
        v-for="tag in labels"
        :key="tag.id"
        class="luogu-tag"
        :style="{ '--native-color': nativeColor(tag.category?.color) }"
        :title="(tag.category?.name || '未分类') + ' · 原生标签 ID ' + tag.id"
      >
        <i aria-hidden="true"></i>{{ tag.name || '标签 #' + tag.id }}
      </span>
      <span v-if="!labels.length" class="luogu-empty-tag">暂无原生标签</span>
    </template>
  </span>
</template>
<style scoped>
.luogu-badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  max-width: 100%;
  vertical-align: middle;
}
.luogu-difficulty,
.luogu-tag {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid color-mix(in srgb, var(--native-color) 40%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--native-color) 8%, transparent);
  color: var(--text, #243c34);
  font-size: 12px;
  line-height: 1.5;
}
.luogu-difficulty {
  font-weight: 700;
}
i {
  display: inline-block;
  flex: 0 0 7px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--native-color);
}
.luogu-empty-tag {
  color: var(--muted, #697970);
  font-size: 12px;
}
</style>
