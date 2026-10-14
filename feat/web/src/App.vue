<script setup>
import { ref, provide, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import Header from './components/Header.vue';
import ThemeEditor from './components/ThemeEditor.vue';
import { auth, notification } from './lib/api.js';
const route = useRoute();
const themeEditor = ref();
provide('openTheme', () => themeEditor.value?.open());
provide('toggleTheme', () => themeEditor.value?.toggle());
function imageError(event) {
  const image = event.target;
  if (
    image instanceof HTMLImageElement &&
    image.src !== location.origin + '/assets/default-avatar.png' &&
    /avatar/.test(image.className)
  )
    image.src = '/assets/default-avatar.png';
}
onMounted(() => document.addEventListener('error', imageError, true));
onBeforeUnmount(() => document.removeEventListener('error', imageError, true));
</script>
<template>
  <Header v-if="route.path !== '/admin.html'" />
  <RouterView v-slot="{ Component }">
    <component
      :is="Component"
      v-if="route.meta.public || auth.authenticated"
      :key="`${route.path}:${auth.authenticated}:${auth.qq_id || ''}`"
    />
  </RouterView>
  <ThemeEditor ref="themeEditor" />
  <div class="forum-toast" :class="{ visible: notification }" role="status">{{ notification }}</div>
</template>
