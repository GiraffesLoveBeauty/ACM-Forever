<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { auth, useRequests } from '../lib/api.js';
import TagManagement from '../views/TagManagement.vue';
import { renderStatementMarkdown } from '../lib/statement-math.js';
import { copyStatementSample } from '../lib/statement-samples.js';
const props = defineProps({
  platform: String,
  problemId: String,
  action: { type: String, default: 'annotation' },
});
const emit = defineEmits(['close', 'saved']);
const request = useRequests(),
  dialog = ref(null),
  editor = ref(null);
const data = ref(null),
  error = ref(''),
  busy = ref(false),
  tab = ref(props.action);
let previousFocus;
let pollTimer;
let disposed = false;
const isAdmin = computed(() => auth.authenticated && ['admin','root'].includes(auth.role));
const executing = ref(false), confirmation = ref(null), job = ref(null), jobError = ref('');
const states = {
  reuse_existing: '复用已有结果',
  not_required: '无需 AI',
  needs_annotation: '待 AI 标注',
  needs_translation: '待 AI 翻译',
  needs_review: '需要复核',
  pending: '正文待处理',
  invalid: '数据异常',
};
const task = computed(() => data.value?.plan?.[tab.value]);
const execution = computed(() => data.value?.execution?.[tab.value]);
const translationHtml = computed(() => data.value?.existing?.translation_active ? renderStatementMarkdown(data.value.existing.translated_statement) : '');
const originalHtml = computed(() => renderStatementMarkdown(data.value?.statement_preview || ''));
function switchTab(next) {
  // Keep a dirty editor mounted while viewing other tasks; do not discard its draft.
  tab.value = next;
  confirmation.value = null;
}
async function load() {
  if (!isAdmin.value) return;
  busy.value = true;
  error.value = '';
  try {
    data.value = await request(
      `/admin/problem-processing/${encodeURIComponent(props.platform)}/${encodeURIComponent(props.problemId)}`,
    );
    const current=Object.values(data.value.jobs || {}).find(j=>['queued','running'].includes(j.status));
    if(current && !disposed){
      job.value=current;executing.value=true;clearTimeout(pollTimer);
      pollTimer=setTimeout(()=>pollJob(current.job_id),1500);
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    busy.value = false;
  }
}
function prepareExecution() {
  if (!isAdmin.value || !execution.value?.can_execute || executing.value) return;
  confirmation.value={task_type:tab.value,revision:execution.value.revision,settings:execution.value.request_settings};
  jobError.value='';
}
async function pollJob(id) {
  if(disposed || !isAdmin.value)return;
  try {
    const result=await request(`/admin/problem-processing/jobs/${id}`,{},'ai-status');
    if(disposed)return;
    job.value=result;
    if(['queued','running'].includes(result.status))pollTimer=setTimeout(()=>pollJob(id),1500);
    else {executing.value=false;emit('saved');await load();}
  } catch(e) {
    if(e.name!=='AbortError')jobError.value='状态查询失败，任务可能仍在运行。请查询同一任务，勿再次发起付费请求。';
  }
}
async function executeTask() {
  if(!isAdmin.value || executing.value || !confirmation.value)return;
  const chosen=confirmation.value;confirmation.value=null;executing.value=true;jobError.value='';
  try {
    const result=await request(`/admin/problem-processing/${encodeURIComponent(props.platform)}/${encodeURIComponent(props.problemId)}/execute`,
      {method:'POST',body:{task_type:chosen.task_type,revision:chosen.revision,confirm:true}},'ai-execute');
    job.value=result;
    if(['queued','running'].includes(result.status) && result.job_id) await pollJob(result.job_id);
    else {executing.value=false;emit('saved');await load();}
  } catch(e) {
    // A lost POST response is not proof that the worker did not start. No automatic repost.
    if(e.name!=='AbortError')jobError.value=e.message+'；未自动重试。请重新检查任务状态。';
    executing.value=false;
  }
}
watch(isAdmin,allowed=>{if(!allowed){clearTimeout(pollTimer);confirmation.value=null;}});
function requestClose() {
  if (editor.value) editor.value.requestClose();
  else emit('close');
}
defineExpose({ requestClose });
onMounted(() => {
  previousFocus = document.activeElement;
  dialog.value?.showModal?.();
  load();
});
onBeforeUnmount(() => {
  disposed=true;clearTimeout(pollTimer);
  dialog.value?.close?.();
  previousFocus?.focus?.();
});
</script>
<template>
  <dialog
    v-if="isAdmin"
    ref="dialog"
    class="processing-drawer"
    aria-labelledby="processing-title"
    @cancel.prevent="requestClose"
    @click="
      (e) => {
        if (e.target === dialog) requestClose();
      }
    "
  >
    <header class="processing-head">
      <div>
        <span>管理后台 / 题库管理 / 题目二次处理</span>
        <h2 id="processing-title">{{ data?.title || props.problemId }}</h2>
        <small>{{ data?.problem_key || `${props.platform} / ${props.problemId}` }}</small>
      </div>
      <button class="btn" aria-label="关闭题目处理" @click="requestClose">关闭</button>
    </header>
    <nav class="processing-tabs" aria-label="题目处理功能">
      <button
        v-for="(label, key) in {
          annotation: 'AI 标签',
          translation: 'AI 翻译',
          manual: '人工标签',
          source: '爬虫原文',
        }"
        :key="key"
        class="btn"
        :class="{ primary: tab === key }"
        :aria-pressed="tab === key"
        @click="switchTab(key)"
      >
        {{ label }}
      </button>
    </nav>
    <div class="processing-body">
      <p class="processing-notice">
        仅 admin / root 可执行。点击确认后只处理当前一道题；已有结果优先复用，未知状态不自动重试。
      </p>
      <p v-if="busy" role="status">正在读取爬虫题面和最新持久化状态…</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="data">
        <div v-show="tab === 'manual'">
          <TagManagement
            v-if="data.edit_available"
            ref="editor"
            embedded
            :platform="props.platform"
            :problem-id="props.problemId"
            @close="emit('close')"
            @saved="
              () => {
                emit('saved');
                load();
              }
            "
          />
          <p v-else role="status">{{ data.edit_block_reason }}</p>
        </div>
        <section v-if="['annotation', 'translation'].includes(tab)" class="processing-task">
          <h3>{{ tab === 'annotation' ? 'AI 算法标签预检' : 'AI 中文翻译预检' }}</h3>
          <p class="processing-state">{{ tab === 'translation' && data.existing?.translation_active ? '已翻译 · 保存译文可用' : states[task?.status] || '输入待核验' }}</p>
          <p>处理依据：{{ tab === 'translation' && data.existing?.translation_active ? '译文已保存并通过本地结构校验；原始响应及离线校订记录均保留。' : execution?.reason || task?.reason || data.issues?.join('、') || '暂无可用依据' }}</p>
          <template v-if="tab === 'annotation'">
            <h4>当前最终有效标签</h4>
            <p>
              {{
                data.existing?.effective_tags?.map((t) => t.name_zh).join('、') || '尚无有效标签'
              }}
            </p>
            <p class="muted">
              {{
                data.existing
                  ? '已有持久化标签优先复用；人工增删持续生效。自动标签不代表人工确认。'
                  : '当前尚无持久化标注结果；本页不会生成或写入虚假的 AI 标签。'
              }}
            </p>
            <p>爬虫原始标签：{{ data.raw_tags?.join('、') || '无' }}</p>
          </template>
          <template v-else>
            <p class="muted">翻译响应仅解析 JSON 并恢复公式占位符，不再用语序、数字、段落或 Markdown 一致性校验拦截结果。题目身份与防重复请求保护继续生效。</p>
            <p>
              识别语言：{{ data.language?.source_language || '未知' }} · {{ data.language?.reason }}
            </p>
            <p v-if="data.protection">
              翻译保护：{{ data.protection.tokens }} 个公式 / 变量 / 代码占位符，{{
                data.protection.segments
              }}
              个段落。
            </p>
            <p v-if="data.existing?.translation_active">
              已激活译文：{{ data.existing.translated_title }}
            </p>
            <article v-if="data.existing?.translation_active" class="problem-statement" @click="copyStatementSample" v-html="translationHtml"></article>
            <p v-if="data.existing?.translation_origin === 'ai_offline_corrected'" class="muted">AI 原响应经离线校订后启用，未人工确认。</p>
            <p v-else-if="!data.existing?.translation_active" class="muted">
              当前没有已激活的中文译文。新采集题可直接预检翻译，无需先做 AI 标签；原文保留，译文独立保存。历史失败或待复核候选不会作为正式翻译。
            </p>
          </template>
          <button class="btn primary" :disabled="busy || executing || !execution?.can_execute" @click="prepareExecution">
            {{ executing ? '任务处理中…' : execution?.status === 'reuse_existing' || execution?.status === 'not_required' ? '已有结果，无需调用' : tab === 'annotation' ? '执行 AI 标签' : '执行 AI 翻译' }}
          </button>
          <button class="btn" :disabled="busy" @click="load">重新检查最新状态</button>
          <p v-if="execution" class="muted">{{ execution.reason }} {{ execution.config_ready ? '' : 'API 配置不可用，执行已禁用。' }}</p>
          <section v-if="confirmation" class="processing-confirm" aria-label="确认单题 AI 执行">
            <h4>确认{{ confirmation.task_type === 'annotation' ? 'AI 标签' : 'AI 中文翻译' }}</h4>
            <p>仅处理 {{ props.problemId }}，最多新增一次付费请求，不自动重试。</p>
            <p>{{ confirmation.settings?.model }} · {{ confirmation.settings?.base_url }}</p>
            <p>超时 90 秒，输出上限 4000 Token。费用以中转站账单为准。</p>
            <button class="btn primary" @click="executeTask">确认执行单题</button>
            <button class="btn" @click="confirmation = null">取消</button>
          </section>
          <p v-if="job" role="status">{{ job.message }}<span v-if="job.usage"> · Token：{{ job.usage.total_tokens ?? '未返回' }}</span></p>
          <p v-if="executing" class="muted">关闭页面不会取消已提交任务；重新打开此题可继续查看状态，请勿重复调用。</p>
          <p v-if="jobError" role="alert">{{ jobError }}</p>
          <button v-if="job?.job_id && jobError" class="btn" @click="pollJob(job.job_id)">查询原任务状态</button>
          <details>
            <summary>任务身份与版本审计</summary>
            <p>
              爬虫哈希：<code>{{ data.source_statement_sha256 || '未提供' }}</code>
            </p>
            <p>
              规范内容：<code>{{ data.normalized_content_hash }}</code>
            </p>
            <p>
              任务语义：<code>{{ task?.task_key }}</code>
            </p>
            <p>提示词版本：{{ task?.policy?.revision || '未知' }}</p>
            <p>
              输入哈希：<code>{{
                tab === 'annotation' ? data.annotation_input_hash : data.translation_input_hash
              }}</code>
            </p>
            <p>模型：{{ execution?.request_settings?.model || '未配置' }}；最多一次请求，重试 0 次。</p>
          </details>
        </section>
        <section v-if="tab === 'source'">
          <h3>已采集原文</h3>
          <p>
            来源：crawler_problems · {{ data.processing_status }} ·
            {{ data.sample_count }} 组结构化样例
          </p>
          <p>
            身份、HTML、公式和样例通过现有 adapter 统一规范化。下方按纯文本显示，不执行原文 HTML。
          </p>
          <p v-if="data.issues?.length" role="status">正文问题：{{ data.issues.join('、') }}</p>
          <article v-if="data.statement_preview" class="problem-statement" @click="copyStatementSample" v-html="originalHtml"></article>
          <p v-else>无可靠正文（PDF 或未完成采集需先处理）</p>
          <p v-if="data.preview_truncated">仅预览前 6000 字符；预检使用完整正文。</p>
        </section>
      </template>
    </div>
  </dialog>
  <p v-else role="alert">AI 翻译和标签管理仅限 admin 或 root。</p>
</template>
<style scoped>
.processing-drawer {
  box-sizing: border-box;
  width: min(1040px, 100vw);
  max-width: 100vw;
  height: 100dvh;
  max-height: 100dvh;
  margin: 0 0 0 auto;
  padding: 0;
  border: 0;
  background: var(--bg, #f5f8f6);
  color: var(--text, #20362f);
  overflow: auto;
  box-shadow: -16px 0 80px #162f3c26;
}
.processing-drawer::backdrop {
  background: #162a3370;
  backdrop-filter: blur(3px);
}
.processing-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 24px;
  background: var(--card-bg, #fff);
  border-bottom: 1px solid #aaa4;
}
.processing-head h2 {
  margin: 8px 0;
  font-size: 23px;
}
.processing-head span,
.processing-head small {
  color: #677d73;
}
.processing-head div {
  min-width: 0;
  overflow-wrap: anywhere;
}
.processing-tabs {
  display: flex;
  gap: 10px;
  padding: 16px 24px;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  background: var(--card-bg, #fff);
  z-index: 2;
  border-bottom: 1px solid #aaa4;
}
.processing-body {
  padding: 0 24px 30px;
}
.processing-notice {
  padding: 14px 18px;
  border: 1px solid #d1dacf;
  border-radius: 8px;
  background: #729e1c0a;
  font-size: 13px;
}
.processing-task {
  padding: 20px;
  border: 1px solid #aaa3;
  border-radius: 10px;
  background: var(--card-bg, #fff);
}
.processing-state {
  font-size: 20px;
  color: #176c60;
  font-weight: 600;
}
.processing-task > .btn {
  margin: 12px 10px 12px 0;
}
.processing-task details {
  margin-top: 20px;
  overflow-wrap: anywhere;
}
.processing-confirm { padding:16px; border:1px solid #b68639; border-radius:8px; background:#d8ad3b10; }
.processing-confirm .btn {margin-right:12px;}
.processing-source {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  line-height: 1.8;
  padding: 20px;
  border: 1px solid #aaa3;
  background: var(--card-bg, #fff);
  border-radius: 8px;
}
.processing-task code {
  font-size: 12px;
}
@media (max-width: 640px) {
  .processing-head,
  .processing-tabs {
    padding: 16px;
  }
  .processing-body {
    padding: 0 14px 20px;
  }
  .processing-task {
    padding: 14px;
  }
}
</style>
