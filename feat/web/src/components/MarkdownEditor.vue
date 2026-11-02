<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { useRequests } from '../lib/api.js';
import { markdown, controlledImage } from '../lib/markdown.js';
import {
  importMarkdownFile,
  insertMarkdown,
  markdownFormats,
  missingImages,
} from '../lib/markdown-source.js';
import { downloadMarkdown } from '../lib/wiki.js';
const props = defineProps({
  modelValue: { type: String, default: '' },
  title: { type: String, default: '' },
  disabled: Boolean,
  mode: String,
  documentType: String,
  documentId: [Number, String],
  prepareUpload: Function,
  uploadImage: Function,
  downloadUrl: String,
});
const request = useRequests();
const emit = defineEmits(['update:modelValue', 'update:title', 'uploading', 'uploaded']);
const input = ref(),
  importInput = ref(),
  imageInput = ref(),
  localMode = ref('write'),
  message = ref(''),
  uploading = ref(false),
  pendingFiles = ref([]);
const mode = computed(() => props.mode || localMode.value),
  missing = computed(() => missingImages(props.modelValue));
let disposed = false,
  downloadController,
  uploadController;
onBeforeUnmount(() => {
  disposed = true;
  downloadController?.abort();
  uploadController?.abort();
  pendingFiles.value = [];
});
async function insert(before, after = '', placeholder = '文字') {
  const result = insertMarkdown(input.value, props.modelValue, before, after, placeholder);
  emit('update:modelValue', result.body);
  await nextTick();
  input.value?.focus();
  input.value?.setSelectionRange(result.start, result.end);
}
async function importFile(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file || props.disabled) return;
  if (
    (props.title.trim() || props.modelValue.trim()) &&
    !confirm('导入 Markdown 会替换当前标题和正文，确定继续吗？')
  )
    return;
  try {
    const parsed = await importMarkdownFile(file);
    if (disposed) return;
    emit('update:title', parsed.title);
    emit('update:modelValue', parsed.body);
    message.value = 'Markdown 已导入，请检查预览并保存。';
  } catch (e) {
    if (!disposed) message.value = '导入失败：' + e.message;
  }
}
async function upload(files) {
  const queue = Array.from(files || []);
  if (!queue.length || uploading.value || props.disabled) return;
  if (queue.length > 10) {
    message.value = '每次最多上传 10 张图片。';
    return;
  }
  let position = input.value?.selectionStart ?? props.modelValue.length;
  let end = input.value?.selectionEnd ?? position;
  uploading.value = true;
  pendingFiles.value = queue;
  emit('uploading', true);
  message.value = '正在上传图片…';
  uploadController = new AbortController();
  try {
    const documentId = props.prepareUpload ? await props.prepareUpload() : props.documentId;
    if (disposed) return;
    if (!documentId) throw Error('请先选择小类并创建草稿，再上传图片。');
    for (const file of queue) {
      let asset;
      if (props.uploadImage) {
        asset = await props.uploadImage(file, { signal: uploadController.signal });
      } else {
        if (file.size > 2 * 1024 * 1024) throw Error('单张图片不能超过 2 MB。');
        const data = new FormData();
        data.append('file', file);
        data.append('document_type', props.documentType);
        data.append('document_id', documentId);
        asset = await request('/markdown/assets', { method: 'POST', body: data });
      }
      if (disposed) return;
      if (!controlledImage(asset.url)) throw Error('服务器未返回有效的图片地址。');
      const alt = (file.name || '图片')
        .replace(/[\[\]\r\n\\]/g, '')
        .replace(/\.[^.]+$/, '')
        .slice(0, 80);
      const snippet = `![${alt}](${asset.url})`;
      const body = props.modelValue.slice(0, position) + snippet + props.modelValue.slice(end);
      if (Array.from(body).length > 20000)
        throw Error('正文不能超过 20000 个字符，请精简后再插入图片。');
      emit('update:modelValue', body);
      position += snippet.length;
      end = position;
      pendingFiles.value = pendingFiles.value.slice(1);
      await nextTick();
      input.value?.focus();
      input.value?.setSelectionRange(position, position);
      emit('uploaded');
    }
    message.value = '图片已插入，请保存正文；发布前仅授权账号可见。';
  } catch (e) {
    if (!disposed && e.name !== 'AbortError') message.value = '图片上传失败：' + e.message;
  } finally {
    if (!disposed) {
      uploading.value = false;
      emit('uploading', false);
    }
  }
}
function imageFile(event) {
  const files = [...(event.target.files || [])];
  event.target.value = '';
  upload(files);
}
function drop(event) {
  const files = [...(event.dataTransfer?.files || [])];
  if (files.length) {
    event.preventDefault();
    upload(files);
  }
}
function paste(event) {
  const files = [...(event.clipboardData?.items || [])]
    .filter((item) => item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter(Boolean);
  if (files.length) {
    event.preventDefault();
    upload(files);
  }
}
async function download() {
  try {
    downloadController?.abort();
    downloadController = new AbortController();
    await downloadMarkdown(props.downloadUrl, downloadController.signal);
    message.value = 'Markdown 已下载。';
  } catch (e) {
    if (e.name !== 'AbortError') message.value = '下载失败：' + e.message;
  }
}
</script>
<template>
  <div class="markdown-editor" @dragover.prevent @drop="drop" @paste="paste">
    <div v-if="!props.mode" class="chips">
      <button
        type="button"
        class="btn"
        :aria-pressed="mode === 'write'"
        @click="localMode = 'write'"
      >
        编辑</button
      ><button
        type="button"
        class="btn"
        :aria-pressed="mode === 'preview'"
        @click="localMode = 'preview'"
      >
        预览
      </button>
    </div>
    <div class="markdown-toolbar" role="toolbar" aria-label="Markdown 格式工具">
      <button type="button" :disabled="disabled || uploading" @click="importInput.click()">
        导入 .md
      </button>
      <input
        ref="importInput"
        type="file"
        accept=".md,.markdown,text/markdown"
        aria-label="选择 Markdown 文件"
        hidden
        @change="importFile"
      />
      <button
        v-for="(label, key) in {
          h1: 'H1',
          h2: 'H2',
          bold: 'B',
          italic: 'I',
          strike: 'S',
          quote: '❝',
          ul: '• 列表',
          ol: '1. 列表',
          code: '</>',
          codeblock: '代码块',
          link: '链接',
        }"
        :key="key"
        type="button"
        :disabled="disabled || uploading"
        @click="insert(...markdownFormats[key])"
      >
        {{ label }}
      </button>
      <button type="button" :disabled="disabled || uploading" @click="imageInput.click()">
        上传图片</button
      ><input
        ref="imageInput"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        aria-label="选择图片"
        :multiple="!!uploadImage"
        hidden
        @change="imageFile"
      />
      <button v-if="downloadUrl" type="button" :disabled="disabled" @click="download">
        下载 MD
      </button>
    </div>
    <div class="compose-editing-panes" :class="{ split: mode === 'split' }">
      <textarea
        v-if="mode !== 'preview'"
        ref="input"
        class="compose-textarea"
        :value="modelValue"
        :disabled="disabled || uploading"
        rows="18"
        aria-label="Markdown 正文"
        placeholder="记录你的思路…"
        @input="emit('update:modelValue', $event.target.value)"
      ></textarea>
      <div
        v-if="mode !== 'write'"
        v-forum-math
        class="compose-preview forum-markdown"
        v-html="markdown(modelValue)"
      ></div>
    </div>
    <p v-if="missing.length" class="muted">
      待上传或关联的图片：{{ missing.join('、') }}。请选择图片上传后替换原引用。
    </p>
    <p v-if="message" role="status">{{ message }}</p>
    <button
      v-if="pendingFiles.length && !uploading"
      type="button"
      class="btn"
      @click="upload(pendingFiles)"
    >
      重试上传
    </button>
  </div>
</template>
