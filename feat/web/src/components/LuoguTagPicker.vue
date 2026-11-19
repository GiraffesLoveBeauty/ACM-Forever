<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue';
import { codeforcesTagCategories, codeforcesTagName } from '../lib/codeforces-tags.js';
import { MAX_NATIVE_TAGS } from '../lib/luogu-problems.js';
import { luoguTagCategories, searchLuoguTags } from '../lib/luogu-tags.js';
const props = defineProps({
  platform: { type: String, default: 'luogu' },
  modelValue: { type: Array, default: () => [] },
  taxonomy: { type: Object, default: () => ({}) },
  tags: { type: Array, default: () => [] },
  triggerLabel: { type: String, default: '' },
  loading: Boolean,
  error: { type: String, default: '' },
});
const emit = defineEmits(['update:modelValue', 'retry']);
const id = 'problem-tag-picker-' + useId();
const trigger = ref(null),
  dialog = ref(null),
  search = ref(null);
const opened = ref(false),
  draft = ref([]),
  query = ref(''),
  active = ref('');
const isCodeforces = computed(() => props.platform === 'codeforces');
const isLuogu = computed(() => props.platform === 'luogu');
const isSingle = computed(() => !isLuogu.value && !isCodeforces.value);
const maxTags = computed(() => (isSingle.value ? 1 : MAX_NATIVE_TAGS));
const categories = computed(() => {
  if (isCodeforces.value) return codeforcesTagCategories(props.tags);
  if (isLuogu.value) return luoguTagCategories(props.taxonomy);
  const ids = new Set(props.tags.filter((value) => typeof value === 'string' && value.trim()));
  const items = [...ids].map((id) => ({ id, name: tagName(id) }));
  return items.length ? [{ id: 'all', name: '', groups: [{ id: 'all', name: '', items }] }] : [];
});
const byId = computed(
  () => new Map((props.taxonomy.tags || []).map((tag) => [String(tag.id), tag])),
);
const selected = computed(() => [
  ...new Map(props.modelValue.map(String).map((value) => [tagKey(value), value])).values(),
]);
const draftKeys = computed(() => new Set(draft.value.map(tagKey)));
const category = computed(
  () => categories.value.find((item) => item.id === active.value) || categories.value[0],
);
const results = computed(() => {
  if (query.value.trim()) return searchLuoguTags(categories.value, query.value);
  if (!isLuogu.value) return categories.value;
  return category.value ? [category.value] : [];
});
const resultCount = computed(() =>
  results.value.reduce(
    (sum, item) => sum + item.groups.reduce((n, group) => n + group.items.length, 0),
    0,
  ),
);
const summary = computed(() => selected.value.slice(0, 3).map(tagName).join('、'));
let body, overflow;
function tagKey(value) {
  return isCodeforces.value ? value.toLowerCase() : value;
}
function isSelected(value) {
  return draftKeys.value.has(tagKey(value));
}
function tagName(value) {
  if (isCodeforces.value || props.platform === 'all') return codeforcesTagName(value);
  if (isLuogu.value) return byId.value.get(value)?.name || '标签 #' + value + '（名称待更新）';
  return value;
}
async function open() {
  draft.value = selected.value.slice(0, isSingle.value ? 1 : undefined);
  query.value = '';
  active.value = categories.value[0]?.id || '';
  opened.value = true;
  body = globalThis.document?.body;
  overflow = body?.style.overflow;
  if (body) body.style.overflow = 'hidden';
  await nextTick();
  if (!opened.value) return;
  if (dialog.value?.showModal) dialog.value.showModal();
  else dialog.value?.setAttribute?.('open', '');
  search.value?.focus?.();
}
function close(restoreFocus = true) {
  if (!opened.value) return;
  opened.value = false;
  dialog.value?.close?.();
  if (body) body.style.overflow = overflow;
  body = null;
  draft.value = [];
  if (restoreFocus) nextTick(() => trigger.value?.focus?.());
}
function toggle(value) {
  if (isSingle.value) {
    draft.value = isSelected(value) ? [] : [value];
    return;
  }
  draft.value = isSelected(value)
    ? draft.value.filter((item) => tagKey(item) !== tagKey(value))
    : draft.value.length < MAX_NATIVE_TAGS
      ? [...draft.value, value]
      : draft.value;
}
function apply() {
  if (draft.value.length > maxTags.value) return;
  const values = [...draft.value];
  close();
  emit('update:modelValue', values);
}
function confirmOnEnter(event) {
  // Let the IME confirm its candidate before applying the filter.
  if (event.isComposing || event.keyCode === 229 || event.target?.composing) return;
  event.preventDefault();
  apply();
}
function activate(value) {
  active.value = value;
  query.value = '';
}
function trapFocus(event) {
  if (event.key !== 'Tab') return;
  const focusable = [...(dialog.value?.querySelectorAll('button, input, [tabindex]') || [])].filter(
    (element) => element.tabIndex >= 0 && !element.disabled && element.getClientRects().length,
  );
  const target = event.shiftKey ? focusable.at(-1) : focusable[0];
  const boundary = event.shiftKey ? focusable[0] : focusable.at(-1);
  if (target && globalThis.document.activeElement === boundary) {
    event.preventDefault();
    target.focus();
  }
}
function moveTab(event, index) {
  const count = categories.value.length;
  const target = {
    ArrowRight: (index + 1) % count,
    ArrowLeft: (index + count - 1) % count,
    Home: 0,
    End: count - 1,
  }[event.key];
  if (target == null) return;
  event.preventDefault();
  activate(categories.value[target].id);
  nextTick(() => dialog.value?.querySelector?.('[role="tab"][aria-selected="true"]')?.focus());
}
watch(
  () => props.modelValue,
  () => close(),
  { deep: true },
);
onBeforeUnmount(() => close(false));
</script>
<template>
  <div class="luogu-tag-picker">
    <div class="luogu-picker-trigger-row">
      <button
        ref="trigger"
        type="button"
        class="btn luogu-picker-trigger"
        aria-haspopup="dialog"
        :aria-expanded="opened"
        @click="open"
      >
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path
            d="M3 5h14M3 10h14M3 15h14M7 3v4m6 1v4m-6 1v4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <span>{{ triggerLabel || (isLuogu ? '按算法筛选' : '按标签筛选') }}</span
        ><span v-if="selected.length" class="luogu-picker-count">{{ selected.length }}</span>
      </button>
      <button
        v-if="selected.length"
        type="button"
        class="btn luogu-picker-reset"
        @click="emit('update:modelValue', [])"
      >
        清空
      </button>
    </div>
    <p v-if="selected.length" class="luogu-picker-summary">
      已选：{{ summary }}<span v-if="selected.length > 3"> 等 {{ selected.length }} 项</span>
    </p>
    <dialog
      v-if="opened"
      :id="id"
      ref="dialog"
      class="luogu-tag-dialog"
      :aria-labelledby="id + '-title'"
      :aria-describedby="id + '-hint'"
      @keydown="trapFocus"
      @cancel.prevent="close()"
      @close="close()"
      @click.self="close()"
    >
      <div class="luogu-picker-layout">
        <div class="luogu-picker-content">
          <header class="luogu-picker-heading">
            <div>
              <h2 :id="id + '-title'">选择标签</h2>
              <p v-if="isSingle" :id="id + '-hint'">一次选择一个标签</p>
              <p v-else :id="id + '-hint'">
                {{ isCodeforces ? 'Codeforces 原生标签' : '洛谷原生分类' }} ·
                多个标签同时满足，最多选择 {{ MAX_NATIVE_TAGS }} 个
              </p>
            </div>
            <button
              type="button"
              class="luogu-picker-close"
              aria-label="关闭标签筛选"
              @click="close()"
            >
              ×
            </button>
          </header>
          <div class="luogu-picker-tools">
            <div v-if="isLuogu" class="luogu-picker-tabs" role="tablist" aria-label="标签分类">
              <button
                v-for="(item, index) in categories"
                :id="id + '-tab-' + item.id"
                :key="item.id"
                type="button"
                role="tab"
                :aria-selected="category?.id === item.id"
                :aria-controls="id + '-results'"
                :tabindex="category?.id === item.id ? 0 : -1"
                :class="{ 'is-searching': query.trim() }"
                @click="activate(item.id)"
                @keydown="moveTab($event, index)"
              >
                {{ item.name }}
              </button>
            </div>
            <label class="luogu-picker-search"
              ><span class="luogu-picker-sr-only">搜索全部标签</span
              ><svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
                <circle
                  cx="8.5"
                  cy="8.5"
                  r="5.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                />
                <path d="m13 13 4 4" stroke="currentColor" stroke-width="1.5" /></svg
              ><input
                ref="search"
                v-model="query"
                type="search"
                placeholder="搜索全部标签"
                @keydown.enter="confirmOnEnter"
            /></label>
          </div>
          <section class="luogu-picker-selected" aria-label="已选标签">
            <div class="luogu-picker-selected-heading">
              <strong
                >已选标签
                <span aria-live="polite">（{{ draft.length }}/{{ maxTags }}）</span></strong
              ><button
                v-if="draft.length"
                type="button"
                class="luogu-picker-text-button"
                @click="draft = []"
              >
                清空已选
              </button>
            </div>
            <div v-if="draft.length" class="luogu-picker-selected-chips">
              <button
                v-for="value in draft"
                :key="value"
                type="button"
                class="luogu-picker-chip is-selected"
                :aria-label="'移除标签：' + tagName(value)"
                @click="toggle(value)"
              >
                {{ tagName(value) }}<span aria-hidden="true">×</span>
              </button>
            </div>
            <p v-else class="luogu-picker-empty-selection">暂未选择，点击下方标签添加</p>
          </section>
          <div
            :id="id + '-results'"
            class="luogu-picker-body"
            :role="!isLuogu || query.trim() ? 'region' : 'tabpanel'"
            :aria-label="
              query.trim()
                ? isSingle
                  ? '标签搜索结果'
                  : '全部分类的搜索结果'
                : isLuogu
                  ? undefined
                  : '全部标签'
            "
            :aria-labelledby="
              isLuogu && !query.trim() && category ? id + '-tab-' + category.id : undefined
            "
            :aria-busy="loading"
            tabindex="0"
          >
            <p v-if="loading" class="luogu-picker-state" role="status">
              {{
                isCodeforces
                  ? '正在加载 Codeforces 标签…'
                  : isLuogu
                    ? '正在加载洛谷原生标签…'
                    : '正在加载标签…'
              }}
            </p>
            <p v-if="error" class="luogu-picker-state" role="alert">
              {{ error }}
              <button type="button" class="btn" :disabled="loading" @click="emit('retry')">
                {{ isLuogu ? '重试分类' : '重试' }}
              </button>
            </p>
            <p v-if="!loading && !categories.length && !error" class="luogu-picker-state">
              {{
                isCodeforces
                  ? '暂无可用的 Codeforces 标签。'
                  : isLuogu
                    ? '原生标签尚未同步，已选条件仍然保留。'
                    : '暂无可用的标签。'
              }}
            </p>
            <p
              v-else-if="!loading && categories.length && !results.length"
              class="luogu-picker-state"
              role="status"
            >
              没有找到匹配的标签，试试其他关键词。
            </p>
            <p v-if="query.trim() && results.length" class="luogu-picker-search-note" role="status">
              {{ isSingle ? '找到' : '全部分类中找到' }} {{ resultCount }} 个标签
            </p>
            <template v-for="item in results" :key="item.id">
              <section v-for="group in item.groups" :key="group.id" class="luogu-picker-group">
                <h3 v-if="!isSingle">
                  <span v-if="query.trim()" class="luogu-picker-group-category"
                    >{{ item.name }} / </span
                  >{{ group.name }}
                </h3>
                <div class="luogu-picker-chips">
                  <button
                    v-for="tag in group.items"
                    :key="tag.id"
                    type="button"
                    class="luogu-picker-chip"
                    :class="{ 'is-selected': isSelected(tag.id) }"
                    :aria-label="tag.name"
                    :aria-pressed="isSelected(tag.id)"
                    :disabled="!isSingle && draft.length >= maxTags && !isSelected(tag.id)"
                    @click="toggle(tag.id)"
                  >
                    <span v-if="isSelected(tag.id)" aria-hidden="true">✓</span>{{ tag.name }}
                  </button>
                </div>
              </section>
            </template>
          </div>
        </div>
        <footer class="luogu-picker-footer">
          <p aria-live="polite">
            {{
              !isSingle && draft.length >= maxTags
                ? `已达 ${MAX_NATIVE_TAGS} 个标签上限，请先移除再添加。`
                : isLuogu
                  ? '未选择标签时，不限制算法。'
                  : '留空时不按标签筛选。'
            }}
          </p>
          <div>
            <button type="button" class="btn" @click="close()">取消</button
            ><button
              type="button"
              class="btn primary"
              :disabled="draft.length > maxTags"
              @click="apply"
            >
              确认筛选
            </button>
          </div>
        </footer>
      </div>
    </dialog>
  </div>
</template>
<style scoped>
.luogu-tag-picker {
  min-width: 0;
}
.luogu-picker-trigger-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.luogu-picker-trigger {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 44px;
  padding-inline: 8px;
  white-space: nowrap;
}
.luogu-picker-trigger > svg {
  flex-shrink: 0;
}
.luogu-picker-count {
  display: inline-grid;
  min-width: 23px;
  height: 23px;
  padding: 0 5px;
  place-items: center;
  background: var(--brand);
  color: var(--panel);
  border-radius: 4px;
  font-size: 12px;
}
.luogu-picker-summary {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.luogu-tag-dialog {
  width: min(1120px, calc(100vw - 40px));
  max-width: none;
  max-height: calc(100dvh - 48px);
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  color: var(--text);
  box-shadow: 0 24px 90px #0006;
  overflow: hidden;
}
.luogu-tag-dialog::backdrop {
  background: #071010a6;
  backdrop-filter: blur(3px);
}
.luogu-picker-layout {
  display: flex;
  flex-direction: column;
  min-height: min(620px, calc(100dvh - 50px));
  max-height: min(840px, calc(100dvh - 50px));
}
.luogu-picker-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.luogu-picker-heading {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 26px 20px;
}
.luogu-picker-heading h2 {
  margin: 0;
  font-size: 23px;
}
.luogu-picker-heading p {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.luogu-picker-close {
  width: 40px;
  min-width: 40px;
  height: 40px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: 30px/1 system-ui;
  cursor: pointer;
}
.luogu-picker-close:hover {
  background: var(--bg);
}
.luogu-picker-tools {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 24px;
  margin: 0 26px;
  border-bottom: 1px solid var(--line);
}
.luogu-picker-tabs {
  display: flex;
  flex: 1;
  align-self: stretch;
  min-width: 0;
  gap: 4px;
  overflow-x: auto;
}
.luogu-picker-tabs button {
  flex-shrink: 0;
  min-height: 50px;
  padding: 10px 15px;
  border: 0;
  border-bottom: 3px solid transparent;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.luogu-picker-tabs button[aria-selected='true']:not(.is-searching) {
  border-bottom-color: var(--brand);
  color: var(--brand);
}
.luogu-picker-search {
  position: relative;
  display: flex;
  flex: 0 1 250px;
  min-width: 160px;
  margin: 0 0 10px;
  align-items: center;
}
.luogu-picker-search:only-child {
  width: 100%;
  flex-grow: 1;
}
.luogu-picker-search > svg {
  position: absolute;
  left: 11px;
  color: var(--muted);
  pointer-events: none;
}
.luogu-picker-search input {
  width: 100%;
  min-width: 0;
  min-height: 40px;
  padding-left: 37px;
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
}
.luogu-picker-selected {
  flex-shrink: 0;
  padding: 19px 26px;
  border-bottom: 1px solid var(--line);
}
.luogu-picker-selected-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.luogu-picker-selected-heading strong {
  font-size: 14px;
}
.luogu-picker-selected-heading strong span {
  color: var(--muted);
  font-weight: 400;
}
.luogu-picker-text-button {
  min-height: 30px;
  border: 0;
  background: transparent;
  color: var(--brand);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.luogu-picker-selected-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  max-height: 98px;
  overflow: auto;
  margin-top: 12px;
}
.luogu-picker-empty-selection {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.luogu-picker-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 26px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.luogu-picker-group {
  padding: 22px 0 26px;
  border-bottom: 1px solid var(--line);
}
.luogu-picker-group:last-child {
  border-bottom: 0;
}
.luogu-picker-group h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}
.luogu-picker-group-category {
  color: var(--muted);
  font-weight: 400;
}
.luogu-picker-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
}
.luogu-picker-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  max-width: 100%;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
}
.luogu-picker-chip:hover:not(:disabled),
.luogu-picker-chip.is-selected {
  border-color: var(--brand);
  background: color-mix(in srgb, var(--brand) 14%, var(--panel));
}
.luogu-picker-chip.is-selected {
  font-weight: 600;
}
.luogu-picker-chip:disabled {
  opacity: 0.45;
  cursor: default;
}
.luogu-picker-state {
  margin: 24px 0;
  color: var(--muted);
  font-size: 14px;
}
.luogu-picker-search-note {
  margin: 16px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.luogu-picker-footer {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 26px;
  border-top: 1px solid var(--line);
}
.luogu-picker-footer p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.luogu-picker-footer > div {
  display: flex;
  flex-shrink: 0;
  gap: 10px;
}
.luogu-picker-footer .btn {
  min-height: 42px;
  min-width: 85px;
}
.luogu-tag-picker button:focus-visible,
.luogu-picker-body:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 3px;
}
.luogu-picker-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (max-width: 700px) {
  .luogu-tag-dialog {
    width: calc(100vw - 20px);
    max-height: calc(100dvh - 24px);
    border-radius: 9px;
  }
  .luogu-picker-layout {
    min-height: min(680px, calc(100dvh - 26px));
    max-height: calc(100dvh - 26px);
  }
  .luogu-picker-heading {
    padding: 17px 16px 12px;
  }
  .luogu-picker-heading h2 {
    font-size: 20px;
  }
  .luogu-picker-heading p {
    line-height: 1.7;
  }
  .luogu-picker-tools {
    flex-direction: column-reverse;
    align-items: stretch;
    gap: 0;
    margin: 0 16px;
  }
  .luogu-picker-search {
    flex: auto;
    min-width: 0;
    margin-bottom: 2px;
  }
  .luogu-picker-search input {
    min-height: 44px;
  }
  .luogu-picker-tabs {
    flex: auto;
    align-self: auto;
  }
  .luogu-picker-tabs button {
    min-height: 48px;
    padding: 10px 13px;
  }
  .luogu-picker-selected {
    padding: 12px 16px;
  }
  .luogu-picker-selected-chips {
    max-height: 88px;
    gap: 6px;
  }
  .luogu-picker-body {
    padding: 0 16px;
  }
  .luogu-picker-group {
    padding: 18px 0;
  }
  .luogu-picker-group h3 {
    margin-bottom: 12px;
  }
  .luogu-picker-chip {
    min-height: 44px;
    padding: 7px 9px;
  }
  .luogu-picker-footer {
    flex-wrap: wrap;
    gap: 9px;
    padding: 12px 16px;
  }
  .luogu-picker-footer > div {
    margin-left: auto;
  }
  .luogu-picker-close {
    width: 44px;
    height: 44px;
  }
}
@media (max-height: 540px) {
  .luogu-picker-layout {
    min-height: 0;
  }
  .luogu-picker-content {
    display: block;
    overflow: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }
  .luogu-picker-body {
    overflow: visible;
  }
  .luogu-picker-heading {
    padding-top: 10px;
    padding-bottom: 8px;
  }
  .luogu-picker-selected {
    padding-top: 8px;
    padding-bottom: 8px;
  }
  .luogu-picker-selected-chips {
    max-height: 48px;
  }
  .luogu-picker-footer {
    padding-top: 8px;
    padding-bottom: 8px;
  }
}
</style>
