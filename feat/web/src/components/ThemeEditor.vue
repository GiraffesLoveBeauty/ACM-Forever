<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import {
  BASE_KEYS,
  OVERRIDE_KEYS,
  LABELS,
  PRESETS,
  presetProfile,
  deriveTokens,
  validateTheme,
  parseThemeJSON,
  contrastChecks,
  repairProfile,
} from '../lib/theme-colors.js';
import { notify } from '../lib/api.js';
import {
  normalizeTemplate,
  themeStorageKey,
  libraryStorageKey,
  templateTheme,
  templateLabel,
} from '../lib/design-template.js';
let initialTemplate = 'original';
try {
  initialTemplate = normalizeTemplate(localStorage.getItem('acm.design-template.v1'));
} catch {
  /* Local-only fallback. */
}
const activeTemplate = ref(initialTemplate);
const createDefaultTheme = () => templateTheme(activeTemplate.value);
const themeKey = () => themeStorageKey(activeTemplate.value);
const libraryKey = () => libraryStorageKey(activeTemplate.value);
const templateName = computed(() => templateLabel(activeTemplate.value));
const clone = (value) => JSON.parse(JSON.stringify(value));
function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch {
    return fallback;
  }
}
let stored;
try {
  stored = validateTheme(read(themeKey(), createDefaultTheme()));
} catch {
  stored = createDefaultTheme();
}
try {
  const legacyMode = localStorage.getItem('theme');
  if (
    activeTemplate.value === 'original' &&
    !localStorage.getItem(themeKey()) &&
    ['light', 'dark'].includes(legacyMode)
  )
    stored.mode = legacyMode;
} catch {
  /* The default theme also works without browser storage. */
}
function loadLibrary() {
  const oldLibrary = read(libraryKey(), { version: 1, schemes: [] });
  const items = Array.isArray(oldLibrary) ? oldLibrary : oldLibrary.schemes;
  return (Array.isArray(items) ? items : [])
    .flatMap((item) => {
      try {
        return [
          {
            id: String(item.id || item.name),
            name: String(item.name).slice(0, 40),
            theme: validateTheme(item.theme),
          },
        ];
      } catch {
        return [];
      }
    })
    .slice(0, 12);
}
const current = ref(stored),
  draft = ref(clone(stored)),
  library = ref(loadLibrary());
const templateSessions = new Map();
function setTemplate(value) {
  const next = normalizeTemplate(value);
  if (next === activeTemplate.value) return;
  if (opened.value) close();
  templateSessions.set(activeTemplate.value, {
    theme: clone(current.value),
    library: clone(library.value),
  });
  activeTemplate.value = next;
  const cached = templateSessions.get(next);
  try {
    current.value = validateTheme(cached?.theme || read(themeKey(), createDefaultTheme()));
  } catch {
    current.value = createDefaultTheme();
  }
  library.value = cached ? clone(cached.library) : loadLibrary();
  draft.value = clone(current.value);
  apply(current.value);
}
const dialog = ref(),
  editMode = ref('light'),
  message = ref(''),
  opened = ref(false);
const media = matchMedia('(prefers-color-scheme: dark)');
const systemDark = ref(media.matches);
const changed = (e) => {
  systemDark.value = e.matches;
};
media.addEventListener('change', changed);
onBeforeUnmount(() => media.removeEventListener('change', changed));
const profile = computed(() => draft.value[editMode.value]);
const checks = computed(() => {
  try {
    return contrastChecks(profile.value, editMode.value === 'dark');
  } catch {
    return [];
  }
});
function apply(theme, forced) {
  try {
    const mode =
      forced || (theme.mode === 'system' ? (systemDark.value ? 'dark' : 'light') : theme.mode);
    const tokens = deriveTokens(theme[mode], mode === 'dark');
    for (const node of [document.documentElement, document.body]) {
      for (const [key, value] of Object.entries(tokens)) node.style.setProperty(key, value);
      node.dataset.theme = mode;
      node.dataset.customTheme = 'true';
      node.style.colorScheme = mode;
    }
    document.documentElement.dataset.designTemplate = activeTemplate.value;
    document.documentElement.dataset.palette = 'custom';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', tokens['--bg']);
  } catch (e) {
    message.value = e.message;
  }
}
watch(
  [current, systemDark],
  () => {
    if (!opened.value) apply(current.value);
  },
  { deep: true, immediate: true },
);
watch(
  draft,
  () => {
    if (opened.value) apply(draft.value, editMode.value);
  },
  { deep: true },
);
watch(editMode, () => apply(draft.value, editMode.value));
let returnFocus;
function open() {
  returnFocus = document.activeElement;
  draft.value = clone(current.value);
  editMode.value = document.documentElement.dataset.theme || 'light';
  message.value = '';
  opened.value = true;
  dialog.value.showModal();
  apply(draft.value, editMode.value);
}
function close() {
  opened.value = false;
  dialog.value.close();
  apply(current.value);
  returnFocus?.focus();
}
function save(persist = true) {
  try {
    current.value = validateTheme(clone(draft.value));
    if (persist) localStorage.setItem(themeKey(), JSON.stringify(current.value));
    close();
  } catch (e) {
    message.value = e.message;
  }
}
function selected(id) {
  const preset = presetProfile(id, editMode.value);
  return (
    BASE_KEYS.every((key) => profile.value.colors[key] === preset.colors[key]) &&
    OVERRIDE_KEYS.every((key) => profile.value.overrides[key] === preset.overrides[key])
  );
}
function repair() {
  try {
    draft.value[editMode.value] = repairProfile(clone(profile.value), editMode.value === 'dark');
  } catch (e) {
    message.value = e.message;
  }
}
function persistLibrary() {
  localStorage.setItem(
    libraryKey(),
    JSON.stringify({
      version: 1,
      schemes: library.value.map(({ name, theme }) => ({ name, theme })),
    }),
  );
}
function saveScheme() {
  let name = prompt('方案名称');
  if (!name?.trim()) return;
  name = name.trim().slice(0, 40);
  try {
    const theme = validateTheme(clone(draft.value));
    library.value = library.value.filter((item) => item.name !== name);
    library.value.push({ id: name, name, theme });
    library.value = library.value.slice(-12);
    persistLibrary();
  } catch (e) {
    message.value = e.message;
  }
}
function removeScheme(id) {
  library.value = library.value.filter((item) => item.id !== id);
  try {
    persistLibrary();
  } catch {
    notify('方案删除未能保存');
  }
}
async function importFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 32768) throw Error('主题 JSON 不得超过 32768 字节');
    draft.value = parseThemeJSON(await file.text());
  } catch (e) {
    message.value = e.message;
  } finally {
    event.target.value = '';
  }
}
function exportFile() {
  try {
    const theme = validateTheme(clone(draft.value));
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(theme, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'acm-theme.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    message.value = e.message;
  }
}
function toggle() {
  const theme = clone(current.value);
  theme.mode = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  current.value = theme;
  if (opened.value) close();
  try {
    localStorage.setItem(themeKey(), JSON.stringify(theme));
  } catch {
    notify('存储不可用，主题仅在本页应用');
  }
}
defineExpose({ open, toggle, setTemplate, getTemplate: () => activeTemplate.value });
</script>
<template>
  <dialog
    ref="dialog"
    class="vue-theme-dialog"
    aria-labelledby="theme-heading"
    @cancel.prevent="close"
    @click="
      (e) => {
        if (e.target === dialog) close();
      }
    "
  >
    <div class="filters">
      <h2 id="theme-heading">自助调色</h2>
      <button class="btn" @click="close">关闭</button>
    </div>
    <p class="muted">当前：{{ templateName }}。配色、明暗模式和收藏方案分别保存。</p>
    <div class="filters">
      <label
        >保存模式<select v-model="draft.mode">
          <option value="system">跟随系统</option>
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select></label
      ><label
        >编辑配色<select v-model="editMode">
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select></label
      >
    </div>
    <div class="filters">
      <button
        v-for="preset in PRESETS"
        :key="preset.id"
        class="btn"
        :class="{ primary: selected(preset.id) }"
        :aria-pressed="selected(preset.id)"
        @click="draft[editMode] = presetProfile(preset.id, editMode)"
      >
        {{ preset.name }}
      </button>
    </div>
    <div class="grid two">
      <label v-for="key in BASE_KEYS" :key="key"
        >{{ LABELS[key] }}<input v-model="profile.colors[key]" type="color"
      /></label>
    </div>
    <details>
      <summary>高级颜色</summary>
      <div class="grid two">
        <label v-for="key in OVERRIDE_KEYS" :key="key"
          >{{ LABELS[key]
          }}<input
            :value="profile.overrides[key] || ''"
            placeholder="自动 / #RRGGBB"
            @change="
              (e) => {
                if (e.target.value) profile.overrides[key] = e.target.value;
                else delete profile.overrides[key];
              }
            "
        /></label>
      </div>
    </details>
    <p role="status">{{ message }}</p>
    <details>
      <summary>
        对比度检查 · {{ checks.filter((item) => item.pass).length }} / {{ checks.length }}
      </summary>
      <p v-for="check in checks" :key="check.label">
        {{ check.pass ? '✓' : '!' }} {{ check.label }} · {{ check.ratio.toFixed(2) }}:1
      </p>
    </details>
    <div class="filters">
      <button class="btn" @click="repair">修复可读性</button
      ><button class="btn" @click="draft = createDefaultTheme()">恢复此模板原配色</button
      ><button class="btn" @click="saveScheme">收藏方案</button>
    </div>
    <div v-for="scheme in library" :key="scheme.id" class="list-item">
      <button class="btn" @click="draft = clone(scheme.theme)">{{ scheme.name }}</button
      ><button class="btn" @click="removeScheme(scheme.id)">删除</button>
    </div>
    <div class="filters">
      <label
        >导入 JSON<input type="file" accept=".json,application/json" @change="importFile" /></label
      ><button class="btn" @click="exportFile">导出 JSON</button>
    </div>
    <div class="filters">
      <button class="btn primary" @click="save()">保存主题</button
      ><button class="btn" @click="save(false)">仅本页应用</button
      ><button class="btn" @click="close">取消</button>
    </div>
  </dialog>
</template>
