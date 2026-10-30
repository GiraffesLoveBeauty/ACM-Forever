<script setup>
import { ref, computed, nextTick } from 'vue';
import { TEMPLATE_CATEGORIES, DESIGN_TEMPLATES } from '../lib/design-template.js';

const props = defineProps({ current: { type: String, required: true } });
const emit = defineEmits(['select']);
const dialog = ref();
const category = ref('all');
const categories = computed(() => [
  { id: 'all', name: '全部', count: DESIGN_TEMPLATES.length },
  ...TEMPLATE_CATEGORIES.map((item) => ({
    ...item,
    count: DESIGN_TEMPLATES.filter((template) => template.category === item.id).length,
  })),
]);
const templates = computed(() =>
  DESIGN_TEMPLATES.filter((item) => category.value === 'all' || item.category === category.value),
);
const categoryName = (id) => TEMPLATE_CATEGORIES.find((item) => item.id === id)?.name || id;
let returnFocus;
function open() {
  returnFocus = document.activeElement;
  category.value = 'all';
  dialog.value.showModal();
  nextTick(() => dialog.value.querySelector('[data-category="all"]')?.focus());
}
function close() {
  dialog.value.close();
  returnFocus?.focus();
}
function choose(template) {
  emit('select', template.id);
  close();
}
defineExpose({ open });
</script>
<template>
  <dialog
    ref="dialog"
    class="template-library"
    aria-labelledby="template-library-title"
    @cancel.prevent="close"
    @click="
      (event) => {
        if (event.target === dialog) close();
      }
    "
  >
    <div class="template-library-surface">
      <div class="template-library-heading">
        <div>
          <span class="template-library-eyebrow">APPEARANCE / 外观</span>
          <h2 id="template-library-title">主题库</h2>
        </div>
        <button class="library-close" aria-label="关闭主题库" @click="close">×</button>
      </div>
      <p class="template-library-description">
        按分类选择设计模板，每个模板保留自己的配色和收藏方案。
      </p>
      <div class="template-library-layout">
        <nav class="template-library-categories" aria-label="主题分类">
          <button
            v-for="item in categories"
            :key="item.id"
            :data-category="item.id"
            :aria-pressed="category === item.id"
            @click="category = item.id"
          >
            <span>{{ item.name }}</span
            ><small>{{ item.count }}</small>
          </button>
        </nav>
        <section class="template-library-results" aria-label="分类下的设计模板">
          <div class="template-library-count" role="status">
            {{ categories.find((item) => item.id === category)?.name }} ·
            {{ templates.length }} 个模板
          </div>
          <div v-if="templates.length" class="template-library-grid">
            <button
              v-for="item in templates"
              :key="item.id"
              class="template-library-card"
              :aria-pressed="props.current === item.id"
              :aria-label="`使用${item.name}`"
              @click="choose(item)"
            >
              <span
                class="template-library-preview"
                :class="`preview-${item.preview}`"
                aria-hidden="true"
              >
                <span class="preview-header"></span><span class="preview-rail"></span
                ><span class="preview-hero"><i></i></span><span class="preview-posts"></span
                ><span class="preview-side"></span>
              </span>
              <span class="template-library-card-meta"
                ><span>{{ categoryName(item.category) }}</span
                ><b v-if="props.current === item.id">✓ 当前使用</b></span
              >
              <strong>{{ item.name }}</strong
              ><span class="template-library-card-description">{{ item.description }}</span>
            </button>
          </div>
          <div v-else class="template-library-empty">
            <span aria-hidden="true">＋</span>
            <h3>此分类暂无模板</h3>
            <p>
              {{ categories.find((item) => item.id === category)?.name }}主题将在添加后显示于此。
            </p>
          </div>
        </section>
      </div>
      <details class="template-library-contribute">
        <summary>制作与投稿说明</summary>
        <p>
          只修改配色：选择模板后打开“自助调色”，编辑并导出 JSON；导入 JSON
          可在当前模板预览，保存后才写入本机。
        </p>
        <p>
          制作完整模板：为模板登记唯一
          ID、名称、分类与简介，添加独立样式及明暗默认配色。样式限定在本模板范围，保留网站已有功能、键盘操作与移动端布局。
        </p>
        <p>
          投稿到主题库：将源码、合法使用的素材、说明和测试结果提交到任务分支，再向仓库发起
          PR。由其他成员评审并合并后发布。浏览器内的配色导入只影响本机，不会自动上传为公共模板。
        </p>
        <p>
          详细编辑示例、文件路径与投稿检查见仓库
          docs/theme-development.md（个人主题开发与投稿规范）。
        </p>
      </details>
    </div>
  </dialog>
</template>
<style scoped>
.template-library {
  --library-text: #202a31;
  width: min(900px, calc(100vw - 32px));
  max-width: none;
  max-height: calc(100dvh - 48px);
  padding: 0;
  border: 1px solid #c7cece;
  border-radius: 12px;
  background: #f5f7f6;
  color: var(--library-text);
  box-shadow: 0 24px 100px #0005;
  overflow: auto;
}
.template-library::backdrop {
  background: #0b1519a8;
}
.template-library-surface {
  padding: 28px;
}
.template-library-contribute {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid #c7cece;
  color: #33474d;
}
.template-library-contribute summary {
  cursor: pointer;
  font-size: 14px;
  font-weight: 700;
}
.template-library-contribute p {
  font-size: 13px;
  line-height: 1.85;
  margin: 12px 0 0;
}
.template-library-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}
.template-library-heading h2 {
  font-size: 26px;
  margin: 6px 0 0;
  color: var(--library-text);
}
.template-library-eyebrow {
  font:
    11px/1.6 system-ui,
    sans-serif;
  letter-spacing: 0.13em;
  color: #53666a;
}
.library-close {
  background: #fff;
  color: #283439;
  width: 40px;
  height: 40px;
  font-size: 26px;
  border: 1px solid #c7cece;
  border-radius: 6px;
  cursor: pointer;
}
.template-library-description {
  font-size: 13px;
  line-height: 1.7;
  color: #536268;
  margin: 14px 0 24px;
}
.template-library-layout {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 24px;
  min-height: 340px;
}
.template-library-categories {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.template-library-categories button {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: transparent;
  color: #394b51;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 11px 12px;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}
.template-library-categories button[aria-pressed='true'] {
  background: #202b30;
  color: #fff;
}
.template-library-categories small {
  font-size: 11px;
  opacity: 0.8;
}
.template-library-count {
  font-size: 12px;
  color: #52646a;
  margin: 0 0 12px;
}
.template-library-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.template-library-card {
  background: #fff;
  color: var(--library-text);
  border: 1px solid #c6d0d0;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}
.template-library-card[aria-pressed='true'] {
  border-color: #23665c;
  box-shadow: inset 0 0 0 1px #23665c;
}
.template-library-card:hover {
  border-color: #23665c;
}
.template-library-card strong {
  font-size: 17px;
}
.template-library-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  font-size: 11px;
  color: #5b686e;
}
.template-library-card-meta b {
  color: #23665c;
  font-weight: 600;
}
.template-library-card-description {
  color: #52646a;
  font-size: 12px;
  line-height: 1.7;
}
.template-library-preview {
  display: block;
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 130px;
  background: #e8e9e4;
  border: 1px solid #d7dfd9;
}
.template-library-preview > span {
  position: absolute;
  display: block;
}
.preview-header {
  inset: 0 0 auto;
  height: 13%;
  background: #fafaf7;
  border-bottom: 1px solid #bec7bd;
}
.preview-rail {
  left: 5%;
  top: 22%;
  width: 17%;
  height: 48%;
  background: #f8f8f3;
  border-top: 2px solid #373d39;
}
.preview-hero {
  top: 22%;
  left: 26%;
  width: 48%;
  height: 36%;
  background: #20251f;
}
.preview-hero i {
  position: absolute;
  width: 28%;
  height: 60%;
  top: 20%;
  right: 10%;
  border: 1px solid #cbd647;
  border-radius: 50%;
}
.preview-posts {
  left: 26%;
  right: 26%;
  top: 65%;
  height: 28%;
  background: repeating-linear-gradient(#f8f8f3 0 11px, #c7cabc 11px 12px);
}
.preview-side {
  right: 5%;
  top: 22%;
  width: 17%;
  height: 60%;
  background: #f8f8f3;
}
.preview-phase :is(.preview-header, .preview-rail, .preview-side) {
  background: #151a1d;
}
.preview-phase .preview-hero {
  background: #151a1d;
}
.preview-phase .preview-hero i {
  width: 40%;
  height: 90%;
  top: 5%;
  right: 5%;
  background: repeating-conic-gradient(#c2cbc855 0deg 1deg, transparent 1deg 12deg);
  border-color: #6c7974;
}
.preview-phase::after {
  content: '';
  position: absolute;
  width: 70%;
  height: 11px;
  top: 40%;
  right: -35%;
  transform: rotate(-50deg);
  background: linear-gradient(#00d7d2 0 25%, #f00091 25% 50%, #d5f500 50% 75%, #385bff 75%);
}
.template-library-empty {
  display: grid;
  place-content: center;
  text-align: center;
  min-height: 280px;
  border: 1px dashed #b6c5c5;
  border-radius: 8px;
  padding: 24px;
}
.template-library-empty > span {
  color: #718782;
  font-size: 36px;
}
.template-library-empty h3 {
  font-size: 17px;
  margin: 6px 0;
  color: var(--library-text);
}
.template-library-empty p {
  font-size: 13px;
  color: #52646a;
  line-height: 1.7;
}
.template-library button:focus-visible {
  outline: 2px solid #23665c;
  outline-offset: 3px;
}
@media (max-width: 600px) {
  .template-library-surface {
    padding: 20px;
  }
  .template-library-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
  .template-library-categories {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 6px;
  }
  .template-library-categories button {
    width: auto;
    gap: 10px;
    padding: 9px 10px;
  }
  .template-library-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
