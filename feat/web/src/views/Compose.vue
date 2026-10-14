<script setup>
import { ref, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router';
import { api, useRequests, notify, showError } from '../lib/api.js';
import { markdown } from '../lib/markdown.js';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const form = reactive({ title: '', body: '', category_id: null }),
  categories = ref([]),
  drafts = ref([]),
  id = ref(null),
  mode = ref('write'),
  input = ref(),
  message = ref('新话题尚未保存'),
  busy = ref(false);
let revision = 0,
  savedRevision = 0,
  timer,
  saving,
  loading = false,
  disposed = false,
  finished = false,
  leaving = false;
function payload() {
  return { title: form.title, body: form.body, category_id: form.category_id || null };
}
async function list() {
  drafts.value = await request('/forum/drafts');
}
watch(
  form,
  () => {
    if (loading) return;
    revision++;
    clearTimeout(timer);
    message.value = '有未保存的修改';
    timer = setTimeout(() => save().catch(showError), 900);
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
        data = payload();
      message.value = '正在保存…';
      const result = await api(id.value ? `/forum/drafts/${id.value}` : '/forum/drafts', {
        method: id.value ? 'PUT' : 'POST',
        body: data,
        keepalive,
      });
      id.value = result.id;
      savedRevision = version;
      if (!keepalive && !leaving && String(route.query.draft_id) !== String(id.value))
        await router.replace({ path: '/compose.html', query: { draft_id: id.value } });
    }
    message.value = '草稿已保存';
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
    if (!form.title.trim() || !form.body.trim() || !form.category_id)
      throw Error('请填写版块、标题和正文。');
    await save();
    const data = await api(`/forum/drafts/${id.value}/submit`, { method: 'POST', body: {} });
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
  if (!finished && !disposed && revision !== savedRevision && !saving)
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
    categories.value = await request('/forum/categories');
    await list();
    if (route.query.draft_id) await choose(route.query.draft_id);
  } catch (e) {
    showError(e);
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
          <div v-else class="compose-preview forum-markdown" v-html="markdown(form.body)"></div>
        </section>
        <div class="compose-actions">
          <button class="btn" :disabled="busy" @click="save().catch(showError)">保存草稿</button
          ><button class="btn primary" :disabled="busy" @click="submit">
            {{ busy ? '正在处理…' : '提交审核' }}</button
          ><button v-if="id" class="btn" :disabled="busy" @click="remove">删除草稿</button
          ><span class="muted">{{ form.body.length }} / 20000</span>
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
