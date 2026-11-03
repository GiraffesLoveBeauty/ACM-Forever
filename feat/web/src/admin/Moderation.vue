<script setup>
import { ref, reactive, computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useRequests, showError, date } from '../lib/api.js';
import { useParams } from '../lib/admin.js';
import { markdown } from '../lib/markdown.js';
import { codeBlocks as vCodeBlocks } from '../lib/code-blocks.js';
import PostCover from '../components/PostCover.vue';
const route = useRoute(),
  update = useParams(),
  request = useRequests(),
  rows = ref([]),
  busy = ref(false);
const tab = computed(() => (route.query.tab === 'reports' ? 'reports' : 'posts'));
const reasons = reactive({}),
  reasonErrors = reactive({});
async function load() {
  rows.value = [];
  try {
    rows.value = await request('/forum/moderation/' + tab.value, {}, 'moderation');
  } catch (e) {
    showError(e);
  }
}
async function decide(id, decision) {
  if (busy.value) return;
  const reason = (reasons[id] || '').trim();
  if (tab.value === 'posts' && decision === 'reject' && !reason) {
    reasonErrors[id] = '请填写退回原因，让作者知道需要修改哪里。';
    return;
  }
  reasonErrors[id] = '';
  busy.value = true;
  try {
    await request(`/forum/moderation/${tab.value}/${id}`, {
      method: 'POST',
      body: {
        decision,
        ...(tab.value === 'posts'
          ? { content_version: rows.value.find((item) => item.id === id)?.content_version }
          : {}),
        ...(tab.value === 'posts' && decision === 'reject' ? { reason } : {}),
      },
    });
    delete reasons[id];
    await load();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
watch(tab, load, { immediate: true });
</script>
<template>
  <div class="forum-admin-tabs">
    <button
      v-for="(label, key) in { posts: '待审核话题', reports: '用户举报' }"
      :key="key"
      class="btn"
      :class="{ primary: tab === key }"
      @click="update({ tab: key })"
    >
      {{ label }}</button
    ><button class="btn" @click="load">刷新</button>
  </div>
  <section class="forum-moderation-list">
    <article v-for="item in rows" :key="item.id" class="forum-moderation-card">
      <div class="forum-post-meta">
        <span class="forum-category-pill">{{ item.category_name || `举报 #${item.id}` }}</span
        ><time>{{ date(item.created_at) }}</time>
      </div>
      <h2>
        <RouterLink
          v-if="tab === 'reports' && item.post_status === 'published'"
          :to="`/post.html?id=${item.post_id}`"
          >{{ item.title }}</RouterLink
        ><template v-else
          >{{ item.title
          }}<small v-if="tab === 'reports'" class="forum-report-status">
            （{{
              { removed: '帖子已删除', pending: '待审核', rejected: '未通过' }[item.post_status] ||
              '帖子不可访问'
            }}）
          </small></template
        >
      </h2>
      <p class="forum-moderation-byline">
        {{ tab === 'posts' ? '投稿人' : '举报人' }}：{{ item.author_name || item.reporter_name }}
      </p>
      <p v-if="tab === 'reports'" class="forum-report-reason">举报理由：{{ item.reason }}</p>
      <PostCover
        :src="item.cover_url"
        :alt="`${item.title}的封面`"
        class="forum-moderation-cover"
      />
      <div
        v-if="item.body"
        class="forum-moderation-body forum-markdown"
        v-forum-math
        v-code-blocks
        v-html="markdown(item.body)"
      ></div>
      <label
        v-if="tab === 'posts'"
        class="forum-review-reason-label"
        :for="`review-reason-${item.id}`"
        >退回原因（退回时必填，作者可见）
        <textarea
          :id="`review-reason-${item.id}`"
          v-model="reasons[item.id]"
          :disabled="busy"
          maxlength="1000"
          rows="3"
          placeholder="请说明问题，以及建议如何修改。"
          :aria-invalid="Boolean(reasonErrors[item.id])"
          :aria-describedby="reasonErrors[item.id] ? `review-error-${item.id}` : undefined"
        ></textarea>
      </label>
      <p v-if="reasonErrors[item.id]" :id="`review-error-${item.id}`" role="alert">
        {{ reasonErrors[item.id] }}
      </p>
      <div class="forum-moderation-actions">
        <button
          v-for="(label, decision) in tab === 'posts'
            ? { publish: '通过并发布', reject: '退回' }
            : { resolve: '确认并处理', dismiss: '驳回举报' }"
          :key="decision"
          class="btn"
          :disabled="busy"
          @click="decide(item.id, decision)"
        >
          {{ label }}
        </button>
      </div>
    </article>
    <p v-if="!rows.length" class="empty">没有待处理内容。</p>
  </section>
</template>
