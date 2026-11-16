<script setup>
import { computed } from 'vue';
import { date } from '../lib/api.js';
const props = defineProps({ task: { type: Object, required: true } });
const result = computed(() => props.task.result || {});
const progress = computed(() => props.task.progress || {});
const active = computed(() => ['queued', 'running'].includes(props.task.status));
const luoguCatalog = computed(
  () => props.task.platform === 'luogu' && ['catalog', 'platform'].includes(result.value.scope),
);
const batch = computed(() =>
  props.task.platform === 'luogu' ? result.value.completed_batches : progress.value.batch,
);
const status = computed(
  () =>
    ({
      queued: '等待拉取',
      running: '正在拉取',
      completed: '拉取完成',
      partial: '部分完成',
      failed: '拉取失败',
      cancelled: '已取消',
    })[props.task.status] || props.task.status,
);
const total = computed(() =>
  progress.value.phase === 'metadata' ? progress.value.metadata_total : progress.value.total,
);
const done = computed(() =>
  progress.value.phase === 'metadata' ? progress.value.metadata_done : progress.value.done,
);
const failures = computed(() => result.value.failures || []);
</script>
<template>
  <div class="problem-sync-status">
    <p role="status" aria-live="polite">
      {{
        { codeforces: 'Codeforces', atcoder: 'AtCoder', luogu: '洛谷' }[task.platform] ||
        task.platform
      }}
      ·
      {{
        task.platform === 'luogu'
          ? { problems: '指定 P 题号', catalog: '题目目录', platform: '目录与题面补全' }[
              result.scope
            ] || '公开 P 题库'
          : result.scope === 'platform'
            ? '全平台'
            : result.contest_id
              ? `比赛 ${result.contest_id}`
              : '比赛'
      }}
      · {{ status }} · 任务 #{{ task.id }}
    </p>
    <p v-if="task.options?.start_at != null || task.options?.end_at != null" class="muted">
      同步范围 · {{ task.options.time_basis === 'first_seen' ? '本站首次收录时间' : '比赛时间' }} ·
      {{ task.options.start_at != null ? date(task.options.start_at) : '不限开始' }} →
      {{
        task.options.end_at != null ? date(task.options.end_at) : '不限结束'
      }}（结束时间不含在内，北京时间）
    </p>
    <p v-if="result.time_unknown_count" class="muted">
      {{
        result.time_unknown_count
      }}
      道题目缺少所选依据的时间，未计入该时间范围；可选择全部或本站首次收录时间补采。
    </p>
    <p v-if="result.difficulty_warning" class="muted">{{ result.difficulty_warning }}</p>
    <progress
      v-if="active || total"
      :max="Math.max(1, total || 0)"
      :value="total ? done || 0 : undefined"
      aria-label="题目拉取进度"
    />
    <p class="muted" v-if="active && progress.phase === 'taxonomy'">正在更新洛谷原生难度与标签…</p>
    <p
      class="muted"
      v-else-if="active && task.platform === 'luogu' && progress.phase === 'catalog'"
    >
      正在同步洛谷目录 · 已读取 {{ result.catalog_pages || progress.page || 0 }} 页 · 已导入
      {{ result.metadata_count || progress.metadata_done || 0 }} 道题目
    </p>
    <p class="muted" v-else-if="active && progress.phase === 'metadata'">
      正在导入题目目录 {{ progress.metadata_done || 0 }} / {{ progress.metadata_total || 0 }} 题
    </p>
    <p class="muted" v-else-if="active && progress.phase === 'contest_catalog'">
      正在补全比赛题目列表 {{ progress.contests_done || 0 }} / {{ progress.contests_total || 0 }} 场
    </p>
    <p class="muted" v-else-if="total || !active">
      已处理 {{ done || 0 }} / {{ total || 0 }} 题 · 成功 {{ result.success_count || 0 }} 题 · 失败
      {{ result.failure_count || 0 }} 题 · 样例 {{ result.sample_count || 0 }} 组 · 跳过
      {{ result.skipped_count || 0 }} 题 · 剩余待拉取 {{ result.remaining_count || 0 }} 题
      <template v-if="result.scope === 'platform'">
        · {{ task.platform === 'luogu' ? '已完成批次' : '批次' }} {{ batch || 0 }} /
        {{ result.batch_count || 0 }}</template
      >
      <template v-if="active && progress.problem_id"> · 当前 {{ progress.problem_id }}</template>
    </p>
    <p class="muted" v-else>
      正在读取{{ result.scope === 'platform' ? '全平台题目目录' : '比赛题目列表' }}…
    </p>
    <p v-if="luoguCatalog && !active" class="muted">
      目录同步结果 · 已读取 {{ result.catalog_pages || 0 }} 页 · 已导入
      {{ result.metadata_count || 0 }} 道题目
    </p>
    <p v-if="luoguCatalog && !active && result.catalog_complete === false" class="muted">
      目录尚未完整同步，已保存的数据保留；可稍后重新发起采集。
    </p>
    <p v-if="result.access_limited" role="alert">
      洛谷暂时限制访问，本次采集已停止。<template v-if="result.retry_after"
        >建议 {{ result.retry_after }} 秒后重试。</template
      >
    </p>
    <p v-if="result.taxonomy_warning" class="muted">原生分类更新失败，暂用已保存的分类。</p>
    <p v-if="result.error" role="alert">{{ result.error }}</p>
    <details v-if="result.contest_catalog_failure_count">
      <summary>比赛题目列表补全失败 {{ result.contest_catalog_failure_count }} 场</summary>
      <ul>
        <li v-for="failure in result.contest_catalog_failures" :key="failure.contest_id">
          {{ failure.contest_id }}：{{ failure.error }}
        </li>
      </ul>
    </details>
    <details v-if="failures.length">
      <summary>
        查看失败原因（{{ failures.length
        }}{{ result.failure_details_truncated ? '，仅前 100 条' : '' }}）
      </summary>
      <ul>
        <li v-for="(failure, index) in failures" :key="index">
          {{ failure.problem_id }}：{{ failure.error }}
        </li>
      </ul>
      <p v-if="result.failure_details_truncated">完整失败记录保存在数据库中。</p>
    </details>
  </div>
</template>
