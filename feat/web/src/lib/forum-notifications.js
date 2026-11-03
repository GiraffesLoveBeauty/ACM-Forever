import { ref } from 'vue';

// Only an invalidation signal is shared; personal notification data stays in its view.
export const forumNotificationVersion = ref(0);
export function notificationsChanged() {
  forumNotificationVersion.value++;
}
