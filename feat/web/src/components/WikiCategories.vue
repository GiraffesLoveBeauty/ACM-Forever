<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import WikiCategoryNav from './WikiCategoryNav.vue';
import { wikiKey } from '../lib/wiki.js';
import { useRequests } from '../lib/api.js';
const request = useRequests(),
  route = useRoute(),
  router = useRouter();
const registerLeave = inject('registerLeaveGuard', () => () => {});
const selected = computed(
  () =>
    tops.value.find((c) => c.id === Number(route.query.category)) ||
    tops.value.find((c) => c.id === state.value?.default_category_id) ||
    tops.value[0],
);
const children = computed(
  () => state.value?.categories.filter((c) => c.parent_id === selected.value?.id) || [],
);
const panel = ref(),
  notice = ref(''),
  lastDeleted = ref();
let initialForm = '';
function unchanged() {
  return !editing.value || JSON.stringify(form.value) === initialForm;
}
function leave() {
  return unchanged() || confirm('分类信息尚未保存，确定离开并放弃本次输入？');
}
const unregisterLeave = registerLeave(leave);
const unregisterRouter = router.beforeEach((to, from) => {
  // Admin guards handle leaving the workspace or changing modules.
  if (
    from.path === '/admin.html' &&
    to.path === from.path &&
    from.query.section === 'wiki' &&
    to.query.section === 'wiki' &&
    (from.query.tab || 'categories') === 'categories' &&
    ((to.query.tab || 'categories') !== 'categories' || to.query.category !== from.query.category)
  ) {
    if (!leave()) return false;
    editing.value = false;
    preview.value = undefined;
  }
});
onBeforeUnmount(() => {
  unregisterLeave();
  unregisterRouter();
});
function select(id) {
  router.push({ path: '/admin.html', query: { section: 'wiki', tab: 'categories', category: id } });
}
async function focusPanel() {
  await nextTick();
  panel.value?.scrollIntoView?.({ block: 'nearest' });
  panel.value?.querySelector('input,select')?.focus({ preventScroll: true });
}
const adminWikiApi = (path, options = {}) => request('/admin/wiki' + path, options);
const state = ref(),
  error = ref(''),
  conflict = ref(false),
  busy = ref(false),
  editing = ref(false),
  preview = ref(),
  target = ref(null),
  replacement = ref(null),
  confirmed = ref(false),
  dragId = ref();
const empty = () => ({
  id: null,
  name: '',
  description: '',
  parent_id: null,
  version: state.value?.navigation_version,
});
const form = ref(empty());
const tops = computed(() => state.value?.categories.filter((c) => c.parent_id == null) || []);
async function load() {
  try {
    state.value = await adminWikiApi('/categories');
    if (!editing.value) form.value = empty();
    if (route.query.category && !tops.value.some((c) => c.id === Number(route.query.category))) {
      await router.replace({
        path: '/admin.html',
        query: { ...route.query, category: selected.value?.id },
      });
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  }
}
async function action(fn) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  conflict.value = false;
  try {
    await fn();
    await load();
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
    conflict.value = e.status === 409;
  } finally {
    busy.value = false;
  }
}
function create(parent = null) {
  if (!leave()) return;
  preview.value = undefined;
  form.value = { ...empty(), parent_id: parent };
  editing.value = true;
  initialForm = JSON.stringify(form.value);
  focusPanel();
}
function edit(item) {
  if (!leave()) return;
  preview.value = undefined;
  form.value = { ...item, version: state.value.navigation_version };
  editing.value = true;
  initialForm = JSON.stringify(form.value);
  focusPanel();
}
async function reconcile() {
  await load();
  if (
    editing.value &&
    confirm('请对照最新目录核对分类信息。确认保留当前表单并基于最新目录重试？')
  ) {
    form.value.version = state.value.navigation_version;
    conflict.value = false;
  }
}
async function save() {
  const previousRoute = route.fullPath;
  await action(async () => {
    const result = await adminWikiApi('/categories' + (form.value.id ? '/' + form.value.id : ''), {
      method: form.value.id ? 'PATCH' : 'POST',
      body: form.value,
    });
    editing.value = false;
    notice.value = '分类已保存，阅读页面已同步更新。';
    if (route.fullPath === previousRoute)
      await router.replace({
        path: '/admin.html',
        query: { section: 'wiki', tab: 'categories', category: result.parent_id || result.id },
      });
  });
}
async function order(ids, parent) {
  await action(() =>
    adminWikiApi('/categories/order', {
      method: 'PUT',
      body: { ids, parent_id: parent, version: state.value.navigation_version },
    }),
  );
}
async function move(item, step) {
  const siblings = state.value.categories
      .filter((c) => c.parent_id === item.parent_id)
      .map((c) => c.id),
    i = siblings.indexOf(item.id),
    j = i + step;
  if (j < 0 || j >= siblings.length) return;
  [siblings[i], siblings[j]] = [siblings[j], siblings[i]];
  await order(siblings, item.parent_id);
}
async function drop(item) {
  const source = state.value.categories.find((c) => c.id === dragId.value);
  if (source?.id === item.id) return;
  if (!source || source.parent_id !== item.parent_id) {
    error.value = '拖动仅支持同级排序；迁移小类请使用编辑功能。';
    return;
  }
  const ids = state.value.categories
    .filter((c) => c.parent_id === item.parent_id)
    .map((c) => c.id)
    .filter((id) => id !== source.id);
  ids.splice(ids.indexOf(item.id), 0, source.id);
  await order(ids, item.parent_id);
}
async function defaults(id) {
  await action(() =>
    adminWikiApi('/settings', {
      method: 'PUT',
      body: { version: state.value.navigation_version, default_category_id: id },
    }),
  );
}
async function inspect(item) {
  if (!leave()) return;
  editing.value = false;
  await action(async () => {
    preview.value = await adminWikiApi(`/categories/${item.id}/delete-preview`, {
      method: 'POST',
      body: {},
    });
    target.value = null;
    replacement.value = null;
    confirmed.value = false;
  });
  focusPanel();
}
async function remove() {
  if (!confirmed.value || !confirm('确认按照预览迁移内容并删除分类？可在无后续冲突时恢复。'))
    return;
  await action(async () => {
    const deleted = await adminWikiApi(`/categories/${preview.value.category.id}/delete`, {
      method: 'POST',
      body: {
        token: preview.value.token,
        target_id: target.value,
        default_category_id: replacement.value,
        idempotency_key: wikiKey(),
      },
    });
    preview.value = null;
    lastDeleted.value = deleted.operation_id;
    notice.value = deleted.message;
  });
}
async function restore(id) {
  if (confirm('恢复此删除操作及原有归属？如有后续变更，系统会拒绝覆盖。'))
    await action(() =>
      adminWikiApi(`/category-operations/${id}/restore`, { method: 'POST', body: {} }).then(() => {
        lastDeleted.value = null;
        notice.value = '分类与原有归属已恢复。';
      }),
    );
}
onMounted(load);
</script>
<template>
  <div class="wiki-admin-categories">
    <div class="wiki-taxonomy-layout">
      <WikiCategoryNav
        :categories="state?.categories || []"
        :active-id="selected?.id"
        management
        :disabled="busy"
        @select="select"
      />
      <section class="wiki-taxonomy-content" :aria-busy="busy">
        <nav class="wiki-breadcrumb" aria-label="分类管理面包屑">
          <span>管理后台</span><span>/</span><RouterLink to="/wiki.html">Wiki</RouterLink
          ><span>/</span><span aria-current="page">分类管理</span>
        </nav>
        <header class="wiki-section-heading wiki-page-heading">
          <div>
            <span class="wiki-kicker">管理后台 / WIKI</span>
            <h1>分类管理</h1>
            <p>大类决定左侧导航，小类决定内容分组。保存后同步更新阅读页面。</p>
          </div>
          <button class="btn primary" :disabled="busy" @click="create()">＋ 新建大类</button>
        </header>
        <div v-if="notice" class="wiki-notice" role="status">
          <span>{{ notice }}</span
          ><button v-if="lastDeleted" class="btn" :disabled="busy" @click="restore(lastDeleted)">
            撤销本次删除
          </button>
        </div>
        <div v-if="error" class="wiki-feedback" role="alert">
          <p>{{ error }}</p>
          <button v-if="conflict && editing" class="btn" :disabled="busy" @click="reconcile">
            核对最新目录并保留输入</button
          ><button v-else class="btn" :disabled="busy" @click="load">刷新目录</button>
        </div>
        <p v-if="!state && !error" role="status">正在加载目录…</p>
        <div ref="panel">
          <form v-if="editing" class="card wiki-edit-form" @submit.prevent="save">
            <h2>{{ form.id ? '编辑' : '新建' }}{{ form.parent_id == null ? '大类' : '小类' }}</h2>
            <p class="muted">
              {{
                form.parent_id == null
                  ? '大类显示在左侧导航。名称、简介和顺序都可以继续调整。'
                  : '小类显示在所属大类中。修改所属大类即可迁移整个小类，文章地址保持不变。'
              }}
            </p>
            <label
              >分类名称<input v-model="form.name" maxlength="80" required :disabled="busy" /></label
            ><label
              >分类简介<textarea
                v-model="form.description"
                maxlength="2000"
                rows="3"
                :disabled="busy"
              ></textarea></label
            ><label
              >所属大类<select
                aria-label="所属大类"
                v-model="form.parent_id"
                :disabled="busy || (form.id && form.parent_id == null)"
              >
                <option v-if="!form.id || form.parent_id == null" :value="null">作为大类</option>
                <option v-for="top in tops" :key="top.id" :value="top.id">{{ top.name }}</option>
              </select></label
            >
            <div class="chips">
              <button class="btn primary" :disabled="busy">保存分类</button
              ><button
                type="button"
                class="btn"
                :disabled="busy"
                @click="
                  editing = false;
                  form = empty();
                "
              >
                取消
              </button>
            </div>
          </form>
          <section
            v-if="preview"
            class="card wiki-delete-preview"
            role="region"
            aria-label="删除影响预览"
          >
            <h2>
              删除{{ preview.category.parent_id == null ? '大类' : '小类' }}「{{
                preview.category.name
              }}」
            </h2>
            <p>
              此分类包含 {{ preview.children_count }} 个小类、{{
                preview.published_count
              }}
              篇已发布文章和 {{ preview.draft_count }} 篇草稿。{{
                preview.children_count || preview.published_count || preview.draft_count
                  ? '请选择接收位置，迁移后再删除分类。'
                  : '这是一个空分类，可以直接删除。'
              }}
            </p>
            <label v-if="preview.children_count || preview.published_count || preview.draft_count"
              >迁移目标<select aria-label="迁移目标" v-model="target" :disabled="busy" required>
                <option :value="null">请选择接收位置</option>
                <option v-for="c in preview.targets" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select></label
            >
            <p class="muted">迁移保留文章内容和地址；接收位置存在同名小类时，需要先调整名称。</p>
            <label v-if="preview.is_default"
              >新默认大类<select aria-label="新默认大类" v-model="replacement" :disabled="busy">
                <option :value="null">请选择新默认大类</option>
                <option
                  v-for="c in tops.filter((c) => c.id !== preview.category.id)"
                  :key="c.id"
                  :value="c.id"
                >
                  {{ c.name }}
                </option>
              </select></label
            >
            <label class="wiki-check"
              ><input
                v-model="confirmed"
                type="checkbox"
                :disabled="busy"
              />我已核对迁移目标及影响范围</label
            >
            <div class="chips">
              <button
                class="btn wiki-danger"
                :disabled="
                  busy ||
                  !confirmed ||
                  ((preview.children_count || preview.published_count || preview.draft_count) &&
                    !target) ||
                  (preview.is_default && tops.length > 1 && !replacement)
                "
                @click="remove"
              >
                确认迁移并删除</button
              ><button class="btn" :disabled="busy" @click="preview = null">取消删除</button
              ><button class="btn" :disabled="busy" @click="inspect(preview.category)">
                重新预览
              </button>
            </div>
          </section>
        </div>
        <template v-if="selected">
          <section
            class="card wiki-category-management"
            draggable="true"
            @dragstart.stop="dragId = selected.id"
            @dragover.prevent
            @drop.stop.prevent="drop(selected)"
          >
            <small class="muted"
              >当前大类<template v-if="state.default_category_id === selected.id">
                · Wiki 默认入口</template
              ></small
            >
            <h2>{{ selected.name }}</h2>
            <p>{{ selected.description || '为这个大类补充简介，帮助读者找到知识。' }}</p>
            <small class="muted"
              >{{ children.length }} 个小类 · 已发布 {{ selected.published_count }} · 草稿
              {{ selected.draft_count }}</small
            >
            <div class="chips wiki-category-actions">
              <button class="btn" :disabled="busy" @click="edit(selected)">编辑大类</button
              ><button
                class="btn"
                :disabled="busy || tops[0]?.id === selected.id"
                :aria-label="'上移' + selected.name"
                @click="move(selected, -1)"
              >
                上移</button
              ><button
                class="btn"
                :disabled="busy || tops.at(-1)?.id === selected.id"
                :aria-label="'下移' + selected.name"
                @click="move(selected, 1)"
              >
                下移</button
              ><button class="btn wiki-danger" :disabled="busy" @click="inspect(selected)">
                删除大类</button
              ><button
                v-if="state.default_category_id !== selected.id"
                class="btn"
                :disabled="busy"
                @click="defaults(selected.id)"
              >
                设为默认</button
              ><RouterLink
                class="btn"
                :to="{ path: '/wiki.html', query: { category: selected.id } }"
                >查看前台 ↗</RouterLink
              >
            </div>
          </section>
          <div class="wiki-section-heading">
            <h2>小类管理</h2>
            <button class="btn primary" :disabled="busy" @click="create(selected.id)">
              ＋ 新建小类
            </button>
          </div>
          <div
            v-for="(child, index) in children"
            :key="child.id"
            class="wiki-admin-row wiki-child-row"
            draggable="true"
            @dragstart.stop="dragId = child.id"
            @dragover.prevent
            @drop.stop.prevent="drop(child)"
          >
            <div>
              <strong
                ><span class="wiki-topic-index">{{ String(index + 1).padStart(2, '0') }}</span
                >{{ child.name }}</strong
              >
              <p>{{ child.description }}</p>
              <small class="muted"
                >已发布 {{ child.published_count }} · 草稿 {{ child.draft_count }}</small
              >
            </div>
            <div class="chips">
              <button class="btn" :disabled="busy" @click="edit(child)">编辑 / 迁移</button
              ><button
                class="btn"
                :disabled="busy || index === 0"
                :aria-label="'上移' + child.name"
                @click="move(child, -1)"
              >
                上移</button
              ><button
                class="btn"
                :disabled="busy || index === children.length - 1"
                :aria-label="'下移' + child.name"
                @click="move(child, 1)"
              >
                下移</button
              ><button class="btn wiki-danger" :disabled="busy" @click="inspect(child)">
                删除
              </button>
            </div>
          </div>
          <p v-if="!children.length" class="wiki-empty">还没有小类，点击“新建小类”开始整理内容。</p>
          <details class="wiki-root-order">
            <summary>大类排序与刷新</summary>
            <p class="muted">拖动同级分类调整顺序，也可以使用上移、下移按钮。</p>
            <div
              v-for="(top, index) in tops"
              :key="top.id"
              class="wiki-admin-row"
              draggable="true"
              @dragstart.stop="dragId = top.id"
              @dragover.prevent
              @drop.stop.prevent="drop(top)"
            >
              <strong>{{ top.name }}</strong>
              <div class="chips">
                <button
                  class="btn"
                  :disabled="busy || index === 0"
                  :aria-label="'上移' + top.name"
                  @click="move(top, -1)"
                >
                  上移</button
                ><button
                  class="btn"
                  :disabled="busy || index === tops.length - 1"
                  :aria-label="'下移' + top.name"
                  @click="move(top, 1)"
                >
                  下移
                </button>
              </div>
            </div>
            <button class="btn" :disabled="busy" @click="load">刷新目录</button>
          </details>
        </template>
        <p v-if="state && !tops.length" class="wiki-empty">尚无分类，请先新建一个大类。</p>
        <section v-if="state?.operations.length" class="wiki-restore-records">
          <h2>删除与恢复记录</h2>
          <div v-for="op in state.operations" :key="op.id" class="wiki-admin-row">
            <span
              >删除记录 #{{ op.id }} ·
              {{ new Date(op.created_at * 1000).toLocaleString('zh-CN') }}</span
            ><button class="btn" :disabled="busy || !!op.restored_at" @click="restore(op.id)">
              {{ op.restored_at ? '已恢复' : '恢复删除' }}
            </button>
          </div>
        </section>
      </section>
    </div>
  </div>
</template>
