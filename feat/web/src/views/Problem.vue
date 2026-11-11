<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { auth, date, useRequests } from '../lib/api.js';
import { originalProblemUrl, renderProblemContent } from '../lib/problem-content.js';
import PdfPreview from '../components/PdfPreview.vue';
import SecondaryProcessingPanel from '../components/SecondaryProcessingPanel.vue';
import { problemReturn } from '../lib/member-problems.js';
import { copyStatementSample } from '../lib/statement-samples.js';

const route = useRoute(),
  request = useRequests();
const detail = ref(null),
  busy = ref(false),
  error = ref(''),
  copyMessage = ref('');
const back = computed(() => problemReturn(route.query.from, ['admin', 'root'].includes(auth.role)));
const original = computed(() => originalProblemUrl(detail.value?.problem_url));
const samples = computed(() => (Array.isArray(detail.value?.samples) ? detail.value.samples : []));
const sampleFiles = computed(() =>
  samples.value.map((sample) => {
    if (!Array.isArray(sample?.attachments)) return [];
    return sample.attachments.flatMap((attachment) => {
      if (typeof attachment?.url !== 'string') return [];
      try {
        const url = new URL(attachment.url);
        if (
          url.protocol !== 'https:' ||
          url.hostname !== 'img.atcoder.jp' ||
          url.username ||
          url.password ||
          url.port ||
          !url.pathname.toLowerCase().endsWith('.zip')
        )
          return [];
        return [
          {
            url: url.href,
            name:
              typeof attachment.name === 'string' && attachment.name.trim()
                ? attachment.name
                : '官方样例 ZIP',
          },
        ];
      } catch {
        return [];
      }
    });
  }),
);
const pdf = computed(() => detail.value?.statement_format === 'pdf');
const pdfUrl = computed(() =>
  detail.value
    ? `/api/${auth.role === 'member' ? 'me/' : ''}problems/${encodeURIComponent(detail.value.platform)}/${encodeURIComponent(detail.value.problem_id)}/statement.pdf`
    : '',
);
const content = computed(() =>
  detail.value?.content_available && !pdf.value
    ? renderProblemContent(detail.value)
    : { html: '', samplesEmbedded: false },
);
let revision = 0;
async function load() {
  const current = ++revision;
  detail.value = null;
  error.value = '';
  copyMessage.value = '';
  busy.value = true;
  document.title = '题目详情 · ACM Forever';
  try {
    const { platform, problem_id: id } = route.query;
    if (typeof platform !== 'string' || !platform || typeof id !== 'string' || !id)
      throw Error('缺少题目平台或题号，请从题库打开题目。');
    const data = await request(
      `/problems/${encodeURIComponent(platform)}/${encodeURIComponent(id)}`,
      {},
      'problem-detail',
    );
    if (current !== revision) return;
    detail.value = data;
    document.title = `${data.problem_name || id} · ACM Forever`;
  } catch (e) {
    if (current === revision && e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (current === revision) busy.value = false;
  }
}
async function copySample(index, kind, button) {
  if (
    !['input', 'output'].includes(kind) ||
    !Number.isInteger(index) ||
    typeof samples.value[index]?.[kind] !== 'string'
  )
    return;
  const current = revision;
  try {
    await navigator.clipboard.writeText(String(samples.value[index][kind] ?? ''));
    if (current !== revision) return;
    copyMessage.value = `已复制样例 ${index + 1} ${kind === 'input' ? '输入' : '输出'}`;
    if (button) button.textContent = '已复制';
  } catch {
    if (current === revision) copyMessage.value = '复制失败，请选择样例文本后手动复制。';
  }
}
function copyEmbedded(event) {
  if (event.target.closest?.('button[data-statement-sample="true"]'))
    return copyStatementSample(event);
  const button = event.target.closest?.('button[data-sample-index][data-sample-kind]');
  if (button && event.currentTarget.contains(button))
    copySample(Number(button.dataset.sampleIndex), button.dataset.sampleKind, button);
}
watch(() => [route.query.platform, route.query.problem_id], load, { immediate: true });
</script>
<template>
  <main class="community-main problem-page">
    <RouterLink class="forum-back-link" :to="back"
      >←
      {{
        back === '/home.html'
          ? '返回个人中心'
          : back.startsWith('/training-tasks.html') ||
              back.startsWith('/admin.html?section=training')
            ? '返回训练任务'
            : '返回题库'
      }}</RouterLink
    >
    <h1>{{ detail?.problem_name || route.query.problem_id || '题目详情' }}</h1>
    <div v-if="detail" class="problem-overview">
      <div id="problem-meta" class="chips">
        <span class="chip">{{
          { codeforces: 'Codeforces', atcoder: 'AtCoder' }[detail.platform] || detail.platform
        }}</span>
        <span class="chip">{{ detail.problem_id }}</span>
        <span class="chip">难度 {{ detail.problem_rating ?? '未知' }}</span>
        <span v-for="tag in detail.tags" :key="tag" class="chip">{{ tag }}</span>
        <span v-if="detail.statement_language" class="chip">{{
          detail.statement_language === 'ja' ? '日文题面' : '英文题面'
        }}</span>
      </div>
      <a
        v-if="original"
        id="problem-original"
        class="btn"
        :href="original"
        target="_blank"
        rel="noopener noreferrer"
        >查看原题 ↗</a
      >
    </div>
    <p v-if="busy" role="status">正在读取已采集题目…</p>
    <section v-else-if="error" class="card" role="alert">
      <p>无法打开题目：{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </section>
    <template v-else-if="detail">
      <SecondaryProcessingPanel
        :key="`${detail.platform}:${detail.problem_id}`"
        :platform="detail.platform"
        :problem-id="detail.problem_id"
      />
      <p id="problem-message" class="muted">
        <template v-if="detail.content_available"
          >已采集{{ pdf ? ' PDF' : '' }}题面<span v-if="!pdf"> · {{ samples.length }} 组样例</span
          ><span v-if="detail.statement_fetched_at">
            · 采集于 {{ date(detail.statement_fetched_at) }}</span
          ><span v-if="detail.last_fetch_status === 'failed'">
            · 最近更新失败，展示上次保存的内容</span
          ></template
        >
        <template v-else>已收录题目目录，正文与样例尚未就绪。</template>
      </p>
      <section
        v-if="detail.content_available && pdf"
        id="problem-pdf"
        class="card problem-statement"
      >
        <h2>PDF 题面</h2>
        <p>可在下方直接阅读已采集的题面、图示与样例。</p>
        <PdfPreview :src="pdfUrl" />
        <a class="btn" :href="pdfUrl" target="_blank" rel="noopener noreferrer">打开已采集 PDF</a>
        <p class="muted">预览未显示时可单独打开 PDF。样例见 PDF 原文，暂不拆分为可复制字段。</p>
      </section>
      <article
        v-else-if="detail.content_available"
        id="problem-statement"
        class="card problem-statement"
        @click="copyEmbedded"
        v-html="content.html"
      ></article>
      <section v-else class="card">
        <h2>题面尚未采集</h2>
        <p v-if="detail.last_fetch_status === 'failed'">
          这道题目上次采集失败，请管理员在题库管理中重新拉取。
        </p>
        <p v-else>
          如果正在拉取该平台全部题目，请等待任务处理到这道题目后重新检查。也可请管理员按比赛或题号采集。
        </p>
        <button class="btn" @click="load">重新检查</button>
      </section>
      <section
        v-if="samples.length && !content.samplesEmbedded"
        id="problem-samples"
        class="card problem-statement problem-samples"
      >
        <h2>样例</h2>
        <div v-for="(sample, index) in samples" :key="index" class="problem-sample-grid">
          <div v-for="kind in ['input', 'output']" :key="kind">
            <template v-if="sample[kind] === null && sample[kind + '_note']">
              <h3>样例 {{ index + 1 }} · {{ kind === 'input' ? '输入' : '输出' }}说明</h3>
              <p>{{ sample[kind + '_note'] }}</p>
            </template>
            <template v-else>
              <div class="statement-sample-heading">
                <h3>样例 {{ index + 1 }} · {{ kind === 'input' ? '输入' : '输出' }}</h3>
                <button class="btn problem-copy" @click="copySample(index, kind)">
                  复制样例 {{ index + 1 }} {{ kind === 'input' ? '输入' : '输出' }}
                </button>
              </div>
              <pre>{{ sample[kind] }}</pre>
            </template>
          </div>
          <div v-if="sampleFiles[index].length" class="problem-sample-attachments">
            <h3>样例附件</h3>
            <ul>
              <li v-for="attachment in sampleFiles[index]" :key="attachment.url">
                <a :href="attachment.url" target="_blank" rel="noopener noreferrer">{{
                  attachment.name
                }}</a>
              </li>
            </ul>
          </div>
        </div>
      </section>
      <p role="status">{{ copyMessage }}</p>
    </template>
  </main>
</template>
