<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { date, notify, useRequests } from '../lib/api.js';
import {
  completions,
  exclusions,
  localTime,
  newDraft,
  phases,
  platformName,
  ruleName,
  taskForm,
  taskPayload,
  utcTime,
} from '../lib/training-tasks.js';
import TaskProblemList from '../components/TaskProblemList.vue';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const options = ref({ statuses: [], capabilities: [] }),
  list = ref({ items: [], total: 0 }),
  task = ref(null),
  form = ref(newDraft()),
  saved = ref(''),
  preview = ref(null),
  confirmed = ref(false),
  loading = ref(false),
  busy = ref(false),
  error = ref(''),
  catalog = ref({ items: [], total: 0 }),
  catalogQuery = ref(''),
  catalogPlatform = ref('codeforces'),
  batch = ref(''),
  batchPlatform = ref('codeforces'),
  catalogPage = ref(1),
  catalogBusy = ref(false),
  progress = ref(null),
  recipient = ref(null),
  reason = ref(''),
  extendedDue = ref(''),
  search = ref(''),
  state = ref(''),
  memberSearch = ref(''),
  memberStatus = ref(''),
  memberIdentity = ref('');
const base = '/admin/training-tasks';
const taskId = computed(() => String(route.query.task_id || ''));
const editing = computed(() => route.query.tab === 'edit' || taskId.value === 'new');
const step = computed(() =>
  [1, 2, 3].includes(Number(route.query.step)) ? Number(route.query.step) : 1,
);
const page = computed(() => Math.max(1, Number(route.query.page) || 1));
const dirty = computed(() => editing.value && JSON.stringify(form.value) !== saved.value);
const enabled = computed(() => options.value.enabled === true);
let revision = 0,
  loadedKey = '',
  editorInitialized = false,
  disposed = false,
  publishKey = '';
function address(changes = {}, replace = false) {
  const query = { ...route.query, section: 'training', ...changes };
  for (const key of Object.keys(query))
    if (query[key] === '' || query[key] == null) delete query[key];
  return router[replace ? 'replace' : 'push']({ path: '/admin.html', query });
}
function auditText(entry) {
  if (entry.action !== 'extended') return '';
  try {
    return '新截止：' + date(JSON.parse(entry.after_json).due_at);
  } catch {
    return '';
  }
}
function goList() {
  return address({
    member_search: null,
    status: null,
    identity: null,
    task_id: null,
    tab: null,
    recipient_id: null,
    step: null,
    page: null,
  });
}
function goTask(id, tab = 'overview') {
  return address({
    member_search: null,
    status: null,
    identity: null,
    task_id: id,
    tab,
    step: null,
    recipient_id: null,
    page: null,
  });
}
function leave(to) {
  if (busy.value) {
    notify('请等待当前操作结束。');
    return false;
  }
  const sameEditor =
    to.path === '/admin.html' &&
    to.query.section === 'training' &&
    String(to.query.task_id || '') === taskId.value &&
    (to.query.tab === 'edit' || taskId.value === 'new');
  return (
    !dirty.value || sameEditor || window.confirm('草稿尚未保存，离开会丢失本次修改。确认离开？')
  );
}
const unregister = inject('registerLeaveGuard', () => () => {})(leave);
function unload(event) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
onMounted(() => window.addEventListener('beforeunload', unload));
onBeforeUnmount(() => {
  disposed = true;
  revision++;
  unregister();
  window.removeEventListener('beforeunload', unload);
});
function restoreForm(data) {
  form.value = data ? taskForm(data) : newDraft();
  saved.value = JSON.stringify(form.value);
  preview.value = null;
  confirmed.value = false;
  publishKey = '';
  reason.value = '';
}
async function load() {
  const version = ++revision;
  error.value = '';
  loading.value = true;
  try {
    if (editing.value && editorInitialized && loadedKey === taskId.value) return;
    if (taskId.value === 'new') {
      task.value = null;
      loadedKey = 'new';
      editorInitialized = true;
      restoreForm(null);
      return;
    }
    if (!editing.value) editorInitialized = false;
    if (!taskId.value) {
      loadedKey = '';
      task.value = null;
      search.value = String(route.query.search || '');
      state.value = String(route.query.state || '');
      const data = await request(
        base +
          '?' +
          new URLSearchParams({
            page: page.value,
            page_size: 20,
            search: search.value,
            state: state.value,
          }),
        {},
        'view',
      );
      if (version === revision) list.value = data;
      return;
    }
    if (!/^[1-9][0-9]*$/.test(taskId.value)) throw Error('任务地址无效，请返回列表重新选择。');
    const data = await request(base + '/' + taskId.value, {}, 'view');
    if (version !== revision) return;
    task.value = data;
    loadedKey = taskId.value;
    if (editing.value) {
      if (data.state !== 'draft') {
        await goTask(data.id);
        return;
      }
      editorInitialized = true;
      restoreForm(data);
    } else {
      extendedDue.value = localTime(data.due_at);
      reason.value = '';
      preview.value = null;
      if (route.query.tab === 'progress' && data.state !== 'draft') await loadProgress(version);
    }
  } catch (e) {
    if (e.name !== 'AbortError' && version === revision) error.value = e.message;
  } finally {
    if (version === revision) loading.value = false;
  }
}
async function loadProgress(version = revision) {
  memberSearch.value = String(route.query.member_search || '');
  memberStatus.value = String(route.query.status || '');
  memberIdentity.value = String(route.query.identity || '');
  const data = await request(
    base +
      '/' +
      taskId.value +
      '/progress?' +
      new URLSearchParams({
        page: page.value,
        page_size: 20,
        search: memberSearch.value,
        status: memberStatus.value,
        identity: memberIdentity.value,
      }),
    {},
    'progress',
  );
  if (version !== revision) return;
  progress.value = data;
  recipient.value = null;
  if (route.query.recipient_id) {
    const item = await request(
      base + '/' + taskId.value + '/progress/' + route.query.recipient_id,
      {},
      'recipient',
    );
    if (version === revision) recipient.value = item;
  }
}
watch(() => route.fullPath, load, { immediate: true });
(async () => {
  try {
    options.value = await request(base + '/options', {}, 'options');
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  }
})();
async function action(operation) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    return await operation();
  } catch (e) {
    if (e.name !== 'AbortError') {
      error.value = e.message;
      if (e.status === 409) {
        preview.value = null;
        confirmed.value = false;
        publishKey = '';
      }
    }
  } finally {
    busy.value = false;
  }
}
async function saveDraft() {
  const result = await request(
    base + (task.value?.id ? '/' + task.value.id : ''),
    {
      method: task.value?.id ? 'PATCH' : 'POST',
      body: taskPayload(form.value, task.value?.version),
    },
    'save',
  );
  task.value = result;
  loadedKey = String(result.id);
  restoreForm(result);
  return result;
}
function save() {
  return action(async () => {
    const data = await saveDraft();
    busy.value = false;
    await address({ task_id: data.id, tab: 'edit' }, true);
    notify('草稿已保存。');
  });
}
function validateStep() {
  if (!form.value.title.trim()) throw Error('请填写任务标题。');
  if (!form.value.problems.length) throw Error('请至少添加一道必做题。');
}
function nextStep() {
  return action(async () => {
    validateStep();
    if (step.value === 1) {
      busy.value = false;
      await address({ step: 2 });
      return;
    }
    if (!form.value.statuses.length) throw Error('请至少选择一种成员身份。');
    if (
      !utcTime(form.value.starts_at) ||
      !utcTime(form.value.due_at) ||
      utcTime(form.value.starts_at) >= utcTime(form.value.due_at)
    )
      throw Error('请设置开始早于截止的周期，时区为 Asia/Shanghai。');
    const data = await saveDraft();
    const checked = await request(
      base + '/' + data.id + '/audience-preview',
      { method: 'POST', body: { version: data.version } },
      'preview',
    );
    preview.value = checked;
    publishKey = crypto.randomUUID();
    confirmed.value = false;
    busy.value = false;
    await address({ task_id: data.id, tab: 'edit', step: 3 }, true);
  });
}
async function previewPage(next) {
  await action(async () => {
    preview.value = await request(
      base + '/' + task.value.id + '/audience-preview?page=' + next,
      { method: 'POST', body: { version: task.value.version } },
      'preview',
    );
    confirmed.value = false;
    publishKey = crypto.randomUUID();
  });
}
function publish() {
  return action(async () => {
    if (!preview.value) throw Error('请先重新生成发放预览。');
    if (dirty.value) throw Error('草稿发生变化，请返回上一步重新预览。');
    const result = await request(
      base + '/' + task.value.id + '/publish',
      {
        method: 'POST',
        headers: { 'Idempotency-Key': publishKey },
        body: {
          version: task.value.version,
          preview_token: preview.value.preview_token,
          confirm_exclusions: confirmed.value,
        },
      },
      'publish',
    );
    saved.value = JSON.stringify(form.value);
    task.value = result;
    busy.value = false;
    await goTask(result.id);
    notify('训练任务已发放。');
  });
}
function move(index, delta) {
  const values = [...form.value.problems];
  [values[index], values[index + delta]] = [values[index + delta], values[index]];
  form.value.problems = values;
}
async function catalogLoad(next = 1) {
  catalogBusy.value = true;
  error.value = '';
  try {
    catalog.value = await request(
      '/problems?' +
        new URLSearchParams({
          platform: catalogPlatform.value,
          tag: catalogQuery.value.trim(),
          page: next,
          page_size: 10,
        }),
      {},
      'catalog',
    );
    catalogPage.value = next;
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (!disposed) catalogBusy.value = false;
  }
}
function addProblems(inputs) {
  return action(async () => {
    const result = await request(
      base + '/resolve-problems',
      {
        method: 'POST',
        body: {
          problems: [...form.value.problems, ...inputs].map((p) => ({
            platform: p.platform,
            problem_id: p.problem_id,
          })),
        },
      },
      'resolve',
    );
    if (result.errors.length)
      throw Error(result.errors.map((e) => '第 ' + (e.index + 1) + ' 项：' + e.message).join('\n'));
    form.value.problems = result.items;
    batch.value = '';
    if (result.duplicates) notify('已去除 ' + result.duplicates + ' 道重复题目。');
  });
}
function addBatch() {
  const ids = batch.value
    .trim()
    .split(/[\s,，;；]+/)
    .filter(Boolean);
  if (ids.length)
    return addProblems(ids.map((problem_id) => ({ platform: batchPlatform.value, problem_id })));
}
function lifecycle(kind) {
  return action(async () => {
    if (kind === 'delete' && !window.confirm('确认删除这份草稿？')) return;
    const data = {
      version: task.value.version,
      reason: reason.value,
      due_at: utcTime(extendedDue.value),
    };
    const result = await request(
      base + '/' + task.value.id + (kind === 'delete' ? '' : '/' + kind),
      { method: kind === 'delete' ? 'DELETE' : 'POST', body: data },
      'lifecycle',
    );
    busy.value = false;
    if (kind === 'delete') {
      saved.value = JSON.stringify(form.value);
      await goList();
    } else {
      task.value = result;
      await load();
    }
    notify(
      kind === 'delete' ? '草稿已删除。' : kind === 'cancel' ? '任务已取消。' : '截止时间已延期。',
    );
  });
}
</script>
<template>
  <div class="training-tasks" :aria-busy="loading || busy">
    <nav class="tt-row tt-muted" aria-label="面包屑">
      <button class="tt-title-button" @click="goList">训练管理</button
      ><template v-if="taskId">
        /
        {{
          editing ? (taskId === 'new' ? '新建训练任务' : '编辑草稿') : task?.title || '任务详情'
        }}</template
      >
    </nav>
    <div v-if="error" role="alert" class="tt-error">
      {{ error }} <button v-if="!editing" class="btn" @click="load">重试</button>
    </div>
    <div v-if="!enabled" class="tt-note">
      训练任务发放尚未开放。可准备草稿和查看历史，开放后才能发布。
    </div>
    <p v-if="loading" role="status" class="tt-note">正在加载训练任务…</p>
    <template v-if="!taskId">
      <div class="tt-between">
        <div>
          <span class="tt-kicker">TRAINING &amp; PROBLEMS / MANAGEMENT</span>
          <h2>训练任务</h2>
          <p class="tt-caption">按身份发放题单、设置完成周期，统一查看完成情况。</p>
        </div>
        <button
          class="btn primary"
          @click="address({ task_id: 'new', tab: 'edit', step: 1, page: null })"
        >
          ＋ 新建训练任务
        </button>
      </div>
      <form class="tt-filter" @submit.prevent="address({ search, state, page: null })">
        <label>搜索任务<input v-model="search" placeholder="任务标题" /></label
        ><label
          >状态<select v-model="state">
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="published">已发布</option>
            <option value="cancelled">已取消</option>
          </select></label
        ><button class="btn" :disabled="loading">筛选</button>
      </form>
      <div v-if="list.items.length" class="tt-table-wrap">
        <table class="tt-table">
          <thead>
            <tr>
              <th>任务 / 身份范围</th>
              <th>周期（北京时间）</th>
              <th>阶段</th>
              <th>按时完成 / 固定人数</th>
              <th>待核验</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in list.items" :key="item.id">
              <td>
                <button
                  class="tt-title-button"
                  @click="goTask(item.id, item.state === 'draft' ? 'edit' : 'overview')"
                >
                  {{ item.title }}
                </button>
                <p class="tt-caption">
                  {{ item.statuses.join(' / ') || '尚未选择身份' }} · {{ item.problem_count }} 题
                </p>
              </td>
              <td>{{ date(item.starts_at) }}<br />至 {{ date(item.due_at) }}</td>
              <td>
                <span class="tt-tag" :class="item.phase">{{ phases[item.phase] }}</span>
              </td>
              <td>{{ item.summary.on_time_count }} / {{ item.summary.recipient_count }} 人</td>
              <td>{{ item.summary.pending_count }} 人</td>
              <td>
                <button
                  class="btn"
                  @click="goTask(item.id, item.state === 'draft' ? 'edit' : 'overview')"
                >
                  {{ item.state === 'draft' ? '编辑草稿' : '查看' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!loading" class="tt-empty">
        暂无符合条件的训练任务。新建任务后可先保存为草稿。
      </div>
      <Pager :page="page" :total="list.total" :busy="loading" @change="address({ page: $event })" />
      <p class="tt-note">
        发放名单在发布时固定，身份变化不会自动增删接收人。同步异常与未绑定会单独列出。
      </p>
    </template>
    <template v-else-if="editing">
      <div>
        <h2>{{ taskId === 'new' ? '新建训练任务' : '编辑训练任务' }}</h2>
        <p class="tt-caption">先确定题单，再确认身份和周期，最后核对发放名单。</p>
      </div>
      <div class="tt-steps" aria-label="发放步骤">
        <button
          v-for="(label, i) in ['任务与题单', '身份与周期', '发布确认']"
          :key="label"
          :aria-current="step === i + 1 ? 'step' : undefined"
          :disabled="busy || i + 1 > step"
          @click="address({ step: i + 1 })"
        >
          <b>{{ i + 1 }}</b
          >{{ label }}
        </button>
      </div>
      <template v-if="step === 1">
        <section class="tt-panel tt-stack">
          <label class="tt-field"
            ><span>任务标题</span
            ><input
              v-model="form.title"
              maxlength="100"
              placeholder="例如：第 1 周 · 二分与贪心" /></label
          ><label class="tt-field"
            ><span>训练说明</span
            ><textarea
              v-model="form.description"
              maxlength="5000"
              placeholder="填写目标和完成要求"
            ></textarea>
          </label>
        </section>
        <section class="tt-panel tt-stack">
          <div class="tt-between">
            <h3>必做题单</h3>
            <span class="tt-tag"
              >{{ form.problems.length }} / {{ options.max_problems || 50 }} 题</span
            >
          </div>
          <TaskProblemList
            :problems="form.problems"
            :from="route.fullPath"
            editable
            :disabled="busy"
            @move="move"
            @remove="form.problems.splice($event, 1)"
          />
          <p v-if="!form.problems.length" class="tt-empty">
            从题库选择，或在下方批量添加标准题号。
          </p>
        </section>
        <section class="tt-panel tt-stack">
          <h3>从题库添加</h3>
          <form class="tt-filter" @submit.prevent="catalogLoad(1)">
            <label
              >题目平台<select v-model="catalogPlatform">
                <option v-for="p in options.capabilities" :key="p.platform" :value="p.platform">
                  {{ p.label }}
                </option>
              </select></label
            ><label
              >题库搜索<input v-model="catalogQuery" placeholder="题号、题名、分类标签" /></label
            ><button class="btn" :disabled="catalogBusy">
              {{ catalogBusy ? '搜索中…' : '搜索题库' }}
            </button>
          </form>
          <div class="tt-catalog">
            <div v-for="p in catalog.items" :key="p.platform + p.problem_id" class="tt-catalog-row">
              <div>
                <strong>{{ p.problem_name || p.problem_id }}</strong>
                <p class="tt-caption">
                  {{ p.problem_id }} · {{ p.problem_rating || '暂无难度' }} · {{ p.tags }}
                </p>
              </div>
              <button
                class="btn"
                :disabled="
                  busy ||
                  form.problems.some(
                    (x) =>
                      x.problem_id.replace(/^cf_/, '') === p.problem_id.replace(/^cf_/, '') &&
                      x.platform === p.platform,
                  )
                "
                @click="addProblems([p])"
              >
                添加
              </button>
            </div>
          </div>
          <Pager
            :page="catalogPage"
            :size="10"
            :total="catalog.total"
            :busy="catalogBusy"
            @change="catalogLoad"
          />
        </section>
        <section class="tt-panel tt-stack">
          <h3>批量题号</h3>
          <label class="tt-field"
            ><span>批量输入平台</span
            ><select v-model="batchPlatform">
              <option v-for="p in options.capabilities" :key="p.platform" :value="p.platform">
                {{ p.label }}
              </option>
            </select></label
          ><label class="tt-field"
            ><span>标准题号</span
            ><textarea v-model="batch" placeholder="706B 702C 1201C"></textarea>
          </label>
          <p class="tt-caption">空格、换行或逗号分隔，自动去重。服务端逐项校验，最多 50 题。</p>
          <div>
            <button class="btn" :disabled="busy || !batch.trim()" @click="addBatch">
              校验并添加题号
            </button>
          </div>
        </section>
      </template>
      <template v-else-if="step === 2">
        <section class="tt-panel tt-stack">
          <h3>接收身份</h3>
          <p class="tt-caption">身份来自成员资料，多选取并集并去重。Web 管理员权限不参与选人。</p>
          <div class="tt-row">
            <label v-for="status in options.statuses" :key="status" class="tt-check"
              ><input v-model="form.statuses" type="checkbox" :value="status" />{{ status }}</label
            >
          </div>
          <p v-if="!options.statuses.length" class="tt-note">
            当前没有可选身份，请先维护成员资料。
          </p>
        </section>
        <section class="tt-panel tt-stack">
          <h3>完成周期</h3>
          <div class="tt-form-grid">
            <label class="tt-field"
              ><span>开始时间</span><input v-model="form.starts_at" type="datetime-local" /></label
            ><label class="tt-field"
              ><span>截止时间</span><input v-model="form.due_at" type="datetime-local"
            /></label>
          </div>
          <p class="tt-caption">统一按 Asia/Shanghai（北京时间）填写和显示，含开始与截止时刻。</p>
        </section>
        <section class="tt-panel tt-stack">
          <h3>完成规则</h3>
          <label class="tt-check tt-rule"
            ><input v-model="form.rule" type="radio" value="period_ac" /><span
              >周期内 AC<small
                >默认规则。开始前的 AC 只显示历史已做；需要在周期内再次通过。</small
              ></span
            ></label
          ><label class="tt-check tt-rule"
            ><input v-model="form.rule" type="radio" value="historical_ac" /><span
              >历史 AC 可计入<small>截止前实际 AC 可计入；尚未开始的任务仍显示未开始。</small></span
            ></label
          >
          <p class="tt-note">
            首期支持 Codeforces。同步晚于截止时，仍按实际 OJ 提交时间判定；截止后 AC 为逾期。
          </p>
        </section>
      </template>
      <template v-else>
        <section class="tt-panel tt-stack">
          <h3>{{ form.title }}</h3>
          <p class="tt-description">{{ form.description }}</p>
          <p>
            {{ date(utcTime(form.starts_at)) }} → {{ date(utcTime(form.due_at)) }} · Asia/Shanghai
          </p>
          <div class="tt-row">
            <span class="tt-tag">{{ ruleName(form.rule) }}</span
            ><span v-for="s in form.statuses" :key="s" class="tt-tag">{{ s }}</span>
          </div>
          <p class="tt-note">
            确认发布后，名单、身份快照、题目顺序和规则将固定。已发布任务只能延期或取消。
          </p>
        </section>
        <template v-if="preview"
          ><div class="tt-stats">
            <div
              v-for="(label, key) in {
                total: '匹配成员',
                recipient_count: '有效接收',
                excluded_count: '排除成员',
                unbound_count: '接收人中未绑定',
              }"
              :key="key"
              class="tt-stat"
            >
              <strong>{{ preview[key] }}</strong
              ><span>{{ label }}（人）</span>
            </div>
          </div>
          <div class="tt-table-wrap">
            <table class="tt-table">
              <thead>
                <tr>
                  <th>成员 / QQ</th>
                  <th>身份</th>
                  <th>发放结果</th>
                  <th>绑定情况</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in preview.items" :key="m.qq_id">
                  <td>
                    {{ m.name }}
                    <p class="tt-caption">{{ m.qq_id }}</p>
                  </td>
                  <td>{{ m.status }}</td>
                  <td>{{ exclusions[m.excluded_reason] || '将接收任务' }}</td>
                  <td>
                    {{
                      m.excluded_reason
                        ? '本次不发放'
                        : m.unbound
                          ? '未绑定也可接收，绑定后核验'
                          : '已绑定'
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <Pager
            :page="preview.page"
            :total="preview.total"
            :busy="busy"
            @change="previewPage"
          /><label v-if="preview.excluded_count" class="tt-check"
            ><input
              v-model="confirmed"
              type="checkbox"
            />我已确认以上排除原因，仍向有效成员发放。</label
          ></template
        >
        <p v-else class="tt-note">预览尚未生成或已失效，请返回“身份与周期”重新预览。</p>
        <TaskProblemList :problems="form.problems" :from="route.fullPath" />
      </template>
      <div class="tt-bar-actions">
        <button class="btn" :disabled="busy" @click="save">
          {{ busy ? '处理中…' : '保存草稿' }}</button
        ><button class="btn" :disabled="busy" @click="goList">返回列表</button
        ><button v-if="step > 1" class="btn" :disabled="busy" @click="address({ step: step - 1 })">
          上一步</button
        ><button v-if="step < 3" class="btn primary" :disabled="busy" @click="nextStep">
          {{ step === 1 ? '下一步' : '保存并预览发放' }}</button
        ><button
          v-else
          class="btn primary"
          :disabled="
            busy ||
            !enabled ||
            !preview ||
            !preview.recipient_count ||
            (preview.excluded_count > 0 && !confirmed) ||
            dirty
          "
          @click="publish"
        >
          确认发布任务</button
        ><button
          v-if="task?.state === 'draft'"
          class="btn"
          :disabled="busy"
          @click="lifecycle('delete')"
        >
          删除草稿
        </button>
      </div>
    </template>
    <template v-else-if="task && !loading">
      <section class="tt-panel tt-stack">
        <div class="tt-between">
          <div>
            <h2>{{ task.title }}</h2>
            <p class="tt-caption">发布人 {{ task.creator_name }} · {{ date(task.published_at) }}</p>
          </div>
          <span class="tt-tag" :class="task.phase">{{ phases[task.phase] }}</span>
        </div>
        <p class="tt-description">{{ task.description }}</p>
        <dl class="tt-detail-grid">
          <div>
            <dt>完成周期 · 北京时间</dt>
            <dd>{{ date(task.starts_at) }} → {{ date(task.due_at) }}</dd>
          </div>
          <div>
            <dt>冻结身份 / 完成规则</dt>
            <dd>{{ task.statuses.join(' / ') }} · {{ ruleName(task.rule) }}</dd>
          </div>
        </dl>
        <p v-if="task.cancel_reason" class="tt-note">取消原因：{{ task.cancel_reason }}</p>
      </section>
      <nav class="tt-tabs">
        <button
          class="btn"
          :aria-current="route.query.tab !== 'progress' ? 'page' : undefined"
          @click="goTask(task.id)"
        >
          任务与题单</button
        ><button
          v-if="task.state !== 'draft'"
          class="btn"
          :aria-current="route.query.tab === 'progress' ? 'page' : undefined"
          @click="goTask(task.id, 'progress')"
        >
          完成情况</button
        ><button class="btn" @click="goList">返回列表</button>
      </nav>
      <template v-if="route.query.tab === 'progress' && progress"
        ><div class="tt-stats">
          <div
            v-for="(label, key) in {
              recipient_count: '固定接收人数',
              on_time_count: '按时完成人数',
              late_count: '逾期完成人数',
              pending_count: '待核验人数',
            }"
            :key="key"
            class="tt-stat"
          >
            <strong>{{ progress.summary[key] }}</strong
            ><span>{{ label }}</span>
          </div>
        </div>
        <p class="tt-note">
          已完成 {{ progress.summary.completed_problem_count }} /
          {{ progress.summary.total_problem_count }} 道成员题目；账号异常
          {{ progress.summary.abnormal_count }}
          人。任务需全部必做题完成，账号异常保留在固定分母中。完成与核验状态独立。
        </p>
        <form
          class="tt-filter"
          @submit.prevent="
            address({
              member_search: memberSearch,
              status: memberStatus,
              identity: memberIdentity,
              page: null,
              recipient_id: null,
            })
          "
        >
          <label>成员搜索<input v-model="memberSearch" placeholder="姓名或 QQ" /></label
          ><label
            >发布时身份<select v-model="memberIdentity">
              <option value="">全部身份</option>
              <option v-for="s in task.statuses" :key="s">{{ s }}</option>
            </select></label
          ><label
            >完成状态<select v-model="memberStatus">
              <option value="">全部状态</option>
              <option value="on_time">按时完成</option>
              <option value="late">逾期完成</option>
              <option value="incomplete">待完成</option>
              <option value="pending">待核验</option>
              <option value="abnormal">账号异常</option>
            </select></label
          ><button class="btn">筛选成员</button>
        </form>
        <div class="tt-table-wrap">
          <table class="tt-table">
            <thead>
              <tr>
                <th>成员 / 身份快照</th>
                <th>完成题目</th>
                <th>任务状态</th>
                <th>核验与账号</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in progress.items" :key="m.id">
                <td>
                  {{ m.name }}
                  <p class="tt-caption">{{ m.status_snapshot }} · {{ m.qq_id || '匿名归档' }}</p>
                </td>
                <td>{{ m.completed_problems }} / {{ m.problem_count }} 题</td>
                <td>{{ completions[m.completion] }}</td>
                <td>
                  {{ m.pending ? '待核验' : '已核验' }}
                  <p class="tt-caption">
                    {{
                      {
                        active: '账号正常',
                        closed: '已注销',
                        disabled: '已停用',
                        changed: '账号代际变化',
                      }[m.account_status]
                    }}
                    · {{ date(m.checked_at) }}
                  </p>
                </td>
                <td>
                  <button class="btn" @click="address({ recipient_id: m.id })">逐题证据</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pager
          :page="page"
          :total="progress.total"
          :busy="loading"
          @change="address({ page: $event, recipient_id: null })"
        />
        <section v-if="recipient" class="tt-panel tt-stack">
          <div class="tt-between">
            <h3>{{ recipient.recipient.name }} · 逐题证据</h3>
            <button class="btn" @click="address({ recipient_id: null })">收起证据</button>
          </div>
          <TaskProblemList :problems="recipient.problems" :from="route.fullPath" />
        </section>
      </template>
      <template v-else
        ><TaskProblemList :problems="task.problems" :from="route.fullPath" />
        <section v-if="task.state === 'published'" class="tt-panel tt-stack">
          <h3>任务维护</h3>
          <p class="tt-caption">
            不修改名单和题单，只允许带原因延期或取消。原始截止：{{ date(task.original_due_at) }}
          </p>
          <label class="tt-field"
            ><span>延期后的截止时间 · 北京时间</span
            ><input v-model="extendedDue" type="datetime-local" /></label
          ><label class="tt-field"
            ><span>延期 / 取消原因</span
            ><textarea
              v-model="reason"
              maxlength="500"
              placeholder="必填，供成员和后续审核追溯"
            ></textarea>
          </label>
          <div class="tt-row">
            <button
              class="btn"
              :disabled="busy || !reason.trim()"
              @click="lifecycle('extend-deadline')"
            >
              延期截止时间</button
            ><button class="btn" :disabled="busy || !reason.trim()" @click="lifecycle('cancel')">
              取消任务
            </button>
          </div>
        </section>
        <section class="tt-panel tt-stack">
          <h3>操作记录</h3>
          <p v-for="(entry, i) in task.audit" :key="i" class="tt-caption">
            {{ date(entry.created_at) }} ·
            {{
              {
                created: '创建草稿',
                draft_updated: '更新草稿',
                published: '发布任务',
                extended: '延期',
                cancelled: '取消任务',
              }[entry.action] || entry.action
            }}
            {{ entry.reason }}<span v-if="auditText(entry)"> · {{ auditText(entry) }}</span>
          </p>
        </section></template
      >
    </template>
  </div>
</template>
