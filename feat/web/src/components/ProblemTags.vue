<script setup>
import { computed } from 'vue';
import AlgorithmTag from './AlgorithmTag.vue';
import { normalizeTags } from '../lib/problem-presentation.js';
const props = defineProps({ tags: { type: [Array, String, Object], default: () => [] } });
const labels = computed(() => normalizeTags(props.tags));
</script>
<template>
  <span class="problem-tags">
    <AlgorithmTag v-for="tag in labels" :key="tag.key" :tag="tag.raw" />
    <span v-if="!labels.length" class="problem-tags-empty">无标签</span>
  </span>
</template>
