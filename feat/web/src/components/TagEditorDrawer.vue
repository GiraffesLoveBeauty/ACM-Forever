<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import TagManagement from '../views/TagManagement.vue';
const props = defineProps({
  platform: { type: String, required: true },
  problemId: { type: String, required: true },
});
const emit = defineEmits(['close', 'saved']);
const dialog = ref(null),
  editor = ref(null);
let previousFocus;
function close() {
  editor.value?.requestClose();
}
onMounted(() => {
  previousFocus = document.activeElement;
  if (dialog.value?.showModal) dialog.value.showModal();
  else dialog.value?.setAttribute?.('open', '');
});
onBeforeUnmount(() => {
  dialog.value?.close?.();
  previousFocus?.focus?.();
});
</script>
<template>
  <dialog
    ref="dialog"
    class="bank-tag-drawer"
    aria-labelledby="bank-tag-editor-title"
    @cancel.prevent="close"
    @click="
      (e) => {
        if (e.target === dialog) close();
      }
    "
  >
    <div class="bank-drawer-head">
      <div>
        <span>题库 / 人工标签</span>
        <h2 id="bank-tag-editor-title">修正算法标签</h2>
      </div>
      <button class="bank-drawer-close" aria-label="关闭标签编辑" @click="close">×</button>
    </div>
    <TagManagement
      ref="editor"
      embedded
      :platform="props.platform"
      :problem-id="props.problemId"
      @saved="emit('saved', $event)"
      @close="emit('close')"
    />
  </dialog>
</template>
<style scoped>
.bank-tag-drawer {
  box-sizing: border-box;
  width: min(950px, 100vw);
  height: 100dvh;
  max-height: 100dvh;
  max-width: 100vw;
  margin: 0 0 0 auto;
  padding: 0;
  border: 0;
  border-left: 1px solid #d8e5df;
  background: var(--bg, #f4f7f5);
  color: var(--text, #20362f);
  overflow: auto;
  box-shadow: -16px 0 80px #162f3c26;
}
.bank-tag-drawer::backdrop {
  background: #162a3370;
  backdrop-filter: blur(3px);
}
.bank-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 18px 24px;
  background: var(--card-bg, #fff);
  border-bottom: 1px solid #dce4e2;
}
.bank-drawer-head span {
  font-size: 11px;
  color: #6b7d76;
}
.bank-drawer-head h2 {
  font-size: 19px;
  margin: 6px 0 0;
}
.bank-drawer-close {
  border: 1px solid #dce4e2;
  background: transparent;
  color: inherit;
  width: 36px;
  height: 36px;
  font: 24px/1 system-ui;
  cursor: pointer;
  border-radius: 6px;
}
.bank-drawer-close:focus-visible {
  outline: 2px solid #176c60;
  outline-offset: 2px;
}
@media (max-width: 640px) {
  .bank-drawer-head {
    padding: 15px 18px;
  }
}
</style>
