<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { auth, avatar, notify, showError, useRequests } from '../lib/api.js';
import { compressAvatar } from '../lib/avatar.js';
import { setProfile } from '../lib/profile-store.js';

/* 侧栏顶部「ACM Forever」区块：点击后在这里换头像、改昵称 */
const emit = defineEmits(['close']);
const request = useRequests();
const open = ref(true);
const busy = ref(false);
const name = ref('');
const preview = ref('');
const avatarUrl = ref(auth.avatar_url || null);
const fileName = ref('');
const input = ref(null);

async function load() {
  try {
    const data = await request('/me/profile', {}, 'quick-profile');
    const user = data?.user || data || {};
    name.value = user.name || '';
    avatarUrl.value = user.avatar_url || null;
    setProfile({ name: user.name, avatar_url: user.avatar_url });
  } catch (error) {
    showError(error);
  }
}

function close() {
  open.value = false;
  emit('close');
}

function pick() {
  input.value?.click();
}

function onFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  fileName.value = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    preview.value = String(reader.result || '');
  };
  reader.readAsDataURL(file);
  upload(file);
  event.target.value = '';
}

async function upload(file) {
  busy.value = true;
  try {
    const compressed = await compressAvatar(file);
    const form = new FormData();
    form.append('avatar', compressed, compressed.name);
    const data = await request('/me/avatar', { method: 'POST', body: form }, 'quick-avatar');
    avatarUrl.value = data.avatar_url;
    auth.avatar_url = data.avatar_url;
    setProfile({ avatar_url: data.avatar_url });
    notify('头像已更新');
  } catch (error) {
    preview.value = '';
    showError(error);
  } finally {
    busy.value = false;
  }
}

async function resetAvatar() {
  busy.value = true;
  try {
    await request('/me/avatar', { method: 'DELETE' }, 'quick-avatar');
    avatarUrl.value = null;
    preview.value = '';
    auth.avatar_url = null;
    setProfile({ avatar_url: null });
    notify('已恢复默认头像');
  } catch (error) {
    showError(error);
  } finally {
    busy.value = false;
  }
}

async function saveName() {
  const value = name.value.trim();
  if (!value) {
    notify('昵称不能为空');
    return;
  }
  busy.value = true;
  try {
    const data = await request('/me/profile', { method: 'PUT', body: { name: value } }, 'quick-profile');
    const saved = (data?.user || {}).name || value;
    name.value = saved;
    setProfile({ name: saved });
    notify('昵称已更新');
  } catch (error) {
    showError(error);
  } finally {
    busy.value = false;
  }
}

function onKey(event) {
  if (event.key === 'Escape') close();
}

onMounted(() => {
  load();
  document.addEventListener('keydown', onKey);
});
onBeforeUnmount(() => document.removeEventListener('keydown', onKey));
</script>

<template>
  <div v-if="open" class="quick-profile-backdrop" @click.self="close">
    <section class="quick-profile" role="dialog" aria-modal="true" aria-labelledby="quick-profile-title">
      <header class="quick-profile-head">
        <h2 id="quick-profile-title">头像与昵称</h2>
        <button type="button" class="quick-profile-close" aria-label="关闭" @click="close">×</button>
      </header>

      <div class="quick-profile-avatar">
        <img class="quick-profile-preview" :src="preview || avatar(avatarUrl)" alt="当前头像" />
        <div class="quick-profile-avatar-copy">
          <p class="quick-profile-hint">图片会自动压缩后上传，最大 2 MB。</p>
          <div class="quick-profile-actions">
            <button type="button" class="btn primary" :disabled="busy" @click="pick">
              {{ busy ? '处理中…' : '上传头像' }}
            </button>
            <button type="button" class="btn" :disabled="busy" @click="resetAvatar">恢复默认</button>
            <input ref="input" type="file" accept="image/*" hidden @change="onFile" />
          </div>
          <p v-if="fileName" class="quick-profile-hint">{{ fileName }}</p>
        </div>
      </div>

      <label class="quick-profile-field">
        <span>昵称</span>
        <input v-model="name" type="text" maxlength="24" placeholder="输入新的昵称" />
      </label>

      <footer class="quick-profile-foot">
        <button type="button" class="btn" @click="close">取消</button>
        <button type="button" class="btn primary" :disabled="busy" @click="saveName">保存昵称</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.quick-profile-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(12, 20, 16, 0.48);
  backdrop-filter: blur(2px);
}
.quick-profile {
  width: min(94vw, 460px);
  display: grid;
  gap: 16px;
  padding: 20px 22px 18px;
  border: 1px solid var(--gh-border-strong, #c2cad6);
  border-radius: var(--gh-radius, 8px);
  background: var(--gh-panel, #ffffff);
  color: var(--gh-fg, #1b2432);
  box-shadow: 0 18px 48px rgba(10, 18, 14, 0.28);
}
.quick-profile-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.quick-profile-head h2 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.01em;
}
.quick-profile-close {
  border: 0;
  background: transparent;
  color: var(--gh-fg-muted, #5b6678);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
}
.quick-profile-close:hover {
  background: var(--gh-hover-bg, #e6eaf1);
}
.quick-profile-avatar {
  display: flex;
  gap: 16px;
  align-items: center;
}
.quick-profile-preview {
  width: 72px;
  height: 72px;
  flex: 0 0 auto;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--gh-border, #d8dee7);
  background: var(--gh-canvas-inset, #e4e8ef);
}
.quick-profile-avatar-copy {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.quick-profile-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.quick-profile-hint {
  margin: 0;
  color: var(--gh-fg-muted, #5b6678);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.quick-profile-field {
  display: grid;
  gap: 6px;
  font-size: 12.5px;
  color: var(--gh-fg-muted, #5b6678);
}
.quick-profile-field input {
  padding: 9px 11px;
  font-size: 13.5px;
  color: var(--gh-fg, #1b2432);
  background: var(--gh-canvas-inset, #e4e8ef);
  border: 1px solid var(--gh-border, #d8dee7);
  border-radius: var(--gh-radius, 6px);
}
.quick-profile-field input:focus-visible {
  outline: 2px solid var(--gh-link, #2f5fd0);
  outline-offset: 1px;
}
.quick-profile-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
@media (max-width: 480px) {
  .quick-profile-avatar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
