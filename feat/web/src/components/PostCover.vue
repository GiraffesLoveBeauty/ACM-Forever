<script setup>
import { computed, ref, watch } from 'vue';
import { postImage } from '../lib/post-images.js';
import ImageLightbox from './ImageLightbox.vue';
const props = defineProps({
  src: String,
  alt: { type: String, default: '帖子封面' },
  eager: Boolean,
  thumbnail: Boolean,
  zoom: Boolean,
});
const source = computed(() => postImage(props.src));
const failed = ref(false);
const viewer = ref();
watch(source, () => {
  failed.value = false;
});
</script>
<template>
  <figure v-if="source" class="post-cover">
    <img
      v-if="!failed"
      :src="thumbnail ? source + '?variant=thumb' : source"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
      :role="zoom ? 'button' : undefined"
      :tabindex="zoom ? 0 : undefined"
      :aria-label="zoom ? `放大查看：${alt}` : undefined"
      @click="zoom && viewer.open(source, alt)"
      @keydown.enter.prevent="zoom && viewer.open(source, alt)"
      @keydown.space.prevent="zoom && viewer.open(source, alt)"
      @error="failed = true"
    />
    <figcaption v-else>
      封面暂时无法显示
      <button v-if="!thumbnail" type="button" class="btn" @click="failed = false">重试</button>
    </figcaption>
    <ImageLightbox v-if="zoom" ref="viewer" />
  </figure>
</template>
