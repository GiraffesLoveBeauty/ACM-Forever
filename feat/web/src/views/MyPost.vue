<script setup>
import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useRequests, date } from '../lib/api.js';
import { markdown } from '../lib/markdown.js';
import { codeBlocks as vCodeBlocks } from '../lib/code-blocks.js';
import PostCover from '../components/PostCover.vue';

const route = useRoute(),
  request = useRequests();
const post = ref(null),
  error = ref(''),
  loading = ref(false);
const labels = {
  pending: '等待审核',
  published: '审核通过，已发布',
  rejected: '审核未通过',
  removed: '帖子已删除',
};
let revision = 0;
async function load() {
  const current = ++revision;
  post.value = null;
  error.value = '';
  loading.value = true;
  try {
    if (!/^\d+$/.test(String(route.query.id || ''))) throw Error('没有指定有效投稿。');
    post.value = await request(`/forum/mine/posts/${route.query.id}`, {}, 'my-post');
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (current === revision) loading.value = false;
  }
}
watch(() => route.query.id, load, { immediate: true });
</script>
<template>
  <main class="community-main forum-feedback-page">
    <RouterLink class="forum-back-link" to="/home.html#my-posts">← 返回我的投稿</RouterLink>
    <p v-if="loading" role="status">正在加载投稿进度…</p>
    <section v-else-if="error" class="community-panel" role="alert">
      <p>投稿加载失败：{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </section>
    <template v-else-if="post">
      <section class="community-panel forum-submission-status" aria-label="投稿进度">
        <div class="panel-heading">
          <h1>投稿进度</h1>
          <button class="btn" @click="load">刷新状态</button>
        </div>
        <h2>{{ post.title }}</h2>
        <p class="forum-feedback-tag">{{ labels[post.status] }}</p>
        <ol class="forum-submission-timeline">
          <li>
            <b>已提交</b><time>{{ date(post.created_at) }}</time>
          </li>
          <li>
            <b>{{
              post.status === 'pending'
                ? '等待管理员审核'
                : post.status === 'removed' && !post.reviewed_at
                  ? '未完成审核，投稿已删除'
                  : '已完成审核'
            }}</b
            ><time v-if="post.reviewed_at">{{ date(post.reviewed_at) }}</time
            ><span v-else-if="post.status === 'pending'" class="muted"
              >审核结果会通过站内通知告知你。</span
            ><span v-else-if="post.status !== 'removed'" class="muted">此前未记录审核时间。</span>
          </li>
          <li v-if="post.status === 'removed'">
            <b>已删除</b><time>{{ date(post.updated_at) }}</time>
          </li>
        </ol>
        <p v-if="post.status === 'rejected'" class="forum-feedback-reason">
          退回原因：{{ post.review_reason || '此前未记录原因，请联系管理员了解详情。' }}
        </p>
        <RouterLink
          v-if="post.status === 'published'"
          class="btn primary"
          :to="`/post.html?id=${post.id}`"
          >查看已发布话题</RouterLink
        >
        <p v-else class="muted">以下原文仅你本人可在此查看。</p>
      </section>
      <article class="community-panel">
        <p class="label">投稿原文 · {{ post.category_name }}</p>
        <h2>{{ post.title }}</h2>
        <PostCover :src="post.cover_url" :alt="`${post.title}的封面`" class="forum-article-cover" />
        <div class="forum-markdown" v-forum-math v-code-blocks v-html="markdown(post.body)"></div>
      </article>
    </template>
  </main>
</template>
