<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRequests, date, showError } from '../lib/api.js';
import { notificationsChanged } from '../lib/forum-notifications.js';
import Pager from '../components/Pager.vue';

const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const data = ref(null),
  loading = ref(false),
  busy = ref(false),
  error = ref('');
const page = computed(() => Math.max(1, Number.parseInt(route.query.page, 10) || 1));
const unreadOnly = computed(() => route.query.unread === '1');
const labels = {
  comment: '有人评论了你的话题',
  reply: '有人回复了你的评论',
  published: '话题审核通过',
  rejected: '话题被退回',
};
let revision = 0;
function navigate(changes) {
  return router.push({ path: '/notifications.html', query: { ...route.query, ...changes } });
}
async function load() {
  const current = ++revision;
  loading.value = true;
  error.value = '';
  data.value = null;
  try {
    const result = await request(
      `/me/notifications?page=${page.value}&unread=${unreadOnly.value ? '1' : '0'}`,
      {},
      'notifications',
    );
    const last = Math.max(1, Math.ceil(result.total / result.page_size));
    if (page.value > last) {
      await router.replace({ path: '/notifications.html', query: { ...route.query, page: last } });
      return;
    }
    data.value = result;
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    if (current === revision) loading.value = false;
  }
}
async function read(item, open = false) {
  if (busy.value) return;
  busy.value = true;
  try {
    if (!item.read_at) await request(`/me/notifications/${item.id}/read`, { method: 'POST' });
    notificationsChanged();
    if (open && item.target_url) await router.push(item.target_url);
    else await load();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function readAll() {
  if (busy.value || !data.value?.unread_count) return;
  busy.value = true;
  const through = data.value.latest_id;
  try {
    await request('/me/notifications/read-all', { method: 'POST', body: { through_id: through } });
    notificationsChanged();
    await load();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
watch([page, unreadOnly], load, { immediate: true });
</script>
<template>
  <main class="community-main forum-feedback-page">
    <RouterLink class="forum-back-link" to="/index.html">← 返回论坛</RouterLink>
    <section class="community-panel">
      <div class="panel-heading">
        <div>
          <p class="label">社区动态</p>
          <h1>我的通知</h1>
          <p class="muted">回复和审核结果会保存在这里。</p>
        </div>
        <RouterLink class="btn" to="/home.html#my-posts">我的投稿</RouterLink>
      </div>
      <div class="forum-feedback-toolbar">
        <div class="chips" role="group" aria-label="通知筛选">
          <button
            class="btn"
            :class="{ primary: !unreadOnly }"
            :aria-pressed="!unreadOnly"
            @click="navigate({ unread: undefined, page: undefined })"
          >
            全部通知
          </button>
          <button
            class="btn"
            :class="{ primary: unreadOnly }"
            :aria-pressed="unreadOnly"
            @click="navigate({ unread: '1', page: undefined })"
          >
            未读通知<span v-if="data">（{{ data.unread_count }}）</span>
          </button>
        </div>
        <div class="chips">
          <button class="btn" :disabled="busy || loading" @click="load">刷新</button>
          <button class="btn" :disabled="busy || loading || !data?.unread_count" @click="readAll">
            全部标为已读
          </button>
        </div>
      </div>
      <p v-if="loading" role="status">正在加载通知…</p>
      <div v-else-if="error" class="forum-feedback-error" role="alert">
        <p>通知加载失败：{{ error }}</p>
        <button class="btn" @click="load">重试</button>
      </div>
      <template v-else-if="data">
        <p v-if="!data.rows.length" class="empty">
          {{ unreadOnly ? '暂无未读通知。' : '暂无通知。收到回复或审核结果后会显示在这里。' }}
        </p>
        <ol v-else class="forum-notification-list">
          <li
            v-for="item in data.rows"
            :key="item.id"
            class="forum-notification-item"
            :class="{ unread: !item.read_at }"
          >
            <div class="forum-feedback-meta">
              <b>{{ labels[item.kind] }}</b
              ><span v-if="!item.read_at" class="forum-feedback-tag">未读</span
              ><time>{{ date(item.created_at) }}</time>
            </div>
            <h2>{{ item.post_title }}</h2>
            <p v-if="['comment', 'reply'].includes(item.kind)" class="muted">
              {{ item.actor_name }} 参与了讨论。
            </p>
            <p v-if="item.kind === 'rejected'" class="forum-feedback-reason">
              退回原因：{{ item.review_reason || '此前未记录原因，请联系管理员了解详情。' }}
            </p>
            <div class="chips">
              <button
                v-if="item.target_url"
                class="btn primary"
                :disabled="busy"
                @click="read(item, true)"
              >
                {{ ['published', 'rejected'].includes(item.kind) ? '查看投稿进度' : '查看讨论' }}
              </button>
              <span v-else class="muted">原话题已不可访问。</span>
              <button v-if="!item.read_at" class="btn" :disabled="busy" @click="read(item)">
                标为已读
              </button>
            </div>
          </li>
        </ol>
        <Pager
          :page="page"
          :total="data.total"
          :size="data.page_size"
          :busy="busy || loading"
          @change="navigate({ page: $event })"
        />
      </template>
    </section>
  </main>
</template>
