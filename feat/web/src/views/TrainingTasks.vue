<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { date, useRequests } from '../lib/api.js';
import { completions, fraction, phases, ruleName } from '../lib/training-tasks.js';
import TaskProblemList from '../components/TaskProblemList.vue';
import OjBindings from '../components/OjBindings.vue';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const list = ref({ items: [], total: 0 }),
  task = ref(null),
  loading = ref(true),
  error = ref(''),
  refreshing = ref(false),
  bindings = ref([]),
  bindingOpen = ref(false),
  bindingBusy = ref(false);
const taskId = computed(() => String(route.query.task_id || ''));
const tab = computed(() =>
  ['active', 'upcoming', 'history'].includes(route.query.tab) ? route.query.tab : 'active',
);
const page = computed(() => Math.max(1, Number(route.query.page) || 1));
const needsBinding = computed(() => task.value?.problems.some((p) => p.verification === 'unbound'));
const base = '/me/training-tasks';
let timer,
  revision = 0,
  disposed = false,
  currentId = '',
  currentTab = '';

function address(changes) {
  const query = { ...route.query, ...changes };
  for (const key of Object.keys(query))
    if (query[key] == null || query[key] === '') delete query[key];
  return router.push({ path: '/training-tasks.html', query });
}
function schedule() {
  clearTimeout(timer);
  if (!disposed && ['queued', 'running'].includes(task.value?.refresh?.status))
    timer = setTimeout(load, 3000);
}
async function load() {
  const operation = ++revision;
  clearTimeout(timer);
  loading.value = true;
  error.value = '';
  if (currentId !== taskId.value) {
    task.value = null;
    bindingOpen.value = false;
    bindings.value = [];
    currentId = taskId.value;
  }
  if (!taskId.value && currentTab !== tab.value) {
    list.value = { items: [], total: 0 };
    currentTab = tab.value;
  }
  try {
    if (taskId.value && !/^[1-9][0-9]*$/.test(taskId.value))
      throw Error('训练任务地址无效，请返回列表重新选择。');
    const data = await request(
      taskId.value
        ? base + '/' + taskId.value
        : base + '?' + new URLSearchParams({ tab: tab.value, page: page.value, page_size: 20 }),
      {},
      'view',
    );
    if (operation !== revision) return;
    if (taskId.value) task.value = data;
    else list.value = data;
    schedule();
  } catch (e) {
    if (e.name !== 'AbortError' && operation === revision) error.value = e.message;
  } finally {
    if (operation === revision) loading.value = false;
  }
}
watch(() => route.fullPath, load, { immediate: true });
onBeforeUnmount(() => {
  disposed = true;
  revision++;
  clearTimeout(timer);
});
async function refresh() {
  if (refreshing.value) return;
  refreshing.value = true;
  error.value = '';
  const operation = revision;
  try {
    const result = await request(
      base + '/' + taskId.value + '/refresh',
      { method: 'POST', body: {} },
      'refresh',
    );
    if (operation !== revision) return;
    task.value.refresh = { ...result.task, status: result.status };
    schedule();
  } catch (e) {
    if (e.name !== 'AbortError' && operation === revision) error.value = e.message;
  } finally {
    if (!disposed) refreshing.value = false;
  }
}
async function openBinding() {
  bindingBusy.value = true;
  error.value = '';
  const operation = revision;
  try {
    const profile = await request('/me/profile', {}, 'bindings');
    if (operation === revision) {
      bindings.value = profile.bindings.filter((b) => ['cf', 'codeforces'].includes(b.platform));
      bindingOpen.value = true;
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (!disposed) bindingBusy.value = false;
  }
}
async function afterBinding() {
  await load();
  if (bindingOpen.value) await openBinding();
}
function refreshText(item) {
  if (!item) return '';
  if (item.result?.codeforces < 0 || item.result?.error)
    return '同步失败，已有进度保留，可稍后重试。';
  return (
    {
      queued: '同步请求已排队，正在等待执行…',
      running: '正在同步 Codeforces 提交记录…',
      completed: '同步已完成，进度按实际提交时间核验。',
      failed: '同步失败，已有进度保留，可稍后重试。',
      cancelled: '同步任务已取消，可稍后重试。',
      interrupted: '同步中断，可重新刷新。',
    }[item.status] || '同步状态待确认，请重新刷新。'
  );
}
</script>
<template>
  <main
    class="community-main training-tasks member-training-tasks"
    :aria-busy="loading || refreshing"
  >
    <nav class="tt-row tt-muted" aria-label="面包屑">
      <RouterLink to="/home.html">个人中心</RouterLink> /
      <RouterLink :to="{ path: '/training-tasks.html', query: { tab } }">训练任务</RouterLink
      ><template v-if="task"> / {{ task.title }}</template>
    </nav>
    <header v-if="!taskId" class="tt-hero">
      <div>
        <span class="tt-kicker">PERSONAL TRAINING / ASSIGNED TASKS</span>
        <h1>训练任务</h1>
        <p>管理员布置的题单，按周期完成。仅展示分配给你的任务。</p>
      </div>
      <span class="tt-hero-mark" aria-hidden="true">think → code → AC</span>
    </header>
    <div v-if="error" class="tt-error" role="alert">
      {{ error }} <button class="btn" :disabled="loading" @click="load">重新加载</button>
    </div>
    <p v-if="loading" class="tt-note" role="status">正在加载训练任务…</p>
    <template v-if="!taskId">
      <nav class="tt-tabs" aria-label="任务分组">
        <button
          v-for="(label, key) in { active: '进行中', upcoming: '未开始', history: '历史任务' }"
          :key="key"
          class="btn"
          :aria-current="tab === key ? 'page' : undefined"
          @click="address({ tab: key, page: null, task_id: null })"
        >
          {{ label }}
        </button>
      </nav>
      <div v-if="list.items.length" class="tt-task-cards">
        <article v-for="item in list.items" :key="item.id" class="tt-panel tt-task-card">
          <div class="tt-between">
            <span class="tt-kicker"
              >TK-{{ String(item.id).padStart(3, '0') }} · 发布时身份
              {{ item.recipient.status_snapshot }}</span
            ><span class="tt-tag" :class="item.phase">{{ phases[item.phase] }}</span>
          </div>
          <h2>{{ item.title }}</h2>
          <p class="tt-caption">{{ date(item.starts_at) }} → {{ date(item.due_at) }} · 北京时间</p>
          <div>
            <p>
              {{ item.recipient.completed_problems }} / {{ item.recipient.problem_count }} 题 ·
              {{ completions[item.recipient.completion] }}
            </p>
            <div
              class="tt-progress"
              :aria-label="
                '已完成 ' +
                item.recipient.completed_problems +
                ' / ' +
                item.recipient.problem_count +
                ' 题'
              "
            >
              <span
                :style="{
                  width:
                    fraction(item.recipient.completed_problems, item.recipient.problem_count) + '%',
                }"
              ></span>
            </div>
          </div>
          <p class="tt-caption">
            {{ ruleName(item.rule) }} · {{ item.creator_name
            }}<span v-if="item.recipient.pending"> · 有待核验的记录</span>
          </p>
          <RouterLink
            class="btn primary"
            :to="{ path: '/training-tasks.html', query: { task_id: item.id, tab } }"
            >查看任务 ↗</RouterLink
          >
        </article>
      </div>
      <div v-else-if="!loading && !error" class="tt-empty">
        {{
          {
            active: '当前没有进行中的任务，可查看未开始或历史任务。',
            upcoming: '暂无未开始的任务。',
            history: '暂无历史任务。',
          }[tab]
        }}
      </div>
      <Pager :page="page" :total="list.total" :busy="loading" @change="address({ page: $event })" />
    </template>
    <template v-else-if="task">
      <div>
        <button class="btn" @click="address({ task_id: null, page: null })">← 返回任务列表</button>
      </div>
      <header class="tt-panel tt-stack">
        <div class="tt-between">
          <span class="tt-kicker"
            >TK-{{ String(task.id).padStart(3, '0') }} · {{ task.creator_name }}</span
          ><span class="tt-tag" :class="task.phase">{{ phases[task.phase] }}</span>
        </div>
        <h1>{{ task.title }}</h1>
        <p class="tt-description">{{ task.description }}</p>
        <p v-if="task.cancel_reason" class="tt-note">任务已取消：{{ task.cancel_reason }}</p>
      </header>
      <section class="tt-panel tt-stack">
        <div class="tt-between">
          <div>
            <h2>我的题目进度</h2>
            <p class="tt-caption">
              按时 {{ task.recipient.on_time_problems }} 题 · 逾期
              {{ task.recipient.late_problems }} 题 · {{ completions[task.recipient.completion] }}
            </p>
          </div>
          <div class="tt-row">
            <strong
              >{{ task.recipient.completed_problems }} /
              {{ task.recipient.problem_count }} 题</strong
            ><button
              v-if="needsBinding"
              class="btn primary"
              :disabled="bindingBusy"
              @click="openBinding"
            >
              绑定 Codeforces</button
            ><button
              class="btn"
              :disabled="
                refreshing ||
                task.state !== 'published' ||
                needsBinding ||
                ['queued', 'running'].includes(task.refresh?.status)
              "
              @click="refresh"
            >
              {{ refreshing ? '正在提交…' : '刷新进度' }}
            </button>
          </div>
        </div>
        <div class="tt-progress">
          <span
            :style="{
              width:
                fraction(task.recipient.completed_problems, task.recipient.problem_count) + '%',
            }"
          ></span>
        </div>
        <p class="tt-caption">
          上次核验 {{ date(task.recipient.checked_at) }} · 最近成功同步
          {{ date(task.recipient.last_success_at) }}
        </p>
        <p v-if="task.refresh" class="tt-note" role="status">{{ refreshText(task.refresh) }}</p>
        <p class="tt-note">
          {{
            task.rule === 'historical_ac'
              ? '历史 AC 可计入；任务未开始时仍显示未开始。'
              : '仅周期内 AC 计入按时完成；开始前的历史 AC 单独标记。'
          }}
          截止后 AC 为逾期，以 OJ
          实际提交时间为准。缺少证据时显示待核验，完成全部必做题才算完成整份任务。
        </p>
      </section>
      <section v-if="bindingOpen" class="tt-panel tt-stack">
        <div class="tt-between">
          <h2>为当前任务绑定账号</h2>
          <button class="btn" @click="bindingOpen = false">收起绑定面板</button>
        </div>
        <p class="tt-caption">
          完成绑定后仍在当前任务，可刷新进度。后续改绑不会继承其他账号的成绩。
        </p>
        <OjBindings :bindings="bindings" @refresh="afterBinding" />
      </section>
      <section class="tt-stack">
        <div class="tt-between">
          <h2>必做题单</h2>
          <span class="tt-tag">全部 {{ task.problems.length }} 题通过</span>
        </div>
        <TaskProblemList :problems="task.problems" :from="route.fullPath" />
      </section>
      <section class="tt-panel tt-stack">
        <h2>任务安排</h2>
        <dl class="tt-detail-grid">
          <div>
            <dt>开始时间</dt>
            <dd>{{ date(task.starts_at) }}</dd>
          </div>
          <div>
            <dt>截止时间</dt>
            <dd>{{ date(task.due_at) }}</dd>
          </div>
          <div>
            <dt>时区</dt>
            <dd>Asia/Shanghai（北京时间）</dd>
          </div>
          <div>
            <dt>我在发布时的身份</dt>
            <dd>{{ task.recipient.status_snapshot }}</dd>
          </div>
          <div>
            <dt>完成规则</dt>
            <dd>{{ ruleName(task.rule) }} · 全部必做题通过</dd>
          </div>
          <div>
            <dt>核验来源</dt>
            <dd>已同步 Codeforces 实际提交记录</dd>
          </div>
        </dl>
        <p v-if="task.original_due_at !== task.due_at" class="tt-caption">
          任务已延期，原始截止：{{ date(task.original_due_at) }}
        </p>
        <p class="tt-caption">
          发放后身份变更不影响已分配任务。绑定变化、同步异常或覆盖不足会单独提示。
        </p>
      </section>
    </template>
  </main>
</template>
