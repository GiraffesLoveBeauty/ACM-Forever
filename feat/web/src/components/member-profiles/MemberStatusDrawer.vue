<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
const props = defineProps({ member: Object, statuses: Array, pending: Array, initial: Object });
const emit = defineEmits(['select', 'draft', 'close', 'cancel']);
const panel = ref(),
  search = ref(''),
  creating = ref(Boolean(props.initial?.creating)),
  name = ref(props.initial?.text || ''),
  error = ref('');
const previous = typeof document !== 'undefined' ? document.activeElement : null;
const candidates = computed(() =>
  [...new Set([...(props.statuses || []), ...(props.pending || [])])]
    .sort()
    .filter((value) => value.includes(search.value.trim())),
);
function remember() {
  emit('draft', { creating: creating.value, text: name.value });
}
async function start() {
  creating.value = true;
  remember();
  await nextTick();
  panel.value?.querySelector?.('[data-new-status]')?.focus();
}
function create() {
  const value = name.value.trim();
  if (!value) error.value = '身份名称不能为空。';
  else if (value.length > 64) error.value = '身份最多 64 字符。';
  else if ([...(props.statuses || []), ...(props.pending || [])].includes(value))
    error.value = '该身份已存在，请选择已有项。';
  else emit('select', value);
}
function keys(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    emit('close');
    return;
  }
  if (event.key !== 'Tab') return;
  const nodes = [
    ...(panel.value?.querySelectorAll?.(
      'button:not(:disabled),input:not(:disabled),[tabindex="0"]',
    ) || []),
  ];
  if (!nodes.length) return;
  const first = nodes[0],
    last = nodes.at(-1);
  if (
    event.shiftKey &&
    (document.activeElement === first || document.activeElement === panel.value)
  ) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
onMounted(async () => {
  await nextTick();
  panel.value?.querySelector?.('input')?.focus();
});
onBeforeUnmount(() => previous?.focus?.());
</script>
<template>
  <div class="member-drawer-mask" @click.self="emit('close')">
    <section
      ref="panel"
      class="member-status-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="status-title"
      tabindex="-1"
      @keydown="keys"
    >
      <header>
        <h2 id="status-title">选择成员身份</h2>
        <button class="btn" aria-label="关闭身份选择器" @click="emit('close')">×</button>
      </header>
      <p>{{ member.name || '成员' }} · QQ {{ member.qq_id }}</p>
      <p class="muted">身份仅为资料标签，不改变账号权限。</p>
      <label>搜索身份<input v-model="search" type="search" /></label>
      <div class="member-status-options">
        <button class="btn" @click="emit('select', '')">设为未填写</button>
        <button
          v-for="status in candidates"
          :key="status"
          class="btn"
          @click="emit('select', status)"
        >
          {{ status }}<small v-if="!statuses.includes(status)"> · 待保存</small>
        </button>
        <button class="btn" @click="start">＋ 新建身份</button>
      </div>
      <form v-if="creating" @submit.prevent="create">
        <label
          >新身份名称<input
            v-model="name"
            data-new-status
            @input="
              error = '';
              remember();
            "
        /></label>
        <p v-if="error" role="alert">{{ error }}</p>
        <button class="btn primary">创建并应用</button>
        <p class="muted">应用到本地草稿，保存资料后才生效。</p>
      </form>
      <button class="btn" @click="emit('cancel')">取消此次身份输入</button>
    </section>
  </div>
</template>
<style scoped>
.member-drawer-mask {
  position: fixed;
  inset: 0;
  background: #0008;
  z-index: 3000;
  display: flex;
  justify-content: flex-end;
}
.member-status-drawer {
  width: min(440px, 100%);
  height: 100%;
  overflow: auto;
  background: var(--panel);
  color: var(--text);
  padding: 24px;
  box-shadow: -8px 0 40px #0002;
  box-sizing: border-box;
}
.member-status-drawer header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.member-status-drawer h2 {
  margin: 0;
}
.member-status-drawer label {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}
.member-status-options {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}
.member-status-options .btn {
  text-align: left;
  justify-content: flex-start;
  white-space: normal;
}
.member-status-drawer form {
  border-top: 1px solid var(--line);
  padding: 12px 0;
}
</style>
