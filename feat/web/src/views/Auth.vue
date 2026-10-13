<script setup>
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, auth, safeNext } from '../lib/api.js';
const route = useRoute(),
  router = useRouter(),
  identifier = ref(''),
  password = ref(''),
  nextPassword = ref(''),
  confirmation = ref(''),
  busy = ref(false),
  message = ref('');
const changing = computed(() => route.path === '/change-password.html');
async function submit() {
  if (busy.value) return;
  busy.value = true;
  message.value = '';
  try {
    if (changing.value) {
      if (nextPassword.value !== confirmation.value) throw Error('两次输入的新密码不一致。');
      await api('/auth/change-password', {
        method: 'POST',
        body: { old_password: password.value, new_password: nextPassword.value },
      });
      auth.must_change_password = false;
    } else {
      const data = await api('/auth/login', {
        method: 'POST',
        body: {
          username: identifier.value,
          ...(/^\d{4,12}$/.test(identifier.value) ? { qq_id: identifier.value } : {}),
          password: password.value,
        },
      });
      Object.assign(auth, data, await api('/auth/me'));
    }
    const next = safeNext(
      route.query.next,
      changing.value ? (auth.role === 'member' ? '/home.html' : '/admin.html') : '/index.html',
    );
    password.value = '';
    nextPassword.value = '';
    confirmation.value = '';
    await router.push(
      auth.must_change_password ? { path: '/change-password.html', query: { next } } : next,
    );
  } catch (e) {
    message.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function logout() {
  try {
    await api('/auth/logout', { method: 'POST' });
    Object.assign(auth, { authenticated: false, csrf_token: '', role: null });
    await router.push('/login.html');
  } catch (e) {
    message.value = e.message;
  }
}
</script>
<template>
  <main class="auth-main">
    <form class="card auth-card" @submit.prevent="submit">
      <h1>{{ changing ? '修改密码' : '欢迎回来' }}</h1>
      <p class="muted">
        {{
          changing
            ? '正式密码为 12–128 位，请避免使用姓名、QQ 或常见密码。'
            : '使用社区账号登录 ACM Forever。'
        }}
      </p>
      <label v-if="!changing"
        >用户名 / QQ<input v-model.trim="identifier" autocomplete="username" required /></label
      ><label
        >{{ changing ? '当前密码' : '密码'
        }}<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required /></label
      ><template v-if="changing"
        ><label
          >新密码<input
            v-model="nextPassword"
            type="password"
            autocomplete="new-password"
            minlength="12"
            maxlength="128"
            required /></label
        ><label
          >确认新密码<input
            v-model="confirmation"
            type="password"
            autocomplete="new-password"
            minlength="12"
            maxlength="128"
            required /></label
      ></template>
      <p role="alert">{{ message }}</p>
      <button class="btn primary" :disabled="busy">
        {{ busy ? '正在处理…' : changing ? '保存新密码' : '登录' }}</button
      ><button v-if="changing" class="btn" type="button" @click="logout">退出登录</button>
    </form>
  </main>
</template>
