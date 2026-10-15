<script setup>
import { computed } from 'vue';
const props = defineProps({ task: { type: Object, required: true } });
const result = computed(() => props.task.result || {});
const progress = computed(() => props.task.progress || {});
const active = computed(() => ['queued', 'running'].includes(props.task.status));
const status = computed(
  () =>
    ({
      queued: '等待拉取',
      running: '正在拉取',
      completed: '拉取完成',
      partial: '部分题目拉取失败',
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
      {{ task.platform === 'codeforces' ? 'Codeforces' : 'AtCoder' }}
      ·
      {{
        result.scope === 'platform'
          ? '全平台'
          : result.contest_id
            ? `比赛 ${result.contest_id}`
            : '比赛'
      }}
      · {{ status }} · 任务 #{{ task.id }}
    </p>
    <progress
      v-if="active || total"
      :max="Math.max(1, total || 0)"
      :value="total ? done || 0 : undefined"
      aria-label="题目拉取进度"
    />
    <p class="muted" v-if="progress.phase === 'metadata'">
      正在导入题目目录 {{ progress.metadata_done || 0 }} / {{ progress.metadata_total || 0 }} 题
    </p>
    <p class="muted" v-else-if="total || !active">
      已处理 {{ progress.done || 0 }} / {{ progress.total || 0 }} 题 · 成功
      {{ result.success_count || 0 }} 题 · 失败 {{ result.failure_count || 0 }} 题 · 样例
      {{ result.sample_count || 0 }} 组 · 跳过 {{ result.skipped_count || 0 }} 题 · 剩余待拉取
      {{ result.remaining_count || 0 }} 题
      <template v-if="result.scope === 'platform'">
        · 批次 {{ progress.batch || 0 }} / {{ result.batch_count || 0 }}</template
      >
      <template v-if="active && progress.problem_id"> · 当前 {{ progress.problem_id }}</template>
    </p>
    <p class="muted" v-else>
      正在读取{{ result.scope === 'platform' ? '全平台题目目录' : '比赛题目列表' }}…
    </p>
    <p v-if="result.error" role="alert">{{ result.error }}</p>
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
