import { ref } from 'vue';
import { auth } from './api.js';

/* 个人资料（昵称 / 头像）的极简共享状态：
   侧栏顶部区块和「头像与昵称」面板都读这里，改完立刻同步。 */
export const profileName = ref('');
export const profileAvatar = ref(null);

export function setProfile(patch = {}) {
  if ('name' in patch) profileName.value = (patch.name || '').trim();
  if ('avatar_url' in patch) {
    profileAvatar.value = patch.avatar_url || null;
    auth.avatar_url = patch.avatar_url || null;
  }
}

export const displayName = () => profileName.value || 'Forever';
export const currentAvatar = () => profileAvatar.value || auth.avatar_url || null;
