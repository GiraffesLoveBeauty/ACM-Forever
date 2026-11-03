<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { auth, useRequests } from '../lib/api.js';
import { forumNotificationVersion } from '../lib/forum-notifications.js';

const request = useRequests();
const unread = ref(null);
const enabled = computed(
  () => auth.authenticated && Boolean(auth.qq_id) && !auth.must_change_password,
);
let timer,
  revision = 0;
async function refresh() {
  clearTimeout(timer);
  const current = ++revision;
  if (!enabled.value) {
    unread.value = null;
    return;
  }
  try {
    if (!document.hidden) {
      const data = await request('/me/notifications/count', {}, 'notification-count');
      if (current === revision) unread.value = data.unread_count;
    }
  } catch {
    // A transient counter failure must not interrupt reading or composing a post.
    if (current === revision) unread.value = null;
  } finally {
    if (enabled.value && current === revision) timer = setTimeout(refresh, 30000);
  }
}
watch(
  [() => auth.qq_id, enabled],
  () => {
    unread.value = null;
    refresh();
  },
  { immediate: true },
);
watch(forumNotificationVersion, refresh);
onMounted(() => document.addEventListener('visibilitychange', refresh));
onBeforeUnmount(() => {
  revision++;
  clearTimeout(timer);
  document.removeEventListener('visibilitychange', refresh);
});
</script>
<template>
  <RouterLink
    v-if="enabled"
    to="/notifications.html"
    class="btn forum-notification-bell"
    :aria-label="unread ? `通知，${unread} 条未读` : '通知'"
  >
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.7"
      aria-hidden="true"
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
    </svg>
    <span>通知</span
    ><span v-if="unread" class="forum-notification-count" aria-hidden="true">{{
      unread > 99 ? '99+' : unread
    }}</span>
  </RouterLink>
</template>
