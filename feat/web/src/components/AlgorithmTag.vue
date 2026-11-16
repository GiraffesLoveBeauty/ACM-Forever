<script setup>
import { computed } from 'vue';
import { algorithmCategory, normalizeTags } from '../lib/problem-presentation.js';
const props = defineProps({
  tag: { type: [String, Object], default: '' },
  as: { type: String, default: 'span' },
});
const category = computed(() => algorithmCategory(props.tag));
const label = computed(() => normalizeTags([props.tag])[0]?.label || '无标签');
</script>
<template>
  <component
    :is="as === 'button' ? 'button' : 'span'"
    class="algorithm-tag"
    :class="`problem-tone-${category.tone}`"
    :title="category.name"
    :data-tag-category="category.category"
    :type="as === 'button' ? 'button' : undefined"
    ><slot>{{ label }}</slot></component
  >
</template>
