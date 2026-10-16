<script setup>
import { inject, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps({ src: { type: String, required: true } });
const loadRenderer = inject('loadPdfRenderer', () => import('../lib/pdfjs.js'));
const host = ref(),
  canvas = ref(),
  page = ref(1),
  pages = ref(0),
  zoom = ref(1);
const loading = ref(false),
  rendering = ref(false),
  error = ref(''),
  canvasStyle = ref({});
let loadingTask,
  pdf,
  renderTask,
  observer,
  generation = 0,
  renderGeneration = 0;

function release() {
  renderGeneration++;
  renderTask?.cancel();
  renderTask = null;
  loadingTask?.destroy().catch(() => {});
  loadingTask = null;
  pdf = null;
}
async function renderPage() {
  if (!pdf || !canvas.value) return;
  const current = ++renderGeneration,
    document = pdf;
  const previous = renderTask;
  renderTask = null;
  previous?.cancel();
  rendering.value = true;
  error.value = '';
  try {
    await previous?.promise.catch(() => {});
    const item = await document.getPage(page.value);
    if (current !== renderGeneration) return;
    const base = item.getViewport({ scale: 1 });
    const width = Math.max(240, host.value?.clientWidth || 800);
    const viewport = item.getViewport({ scale: (width / base.width) * zoom.value });
    const ratio = Math.min(
      globalThis.devicePixelRatio || 1,
      2,
      Math.sqrt(16000000 / (viewport.width * viewport.height)),
    );
    canvas.value.width = Math.floor(viewport.width * ratio);
    canvas.value.height = Math.floor(viewport.height * ratio);
    canvasStyle.value = { width: viewport.width + 'px', height: viewport.height + 'px' };
    const task = item.render({
      canvasContext: canvas.value.getContext('2d'),
      viewport,
      transform: [ratio, 0, 0, ratio, 0, 0],
    });
    renderTask = task;
    await task.promise;
  } catch (e) {
    if (current === renderGeneration && e.name !== 'RenderingCancelledException')
      error.value = 'PDF 预览失败，请重试或单独打开 PDF。';
  } finally {
    if (current === renderGeneration) rendering.value = false;
  }
}
async function load() {
  const current = ++generation;
  release();
  loading.value = true;
  error.value = '';
  pages.value = 0;
  page.value = 1;
  zoom.value = 1;
  try {
    const renderer = await loadRenderer();
    if (current !== generation) return;
    loadingTask = renderer.openPdf(props.src);
    const document = await loadingTask.promise;
    if (current !== generation) return;
    pdf = document;
    pages.value = document.numPages;
    await renderPage();
  } catch {
    if (current === generation) error.value = 'PDF 加载失败，请重试或单独打开 PDF。';
  } finally {
    if (current === generation) loading.value = false;
  }
}
watch(() => props.src, load);
watch([page, zoom], renderPage);
onMounted(() => {
  load();
  if (typeof ResizeObserver !== 'undefined') {
    let width = 0;
    observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0].contentRect.width);
      if (next !== width) {
        width = next;
        renderPage();
      }
    });
    observer.observe(host.value);
  }
});
onBeforeUnmount(() => {
  generation++;
  observer?.disconnect();
  release();
});
</script>
<template>
  <div class="pdf-preview" :aria-busy="loading || rendering">
    <div v-if="pages" class="pdf-preview-toolbar">
      <button class="btn" :disabled="page <= 1 || loading" @click="page--">上一页</button>
      <span role="status">第 {{ page }} / {{ pages }} 页</span>
      <button class="btn" :disabled="page >= pages || loading" @click="page++">下一页</button>
      <button
        class="btn"
        :disabled="zoom <= 0.5"
        aria-label="缩小 PDF"
        @click="zoom = Math.max(0.5, zoom - 0.25)"
      >
        −
      </button>
      <button class="btn" @click="zoom = 1">适应宽度</button>
      <button
        class="btn"
        :disabled="zoom >= 2"
        aria-label="放大 PDF"
        @click="zoom = Math.min(2, zoom + 0.25)"
      >
        ＋
      </button>
    </div>
    <p v-if="loading" role="status">正在加载 PDF…</p>
    <p v-if="error" role="alert">{{ error }} <button class="btn" @click="load">重新加载</button></p>
    <div ref="host" class="pdf-preview-page">
      <canvas
        v-show="pages && !error"
        ref="canvas"
        :style="canvasStyle"
        role="img"
        :aria-label="`PDF 第 ${page} 页`"
      ></canvas>
    </div>
  </div>
</template>
