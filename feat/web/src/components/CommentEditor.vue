<script setup>
import { nextTick, ref } from 'vue';
import CommentMarkdown from './CommentMarkdown.vue';
const props = defineProps({ modelValue: { type: String, default: '' }, disabled: Boolean });
const emit = defineEmits(['update:modelValue']);
const preview = ref(false),
  input = ref();
async function focus() {
  preview.value = false;
  await nextTick();
  input.value?.focus();
}
defineExpose({ focus });
</script>
<template>
  <div class="comment-editor">
    <div class="chips" role="group" aria-label="评论编辑模式">
      <button type="button" class="btn" :aria-pressed="!preview" @click="preview = false">
        编辑评论
      </button>
      <button type="button" class="btn" :aria-pressed="preview" @click="preview = true">
        预览评论
      </button>
    </div>
    <p class="muted" id="comment-markdown-help">
      支持 Markdown、$公式$ 和代码块（如 ```cpp、```python、```java），最多 5000 字。
    </p>
    <textarea
      v-show="!preview"
      ref="input"
      :value="props.modelValue"
      :disabled="disabled"
      rows="5"
      maxlength="5000"
      aria-label="评论内容"
      aria-describedby="comment-markdown-help"
      placeholder="写下你的问题、想法或补充…"
      @input="emit('update:modelValue', $event.target.value)"
    ></textarea>
    <div v-if="preview" aria-label="评论预览" class="comment-preview">
      <CommentMarkdown v-if="modelValue.trim()" :source="modelValue" />
      <p v-else class="muted">输入评论后可查看预览。</p>
    </div>
  </div>
</template>
<style scoped>
.comment-editor {
  min-width: 0;
}
.comment-preview {
  min-height: 7rem;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
</style>
