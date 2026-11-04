<script setup>
import { computed, onMounted, ref } from 'vue';
import { auth, useRequests } from '../lib/api.js';
const request = useRequests(),
  data = ref(null),
  error = ref(''),
  filter = ref('');
const items = computed(() =>
  (data.value?.items || []).filter(
    (p) =>
      !filter.value ||
      p.effective_tags.some((t) => t.name_zh.includes(filter.value)) ||
      p.title.toLowerCase().includes(filter.value.toLowerCase()),
  ),
);
onMounted(async () => {
  try {
    data.value = await request('/secondary/problems');
  } catch (e) {
    error.value = e.message;
  }
});
</script>
<template>
  <main class="community-main processing-demo">
    <p class="muted">ACM Forever / 本地验收 / 题目二次处理</p>
    <h1>标签与翻译，接入真实题目详情</h1>
    <p>独立数据库与持久数据副本。管理员可在本地修正标签；采集和 AI 执行均已禁用。</p>
    <RouterLink class="btn primary" to="/my-problems.html">进入题库与标签筛选 →</RouterLink>
    <RouterLink
      v-if="['admin', 'root'].includes(auth.role)"
      class="btn"
      to="/admin.html?section=problems"
      >后台题库：AI 翻译与标签管理 →</RouterLink
    >
    <div v-if="data" class="demo-metrics">
      <section class="card">
        <strong>{{ data.count }}</strong
        ><span>已有真实标注</span>
      </section>
      <section class="card">
        <strong>{{ data.active_translations }}</strong
        ><span>已激活真实译文</span>
      </section>
      <section class="card">
        <strong>{{ data.real_api_calls }}</strong
        ><span>本地演示 AI 调用</span>
      </section>
    </div>
    <p class="muted">
      AI 标签自动生效不代表已通过人工确认。本页使用当前持久目录快照，未伪造翻译结果。
    </p>
    <label>按标签或标题筛选 <input v-model="filter" placeholder="例如：动态规划 / Train" /></label>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="demo-problems">
      <RouterLink
        v-for="p in items"
        :key="p.problem_key"
        class="card demo-problem"
        :to="{ path: '/problem.html', query: { platform: p.platform, problem_id: p.problem_id } }"
      >
        <span class="muted">{{ p.problem_key }}</span>
        <h2>{{ p.title }}</h2>
        <div class="chips">
          <span v-for="tag in p.effective_tags" :key="tag.id" class="chip">{{ tag.name_zh }}</span>
        </div>
        <p class="muted">
          {{
            {
              auto: '自动标签 · 未人工确认',
              corrected: '人工修正',
              verified: '人工确认',
              needs_review: '需复核',
            }[p.review_status]
          }}
          · {{ p.translation_active ? '有中文译文' : '无可用中文译文' }}
        </p>
        <span>打开题目详情 →</span>
      </RouterLink>
    </div>
  </main>
</template>
<style scoped>
.processing-demo {
  padding-bottom: 70px;
}
.demo-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 28px 0;
}
.demo-metrics section {
  display: grid;
  gap: 8px;
}
.demo-metrics strong {
  font-size: 32px;
  color: #309c91;
}
.demo-problems {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 24px;
}
.demo-problem {
  text-decoration: none;
  color: inherit;
  transition: transform 0.15s;
}
.demo-problem:hover {
  transform: translateY(-3px);
}
.demo-problem h2 {
  font-size: 21px;
  margin: 12px 0;
}
.processing-demo input {
  max-width: 400px;
  margin: 10px 0;
}
@media (max-width: 720px) {
  .demo-problems {
    grid-template-columns: 1fr;
  }
  .demo-metrics {
    gap: 8px;
  }
  .demo-metrics section {
    padding: 14px;
  }
  .demo-metrics strong {
    font-size: 25px;
  }
}
</style>
