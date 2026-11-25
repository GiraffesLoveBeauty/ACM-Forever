<script setup>
import { computed, onMounted, ref } from 'vue';

/* 四套主题：色板只在这里登记，样式在 themes.css 里按类名生效 */
const THEMES = [
  { id: 'original', label: '原版', swatch: '#d9e65a' },
  { id: 'mist', label: '晨雾', swatch: '#4c6ef5' },
  { id: 'forest', label: '林绿', swatch: '#9ebd00' },
  { id: 'sand', label: '暖砂', swatch: '#c4703c' },
  { id: 'ink', label: '墨夜', swatch: '#22252a' },
];
const STORAGE_KEY = 'acm-theme';
const current = ref('original');

const themeClass = (id) => `theme-${id}`;

function apply(id) {
  current.value = id;
  const root = globalThis.document?.documentElement;
  if (!root?.classList) return; /* jsdom 测试环境可能没有 documentElement/classList */
  for (const theme of THEMES) root.classList.remove(themeClass(theme.id));
  root.classList.add(themeClass(id));
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* 隐私模式下忽略存储失败 */
  }
}

onMounted(() => {
  let stored = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch {
    stored = null;
  }
  const initial = THEMES.some((theme) => theme.id === stored) ? stored : current.value;
  apply(initial);
});

const activeLabel = computed(
  () => THEMES.find((theme) => theme.id === current.value)?.label || '原版',
);
</script>

<template>
  <div class="gh-theme-switch" role="group" aria-label="主题选择">
    <span class="gh-theme-switch__label">主题</span>
    <button
      v-for="theme in THEMES"
      :key="theme.id"
      type="button"
      class="gh-theme-swatch"
      :class="{ 'is-active': current === theme.id }"
      :style="{ background: theme.swatch }"
      :title="theme.label"
      :aria-label="`切换到${theme.label}`"
      :aria-pressed="current === theme.id"
      @click="apply(theme.id)"
    />
    <span class="gh-theme-switch__label">{{ activeLabel }}</span>
  </div>
</template>
