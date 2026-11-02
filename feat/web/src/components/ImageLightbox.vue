<script setup>
import { ref } from 'vue';
import { postImage } from '../lib/post-images.js';
const dialog = ref(),
  source = ref(''),
  description = ref(''),
  failed = ref(false);
function open(url, alt = '') {
  if (!postImage(url)) return;
  source.value = url;
  description.value = alt || '帖子图片';
  failed.value = false;
  if (!dialog.value.open) dialog.value.showModal();
}
defineExpose({ open });
</script>
<template>
  <dialog ref="dialog" class="forum-image-lightbox" aria-label="图片预览" @close="source = ''">
    <button type="button" class="btn" autofocus @click="dialog.close()">关闭图片</button>
    <template v-if="source">
      <p v-if="failed" role="alert">
        图片暂时无法加载。<button type="button" class="btn" @click="failed = false">重试</button>
      </p>
      <img v-else :src="source" :alt="description" @error="failed = true" />
    </template>
  </dialog>
</template>
<style scoped>
.forum-image-lightbox {
  max-width: 94vw;
  max-height: 94vh;
  padding: 16px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--text);
}
.forum-image-lightbox::backdrop {
  background: #000b;
}
.forum-image-lightbox > button {
  display: block;
  margin: 0 0 12px auto;
}
.forum-image-lightbox img {
  display: block;
  max-width: 85vw;
  max-height: 78vh;
  object-fit: contain;
}
</style>
