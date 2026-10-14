<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useRequests, auth, avatar, external, date, showError } from '../lib/api.js';
import { compressAvatar } from '../lib/avatar.js';
import CommunityArt from '../components/CommunityArt.vue';
const request = useRequests(),
  profile = ref(),
  tab = ref('posts'),
  posts = ref([]),
  busy = ref(false),
  input = ref(),
  preview = ref(''),
  note = ref('选择图片后会自动压缩并上传（最大 2 MB）');
let avatarRevision = 0,
  disposed = false;
const stats = computed(() => {
  const counts = profile.value?.platform_counts || {};
  return [
    [profile.value?.total_count || 0, '累计 AC', '✦'],
    [counts.codeforces || 0, 'Codeforces', 'CF'],
    [counts.atcoder || 0, 'AtCoder', 'At'],
    [
      Object.entries(counts)
        .filter(([k]) => !['codeforces', 'atcoder'].includes(k))
        .reduce((sum, [, c]) => sum + c, 0),
      '其他平台',
      '＋',
    ],
  ];
});
function clearPreview() {
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = '';
}
async function load() {
  const version = avatarRevision;
  try {
    const data = await request('/me/profile', {}, 'profile');
    if (version !== avatarRevision) data.user.avatar_url = auth.avatar_url;
    profile.value = data;
  } catch (e) {
    showError(e);
  }
}
async function content() {
  try {
    posts.value = await request(`/forum/mine/${tab.value}`, {}, 'mine');
  } catch (e) {
    showError(e);
  }
}
async function rename() {
  const name = prompt('请输入新昵称', profile.value?.user.name || '');
  if (!name) return;
  try {
    await request('/me/profile', { method: 'PUT', body: { name } });
    await load();
  } catch (e) {
    showError(e);
  }
}
async function upload(event) {
  const file = event.target.files?.[0];
  if (!file || busy.value) return;
  busy.value = true;
  clearPreview();
  preview.value = URL.createObjectURL(file);
  note.value = '正在压缩图片…';
  try {
    const compressed = await compressAvatar(file);
    if (disposed) return;
    const form = new FormData();
    form.append('avatar', compressed, compressed.name);
    note.value = '正在上传…';
    const data = await request('/me/avatar', { method: 'POST', body: form });
    avatarRevision++;
    auth.avatar_url = data.avatar_url;
    if (profile.value) profile.value.user.avatar_url = data.avatar_url;
    note.value = `头像已更新（${Math.ceil(compressed.size / 1024)} KB）`;
  } catch (e) {
    if (e.name !== 'AbortError') note.value = '上传失败：' + e.message;
  } finally {
    clearPreview();
    busy.value = false;
    event.target.value = '';
  }
}
async function reset() {
  if (busy.value) return;
  busy.value = true;
  try {
    await request('/me/avatar', { method: 'DELETE' });
    avatarRevision++;
    auth.avatar_url = null;
    if (profile.value) profile.value.user.avatar_url = null;
    note.value = '已恢复默认头像';
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
watch(tab, content);
onMounted(() => Promise.allSettled([load(), content()]));
onBeforeUnmount(() => {
  disposed = true;
  clearPreview();
});
</script>
<template>
  <main class="community-main personal-main">
    <section class="personal-welcome">
      <div>
        <h1>{{ profile ? `欢迎回来，${profile.user.name}` : '个人中心' }}</h1>
        <p>查看刷题进度、账号绑定和社区参与。</p>
      </div>
      <CommunityArt scene="journey" /><RouterLink class="personal-rank-link" to="/leaderboard.html"
        ><span>社区排行榜</span><b>查看大家的进度　↗</b></RouterLink
      >
    </section>
    <section class="profile-stat-grid grid kpis">
      <div v-for="([count, label, icon], i) in stats" :key="i" class="card profile-stat-card">
        <div class="stat-icon">{{ icon }}</div>
        <div class="label">{{ label }}</div>
        <div class="value">{{ count }}</div>
        <small>已通过题目</small>
      </div>
    </section>
    <section class="community-panel">
      <div class="panel-heading"><h2>训练与题目</h2></div>
      <div class="chips">
        <RouterLink class="btn" to="/challenge.html">今日训练</RouterLink
        ><RouterLink class="btn" to="/problem-bank.html">题库</RouterLink
        ><RouterLink class="btn" to="/contest-review.html">赛事复盘</RouterLink
        ><RouterLink class="btn" to="/change-password.html?next=/home.html">修改密码</RouterLink>
      </div>
    </section>
    <div class="personal-columns">
      <section class="community-panel profile-details-panel">
        <div class="panel-heading">
          <h2>个人资料</h2>
          <button class="btn" @click="rename">修改昵称</button>
        </div>
        <p class="panel-caption">绑定账号和做题统计仅本人及管理员可见。</p>
        <div class="profile-avatar-editor">
          <img
            class="user-avatar profile-avatar-preview"
            :src="preview || avatar(profile?.user.avatar_url)"
            alt="当前头像"
          />
          <div class="profile-avatar-copy">
            <b>社区头像</b><small role="status">{{ note }}</small>
            <div class="profile-avatar-actions">
              <button class="btn primary" :disabled="busy" @click="input.click()">
                {{ busy ? '处理中…' : '上传头像' }}</button
              ><input ref="input" type="file" accept="image/*" hidden @change="upload" /><button
                class="btn"
                :disabled="busy"
                @click="reset"
              >
                恢复默认
              </button>
            </div>
          </div>
        </div>
        <div class="profile-binding-grid">
          <div
            v-for="(label, key) in {
              name: '社区昵称',
              status: '身份',
              cf_handle: 'Codeforces',
              luogu_id: '洛谷',
              atcoder_handle: 'AtCoder',
              nowcoder_id: '牛客',
            }"
            :key="key"
            class="binding-row"
          >
            <span>{{ label }}</span
            ><b>{{ profile?.user[key] || '未设置' }}</b>
          </div>
        </div>
      </section>
      <section class="community-panel recent-panel">
        <div class="panel-heading"><h2>最近 AC</h2></div>
        <div class="list">
          <div
            v-for="(item, i) in profile?.recent_ac?.slice(0, 6) || []"
            :key="i"
            class="recent-ac-row"
          >
            <span class="recent-ac-check">✓</span
            ><span class="recent-ac-copy"
              ><b>{{ item.problem_name || item.problem_id }}</b
              ><small
                >{{ item.platform }} · {{ item.problem_rating || '难度未知' }} ·
                {{ date(item.submit_time) }}</small
              ></span
            ><a
              v-if="item.problem_url"
              class="recent-ac-open"
              :href="external(item.problem_url)"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="打开题目"
              >↗</a
            >
          </div>
          <p v-if="!profile?.recent_ac?.length" class="empty">暂无 AC 记录</p>
        </div>
      </section>
    </div>
    <section class="community-panel personal-community-panel">
      <div class="panel-heading">
        <h2>我的社区内容</h2>
        <RouterLink class="panel-text-link" to="/compose.html">查看草稿 / 写新话题　↗</RouterLink>
      </div>
      <div class="personal-content-tabs">
        <button
          v-for="(label, key) in { posts: '我的话题', bookmarks: '我的收藏' }"
          :key="key"
          class="personal-content-tab"
          :class="{ active: tab === key }"
          @click="tab = key"
        >
          {{ label }}
        </button>
      </div>
      <div class="personal-content-list">
        <RouterLink
          v-for="item in posts"
          :key="item.id"
          class="personal-community-item"
          :to="`/post.html?id=${item.id}`"
          ><span class="personal-community-icon">{{ tab === 'posts' ? '↗' : '☆' }}</span
          ><span class="personal-community-copy"
            ><b>{{ item.title }}</b
            ><small
              >{{ item.category_name }} ·
              {{
                { pending: '待审核', published: '已发布', rejected: '未通过' }[item.status] ||
                item.author_name
              }}</small
            ></span
          ></RouterLink
        >
        <p v-if="!posts.length" class="empty">这里还没有内容，去论坛看看吧。</p>
      </div>
    </section>
  </main>
</template>
