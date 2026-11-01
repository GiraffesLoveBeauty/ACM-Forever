<script setup>
import { computed, ref, watch } from 'vue';
import { postImage } from '../lib/post-images.js';
const props = defineProps({
  src: String,
  alt: { type: String, default: '帖子封面' },
  eager: Boolean,
});
const source = computed(() => postImage(props.src));
const failed = ref(false);
watch(source, () => {
  failed.value = false;
});
</script>
<template>
  <figure v-if="source" class="post-cover">
    <img
      v-if="!failed"
      :src="source"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
      @error="failed = true"
    />
    <figcaption v-else>封面暂时无法显示</figcaption>
  </figure>
</template>
