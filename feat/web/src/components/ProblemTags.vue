<script setup>
import { computed } from 'vue';
import AlgorithmTag from './AlgorithmTag.vue';
import { normalizeTags } from '../lib/problem-presentation.js';
const props = defineProps({
  tags: { type: [Array, String, Object], default: () => [] },
  neutral: { type: Boolean, default: false },
});
const labels = computed(() => normalizeTags(props.tags));
</script>
<template>
  <span class="problem-tags">
    <template v-for="tag in labels" :key="tag.key">
      <span
        v-if="neutral"
        class="algorithm-tag problem-tone-neutral"
        title="原始标签 · 尚未关联原生分类"
        >{{ tag.label }}</span
      >
      <AlgorithmTag v-else :tag="tag.raw" />
    </template>
    <span v-if="!labels.length" class="problem-tags-empty">无标签</span>
  </span>
</template>
