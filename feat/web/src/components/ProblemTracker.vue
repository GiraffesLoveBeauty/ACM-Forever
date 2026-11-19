<script setup>
import { computed } from 'vue';
import { date } from '../lib/api.js';
import { problemLink } from '../lib/member-problems.js';
import { difficultyPresentation } from '../lib/problem-presentation.js';
import ProblemDifficulty from './ProblemDifficulty.vue';
import ProblemTags from './ProblemTags.vue';

const props = defineProps({
  contests: { type: Array, default: () => [] },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  from: { type: String, required: true },
});
const columns = computed(() => Math.max(1, ...props.contests.map((row) => row.problems.length)));
const statuses = { solved: '已 AC', attempted: '尝试未通过', unseen: '未记录' };
function status(problem) {
  return statuses[problem.status] || statuses.unseen;
}
function contestName(contest) {
  return (
    contest.contest_name ||
    (contest.platform === 'codeforces'
      ? `Codeforces #${contest.contest_id}`
      : `AtCoder ${contest.contest_id}`)
  );
}
function description(problem) {
  return [
    problem.problem_id,
    problem.problem_name || '未命名题目',
    status(problem),
    problem.ac_at
      ? `AC ${date(problem.ac_at)}`
      : problem.last_submit_at
        ? `最近提交 ${date(problem.last_submit_at)}`
        : '暂无同步提交记录',
  ].join(' · ');
}
</script>

<template>
  <div class="problem-tracker">
    <div class="tracker-legend" aria-label="做题状态图例">
      <span class="tracker-status tracker-solved">✓ 已 AC</span>
      <span class="tracker-status tracker-attempted">◐ 尝试未通过</span>
      <span class="tracker-status tracker-unseen">— 未记录</span>
    </div>
    <p class="muted tracker-note">
      进度仅依据当前账号已同步的记录；“未记录”不代表原站从未提交。难度颜色按所属平台划分，点击题目查看站内题面。
    </p>
    <div class="tracker-scroll" role="region" aria-label="比赛做题进度表，可横向滚动" tabindex="0">
      <table class="problem-tracker-table">
        <caption>
          本人比赛做题进度
        </caption>
        <thead>
          <tr>
            <th scope="col" class="tracker-number">序号</th>
            <th scope="col" class="tracker-contest">比赛 / AC 进度</th>
            <th v-for="column in columns" :key="column" scope="col">题目 {{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(contest, index) in contests"
            :key="`${contest.platform}-${contest.contest_id}`"
          >
            <td class="tracker-number">{{ (page - 1) * pageSize + index + 1 }}</td>
            <th scope="row" class="tracker-contest">
              <span class="tracker-contest-name">{{ contestName(contest) }}</span>
              <small
                >{{ contest.platform === 'codeforces' ? 'Codeforces' : 'AtCoder' }} ·
                {{ contest.contest_id }}</small
              >
              <small class="tracker-start-time">{{
                contest.start_time ? `开始 ${date(contest.start_time)}` : '比赛时间未收录'
              }}</small>
              <span class="tracker-progress"
                >已 AC {{ contest.solved_count }} / {{ contest.total_count
                }}<template v-if="contest.attempted_count">
                  · 尝试未通过 {{ contest.attempted_count }}</template
                ></span
              >
              <progress
                :value="contest.solved_count"
                :max="Math.max(1, contest.total_count)"
                :aria-label="`${contestName(contest)} 已 AC ${contest.solved_count} / ${contest.total_count}`"
              />
            </th>
            <td
              v-for="problem in contest.problems"
              :key="problem.problem_id"
              class="tracker-problem"
              :class="`tracker-${statuses[problem.status] ? problem.status : 'unseen'}`"
            >
              <RouterLink
                :to="problemLink(problem, from)"
                :title="description(problem)"
                :aria-label="description(problem)"
              >
                <span
                  class="tracker-problem-name"
                  :style="{ '--tracker-rating': difficultyPresentation(problem).color }"
                  >{{ problem.problem_index }}. {{ problem.problem_name || '未命名题目' }}</span
                >
                <ProblemDifficulty :problem="problem" class="tracker-rating" />
                <ProblemTags
                  :tags="problem.tags"
                  :platform="contest.platform"
                  class="tracker-tags"
                />
                <span class="tracker-state-label"
                  >{{
                    problem.status === 'solved' ? '✓' : problem.status === 'attempted' ? '◐' : '—'
                  }}
                  {{ status(problem) }}</span
                >
              </RouterLink>
            </td>
            <td
              v-for="blank in columns - contest.problems.length"
              :key="`blank-${blank}`"
              class="tracker-blank"
              aria-label="无此题"
            />
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.problem-tracker {
  --tracker-contest-width: 220px;
  --tracker-problem-width: 132px;
  min-width: 0;
}
.tracker-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 20px 0 12px;
}
.tracker-status {
  padding: 7px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
}
.tracker-solved {
  background: color-mix(in srgb, #35b76c 24%, var(--panel));
}
.tracker-attempted {
  background: color-mix(in srgb, #e5ac36 19%, var(--panel));
}
.tracker-unseen {
  background: var(--panel);
}
.tracker-note {
  line-height: 1.7;
  margin: 0 0 20px;
}
.tracker-scroll {
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.tracker-scroll:focus-visible {
  outline: 2px solid var(--brand-strong);
  outline-offset: 3px;
}
.problem-tracker-table {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
  margin: 0;
  color: var(--text);
}
caption {
  text-align: left;
  padding: 12px 16px;
  background: var(--panel);
  color: var(--muted);
}
th,
td {
  padding: 0;
  border: 0;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  text-align: left;
  white-space: normal;
}
thead th {
  padding: 14px 16px;
  background: var(--panel);
  white-space: nowrap;
}
.tracker-number {
  width: 44px;
  min-width: 44px;
  padding: 12px 6px;
  text-align: center;
  color: var(--muted);
}
.tracker-contest {
  position: sticky;
  left: 0;
  z-index: 1;
  width: var(--tracker-contest-width);
  min-width: var(--tracker-contest-width);
  max-width: var(--tracker-contest-width);
  padding: 12px;
  background: var(--panel);
  color: var(--text);
  box-shadow: 1px 0 var(--line);
}
thead .tracker-contest {
  z-index: 3;
}
.tracker-contest-name {
  display: block;
  overflow-wrap: anywhere;
  font-weight: 600;
  line-height: 1.5;
}
.tracker-contest small {
  display: block;
  color: var(--muted);
  margin-top: 6px;
  font-weight: 400;
}
.tracker-progress {
  display: block;
  margin-top: 10px;
  font-weight: 400;
  font-size: 13px;
}
progress {
  display: block;
  width: 100%;
  height: 6px;
  margin-top: 8px;
  accent-color: #35b76c;
}
.tracker-problem {
  width: var(--tracker-problem-width);
  min-width: var(--tracker-problem-width);
  max-width: var(--tracker-problem-width);
}
.tracker-problem a {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 124px;
  padding: 12px;
  color: var(--text);
  text-decoration: none;
}
.tracker-problem a:hover {
  background: color-mix(in srgb, var(--brand-strong) 10%, transparent);
}
.tracker-problem a:focus-visible {
  outline: 2px solid var(--brand-strong);
  outline-offset: -3px;
}
.tracker-problem-name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  line-height: 1.5;
  font-weight: 600;
  color: color-mix(in srgb, var(--tracker-rating) 80%, var(--text));
}
.tracker-rating {
  align-self: flex-start;
}
.tracker-tags {
  font-size: 11px;
}
.tracker-state-label {
  font-size: 12px;
  margin-top: auto;
}
.tracker-blank {
  min-width: var(--tracker-problem-width);
  background: var(--subtle-bg);
}
@media (min-width: 641px) and (max-width: 1320px) {
  .problem-tracker {
    --tracker-contest-width: 200px;
    --tracker-problem-width: 120px;
  }
}
@media (max-width: 640px) {
  .problem-tracker {
    --tracker-contest-width: 140px;
    --tracker-problem-width: 136px;
  }
}
</style>
