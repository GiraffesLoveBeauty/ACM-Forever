<script setup>
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { auth, api, avatar, date, showError } from '../lib/api.js';
import { postImage, postExcerpt } from '../lib/post-images.js';
import PostCover from './PostCover.vue';
const props = defineProps({ post: { type: Object, required: true }, returnTo: String });
const target = computed(() => ({
  path: '/post.html',
  query: { id: props.post.id, ...(props.returnTo ? { from: props.returnTo } : {}) },
}));
const router = useRouter(),
  busy = ref(false);
async function toggle(kind) {
  if (!auth.authenticated)
    return router.push({
      path: '/login.html',
      query: { next: router.currentRoute.value.fullPath },
    });
  if (busy.value) return;
  busy.value = true;
  try {
    const result = await api(`/forum/posts/${props.post.id}/${kind}`, { method: 'POST' });
    const key = kind === 'like' ? 'viewer_liked' : 'viewer_bookmarked';
    if (kind === 'like' && Boolean(props.post[key]) !== result.active)
      props.post.likes_count = Math.max(
        0,
        (props.post.likes_count || 0) + (result.active ? 1 : -1),
      );
    props.post[key] = result.active;
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <article class="forum-post-card" :data-category="post.category_slug || 'discussion'">
    <div class="forum-post-card-layout" :class="{ 'has-cover': postImage(post.cover_url) }">
      <div class="forum-post-card-copy">
        <div class="forum-post-meta">
          <span class="forum-category-pill">{{ post.category_name }}</span
          ><span v-if="post.is_pinned" class="forum-pinned">置顶</span
          ><time class="forum-post-time">{{ date(post.created_at) }}</time>
        </div>
        <h2>
          <RouterLink :to="target">{{ post.title }}</RouterLink>
        </h2>
        <RouterLink class="forum-post-excerpt" :to="target">{{
          postExcerpt(post.excerpt)
        }}</RouterLink>
        <div class="forum-post-author">
          <img class="forum-avatar" :src="avatar(post.author_avatar_url)" alt="作者头像" /><span>{{
            post.author_name || 'ACM 成员'
          }}</span
          ><span>· 计量 ACMer</span>
        </div>
      </div>
      <RouterLink
        v-if="postImage(post.cover_url)"
        class="forum-post-cover-link"
        :to="target"
        :aria-label="`阅读：${post.title}`"
      >
        <PostCover
          :src="post.cover_url"
          :alt="`${post.title}的封面`"
          thumbnail
          class="forum-card-cover"
        />
      </RouterLink>
      <RouterLink
        v-else
        class="forum-post-cover-link forum-post-cover-placeholder"
        :to="target"
        :aria-label="`阅读：${post.title}`"
      >
        <svg
          viewBox="0 0 48 48"
          width="42"
          height="42"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M12 7h16l8 8v26H12zM28 7v9h8M19 24h10M19 30h10" />
        </svg>
        <span>{{ post.category_name || '社区话题' }}</span>
      </RouterLink>
    </div>
    <div class="forum-post-actions">
      <RouterLink :to="{ ...target, hash: '#comments' }"
        >▤ {{ post.comments_count || 0 }} 条评论</RouterLink
      ><button :class="{ 'is-active': post.viewer_liked }" :disabled="busy" @click="toggle('like')">
        {{ post.viewer_liked ? '♥' : '♡' }} {{ post.likes_count || 0 }} 赞</button
      ><span>◉ {{ post.views_count || 0 }} 阅读</span
      ><button
        :class="{ 'is-active': post.viewer_bookmarked }"
        :disabled="busy"
        @click="toggle('bookmark')"
      >
        {{ post.viewer_bookmarked ? '★ 已收藏' : '☆ 收藏' }}
      </button>
    </div>
  </article>
</template>
