<script setup>
import { ref, reactive, inject, onMounted } from 'vue';
import { useRequests, notify, showError } from '../lib/api.js';
const request = useRequests(),
  openTheme = inject('openTheme'),
  font = ref(1),
  time = ref(''),
  group = ref(''),
  qq = ref(''),
  admins = reactive({ root: [], admins: [], can_manage: false });
async function save(path, body, message) {
  try {
    const data = await request(path, { method: 'PUT', body });
    notify(message);
    return data;
  } catch (e) {
    showError(e);
  }
}
async function appearance() {
  if (await save('/ui/preferences', { font_scale: font.value }, '字号已保存'))
    document.documentElement.style.setProperty('--font-scale', font.value);
}
function add() {
  const value = qq.value.trim();
  if (!/^\d{4,12}$/.test(value)) return notify('请输入有效 QQ 号。');
  if (!admins.admins.includes(value) && !admins.root.includes(value)) admins.admins.push(value);
  qq.value = '';
}
async function bot() {
  const data = await save('/admins', { admins: admins.admins }, 'QQBot 管理员已保存');
  if (data) Object.assign(admins, data);
}
async function report(disable = false) {
  if (
    await save(
      '/settings/contest-report',
      { time: disable ? '' : time.value },
      disable ? '比赛播报已关闭' : '比赛播报时间已保存',
    )
  )
    if (disable) time.value = '';
}
onMounted(async () => {
  const results = await Promise.allSettled([
    request('/ui/preferences'),
    request('/settings/contest-report'),
    request('/admins'),
  ]);
  for (const [i, result] of results.entries()) {
    if (result.status === 'rejected') {
      showError(result.reason);
      continue;
    }
    if (i === 0) font.value = result.value.font_scale || 1;
    if (i === 1) {
      time.value = result.value.time || '';
      group.value = result.value.group_id || '';
    }
    if (i === 2) Object.assign(admins, result.value);
  }
});
</script>
<template>
  <section class="admin-panel">
    <h2>外观</h2>
    <p class="muted">自助调色仅保存在当前浏览器。</p>
    <button class="btn" @click="openTheme">打开自助调色</button>
    <form class="filters" @submit.prevent="appearance">
      <label
        >字号比例<input
          v-model="font"
          type="number"
          min="0.8"
          max="1.5"
          step="0.05"
          required /></label
      ><button class="btn primary">保存字号</button>
    </form>
  </section>
  <section class="admin-panel">
    <h2>比赛播报</h2>
    <p class="muted">按北京时间每日播报近期 Codeforces 比赛。</p>
    <form class="filters" @submit.prevent="report()">
      <label>时间<input v-model="time" type="time" required /></label
      ><button class="btn primary">保存时间</button
      ><button class="btn" type="button" @click="report(true)">关闭播报</button>
    </form>
    <p>通知群：{{ group || '未配置，请在 QQ 中配置通知群' }}</p>
  </section>
  <section class="admin-panel">
    <h2>QQBot 管理员</h2>
    <p class="muted">与 Web 角色分别管理。全局 QQBot Root 不能在此移除。</p>
    <p>QQBot Root：{{ admins.root.join('、') || '尚未配置' }}</p>
    <div v-for="id in admins.admins" :key="id" class="list-item">
      <span>QQ {{ id }}</span
      ><button
        class="btn"
        :disabled="!admins.can_manage"
        @click="admins.admins = admins.admins.filter((value) => value !== id)"
      >
        移除
      </button>
    </div>
    <form class="filters" @submit.prevent="add">
      <label>管理员 QQ<input v-model="qq" inputmode="numeric" placeholder="4–12 位数字" /></label
      ><button class="btn" :disabled="!admins.can_manage">添加到名单</button>
    </form>
    <button class="btn primary" :disabled="!admins.can_manage" @click="bot">
      保存 QQBot 管理员
    </button>
  </section>
</template>
