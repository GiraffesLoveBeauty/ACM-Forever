<script setup>
import { computed } from 'vue';
import { algorithmCategory, normalizeTags } from '../lib/problem-presentation.js';
import { codeforcesTagName } from '../lib/codeforces-tags.js';
const props = defineProps({
  tag: { type: [String, Object], default: '' },
  as: { type: String, default: 'span' },
  platform: { type: String, default: '' },
});
const category = computed(() => algorithmCategory(props.tag));
const label = computed(() => {
  const name = normalizeTags([props.tag])[0]?.label;
  if (!name) return '无标签';
  return props.platform === 'codeforces' ? codeforcesTagName(name) : name;
});
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
