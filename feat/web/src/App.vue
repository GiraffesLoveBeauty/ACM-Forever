<script setup>
import { ref, provide, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import Header from './components/Header.vue';
import ThemeEditor from './components/ThemeEditor.vue';
import { auth, notification, pageLoadError } from './lib/api.js';
const route = useRoute();
const themeEditor = ref();
const loadErrorHeading = ref();
watch(
  pageLoadError,
  async (error) => {
    if (!error) return;
    await nextTick();
    loadErrorHeading.value?.focus?.();
  },
  { immediate: true },
);
provide('openTheme', () => themeEditor.value?.open());
provide('toggleTheme', () => themeEditor.value?.toggle());
provide('setDesignTemplate', (template) => themeEditor.value?.setTemplate(template));
provide('getDesignTemplate', () => themeEditor.value?.getTemplate?.());
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
function reloadPage() {
  location.assign(pageLoadError.value.target);
}
</script>
<template>
  <Header />
  <section v-if="pageLoadError" class="community-main" aria-label="页面加载提示">
    <section class="card" role="alert">
      <h1 ref="loadErrorHeading" tabindex="-1">页面加载失败</h1>
      <p>网络可能已中断，或页面刚刚更新。请检查网络后重新加载。</p>
      <button class="btn primary" @click="reloadPage">重新加载目标页面</button>
      <button v-if="route.matched.length" class="btn" @click="pageLoadError = null">
        继续当前页面
      </button>
      <RouterLink class="btn" to="/index.html">返回社区</RouterLink>
    </section>
  </section>
  <RouterView v-slot="{ Component }">
    <component
      :is="Component"
      v-if="route.meta.public || auth.authenticated"
      :key="
        route.path === '/account-closure.html'
          ? route.path
          : `${route.path}:${auth.authenticated}:${auth.qq_id || ''}`
      "
    />
  </RouterView>
  <ThemeEditor ref="themeEditor" />
  <div class="forum-toast" :class="{ visible: notification }" role="status">{{ notification }}</div>
</template>
