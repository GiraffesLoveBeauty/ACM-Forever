<script setup>
import { computed, onMounted, ref } from 'vue';
import { wikiKey } from '../lib/wiki.js';
import { useRequests } from '../lib/api.js';
const request = useRequests();
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
  } catch (e) {
    error.value = e.message;
  }
}
async function action(fn) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = e.message;
    conflict.value = e.status === 409;
  } finally {
    busy.value = false;
  }
}
function create(parent = null) {
  form.value = { ...empty(), parent_id: parent };
  editing.value = true;
}
function edit(item) {
  form.value = { ...item, version: state.value.navigation_version };
  editing.value = true;
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
  await action(async () => {
    await adminWikiApi('/categories' + (form.value.id ? '/' + form.value.id : ''), {
      method: form.value.id ? 'PATCH' : 'POST',
      body: form.value,
    });
    editing.value = false;
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
  await action(async () => {
    preview.value = await adminWikiApi(`/categories/${item.id}/delete-preview`, {
      method: 'POST',
      body: {},
    });
    target.value = null;
    replacement.value = null;
    confirmed.value = false;
  });
}
async function remove() {
  if (!confirmed.value || !confirm('确认按照预览迁移内容并删除分类？可在无后续冲突时恢复。'))
    return;
  await action(async () => {
    await adminWikiApi(`/categories/${preview.value.category.id}/delete`, {
      method: 'POST',
      body: {
        token: preview.value.token,
        target_id: target.value,
        default_category_id: replacement.value,
        idempotency_key: wikiKey(),
      },
    });
    preview.value = null;
  });
}
async function restore(id) {
  if (confirm('恢复此删除操作及原有归属？如有后续变更，系统会拒绝覆盖。'))
    await action(() =>
      adminWikiApi(`/category-operations/${id}/restore`, { method: 'POST', body: {} }),
    );
}
onMounted(load);
</script>
<template>
  <div class="wiki-admin-categories">
    <div class="chips">
      <button class="btn primary" :disabled="busy" @click="create()">新建大类</button
      ><button class="btn" :disabled="busy" @click="load">刷新目录</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <button v-if="conflict && editing" class="btn" @click="reconcile">
      核对最新目录并保留输入
    </button>
    <p v-if="!state" role="status">正在加载目录…</p>
    <form v-if="editing" class="card wiki-edit-form" @submit.prevent="save">
      <h2>{{ form.id ? '编辑分类' : '新建分类' }}</h2>
      <label>分类名称<input v-model="form.name" maxlength="80" required /></label
      ><label
        >分类简介<textarea v-model="form.description" maxlength="2000" rows="3"></textarea></label
      ><label
        >所属大类<select v-model="form.parent_id" :disabled="form.id && form.parent_id == null">
          <option v-if="!form.id || form.parent_id == null" :value="null">作为大类</option>
          <option v-for="top in tops" :key="top.id" :value="top.id">{{ top.name }}</option>
        </select></label
      >
      <div class="chips">
        <button class="btn primary" :disabled="busy">保存分类</button
        ><button
          type="button"
          class="btn"
          @click="
            editing = false;
            form = empty();
          "
        >
          取消
        </button>
      </div>
    </form>
    <p v-if="state && !tops.length">尚无分类，请先新建一个大类。</p>
    <section
      v-for="top in tops"
      :key="top.id"
      class="card wiki-category-management"
      draggable="true"
      @dragstart.stop="dragId = top.id"
      @dragover.prevent
      @drop.stop.prevent="drop(top)"
    >
      <div class="wiki-admin-row">
        <div>
          <h2>
            {{ top.name }} <small v-if="state.default_category_id === top.id">默认入口</small>
          </h2>
          <p>{{ top.description }}</p>
        </div>
        <div class="chips">
          <button class="btn" :disabled="busy" @click="create(top.id)">新建小类</button
          ><button class="btn" :disabled="busy" @click="edit(top)">编辑大类</button
          ><button
            class="btn"
            :disabled="busy"
            :aria-label="'上移' + top.name"
            @click="move(top, -1)"
          >
            ↑</button
          ><button
            class="btn"
            :disabled="busy"
            :aria-label="'下移' + top.name"
            @click="move(top, 1)"
          >
            ↓</button
          ><button
            class="btn"
            :disabled="busy || state.default_category_id === top.id"
            @click="defaults(top.id)"
          >
            设为默认</button
          ><button class="btn" :disabled="busy" @click="inspect(top)">删除预览</button>
        </div>
      </div>
      <div
        v-for="child in state.categories.filter((c) => c.parent_id === top.id)"
        :key="child.id"
        class="wiki-admin-row wiki-child-row"
        draggable="true"
        @dragstart.stop="dragId = child.id"
        @dragover.prevent
        @drop.stop.prevent="drop(child)"
      >
        <div>
          <b>{{ child.name }}</b>
          <p>{{ child.description }}</p>
          <small>已发布 {{ child.published_count }} · 草稿 {{ child.draft_count }}</small>
        </div>
        <div class="chips">
          <button class="btn" :disabled="busy" @click="edit(child)">编辑 / 迁移</button
          ><button
            class="btn"
            :disabled="busy"
            :aria-label="'上移' + child.name"
            @click="move(child, -1)"
          >
            ↑</button
          ><button
            class="btn"
            :disabled="busy"
            :aria-label="'下移' + child.name"
            @click="move(child, 1)"
          >
            ↓</button
          ><button class="btn" :disabled="busy" @click="inspect(child)">删除预览</button>
        </div>
      </div>
    </section>
    <section
      v-if="preview"
      class="card wiki-delete-preview"
      role="region"
      aria-label="删除影响预览"
    >
      <h2>删除“{{ preview.category.name }}”的影响</h2>
      <p>
        小类 {{ preview.children_count }} 个 · 已发布 {{ preview.published_count }} 篇 · 草稿
        {{ preview.draft_count }} 篇
      </p>
      <p v-if="preview.is_default">此分类为默认入口，请同步选择新默认大类。</p>
      <label v-if="preview.children_count || preview.published_count || preview.draft_count"
        >迁移目标<select v-model="target" required>
          <option :value="null">请选择接收分类</option>
          <option v-for="c in preview.targets" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select></label
      ><label v-if="preview.is_default"
        >新默认大类<select v-model="replacement">
          <option :value="null">无默认分类</option>
          <option
            v-for="c in tops.filter((c) => c.id !== preview.category.id)"
            :key="c.id"
            :value="c.id"
          >
            {{ c.name }}
          </option>
        </select></label
      ><label class="wiki-check"
        ><input v-model="confirmed" type="checkbox" />我已核对迁移目标及影响范围</label
      >
      <div class="chips">
        <button
          class="btn primary"
          :disabled="
            busy ||
            !confirmed ||
            ((preview.children_count || preview.published_count || preview.draft_count) && !target)
          "
          @click="remove"
        >
          确认迁移并删除</button
        ><button class="btn" @click="preview = null">取消删除</button
        ><button class="btn" :disabled="busy" @click="inspect(preview.category)">重新预览</button>
      </div>
    </section>
    <section v-if="state?.operations.length" class="card">
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
  </div>
</template>
