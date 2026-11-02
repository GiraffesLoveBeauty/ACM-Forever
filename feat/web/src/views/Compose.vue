<script setup>
import { computed, ref, reactive, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router';
import { api, useRequests, notify, showError, auth } from '../lib/api.js';
import { sourceFields } from '../lib/markdown-source.js';
import MarkdownEditor from '../components/MarkdownEditor.vue';
import { postImage, uploadPostImage } from '../lib/post-images.js';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive({ title: '', body: '', category_id: null, cover_image_id: null }),
  categories = ref([]),
  drafts = ref([]),
  id = ref(null),
  mode = ref('split'),
  coverInput = ref(),
  imageUploadMessage = ref(''),
  recoveryCandidate = ref(null),
  recoveryKeyForCandidate = ref(''),
  message = ref('新话题尚未保存'),
  busy = ref(false);
const coverSource = computed(() =>
  postImage(form.cover_image_id ? `/api/forum/images/${form.cover_image_id}` : ''),
);
let revision = 0,
  savedRevision = 0,
  timer,
  saving,
  loading = false,
  disposed = false,
  finished = false,
  leaving = false,
  recoveryTabId = '',
  recoveryResolved = false,
  coverController;
function payload() {
  return {
    title: form.title,
    body: form.body,
    category_id: form.category_id || null,
    cover_image_id: form.cover_image_id || null,
  };
}
function recoveryKey(draftId = id.value) {
  const scope = draftId == null ? 'new' : String(draftId);
  return `acm-forum-compose:${auth.qq_id || 'member'}:${scope}:tab:${recoveryTabId || 'tab'}`;
}
function workingRecoveryKey(draftId = id.value) {
  return `${recoveryKey(draftId)}:working`;
}
function removeRecoveryKey(key) {
  try {
    localStorage.removeItem(key);
    localStorage.removeItem(`acm-forum-compose-handled:${key}`);
  } catch {
    // Private browsing or storage quotas can disable local recovery.
  }
}
function markRecoveryHandled(key) {
  try {
    const stored = localStorage.getItem(key);
    if (stored) localStorage.setItem(`acm-forum-compose-handled:${key}`, stored);
  } catch {
    // Handled markers are best-effort; the recovery copy remains available.
  }
}
function persistRecovery() {
  const key = recoveryCandidate.value && !recoveryResolved ? workingRecoveryKey() : recoveryKey();
  try {
    localStorage.setItem(key, JSON.stringify({ payload: payload(), updated_at: Date.now() }));
    localStorage.removeItem(`acm-forum-compose-handled:${key}`);
    return true;
  } catch {
    return false;
  }
}
function migrateRecovery(previousId, nextId) {
  const previousKeys = [recoveryKey(previousId), workingRecoveryKey(previousId)];
  const nextKeys = [recoveryKey(nextId), workingRecoveryKey(nextId)];
  for (let index = 0; index < previousKeys.length; index++) {
    const previousKey = previousKeys[index],
      nextKey = nextKeys[index];
    if (previousKey === nextKey) continue;
    try {
      const stored = localStorage.getItem(previousKey);
      if (stored) {
        localStorage.setItem(nextKey, stored);
        localStorage.removeItem(`acm-forum-compose-handled:${nextKey}`);
        if (localStorage.getItem(previousKey) === stored) removeRecoveryKey(previousKey);
      }
    } catch {
      // Keep the previous key when the new location cannot be written.
    }
  }
  if (recoveryKeyForCandidate.value === previousKeys[0])
    recoveryKeyForCandidate.value = nextKeys[0];
  else if (recoveryKeyForCandidate.value === previousKeys[1])
    recoveryKeyForCandidate.value = nextKeys[1];
}
function discoverRecovery(serverPayload) {
  const key = recoveryKey(),
    workingKey = workingRecoveryKey();
  let candidate = null;
  recoveryCandidate.value = null;
  recoveryKeyForCandidate.value = '';
  recoveryResolved = true;
  try {
    const prefix = `acm-forum-compose:${auth.qq_id || 'member'}:${id.value == null ? 'new' : id.value}:tab:`;
    for (let index = 0; index < localStorage.length; index++) {
      const candidateKey = localStorage.key(index);
      if (!candidateKey?.startsWith(prefix)) continue;
      const suffix = candidateKey.slice(prefix.length);
      if (!/^[^:]+(?::working)?$/.test(suffix)) continue;
      const handledKey = `acm-forum-compose-handled:${candidateKey}`;
      const stored = localStorage.getItem(candidateKey);
      if (!stored) continue;
      if (localStorage.getItem(handledKey) === stored) continue;
      try {
        const parsed = JSON.parse(stored);
        if (
          parsed?.payload &&
          typeof parsed.payload.title === 'string' &&
          typeof parsed.payload.body === 'string' &&
          (!candidate || Number(parsed.updated_at || 0) > Number(candidate.value.updated_at || 0))
        )
          candidate = { key: candidateKey, value: parsed };
      } catch {
        // Ignore a corrupt tab copy and keep searching for a valid recovery.
      }
    }
    if (!candidate) {
      const legacyKey = `acm-forum-compose:${auth.qq_id || 'member'}:${id.value == null ? 'new' : id.value}`;
      const stored = localStorage.getItem(legacyKey);
      if (stored) {
        localStorage.setItem(key, stored);
        localStorage.removeItem(legacyKey);
        candidate = { key, value: JSON.parse(stored) };
      }
    }
    if (!candidate?.value?.payload) return;
    if (candidate.key === workingKey) {
      try {
        localStorage.setItem(key, JSON.stringify(candidate.value));
        candidate.key = key;
      } catch {
        // Keep the original copy if storage cannot duplicate it.
      }
    }
    const local = candidate.value.payload;
    if (
      serverPayload &&
      local.title === serverPayload.title &&
      local.body === serverPayload.body &&
      String(local.category_id || '') === String(serverPayload.category_id || '') &&
      (local.cover_image_id || null) === (serverPayload.cover_image_id || null)
    ) {
      if (candidate.key === key || candidate.key === workingKey) removeRecoveryKey(candidate.key);
      else markRecoveryHandled(candidate.key);
      return;
    }
    recoveryCandidate.value = local;
    recoveryKeyForCandidate.value = candidate.key;
    recoveryResolved = false;
  } catch {
    recoveryCandidate.value = null;
  }
}
function markDirty() {
  revision++;
  clearTimeout(timer);
  const persisted = persistRecovery();
  message.value = persisted ? '有未保存的修改' : '本地恢复保存失败，请尽快复制内容';
  timer = setTimeout(() => save().catch(showError), 900);
}
function restoreRecovery() {
  if (!recoveryCandidate.value) return;
  const candidateKey = recoveryKeyForCandidate.value;
  loading = true;
  Object.assign(form, {
    title: recoveryCandidate.value.title || '',
    body: recoveryCandidate.value.body || '',
    category_id: recoveryCandidate.value.category_id || null,
    cover_image_id: recoveryCandidate.value.cover_image_id || null,
  });
  loading = false;
  recoveryResolved = true;
  if (candidateKey && candidateKey !== recoveryKey() && candidateKey !== workingRecoveryKey())
    markRecoveryHandled(candidateKey);
  removeRecoveryKey(recoveryKey());
  removeRecoveryKey(workingRecoveryKey());
  recoveryCandidate.value = null;
  recoveryKeyForCandidate.value = '';
  markDirty();
}
function discardRecovery() {
  const candidateKey = recoveryKeyForCandidate.value;
  if (candidateKey && candidateKey !== recoveryKey() && candidateKey !== workingRecoveryKey())
    markRecoveryHandled(candidateKey);
  removeRecoveryKey(recoveryKey());
  removeRecoveryKey(workingRecoveryKey());
  recoveryCandidate.value = null;
  recoveryKeyForCandidate.value = '';
  recoveryResolved = true;
  if (revision !== savedRevision) persistRecovery();
}
async function prepareImageUpload() {
  if (!id.value && revision === savedRevision) revision++;
  await save();
  return id.value;
}
async function uploadBodyImage(file, options) {
  const result = await uploadPostImage(file, options);
  if (!postImage(result.url)) throw Error('服务器未返回有效的图片地址。');
  return result;
}
async function selectCover(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file || busy.value) return;
  busy.value = true;
  coverController = new AbortController();
  imageUploadMessage.value = '正在处理并上传封面…';
  try {
    const result = await uploadBodyImage(file, { signal: coverController.signal });
    if (disposed) return;
    form.cover_image_id = result.id;
    await save();
    if (!disposed) imageUploadMessage.value = '封面已上传并保存到草稿。';
  } catch (error) {
    if (!disposed && error.name !== 'AbortError') {
      imageUploadMessage.value = error.message;
      showError(error);
    }
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function list() {
  drafts.value = await request('/forum/drafts');
}
watch(
  form,
  () => {
    if (loading) return;
    markDirty();
  },
  { flush: 'sync' },
);
async function save({ keepalive = false } = {}) {
  clearTimeout(timer);
  if (saving) return saving;
  if (revision === savedRevision || disposed) return;
  saving = (async () => {
    while (revision !== savedRevision && !disposed) {
      const version = revision,
        data = { ...payload(), ...sourceFields(form) },
        previousId = id.value;
      message.value = '正在保存…';
      const result = await api(id.value ? `/forum/drafts/${id.value}` : '/forum/drafts', {
        method: id.value ? 'PUT' : 'POST',
        body: data,
        keepalive,
      });
      id.value = result.id;
      if (previousId !== id.value) migrateRecovery(previousId, id.value);
      savedRevision = version;
      if (revision === version) {
        if (recoveryKeyForCandidate.value !== workingRecoveryKey() || recoveryResolved)
          removeRecoveryKey(workingRecoveryKey());
        if (!recoveryCandidate.value || recoveryResolved) {
          removeRecoveryKey(recoveryKey());
          removeRecoveryKey(recoveryKey(previousId));
        }
      } else persistRecovery();
      if (!keepalive && !leaving && String(route.query.draft_id) !== String(id.value))
        await router.replace({ path: '/compose.html', query: { draft_id: id.value } });
    }
    if (revision === savedRevision) message.value = '草稿已保存';
  })();
  try {
    await saving;
  } catch (e) {
    message.value = '保存失败：' + e.message;
    throw e;
  } finally {
    saving = null;
  }
  if (!keepalive) list().catch(showError);
}
async function choose(draftId) {
  if (busy.value) return;
  busy.value = true;
  try {
    await save();
    loading = true;
    const data = draftId
      ? await request(`/forum/drafts/${draftId}`, {}, 'draft')
      : { title: '', body: '', category_id: null, cover_image_id: null };
    Object.assign(form, {
      title: data.title || '',
      body: data.body || '',
      category_id: data.category_id || null,
      cover_image_id: data.cover_image_id || null,
    });
    id.value = draftId;
    revision = 0;
    savedRevision = 0;
    recoveryCandidate.value = null;
    recoveryKeyForCandidate.value = '';
    recoveryResolved = true;
    discoverRecovery(payload());
    imageUploadMessage.value = '';
    message.value = draftId ? '已读取草稿' : '新话题尚未保存';
    await router.replace({ path: '/compose.html', query: draftId ? { draft_id: draftId } : {} });
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
    busy.value = false;
  }
}
async function submit() {
  if (busy.value) return;
  busy.value = true;
  try {
    if (recoveryCandidate.value) throw Error('请先恢复或丢弃本地恢复内容，再提交草稿。');
    if (!form.title.trim() || !form.body.trim() || !form.category_id)
      throw Error('请填写版块、标题和正文。');
    await save();
    const data = await api(`/forum/drafts/${id.value}/submit`, { method: 'POST', body: {} });
    removeRecoveryKey(recoveryKey());
    removeRecoveryKey(workingRecoveryKey());
    recoveryResolved = true;
    finished = true;
    notify(data.message || '话题已提交审核');
    await router.push('/index.html');
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function remove() {
  if (!id.value || busy.value || !confirm('删除当前草稿？')) return;
  busy.value = true;
  clearTimeout(timer);
  try {
    if (saving) await saving;
    await api(`/forum/drafts/${id.value}`, { method: 'DELETE' });
    removeRecoveryKey(recoveryKey());
    removeRecoveryKey(workingRecoveryKey());
    loading = true;
    Object.assign(form, { title: '', body: '', category_id: null, cover_image_id: null });
    id.value = null;
    revision = savedRevision = 0;
    await router.replace('/compose.html');
    await list();
    message.value = '草稿已删除';
    imageUploadMessage.value = '';
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
    busy.value = false;
  }
}
function unload(event) {
  if (revision !== savedRevision || saving || busy.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
function pagehide() {
  if (!finished && revision !== savedRevision) persistRecovery();
  if (!finished && !disposed && id.value != null && revision !== savedRevision && !saving)
    save({ keepalive: true }).catch(() => {
      /* The page is leaving; a failed request must not report a successful save. */
    });
}
onBeforeRouteLeave(async () => {
  if (finished) return true;
  if (busy.value) {
    notify('正在处理草稿，请稍候再离开。');
    return false;
  }
  leaving = true;
  try {
    await save();
    return true;
  } catch {
    const allowed = confirm('草稿未能保存。仍要离开并放弃未保存的修改？');
    if (!allowed) leaving = false;
    return allowed;
  }
});
onMounted(async () => {
  window.addEventListener('beforeunload', unload);
  window.addEventListener('pagehide', pagehide);
  try {
    // sessionStorage is copied when a tab is duplicated, so each editor instance needs a fresh key.
    recoveryTabId =
      window.crypto?.randomUUID?.() ||
      `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    id.value = route.query.draft_id || null;
    // Read the same user's local copy before any request so offline starts can recover it.
    discoverRecovery();
    const results = await Promise.allSettled([
      request('/forum/categories'),
      list(),
      route.query.draft_id
        ? request(`/forum/drafts/${route.query.draft_id}`, {}, 'draft')
        : Promise.resolve(null),
    ]);
    if (results[0].status === 'fulfilled') categories.value = results[0].value;
    else showError(results[0].reason);
    if (results[1].status === 'rejected') showError(results[1].reason);
    if (route.query.draft_id) {
      if (results[2].status === 'fulfilled') {
        loading = true;
        Object.assign(form, {
          title: results[2].value.title || '',
          body: results[2].value.body || '',
          category_id: results[2].value.category_id || null,
          cover_image_id: results[2].value.cover_image_id || null,
        });
        discoverRecovery(payload());
        message.value = '已读取草稿';
      } else {
        showError(results[2].reason);
        if (results[2].reason?.status === 404) {
          // Keep the recovery candidate discovered under the missing draft ID,
          // but make subsequent saves create a fresh draft instead of PUTting to a 404.
          id.value = null;
          await router.replace({ path: '/compose.html', query: {} });
        }
      }
    } else message.value = '新话题尚未保存';
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
  }
});
onBeforeUnmount(() => {
  disposed = true;
  coverController?.abort();
  clearTimeout(timer);
  window.removeEventListener('beforeunload', unload);
  window.removeEventListener('pagehide', pagehide);
});
</script>
<template>
  <main class="compose-main">
    <div class="compose-topline">
      <RouterLink to="/index.html">← 返回论坛</RouterLink
      ><span class="compose-save-state" role="status">{{ message }}</span>
    </div>
    <div v-if="recoveryCandidate" class="compose-recovery" role="status">
      <span>发现一份尚未同步到账号的本地内容。请选择恢复或丢弃后继续编辑。</span>
      <div>
        <button type="button" :disabled="busy" @click="restoreRecovery">恢复内容</button>
        <button type="button" :disabled="busy" @click="discardRecovery">丢弃</button>
      </div>
    </div>
    <div class="compose-grid">
      <section class="compose-editor-panel">
        <div class="compose-heading">
          <span class="panel-eyebrow">WRITE SOMETHING GOOD</span>
          <h1>发布新话题</h1>
          <p>写下问题、题解或训练心得。草稿会自动保存到你的账号。</p>
        </div>
        <div class="compose-basics">
          <div class="compose-basics-fields">
            <label class="compose-field"
              >选择版块<select v-model="form.category_id" :disabled="busy">
                <option :value="null">选择一个版块</option>
                <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select></label
            ><label class="compose-field"
              >话题标题<input
                v-model="form.title"
                :disabled="busy"
                maxlength="240"
                placeholder="用一句话概括你想讨论的内容"
            /></label>
          </div>
          <section class="compose-cover-field" aria-label="帖子封面">
            <span>帖子封面 <small>选填</small></span>
            <img
              v-if="coverSource"
              :src="coverSource"
              alt="当前帖子封面"
              class="compose-cover-preview"
            />
            <button
              v-else
              class="compose-cover-empty"
              type="button"
              :disabled="busy"
              @click="coverInput?.click()"
            >
              <b aria-hidden="true">＋</b><span>上传一张封面</span
              ><small>让你的分享更容易被发现</small>
            </button>
            <input
              ref="coverInput"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              aria-label="选择帖子封面"
              hidden
              :disabled="busy"
              @change="selectCover"
            />
            <div class="compose-cover-actions">
              <button
                v-if="coverSource"
                class="btn"
                type="button"
                :disabled="busy"
                @click="coverInput?.click()"
              >
                更换封面
              </button>
              <button
                v-if="coverSource"
                class="btn"
                type="button"
                :disabled="busy"
                @click="form.cover_image_id = null"
              >
                移除封面
              </button>
            </div>
          </section>
        </div>
        <section class="compose-body-field">
          <div class="compose-body-label">
            <span>正文 <small>Markdown · LaTeX · 图片</small></span>
            <div class="compose-view-tabs">
              <button
                v-for="(label, key) in { write: '编辑', split: '双栏', preview: '预览' }"
                :key="key"
                :class="{ active: mode === key }"
                @click="mode = key"
              >
                {{ label }}
              </button>
            </div>
          </div>
          <p class="compose-image-hint">
            支持选择、粘贴或拖入 PNG / JPEG / WebP，原图最大 20 MB，上传前会自动压缩。
          </p>
          <p v-if="imageUploadMessage" class="compose-image-status" role="status">
            {{ imageUploadMessage }}
          </p>
          <MarkdownEditor
            v-model="form.body"
            v-model:title="form.title"
            :mode="mode"
            :disabled="busy"
            document-type="forum_draft"
            :document-id="id"
            :prepare-upload="prepareImageUpload"
            :upload-image="uploadBodyImage"
            :download-url="id ? `/api/forum/drafts/${id}/markdown` : ''"
            @uploading="busy = $event"
            @uploaded="save().catch(showError)"
          />
        </section>
        <div class="compose-actions">
          <button class="btn" :disabled="busy" @click="save().catch(showError)">保存草稿</button
          ><button class="btn primary" :disabled="busy" @click="submit">
            {{ busy ? '正在处理…' : '提交审核' }}</button
          ><button v-if="id" class="btn" :disabled="busy" @click="remove">删除草稿</button
          ><span class="muted">{{ Array.from(form.body).length }} / 20000</span>
        </div>
      </section>
      <aside class="compose-sidebar">
        <section class="forum-rail-card">
          <h2>我的草稿</h2>
          <button class="btn" :disabled="busy" @click="choose(null)">＋ 新话题</button
          ><button
            v-for="draft in drafts"
            :key="draft.id"
            class="vue-draft-item"
            :class="{ active: String(id) === String(draft.id) }"
            :disabled="busy"
            @click="choose(draft.id)"
          >
            <b>{{ draft.title || '未命名草稿' }}</b>
          </button>
          <p v-if="!drafts.length" class="muted">暂时没有草稿</p>
        </section>
        <section class="forum-rail-card">
          <h2>让讨论更清楚</h2>
          <p>描述问题背景、展示自己的尝试，题解请注明来源。</p>
        </section>
      </aside>
    </div>
  </main>
</template>
