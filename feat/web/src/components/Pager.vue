<script setup>
defineProps({
  page: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  size: { type: Number, default: 20 },
  busy: Boolean,
});
defineEmits(['change']);
</script>
<template>
  <div class="admin-pagination">
    <button class="btn" :disabled="busy || page <= 1" @click="$emit('change', page - 1)">
      上一页</button
    ><span>第 {{ page }} / {{ Math.max(1, Math.ceil(total / size)) }} 页 · {{ total }} 条</span
    ><button
      class="btn"
      :disabled="busy || page * size >= total"
      @click="$emit('change', page + 1)"
    >
      下一页
    </button>
  </div>
</template>
