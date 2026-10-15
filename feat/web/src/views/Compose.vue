<script setup>
import { ref, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router';
import { api, useRequests, notify, showError, auth } from '../lib/api.js';
import { markdown } from '../lib/markdown.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive({ title: '', body: '', category_id: null }),
  categories = ref([]),
  drafts = ref([]),
  id = ref(null),
  mode = ref('write'),
  input = ref(),
  fileInput = ref(),
  recoveryCandidate = ref(null),
  recoveryKeyForCandidate = ref(''),
  message = ref('新话题尚未保存'),
  busy = ref(false);
let revision = 0,
  savedRevision = 0,
  timer,
  saving,
  loading = false,
  disposed = false,
  finished = false,
  leaving = false,
  recoveryTabId = '',
  recoveryResolved = false;
function payload() {
  return { title: form.title, body: form.body, category_id: form.category_id || null };
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
  const key = recoveryCandidate.value && !recoveryResolved
    ? workingRecoveryKey()
    : recoveryKey();
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
    const previousKey = previousKeys[index], nextKey = nextKeys[index];
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
  if (recoveryKeyForCandidate.value === previousKeys[0]) recoveryKeyForCandidate.value = nextKeys[0];
  else if (recoveryKeyForCandidate.value === previousKeys[1]) recoveryKeyForCandidate.value = nextKeys[1];
}
function discoverRecovery(serverPayload) {
  const key = recoveryKey(), workingKey = workingRecoveryKey();
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
          parsed?.payload && typeof parsed.payload.title === 'string' &&
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
    if (serverPayload &&
      local.title === serverPayload.title && local.body === serverPayload.body &&
      String(local.category_id || '') === String(serverPayload.category_id || '')
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
function findFirstMarkdownH1(source) {
  let offset = 0;
  for (const token of marked.lexer(source, { gfm: true })) {
    const raw = String(token.raw || '');
    if (!raw) continue;
    let startOffset = source.indexOf(raw, offset);
    if (token.type === 'heading' && token.depth === 1) {
      while (startOffset >= 0) {
        const lineStart = source.lastIndexOf('\n', startOffset - 1) + 1;
        if (/^[\t ]{0,3}$/.test(source.slice(lineStart, startOffset))) break;
        startOffset = source.indexOf(raw, startOffset + 1);
      }
    }
    if (startOffset < 0) continue;
    if (token.type === 'heading' && token.depth === 1) {
      const inlineHtml = DOMPurify.sanitize(marked.parseInline(token.text || '', { gfm: true }));
      const titleNode = document.createElement('div');
      titleNode.innerHTML = inlineHtml;
      return { startOffset, endOffset: startOffset + raw.length, title: titleNode.textContent.trim() };
    }
    offset = startOffset + raw.length;
  }
  return null;
}
async function importMarkdown(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file || busy.value) return;
  if (!/\.(md|markdown)$/i.test(file.name)) {
    notify('请选择 .md 或 .markdown 文件。');
    return;
  }
  if (file.size > 102400) {
    notify('Markdown 文件不能超过 100 KB。');
    return;
  }
  if ((form.title.trim() || form.body.trim()) && !confirm('导入 Markdown 会替换当前标题和正文，确定继续吗？')) return;
  busy.value = true;
  try {
    const text = (await file.text()).replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
    const heading = findFirstMarkdownH1(text);
    let title = Array.from(file.name.replace(/\.(md|markdown)$/i, '')).slice(0, 120).join('');
    let body = text;
    if (heading) {
      title = Array.from(heading.title).slice(0, 120).join('');
      body = (text.slice(0, heading.startOffset) + text.slice(heading.endOffset)).replace(/^\n+/, '');
    }
    if (Array.from(body).length > 20000) throw Error('Markdown 正文超过 20000 个字符，请精简后再导入。');
    form.title = title;
    form.body = body;
    notify('Markdown 已导入，草稿正在自动保存。');
  } catch (error) {
    showError(error);
  } finally {
    busy.value = false;
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
        data = payload(),
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
      : { title: '', body: '', category_id: null };
    Object.assign(form, {
      title: data.title || '',
      body: data.body || '',
      category_id: data.category_id || null,
    });
    id.value = draftId;
    revision = 0;
    savedRevision = 0;
    recoveryCandidate.value = null;
    recoveryKeyForCandidate.value = '';
    recoveryResolved = true;
    discoverRecovery(payload());
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
    Object.assign(form, { title: '', body: '', category_id: null });
    id.value = null;
    revision = savedRevision = 0;
    await router.replace('/compose.html');
    await list();
    message.value = '草稿已删除';
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
    busy.value = false;
  }
}
const formats = {
  h1: ['# ', ''],
  h2: ['## ', ''],
  bold: ['**', '**'],
  italic: ['*', '*'],
  strike: ['~~', '~~'],
  quote: ['> ', ''],
  ul: ['- ', ''],
  ol: ['1. ', ''],
  code: ['`', '`'],
  codeblock: ['\n```\n', '\n```\n'],
  link: ['[', '](https://)'],
};
async function format(kind) {
  const node = input.value;
  if (!node) return;
  const start = node.selectionStart,
    end = node.selectionEnd,
    [before, after] = formats[kind];
  const text = form.body.slice(start, end) || '文字';
  form.body = form.body.slice(0, start) + before + text + after + form.body.slice(end);
  await nextTick();
  node.focus();
  node.setSelectionRange(start + before.length, start + before.length + text.length);
}
function unload(event) {
  if (revision !== savedRevision || saving) {
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
    recoveryTabId = window.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    id.value = route.query.draft_id || null;
    // Read the same user's local copy before any request so offline starts can recover it.
    discoverRecovery();
    const results = await Promise.allSettled([
      request('/forum/categories'),
      list(),
      route.query.draft_id ? request(`/forum/drafts/${route.query.draft_id}`, {}, 'draft') : Promise.resolve(null),
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
        });
        discoverRecovery(payload());
        message.value = '已读取草稿';
      } else showError(results[2].reason);
    } else message.value = '新话题尚未保存';
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
  }
});
onBeforeUnmount(() => {
  disposed = true;
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
        <label class="compose-field"
          >选择版块<select v-model="form.category_id" :disabled="busy">
            <option :value="null">选择一个版块</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></label
        ><label class="compose-field"
          >话题标题<input
            v-model="form.title"
            :disabled="busy"
            maxlength="120"
            placeholder="用一句话概括你想讨论的内容"
        /></label>
        <section class="compose-body-field">
          <div class="compose-body-label">
            <span>正文 <small>支持 Markdown</small></span>
            <div class="compose-view-tabs">
              <button
                v-for="(label, key) in { write: '编辑', preview: '预览' }"
                :key="key"
                :class="{ active: mode === key }"
                @click="mode = key"
              >
                {{ label }}
              </button>
            </div>
          </div>
          <div
            v-if="mode === 'write'"
            class="markdown-toolbar"
            role="toolbar"
            aria-label="Markdown 格式工具"
          >
            <button type="button" :disabled="busy" @click="fileInput?.click()">导入 .md</button>
            <input
              ref="fileInput"
              type="file"
              accept=".md,.markdown,text/markdown,text/plain"
              aria-label="选择 Markdown 文件"
              hidden
              :disabled="busy"
              @change="importMarkdown"
            />
            <span class="toolbar-divider"></span>
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
              :disabled="busy"
              @click="format(key)"
            >
              {{ label }}
            </button>
          </div>
          <textarea
            v-if="mode === 'write'"
            ref="input"
            v-model="form.body"
            class="compose-textarea"
            :disabled="busy"
            rows="18"
            maxlength="20000"
            placeholder="记录你的思路…"
          ></textarea>
          <div v-else v-forum-math class="compose-preview forum-markdown" v-html="markdown(form.body)"></div>
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
