<script setup>
import { ref, watch, computed } from 'vue';
import { auth, useRequests } from '../lib/api.js';
import { renderStatementMarkdown } from '../lib/statement-math.js';
import { copyStatementSample } from '../lib/statement-samples.js';
const props = defineProps({ platform: String, problemId: String });
const data = ref(null),
  error = ref(''),
  unprocessed = ref(false),
  busy = ref(false),
  showTranslation = ref(false);
const request = useRequests();
const sources = {
  ai: 'AI 自动标注',
  cf_rule_mapping: 'CF 原始标签映射',
  manual_add: '人工添加',
  legacy_human: '历史人工确认',
};
const reviews = {
  auto: '自动生效 · 未人工确认',
  corrected: '人工修正',
  verified: '人工完整确认',
  needs_review: '需要复核',
};
const translations = {
  missing: '待翻译',
  needs_review: '待复核 · 没有可用译文',
  auto: '真实 AI 翻译 · 未人工确认',
  stale: '题面已变化 · 译文需复核',
  mock: 'Mock 演示',
};
const translated = computed(() =>
  data.value?.translation_active ? renderStatementMarkdown(data.value.translated_statement) : '',
);
let revision = 0;
async function load() {
  const current = ++revision;
  data.value = null;
  error.value = '';
  unprocessed.value = false;
  showTranslation.value = false;
  busy.value = true;
  try {
    const row = await request(
      `/secondary/problems/${encodeURIComponent(props.platform)}/${encodeURIComponent(props.problemId)}`,
      {},
      'secondary',
    );
    if (current === revision) { data.value = row; showTranslation.value = Boolean(row.translation_active); }
  } catch (e) {
    if (current === revision && e.name !== 'AbortError') {
      if (e.status === 404) unprocessed.value = true;
      else error.value = e.message;
    }
  } finally {
    if (current === revision) busy.value = false;
  }
}
watch(
  () => [props.platform, props.problemId],
  () => {
    load();
  },
  { immediate: true },
);
</script>
<template>
  <section class="card secondary-panel" aria-label="算法标签与中文翻译">
    <div class="secondary-heading">
      <h2>算法标签与中文翻译</h2>
      <button class="btn" :disabled="busy" @click="load">刷新标签与译文</button>
      <span class="chip">本地隔离接入</span
      ><RouterLink
        v-if="auth.authenticated && ['admin', 'root'].includes(auth.role)"
        class="btn"
        :to="{
          path: '/admin.html',
          query: {
            section: 'problems',
            platform: props.platform,
            problem_id: props.problemId,
            action: 'translation',
          },
        }"
      >
        后台管理 · 翻译与标签
      </RouterLink>
    </div>
    <p v-if="busy" role="status">正在读取持久化结果…</p>
    <p v-else-if="error" role="status">二次处理数据暂不可用：{{ error }}</p>
    <p v-else-if="unprocessed" role="status">
      这道题尚未进行二次处理，目前展示爬虫原文。管理员可进入后台管理，预检并执行 AI 翻译或标签标注；翻译无需先完成标签。
    </p>
    <template v-else-if="data">
      <p class="muted">
        {{ data.problem_key }} · V{{ data.taxonomy_version }} · {{ data.model || '规则映射' }}
      </p>
      <h3>最终有效标签</h3>
      <div class="secondary-tags">
        <span
          v-for="tag in data.effective_tags"
          :key="tag.id"
          class="secondary-tag"
          :title="tag.id"
        >
          <strong>{{ tag.name_zh }}</strong
          ><small
            >{{ sources[tag.source] || tag.source
            }}{{ tag.tag_kind === 'provisional' ? ' · 临时大类' : '' }}</small
          > </span
        ><span v-if="!data.effective_tags.length" class="muted">空标签</span>
      </div>
      <p>
        <span class="secondary-status">{{
          reviews[data.review_status] || data.review_status
        }}</span>
        · 人工历史 {{ data.manual_history_count }} 条
      </p>
      <details>
        <summary>查看自动标签、人工覆盖与数据来源</summary>
        <p>原始自动标签：{{ data.auto_tags.map((t) => t.name_zh).join('、') || '空' }}</p>
        <p>
          人工新增：{{ data.manual_added_ids.join('、') || '无' }}；人工删除：{{
            data.manual_removed_ids.join('、') || '无'
          }}
        </p>
        <p>
          标注响应：{{ data.annotation_status }}；内容哈希：<code>{{ data.content_hash }}</code>
        </p>
        <p v-for="link in data.source_links" :key="link" class="muted">原始来源：{{ link }}</p>
        <p v-if="data.needs_review_reasons.length">
          复核原因：{{ data.needs_review_reasons.join('、') }}
        </p>
      </details>
      <div class="secondary-translation">
        <h3>中文翻译</h3>
        <p v-if="data.translation_validation_mode === 'parse_only'" class="muted">AI 自动译文 · 未进行本地内容一致性校验 · 尚未人工确认。</p>
        <p v-if="data.translation_origin === 'ai_offline_corrected'" class="muted">AI 原响应经离线结构校订后启用，尚未经人工确认；原始响应与校订审计均保留。</p>
        <p>{{ translations[data.translation_status] || '状态：' + data.translation_status }}</p>
        <template v-if="data.translation_active">
          <button class="btn" @click="showTranslation = !showTranslation">
            {{ showTranslation ? '收起中文译文' : '展开中文译文' }}
          </button>
          <article v-if="showTranslation" class="problem-statement" @click="copyStatementSample">
            <h3>{{ data.translated_title }}</h3>
            <div v-html="translated"></div>
          </article>
        </template>
        <p v-else class="muted">当前没有已激活的真实中文译文。下方保留原文；本页面不会调用 AI。</p>
        <p v-if="data.translation_task_states.length" class="muted">
          历史翻译执行状态：{{
            data.translation_task_states.join('、')
          }}。{{ data.translation_active ? '当前展示已通过本地结构校验的保存译文；历史失败记录保留供审计。' : '历史候选未作为正式译文展示。' }}
        </p>
      </div>
    </template>
  </section>
</template>
<style scoped>
.secondary-panel {
  border-top: 3px solid #309c91;
  margin: 24px 0;
}
.secondary-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.secondary-heading h2 {
  margin: 0;
}
.secondary-tags {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.secondary-tag {
  display: grid;
  gap: 4px;
  padding: 10px 15px;
  border: 1px solid #309c9166;
  border-radius: 10px;
  background: #309c9110;
}
.secondary-tag small {
  font-size: 11px;
  opacity: 0.8;
}
.secondary-status {
  font-weight: 600;
  color: #309c91;
}
.secondary-panel details {
  margin: 18px 0;
  overflow-wrap: anywhere;
}
.secondary-panel summary {
  cursor: pointer;
}
.secondary-translation {
  border-top: 1px solid #8883;
  margin-top: 20px;
  padding-top: 8px;
}
.secondary-translation article {
  margin-top: 20px;
}
</style>
