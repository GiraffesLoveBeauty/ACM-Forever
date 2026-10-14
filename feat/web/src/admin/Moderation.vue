<script setup>
import { ref, computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useRequests, showError, date } from '../lib/api.js';
import { useParams } from '../lib/admin.js';
import { markdown } from '../lib/markdown.js';
const route = useRoute(),
  update = useParams(),
  request = useRequests(),
  rows = ref([]),
  busy = ref(false);
const tab = computed(() => (route.query.tab === 'reports' ? 'reports' : 'posts'));
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
  busy.value = true;
  try {
    await request(`/forum/moderation/${tab.value}/${id}`, { method: 'POST', body: { decision } });
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
        <RouterLink v-if="tab === 'reports'" :to="`/post.html?id=${item.post_id}`">{{
          item.title
        }}</RouterLink
        ><template v-else>{{ item.title }}</template>
      </h2>
      <p class="forum-moderation-byline">
        {{ tab === 'posts' ? '投稿人' : '举报人' }}：{{ item.author_name || item.reporter_name }}
      </p>
      <div
        v-if="tab === 'posts'"
        class="forum-moderation-body forum-markdown"
        v-html="markdown(item.body)"
      ></div>
      <p v-else>{{ item.reason }}</p>
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
