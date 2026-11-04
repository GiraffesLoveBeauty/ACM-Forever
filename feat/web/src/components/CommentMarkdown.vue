<script setup>
import { computed } from 'vue';
import { markdown } from '../lib/markdown.js';
import { codeBlocks as vCodeBlocks } from '../lib/code-blocks.js';
const props = defineProps({ source: { type: String, default: '' } });
const rendered = computed(() => {
  const node = document.createElement('div');
  node.innerHTML = markdown(props.source);
  // Comments have no asset ownership/reference lifecycle; keep images as text.
  for (const image of node.querySelectorAll('img'))
    image.replaceWith(document.createTextNode(`[图片：${image.alt || '未提供描述'}]`));
  return node.innerHTML;
});
</script>
<template>
  <div class="forum-markdown comment-markdown" v-forum-math v-code-blocks v-html="rendered"></div>
</template>
<style scoped>
.comment-markdown {
  min-width: 0;
  overflow-wrap: anywhere;
}
.comment-markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
}
</style>
