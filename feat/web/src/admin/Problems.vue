<script setup>
import { computed } from 'vue';
import { auth } from '../lib/api.js';
import ProblemCollection from '../components/ProblemCollection.vue';

const manager = computed(() => ['admin', 'root'].includes(auth.role));
</script>
<template>
  <ProblemCollection v-if="manager" />
</template>
