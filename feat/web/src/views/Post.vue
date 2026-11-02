<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRequests, auth, avatar, date, showError, notify } from '../lib/api.js';
import { markdown } from '../lib/markdown.js';
import { postImage } from '../lib/post-images.js';
import PostCover from '../components/PostCover.vue';
import ImageLightbox from '../components/ImageLightbox.vue';
const imageViewer = ref();
function viewImage(event) {
  if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
  if (
    event.target.tagName === 'IMG' &&
    !event.target.closest('a') &&
    postImage(event.target.getAttribute('src'))
  ) {
    event.preventDefault();
    imageViewer.value.open(event.target.getAttribute('src'), event.target.alt);
  }
}
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const post = ref(),
  error = ref(''),
  body = ref(''),
  parent = ref(0),
  busy = ref(false),
  article = ref(),
  input = ref(),
  toc = ref([]),
  activeHeading = ref('');
let observer;
const roots = computed(() => (post.value?.comments || []).filter((c) => !c.parent_id));
async function load() {
  try {
    if (!route.query.id) throw Error('没有指定话题。');
    post.value = await request(`/forum/posts/${encodeURIComponent(route.query.id)}`, {}, 'post');
    document.title = `${post.value.title} · ACM Forever`;
    await buildToc();
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message;
  }
}
async function buildToc() {
  await nextTick();
  observer?.disconnect();
  const headings = [...(article.value?.querySelectorAll('h1,h2,h3') || [])];
  for (const image of article.value?.querySelectorAll('img') || []) {
    if (!postImage(image.getAttribute('src')) || image.closest('a')) continue;
    image.tabIndex = 0;
    image.setAttribute('role', 'button');
    image.setAttribute('aria-label', `放大查看：${image.alt || '正文图片'}`);
  }
  toc.value = headings.map((node, i) => {
    node.id = `post-section-${i + 1}`;
    return { id: node.id, text: node.textContent, level: node.tagName.slice(1) };
  });
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) if (entry.isIntersecting) activeHeading.value = entry.target.id;
    },
    { rootMargin: '-12% 0px -72% 0px' },
  );
  headings.forEach((h) => observer.observe(h));
  if (route.hash) document.getElementById(route.hash.slice(1))?.scrollIntoView();
}
function loginRequired() {
  if (auth.authenticated) return false;
  router.push({ path: '/login.html', query: { next: route.fullPath } });
  return true;
}
function focusComment(id = 0) {
  if (loginRequired()) return;
  parent.value = id;
  input.value?.focus();
  document.getElementById('comments')?.scrollIntoView({ behavior: 'smooth' });
}
async function action(kind) {
  if (loginRequired() || busy.value) return;
  let payload;
  if (kind === 'report') {
    const reason = prompt('请简要说明举报原因');
    if (!reason) return;
    payload = { reason };
  }
  busy.value = true;
  try {
    await request(`/forum/posts/${route.query.id}/${kind}`, { method: 'POST', body: payload });
    if (kind === 'report') notify('已提交举报，管理员会进行核查。');
    else await load();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function deletePost() {
  if (loginRequired() || busy.value) return;
  if (!confirm('确定删除这篇帖子吗？删除后会从论坛中移除。')) return;
  busy.value = true;
  try {
    await request(`/forum/posts/${route.query.id}`, { method: 'DELETE' });
    notify('帖子已删除');
    await router.push('/index.html');
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function comment() {
  if (loginRequired() || busy.value) return;
  busy.value = true;
  try {
    await request(`/forum/posts/${route.query.id}/comments`, {
      method: 'POST',
      body: { body: body.value, parent_id: parent.value },
    });
    body.value = '';
    parent.value = 0;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
watch(
  () => route.query.id,
  () => {
    post.value = null;
    error.value = '';
    body.value = '';
    parent.value = 0;
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => observer?.disconnect());
</script>
<template>
  <main class="forum-post-layout">
    <RouterLink class="forum-back-link" to="/index.html">← 返回论坛</RouterLink>
    <div v-if="error" class="forum-empty">
      <h2>话题暂时无法打开</h2>
      <p>{{ error }}</p>
    </div>
    <div v-else-if="!post" class="forum-loading">正在加载话题…</div>
    <div v-else class="forum-post-columns">
      <article class="forum-post-detail">
        <article class="forum-article">
          <header class="forum-article-header">
            <div class="forum-post-meta">
              <span class="forum-category-pill">{{ post.category_name }}</span
              ><span v-if="post.is_pinned" class="forum-pinned">置顶</span
              ><time>{{ date(post.created_at) }}</time>
            </div>
            <h1>{{ post.title }}</h1>
            <div class="forum-article-byline">
              <img
                class="forum-avatar small"
                :src="avatar(post.author_avatar_url)"
                alt="作者头像"
              /><b>{{ post.author_name }}</b>
              <span>· {{ date(post.created_at) }}</span>
              <span>· {{ post.views_count }} 阅读</span>
            </div>
          </header>
          <PostCover
            :src="post.cover_url"
            :alt="`${post.title}的封面`"
            eager
            zoom
            class="forum-article-cover"
          />
          <div
            ref="article"
            class="forum-article-body forum-markdown"
            v-forum-math
            @click="viewImage"
            @keydown="viewImage"
            v-html="markdown(post.body)"
          ></div>
          <div class="forum-detail-actions">
            <button
              class="btn"
              :class="{ 'is-active': post.viewer_liked }"
              :disabled="busy"
              @click="action('like')"
            >
              {{ post.viewer_liked ? '♥' : '♡' }} {{ post.likes_count }} 赞</button
            ><button class="btn" :disabled="busy" @click="action('bookmark')">
              {{ post.viewer_bookmarked ? '★ 已收藏' : '☆ 收藏' }}</button
            ><button class="btn" :disabled="busy" @click="action('report')">举报</button
            ><button
              v-if="post.viewer_is_author"
              class="btn forum-delete-post"
              :disabled="busy"
              @click="deletePost"
            >
              删除帖子</button
            ><span>◉ {{ post.views_count }} 阅读</span>
          </div>
        </article>
        <section id="comments" class="forum-comments">
          <div class="forum-comments-heading">
            <h2>讨论区</h2>
            <span>{{ post.comments?.length || 0 }} 条评论</span>
          </div>
          <form class="forum-comment-form" @submit.prevent="comment">
            <textarea
              ref="input"
              v-model="body"
              rows="3"
              maxlength="5000"
              required
              placeholder="写下你的问题、想法或补充…"
            ></textarea>
            <div class="forum-comment-form-bottom">
              <button v-if="parent" type="button" class="btn" @click="parent = 0">
                正在回复评论 · 取消回复</button
              ><button class="btn primary" :disabled="busy">发布评论</button>
            </div>
          </form>
          <div v-if="!roots.length" class="forum-empty">还没有评论，来开启第一轮讨论吧。</div>
          <article v-for="item in roots" :key="item.id" class="forum-comment">
            <div class="forum-post-author">
              <img
                class="forum-avatar small"
                :src="avatar(item.author_avatar_url)"
                alt="评论者头像"
              /><b>{{ item.author_name }}</b
              ><time>{{ date(item.created_at) }}</time>
            </div>
            <p class="plain-comment">{{ item.body }}</p>
            <button class="forum-reply-button" @click="focusComment(item.id)">回复</button>
            <div
              v-for="reply in post.comments.filter((r) => Number(r.parent_id) === Number(item.id))"
              :key="reply.id"
              class="forum-comment-reply"
            >
              <div class="forum-post-author">
                <img
                  class="forum-avatar small"
                  :src="avatar(reply.author_avatar_url)"
                  alt="回复者头像"
                /><b>{{ reply.author_name }}</b
                ><time>{{ date(reply.created_at) }}</time>
              </div>
              <p class="plain-comment">{{ reply.body }}</p>
            </div>
          </article>
        </section>
      </article>
      <aside class="forum-detail-rail">
        <section class="forum-rail-card forum-toc-card">
          <div class="forum-side-title">文章目录</div>
          <nav class="forum-toc" aria-label="文章目录">
            <ol v-if="toc.length">
              <li
                v-for="heading in toc"
                :key="heading.id"
                :class="`forum-toc-level-${heading.level}`"
              >
                <a :href="`#${heading.id}`" :class="{ active: activeHeading === heading.id }">{{
                  heading.text
                }}</a>
              </li>
            </ol>
            <p v-else class="muted">这篇文章还没有分级标题。</p>
          </nav>
        </section>
        <section class="forum-rail-card">
          <div class="forum-side-title">参与讨论</div>
          <p class="muted">友善交流，补充清晰的问题背景与思路。</p>
          <button class="btn primary forum-write" @click="focusComment()">写下你的想法</button>
        </section>
        <RouterLink class="forum-rank-link" to="/leaderboard.html">♛　查看社区刷题榜</RouterLink>
      </aside>
    </div>
    <ImageLightbox ref="imageViewer" />
  </main>
</template>
