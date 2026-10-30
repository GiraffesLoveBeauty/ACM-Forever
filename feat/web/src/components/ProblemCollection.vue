<script setup>
import { computed, reactive, watch } from 'vue';
import { useProblemCollection } from '../lib/problem-collection.js';
import ProblemDatabaseBrowser from './ProblemDatabaseBrowser.vue';
import ProblemTaskProgress from './ProblemTaskProgress.vue';
const emit = defineEmits(['published']);
const {
  database,
  databaseMessage,
  initializing,
  initialize,
  task,
  message,
  locked,
  submitting,
  cancelling,
  cancel,
  checkTask,
  submit: collectionSubmit,
} = useProblemCollection(() => emit('published'));
const form = reactive({
  platform: 'atcoder',
  scope: 'contest',
  language: 'en',
  contest_id: '',
  problem_ids: '',
  limit: 20,
  batch_size: 100,
  refresh: false,
});
const full = computed(() => form.scope === 'platform');
const cf = computed(() => form.platform === 'codeforces');
watch(cf, (value) => {
  if (value) form.language = 'en';
});
const active = computed(() => task.value && ['queued', 'running'].includes(task.value.status));
async function submit() {
  const count = Number(full.value ? form.batch_size : form.limit);
  if (!Number.isInteger(count) || count < 1 || count > 100) {
    message.value = '题数必须为 1–100 的整数。';
    return;
  }
  const ids = [
    ...new Set(
      form.problem_ids
        .trim()
        .split(/[\s,，]+/)
        .filter(Boolean),
    ),
  ];
  if (!full.value && ids.length > 100) {
    message.value = '最多指定 100 个题号。';
    return;
  }
  const payload = {
    platform: form.platform,
    scope: form.scope,
    language: cf.value ? 'en' : form.language,
    refresh: form.refresh,
  };
  if (full.value) payload.batch_size = count;
  else
    Object.assign(payload, { contest_id: form.contest_id.trim(), problem_ids: ids, limit: count });
  await collectionSubmit(payload);
}
</script>
<template>
  <section class="admin-section" aria-labelledby="problem-db-heading">
    <div class="admin-section-heading">
      <div>
        <h2 id="problem-db-heading">服务端数据库</h2>
        <p>初始化 SQLite 表结构，保留已有题目与样例。</p>
      </div>
    </div>
    <div class="admin-panel">
      <div class="admin-form-footer">
        <p class="admin-message" role="status">{{ databaseMessage }}</p>
        <button
          id="problem-db-init"
          class="btn admin-button"
          :disabled="initializing"
          @click="initialize"
        >
          {{ initializing ? '正在初始化…' : '初始化数据库' }}
        </button>
      </div>
      <div class="chips">
        <span v-for="row in database?.platforms || []" :key="row.platform" class="chip"
          >{{
            row.platform === 'codeforces'
              ? 'Codeforces'
              : row.platform === 'atcoder'
                ? 'AtCoder'
                : row.platform
          }}
          · 目录 {{ row.total }} 题 · 已采集 {{ row.collected }} 题 · 失败 {{ row.failed }} 题 ·
          样例 {{ row.samples }} 组</span
        >
      </div>
    </div>
  </section>
  <ProblemDatabaseBrowser v-if="database?.initialized" />
  <section v-else-if="database" class="admin-section">
    <div class="admin-section-heading">
      <div>
        <h2>题库记录</h2>
        <p>初始化 SQLite 数据库后即可浏览已保存的题目与题面。</p>
      </div>
    </div>
  </section>
  <section class="admin-section problem-sync" aria-labelledby="problem-sync-heading">
    <div class="admin-section-heading">
      <div>
        <h2 id="problem-sync-heading">拉取题目</h2>
        <p>从公开比赛采集题面与样例，保存到题库。</p>
      </div>
      <RouterLink class="admin-jump" to="/admin.html?section=tasks">查看同步任务 →</RouterLink>
    </div>
    <div class="admin-panel">
      <form id="problem-sync-form" @submit.prevent="submit">
        <fieldset id="problem-sync-fields" :disabled="locked">
          <div class="admin-create-grid">
            <label
              >平台<select id="sync-platform" v-model="form.platform">
                <option value="atcoder">AtCoder</option>
                <option value="codeforces">Codeforces</option>
              </select></label
            >
            <label
              >拉取范围<select id="sync-scope" v-model="form.scope">
                <option value="contest">单场比赛</option>
                <option value="platform">该平台全部题目</option>
              </select></label
            >
            <label
              >题面语言<select id="sync-language" v-model="form.language" :disabled="cf">
                <option value="en">英文</option>
                <option value="ja">日文</option>
              </select></label
            >
            <label v-if="full"
              >每批处理题数<input
                id="sync-batch-size"
                v-model.number="form.batch_size"
                type="number"
                min="1"
                max="100"
                step="1"
                required
            /></label>
            <label v-else
              >最多拉取题数<input
                id="sync-limit"
                v-model.number="form.limit"
                type="number"
                min="1"
                max="100"
                step="1"
                required
            /></label>
            <label v-if="!full"
              >比赛 ID<input
                id="sync-contest"
                v-model.trim="form.contest_id"
                required
                maxlength="100"
                :pattern="cf ? '[1-9][0-9]{0,4}' : '[A-Za-z0-9_-]{1,100}'"
                :inputmode="cf ? 'numeric' : 'text'"
                :placeholder="cf ? '例如 1843' : '例如 abc370'"
              /><small>{{
                cf ? '普通公开比赛 ID，暂不支持 Gym。' : '填写 AtCoder 比赛 ID。'
              }}</small></label
            >
            <label v-if="!full"
              >指定题号（选填）<input
                id="sync-problems"
                v-model="form.problem_ids"
                :placeholder="cf ? '例如 1843A, 1843B' : '例如 abc370_a, abc370_b'"
              /><small>多个题号用逗号或空格分隔；留空时按比赛题序拉取。</small></label
            >
          </div>
          <div class="admin-form-footer">
            <label class="admin-toggle"
              ><input id="sync-refresh" v-model="form.refresh" type="checkbox" /><span
                >重新拉取已有题目</span
              ></label
            ><button class="btn primary admin-button" type="submit">
              {{
                submitting
                  ? '提交中…'
                  : active
                    ? '正在拉取…'
                    : full
                      ? '拉取该平台全部题目'
                      : '开始拉取'
              }}
            </button>
          </div>
        </fieldset>
      </form>
      <p class="admin-form-note">
        {{
          full
            ? '先导入公开题目目录，再自动逐批拉取全部题面与样例；每批题数不是总数量上限。全量采集可能持续数小时，默认跳过已采集题目，再次运行可继续未完成题目。'
            : '默认跳过已采集题目。题数为本次上限；离开页面后后台任务继续执行。'
        }}
      </p>
      <p v-if="message" role="status" aria-live="polite">{{ message }}</p>
      <ProblemTaskProgress v-if="task" :task="task" />
      <div class="chips problem-sync-actions">
        <button class="btn" type="button" :disabled="submitting" @click="checkTask">
          刷新采集状态
        </button>
        <button v-if="active" class="btn" type="button" :disabled="cancelling" @click="cancel">
          {{ cancelling ? '正在取消…' : '取消采集' }}
        </button>
      </div>
    </div>
  </section>
</template>
