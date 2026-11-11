<script setup>
import { date, external } from '../lib/api.js';
import { problemLink } from '../lib/member-problems.js';
import { completions, verifications, platformName, tagList } from '../lib/training-tasks.js';
defineProps({
  problems: { type: Array, default: () => [] },
  from: String,
  editable: Boolean,
  disabled: Boolean,
});
defineEmits(['move', 'remove']);
</script>
<template>
  <ol class="tt-problems">
    <li
      v-for="(problem, index) in problems"
      :key="problem.platform + problem.problem_id"
      class="tt-problem"
    >
      <span class="tt-problem-num">{{ index + 1 }}</span>
      <div class="tt-problem-copy tt-stack" style="gap: 7px">
        <strong>{{ problem.problem_name || problem.problem_id }}</strong>
        <div class="tt-row">
          <span class="tt-tag"
            >{{ platformName(problem.platform) }} {{ problem.problem_id.replace(/^cf_/, '') }}</span
          >
          <span v-if="problem.problem_rating" class="tt-tag"
            >难度 {{ problem.problem_rating }}</span
          >
          <span v-for="tag in tagList(problem.tags)" :key="tag" class="tt-tag">{{ tag }}</span>
        </div>
        <p v-if="!problem.content_available" class="tt-caption">
          站内题面尚未采集，可从可信原题入口练习。
        </p>
        <p v-if="problem.supported === false" class="tt-caption">
          该平台暂不支持自动核验，发布前需要更换。
        </p>
        <template v-if="problem.status">
          <div class="tt-row">
            <span class="tt-tag" :class="problem.status">{{ completions[problem.status] }}</span
            ><span class="tt-caption">{{ verifications[problem.verification] || '待核验' }}</span>
          </div>
          <p v-if="problem.evidence" class="tt-caption">
            实际 AC：{{ date(problem.evidence.accepted_at)
            }}<span v-if="problem.evidence.external_submission_id">
              · 提交 #{{ problem.evidence.external_submission_id }}</span
            >
          </p>
          <p class="tt-caption">
            最后核验 {{ date(problem.checked_at) }} · 同步成功 {{ date(problem.sync_success_at) }}
          </p>
        </template>
      </div>
      <div class="tt-problem-actions">
        <RouterLink class="btn" :to="problemLink(problem, from)">查看题目</RouterLink>
        <a
          v-if="problem.problem_url"
          class="btn"
          :href="external(problem.problem_url)"
          target="_blank"
          rel="noopener noreferrer"
          >原题 ↗</a
        >
        <template v-if="editable">
          <button
            class="btn"
            :disabled="disabled || index === 0"
            :aria-label="'上移第 ' + (index + 1) + ' 题'"
            @click="$emit('move', index, -1)"
          >
            上移
          </button>
          <button
            class="btn"
            :disabled="disabled || index === problems.length - 1"
            :aria-label="'下移第 ' + (index + 1) + ' 题'"
            @click="$emit('move', index, 1)"
          >
            下移
          </button>
          <button
            class="btn"
            :disabled="disabled"
            :aria-label="'移除第 ' + (index + 1) + ' 题'"
            @click="$emit('remove', index)"
          >
            移除
          </button>
        </template>
      </div>
    </li>
  </ol>
</template>
