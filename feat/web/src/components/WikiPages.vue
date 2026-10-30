<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth, useRequests } from '../lib/api.js';
import { downloadMarkdown, wikiKey } from '../lib/wiki.js';
import { sourceFields } from '../lib/markdown-source.js';
import MarkdownEditor from './MarkdownEditor.vue';
import MarkdownView from './MarkdownView.vue';
import Pager from './Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests(),
  registerLeave = inject('registerLeaveGuard', () => () => {});
const adminWikiApi = (path, options = {}) => request('/admin/wiki' + path, options);
const nav = ref(),
  listing = ref(),
  page = ref(),
  error = ref(''),
  status = ref(''),
  busy = ref(false),
  history = ref([]),
  historical = ref(),
  conflict = ref(),
  recovery = ref();
const form = reactive({
  title: '',
  body: '',
  slug: '',
  category_id: null,
  summary: '',
  tags: '',
  aliases: '',
  source: '',
  license: '',
  exercises: [],
});
const filters = reactive({
  q: route.query.q || '',
  category_id: route.query.category_id || '',
  state: route.query.state || '',
});
const children = computed(() => nav.value?.categories.filter((c) => c.parent_id != null) || []);
const dirty = computed(() => JSON.stringify(form) !== saved.value),
  saved = ref('');
let initialized = false,
  timer,
  saving,
  disposed = false,
  loading = false,
  loadRevision = 0,
  downloadController,
  updatingRoute = false,
  leaving = false;
const editorOwner = auth.qq_id;
const key = (id = page.value?.id) => `acm-wiki:${editorOwner}:${id || 'new'}`;
function content() {
  return {
    ...sourceFields(form),
    summary: form.summary,
    tags: form.tags
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
    aliases: form.aliases
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
    source: form.source,
    license: form.license,
    exercises: form.exercises
      .filter((e) => e.label.trim() || e.url.trim())
      .map((e) => ({ label: e.label, url: e.url })),
  };
}
function fill(data) {
  loading = true;
  page.value = data;
  Object.assign(
    form,
    data
      ? {
          ...data.draft,
          slug: data.slug,
          category_id: data.category_id,
          tags: data.draft.tags.join(', '),
          aliases: data.draft.aliases.join(', '),
          exercises: data.draft.exercises.map((e) => ({ ...e })),
        }
      : {
          title: '',
          body: '',
          slug: '',
          category_id: children.value[0]?.id || null,
          summary: '',
          tags: '',
          aliases: '',
          source: '',
          license: '',
          exercises: [],
        },
  );
  for (const name of Object.keys(form))
    if (
      ![
        'title',
        'body',
        'slug',
        'category_id',
        'summary',
        'tags',
        'aliases',
        'source',
        'license',
        'exercises',
      ].includes(name)
    )
      delete form[name];
  saved.value = JSON.stringify(form);
  loading = false;
  conflict.value = null;
  recovery.value = null;
  try {
    const stored = JSON.parse(localStorage.getItem(key()) || 'null');
    if (stored && JSON.stringify(stored.form) !== saved.value) recovery.value = stored;
  } catch {
    /* Invalid recovery data is ignored. */
  }
}
async function load() {
  const revision = ++loadRevision;
  try {
    error.value = '';
    const navigation = await request('/admin/wiki/categories', {}, 'wiki-admin-navigation');
    const rows = await request(
      '/admin/wiki/pages?' +
        new URLSearchParams({
          q: route.query.q || '',
          category_id: route.query.category_id || '',
          state: route.query.state || '',
          page: route.query.page || 1,
        }),
      {},
      'wiki-admin-list',
    );
    if (revision !== loadRevision) return;
    nav.value = navigation;
    listing.value = rows;
    const id = Number(route.query.page_id) || null;
    if (!initialized || page.value?.id !== id) {
      const data = id ? await request('/admin/wiki/pages/' + id, {}, 'wiki-admin-page') : null;
      if (revision !== loadRevision) return;
      fill(data);
      initialized = true;
      history.value = [];
      historical.value = null;
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  }
}
function persist() {
  try {
    localStorage.setItem(
      key(),
      JSON.stringify({
        form: { ...form },
        version: page.value?.version,
        base_revision_id: page.value?.draft_revision_id,
      }),
    );
  } catch {
    /* Server save remains the authoritative path. */
  }
}
async function save() {
  clearTimeout(timer);
  if (saving) return saving;
  if (!dirty.value || !initialized) return;
  if (recovery.value) throw Error('请先恢复或丢弃本地内容，再保存。');
  saving = (async () => {
    while (dirty.value && !disposed) {
      const snapshot = JSON.stringify(form),
        payload = content(),
        previousKey = key();
      if (!form.category_id) throw Error('请先创建并选择一个小类。');
      status.value = '正在保存草稿…';
      let result = page.value;
      if (!result) {
        const slug = form.slug || 'wiki-' + wikiKey().split('-').slice(0, 2).join('-');
        result = await adminWikiApi('/pages', {
          method: 'POST',
          body: { ...payload, category_id: form.category_id, slug },
        });
        if (!form.slug) {
          loading = true;
          form.slug = result.slug;
          loading = false;
        }
      } else {
        if (Number(form.category_id) !== result.category_id)
          result = await adminWikiApi('/pages/' + result.id, {
            method: 'PATCH',
            body: { category_id: Number(form.category_id), version: result.version },
          });
        result = await adminWikiApi(`/pages/${result.id}/revisions`, {
          method: 'POST',
          body: { ...payload, version: result.version, base_revision_id: result.draft_revision_id },
        });
      }
      page.value = result;
      const snapshotForm = JSON.parse(snapshot);
      if (!snapshotForm.slug) snapshotForm.slug = result.slug;
      saved.value = JSON.stringify(snapshotForm);
      status.value = '草稿已保存 · 修订 #' + result.draft_revision_id;
      try {
        localStorage.removeItem(previousKey);
        if (!dirty.value) localStorage.removeItem(key());
      } catch {
        /* Recovery cleanup is best effort. */
      }
      if (dirty.value) persist();
      if (!leaving && String(route.query.page_id) !== String(result.id)) {
        updatingRoute = true;
        try {
          await router.replace({
            path: '/admin.html',
            query: { ...route.query, section: 'wiki', tab: 'pages', page_id: result.id },
          });
        } finally {
          updatingRoute = false;
        }
      }
    }
  })();
  try {
    await saving;
    conflict.value = null;
    await refreshList();
  } catch (e) {
    error.value = e.message;
    status.value = '保存失败，输入已保留';
    persist();
    if (e.status === 409 && page.value)
      conflict.value = await adminWikiApi('/pages/' + page.value.id).catch(() => null);
    throw e;
  } finally {
    saving = null;
  }
}
async function refreshList() {
  listing.value = await request(
    '/admin/wiki/pages?' + new URLSearchParams({ ...filters, page: route.query.page || 1 }),
    {},
    'wiki-admin-list',
  );
}
async function act(fn) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function publish() {
  await act(async () => {
    await save();
    if (!page.value) throw Error('请先保存文章。');
    const result = await adminWikiApi(`/revisions/${page.value.draft_revision_id}/publish`, {
      method: 'POST',
      body: { version: page.value.version, idempotency_key: wikiKey() },
    });
    page.value = result;
    status.value = '文章已发布，公开正文与搜索已更新。';
    await refreshList();
  });
}
async function prepareUpload() {
  await save();
  return page.value?.id;
}
function query(extra = {}) {
  router.push({
    path: '/admin.html',
    query: {
      section: 'wiki',
      tab: 'pages',
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      ...extra,
    },
  });
}
async function showHistory() {
  await act(async () => {
    history.value = await adminWikiApi(`/pages/${page.value.id}/revisions`);
  });
}
async function viewRevision(id) {
  await act(async () => {
    historical.value = await adminWikiApi('/revisions/' + id);
  });
}
async function restore(id) {
  if (dirty.value && !confirm('历史回退会创建新草稿；当前未保存内容保留在本地恢复副本中。继续？'))
    return;
  await act(async () => {
    const result = await adminWikiApi(`/pages/${page.value.id}/restore`, {
      method: 'POST',
      body: {
        revision_id: id,
        version: page.value.version,
        base_revision_id: page.value.draft_revision_id,
      },
    });
    try {
      localStorage.removeItem(key());
    } catch {}
    fill(result);
    historical.value = null;
    status.value = '已基于历史内容创建草稿，发布后才会公开。';
    history.value = await adminWikiApi(`/pages/${page.value.id}/revisions`);
  });
}
async function visibility(revision) {
  await act(async () => {
    await adminWikiApi('/revisions/' + revision.id, {
      method: 'PATCH',
      body: { version: page.value.version, hidden: !revision.hidden },
    });
    page.value = await adminWikiApi('/pages/' + page.value.id);
    history.value = await adminWikiApi(`/pages/${page.value.id}/revisions`);
  });
}
async function download(id) {
  await act(async () => {
    downloadController?.abort();
    downloadController = new AbortController();
    await downloadMarkdown(`/api/admin/wiki/revisions/${id}/markdown`, downloadController.signal);
  });
}
function recover() {
  const stored = recovery.value;
  loading = true;
  Object.assign(form, stored.form);
  if (page.value) {
    page.value.version = stored.version;
    page.value.draft_revision_id = stored.base_revision_id;
  }
  loading = false;
  recovery.value = null;
  status.value = '本地内容已恢复，请核对后保存。';
}
function discard() {
  try {
    localStorage.removeItem(key());
  } catch {}
  recovery.value = null;
}
function rebase() {
  if (!confirm('已对照当前服务器版本，保留你的输入并基于最新版本继续保存？')) return;
  page.value = conflict.value;
  conflict.value = null;
  persist();
}
async function leave() {
  if (!dirty.value) return true;
  leaving = true;
  try {
    await save();
    return true;
  } catch {
    return confirm('草稿尚未保存，仍要离开？本地恢复副本会保留。');
  } finally {
    leaving = false;
  }
}
const unregisterLeave = registerLeave(leave);
const unregisterRouter = router.beforeEach(async (to) => {
  if (updatingRoute) return true;
  if (
    to.path === '/admin.html' &&
    to.query.section === 'wiki' &&
    (to.query.tab !== 'pages' ||
      String(to.query.page_id || '') !== String(route.query.page_id || ''))
  )
    return leave();
});
function unload(event) {
  if (dirty.value) {
    persist();
    event.preventDefault();
    event.returnValue = '';
  }
}
watch(
  form,
  () => {
    if (loading || !initialized) return;
    persist();
    clearTimeout(timer);
    if (
      !recovery.value &&
      !conflict.value &&
      form.category_id &&
      (form.title.trim() || form.body.trim())
    )
      timer = setTimeout(() => save().catch(() => {}), 1400);
  },
  { deep: true, flush: 'sync' },
);
watch(
  () => [
    route.query.page_id,
    route.query.page,
    route.query.q,
    route.query.category_id,
    route.query.state,
  ],
  load,
);
onMounted(() => {
  load();
  window.addEventListener('beforeunload', unload);
});
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  loadRevision++;
  downloadController?.abort();
  unregisterLeave();
  unregisterRouter();
  window.removeEventListener('beforeunload', unload);
});
</script>
<template>
  <div class="wiki-pages-admin">
    <p v-if="error" role="alert">{{ error }}</p>
    <form class="filters" @submit.prevent="query()">
      <label>搜索文章<input v-model="filters.q" maxlength="100" /></label
      ><label
        >按小类筛选<select v-model="filters.category_id">
          <option value="">全部小类</option>
          <option v-for="c in children" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select></label
      ><label
        >文章状态<select v-model="filters.state">
          <option value="">全部</option>
          <option value="draft">有草稿</option>
          <option value="published">已发布</option>
        </select></label
      ><button class="btn">查询文章</button
      ><button type="button" class="btn primary" @click="query({ page_id: undefined })">
        新建文章
      </button>
    </form>
    <div class="wiki-editor-layout">
      <aside class="wiki-admin-article-list">
        <button
          v-for="item in listing?.items || []"
          :key="item.id"
          class="wiki-page-choice"
          :class="{ active: page?.id === item.id }"
          @click="query({ page_id: item.id, page: route.query.page || 1 })"
        >
          <b>{{ item.title || '未命名草稿' }}</b
          ><small
            >{{ item.category_name }} · {{ item.published_revision_id ? '已发布' : '未发布'
            }}{{ item.draft_revision_id !== item.published_revision_id ? ' / 有草稿' : '' }}</small
          >
        </button>
        <p v-if="listing && !listing.items.length">没有匹配文章。</p>
        <Pager
          v-if="listing"
          :page="Number(route.query.page) || 1"
          :total="listing.total"
          :size="20"
          @change="query({ page: $event })"
        />
      </aside>
      <section class="wiki-editor-main">
        <h2>{{ page ? '编辑文章' : '新建文章' }}</h2>
        <p v-if="!children.length">请先到分类管理新建大类和小类，再创建文章。</p>
        <div v-if="recovery" class="compose-recovery" role="status">
          发现本账号尚未保存的本地内容。<button class="btn" @click="recover">恢复内容</button
          ><button class="btn" @click="discard">丢弃本地内容</button>
        </div>
        <label>文章标题<input v-model="form.title" :disabled="busy" maxlength="240" /></label
        ><label
          >稳定 slug<input
            v-model="form.slug"
            :disabled="busy || !!page"
            placeholder="例如 disjoint-set-union；留空则自动生成"
            pattern="[a-z0-9]+(-[a-z0-9]+)*" /></label
        ><label
          >所属小类<select v-model="form.category_id" :disabled="busy">
            <option :value="null">请选择小类</option>
            <option v-for="c in children" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></label
        ><label
          >文章摘要<textarea
            v-model="form.summary"
            :disabled="busy"
            rows="2"
            maxlength="2000"
          ></textarea>
        </label>
        <div class="wiki-editor-metadata">
          <label>标签（逗号分隔）<input v-model="form.tags" :disabled="busy" /></label
          ><label>搜索别名（逗号分隔）<input v-model="form.aliases" :disabled="busy" /></label>
        </div>
        <MarkdownEditor
          v-model="form.body"
          v-model:title="form.title"
          :disabled="busy"
          document-type="wiki"
          :document-id="page?.id"
          :prepare-upload="prepareUpload"
          :download-url="page ? `/api/admin/wiki/revisions/${page.draft_revision_id}/markdown` : ''"
        />
        <details>
          <summary>关联练习与来源</summary>
          <fieldset class="wiki-exercises">
            <legend>关联练习</legend>
            <div v-for="(exercise, index) in form.exercises" :key="index" class="wiki-exercise-row">
              <label
                >练习名称<input
                  v-model="exercise.label"
                  :disabled="busy"
                  maxlength="120"
                  placeholder="例如：并查集基础练习" /></label
              ><label
                >题目链接<input
                  v-model="exercise.url"
                  :disabled="busy"
                  maxlength="1000"
                  placeholder="站内题面或可信 OJ 的 HTTPS 链接" /></label
              ><button
                type="button"
                class="btn"
                :disabled="busy"
                @click="form.exercises.splice(index, 1)"
              >
                移除练习 {{ index + 1 }}
              </button>
            </div>
            <button
              type="button"
              class="btn"
              :disabled="busy || form.exercises.length >= 30"
              @click="form.exercises.push({ label: '', url: '' })"
            >
              添加关联练习
            </button>
          </fieldset>
          <label>来源说明<input v-model="form.source" :disabled="busy" maxlength="2000" /></label
          ><label>许可说明<input v-model="form.license" :disabled="busy" maxlength="2000" /></label>
        </details>
        <p role="status">
          {{ status || '可上传 Markdown 或在线编写；草稿不会自动发布。' }} ·
          {{ Array.from(form.body).length }} / 20000 字符{{ dirty ? ' · 尚未保存' : '' }}
        </p>
        <div class="chips">
          <button class="btn" :disabled="busy" @click="act(save)">保存草稿</button
          ><button
            class="btn primary"
            :disabled="busy || !form.title.trim() || !form.body.trim()"
            @click="publish"
          >
            发布文章</button
          ><button v-if="page" class="btn" :disabled="busy" @click="showHistory">版本历史</button
          ><RouterLink
            v-if="page?.published_revision_id"
            class="btn"
            :to="{ path: '/wiki.html', query: { slug: page.slug } }"
            >阅读公开版本 ↗</RouterLink
          >
        </div>
        <section v-if="conflict" class="card wiki-conflict" role="alert">
          <h3>保存冲突：你的输入已保留</h3>
          <p>请对照当前服务器内容，再决定如何合并。</p>
          <h4>服务器当前草稿</h4>
          <pre>{{ conflict.draft.title }}\n{{ conflict.draft.body }}</pre>
          <h4>你的编辑内容</h4>
          <pre>{{ form.title }}\n{{ form.body }}</pre>
          <button class="btn" @click="rebase">保留输入，基于最新版本继续编辑</button>
        </section>
        <section v-if="history.length" class="card">
          <h3>版本历史</h3>
          <div v-for="r in history" :key="r.id" class="wiki-history-row">
            <span
              >#{{ r.id }} {{ r.title }} · {{ r.published_at ? '曾发布' : '草稿'
              }}{{ r.hidden ? ' / 已隐藏' : '' }}</span
            >
            <div class="chips">
              <button class="btn" @click="viewRevision(r.id)">查看内容</button
              ><button class="btn" @click="download(r.id)">下载此版 MD</button
              ><button class="btn" :disabled="busy" @click="restore(r.id)">基于此版新建草稿</button
              ><button
                v-if="r.published_at && r.id !== page.published_revision_id"
                class="btn"
                :disabled="busy"
                @click="visibility(r)"
              >
                {{ r.hidden ? '恢复公开历史' : '隐藏公开历史' }}
              </button>
            </div>
          </div>
        </section>
        <section v-if="historical" class="card">
          <h3>修订 #{{ historical.id }}：{{ historical.title }}</h3>
          <MarkdownView :source="historical.body" /><button class="btn" @click="historical = null">
            关闭历史预览
          </button>
        </section>
      </section>
    </div>
  </div>
</template>
