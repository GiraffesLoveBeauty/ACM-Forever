<script setup>
import { computed } from 'vue';
import LuoguBadges from './LuoguBadges.vue';
import { difficultyPresentation } from '../lib/problem-presentation.js';
const props = defineProps({
  problem: { type: Object, default: () => ({}) },
  platform: { type: String, default: '' },
});
const display = computed(() => difficultyPresentation(props.problem, props.platform));
</script>
<template>
  <LuoguBadges v-if="display.system === 'luogu'" :problem="problem" :tags="false" />
  <span
    v-else
    class="problem-difficulty"
    :class="`problem-tone-${display.tone}`"
    :title="display.title"
    :data-rating-system="display.system"
    >{{ display.label }}</span
  >
</template>
