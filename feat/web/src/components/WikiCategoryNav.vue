<script setup>
import { computed } from 'vue';
const props = defineProps({
  categories: { type: Array, default: () => [] },
  activeId: Number,
  management: Boolean,
  disabled: Boolean,
});
defineEmits(['select']);
const tops = computed(() => props.categories.filter((c) => c.parent_id == null));
const count = (id) => props.categories.filter((c) => c.parent_id === id).length;
const icons = [
  'M12 7C9 4 5 4 2 5v14c3-1 7-1 10 2m0-14c3-3 7-3 10-2v14c-3-1-7-1-10 2V7',
  'm14 6 4 4m-9 3-6 6a2 2 0 0 0 3 3l6-6a7 7 0 0 0 9-9l-4 4-4-4 4-4a7 7 0 0 0-8 10Z',
  'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm4 6-2 6-6 2 2-6 6-2Z',
];
</script>
<template>
  <aside class="wiki-categories" :aria-label="management ? '管理 Wiki 大类导航' : 'Wiki 大类导航'">
    <p class="wiki-nav-label">WIKI / 大类导航</p>
    <nav aria-label="知识大类">
      <button
        v-for="(top, index) in tops"
        :key="top.id"
        type="button"
        :disabled="disabled"
        class="wiki-category"
        :class="{ active: activeId === top.id }"
        :aria-current="activeId === top.id ? 'page' : undefined"
        @click="$emit('select', top.id)"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          aria-hidden="true"
        >
          <path :d="icons[index % icons.length]" />
        </svg>
        <span
          ><strong>{{ top.name }}</strong
          ><small>{{ count(top.id) }} 个小类 · {{ top.published_count || 0 }} 篇文章</small></span
        >
      </button>
    </nav>
    <p v-if="!tops.length" class="muted">知识目录正在准备</p>
    <div v-if="management" class="wiki-nav-tail">
      <RouterLink class="btn" to="/wiki.html">← 返回 Wiki</RouterLink>
    </div>
  </aside>
</template>
