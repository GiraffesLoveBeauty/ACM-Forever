<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router';
import { forumState, forumQuery } from '../lib/forum-state.js';
import { useRequests, showError } from '../lib/api.js';
import GraphArt from '../components/GraphArt.vue';
import PostCard from '../components/PostCard.vue';
import Pager from '../components/Pager.vue';
const viewModeKey = 'acm.forum.view.v1';
function savedViewMode() {
  try {
    return localStorage.getItem(viewModeKey) === 'grid' ? 'grid' : 'list';
  } catch {
    return 'list';
  }
}
const request = useRequests(),
  categories = ref([]),
  posts = ref([]),
  hot = ref([]),
  total = ref(0),
  loading = ref(false),
  error = ref(''),
  query = ref(''),
  savedView = ref(savedViewMode());
const route = useRoute(),
  router = useRouter();
const filters = computed(() => forumState(route.query, savedView.value));
const page = computed(() => filters.value.page);
const viewMode = computed(() => filters.value.view);
const listAddress = computed(
  () => route.path + '?' + new URLSearchParams(forumQuery(filters.value)),
);
function navigate(changes, replace = false) {
  return router[replace ? 'replace' : 'push']({
    path: route.path,
    query: forumQuery({ ...filters.value, ...changes }),
  });
}
function changeViewMode(mode) {
  savedView.value = mode;
  try {
    localStorage.setItem(viewModeKey, mode);
  } catch {
    // The current page can still switch views when browser storage is unavailable.
  }
  navigate({ view: mode });
}
const directory = computed(() => [
  {
    slug: '',
    name: '全部话题',
    description: '看看社区正在讨论什么',
    post_count: categories.value.reduce((sum, c) => sum + Number(c.post_count || 0), 0),
  },
  ...categories.value,
]);
async function load() {
  loading.value = true;
  error.value = '';
  const requestedAddress = listAddress.value;
  try {
    const data = await request(
      '/forum/posts?' +
        new URLSearchParams({
          sort: filters.value.sort,
          category: filters.value.category,
          q: filters.value.q,
          page: page.value,
          page_size: 12,
        }),
      {},
      'feed',
    );
    if (page.value > Math.max(1, Math.ceil(data.total / 12))) {
      await navigate({ page: Math.max(1, Math.ceil(data.total / 12)) }, true);
      return;
    }
    posts.value = data.rows;
    total.value = data.total;
    await nextTick();
    try {
      const position = Number(sessionStorage.getItem('acm.forum.scroll:' + requestedAddress));
      if (position > 0 && listAddress.value === requestedAddress) window.scrollTo?.(0, position);
    } catch {
      /* Browsing still works when storage is disabled. */
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      error.value = e.message;
      loading.value = false;
    }
    return;
  }
  loading.value = false;
}
watch(
  () => route.fullPath,
  () => {
    query.value = filters.value.q;
    posts.value = [];
    load();
  },
  { immediate: true },
);
onBeforeRouteLeave(() => {
  try {
    sessionStorage.setItem('acm.forum.scroll:' + listAddress.value, String(window.scrollY || 0));
  } catch {}
});
onMounted(async () => {
  await Promise.allSettled([
    request('/forum/categories')
      .then((data) => {
        categories.value = data;
      })
      .catch(showError),
    request('/forum/posts?sort=hot&page_size=4')
      .then((data) => {
        hot.value = data.rows;
      })
      .catch(showError),
  ]);
});
</script>
<template>
  <a class="industrial-skip" href="#forum-feed">跳到讨论话题</a>
  <main class="forum-home-layout">
    <aside class="forum-rail forum-left-rail" aria-label="社区介绍与快捷入口">
      <div class="forum-community-card">
        <span class="community-spark">✦</span>
        <h2>让每一次思考<br />都被看见</h2>
        <p>和计量 ACMer 一起提问、讨论、进步。</p>
      </div>
      <div class="forum-side-links">
        <RouterLink to="/leaderboard.html">♛　查看刷题排行榜</RouterLink
        ><RouterLink to="/home.html">◉　进入个人中心</RouterLink>
      </div>
    </aside>
    <section class="forum-feed-column" aria-label="社区讨论">
      <div class="forum-welcome">
        <div class="industrial-hero-dots" aria-hidden="true"></div>
        <div class="industrial-hero-copy">
          <span class="forum-kicker">ACM FOREVER / 计量算法社区</span>
          <h1>拆解问题。<br />连接思路。</h1>
          <p>从卡住的那一步开始。分享题解、交流训练，和大家一起走向下一个 AC。</p>
          <RouterLink class="forum-hero-cta" to="/compose.html"
            >写一个新话题 <span>＋</span></RouterLink
          >
        </div>
        <GraphArt />
        <div class="industrial-hero-bottom" aria-hidden="true">
          <span>思考 / 编写 / 交流</span><span>s → v → d → t</span>
        </div>
      </div>
      <section class="forum-directory" aria-labelledby="directory-title">
        <div class="forum-directory-heading">
          <h2 id="directory-title">探索版块</h2>
          <span class="muted"
            >{{ categories.length }} 个版块 · {{ directory[0].post_count }} 个话题</span
          >
        </div>
        <div class="forum-directory-grid">
          <button
            v-for="c in directory"
            :key="c.slug"
            :data-category="c.slug || 'all'"
            class="forum-directory-card"
            :class="{ active: filters.category === c.slug }"
            :aria-pressed="filters.category === c.slug"
            @click="navigate({ category: c.slug, page: 1 })"
          >
            <span class="forum-directory-icon" :class="`directory-${c.slug || 'all'}`"
              ><svg
                v-if="c.slug === 'solution'"
                viewBox="0 0 24 24"
                width="20"
                height="20"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path
                  d="M12 6.5C9.6 5 6.8 4.5 3 5v13c3.8-.5 6.6 0 9 1.5 2.4-1.5 5.2-2 9-1.5V5c-3.8-.5-6.6 0-9 1.5Z"
                />
                <path d="M12 6.5v13M6 8.5l3 .6m6 0 3-.6" /></svg
              ><template v-else>{{
                { help: '?', experience: '✎', events: '↗' }[c.slug] || '✦'
              }}</template></span
            ><span class="forum-directory-copy"
              ><b>{{ c.name }}</b
              ><small>{{ c.description || '与计量 ACMer 分享想法与经验。' }}</small></span
            ><span class="forum-directory-count"
              ><strong>{{ c.post_count || 0 }}</strong
              ><small>话题</small></span
            >
          </button>
        </div>
      </section>
      <form
        class="forum-search"
        @submit.prevent="navigate({ q: query.trim().slice(0, 100), page: 1 })"
      >
        <label class="visually-hidden" for="search-query">搜索话题</label><span>⌕</span
        ><input
          id="search-query"
          v-model="query"
          type="search"
          placeholder="搜索问题、题解或学习经验"
        /><button>搜索</button>
      </form>
      <div class="forum-feed-toolbar">
        <h2 class="industrial-feed-title">讨论话题</h2>
        <div class="forum-tabs" role="group" aria-label="话题排序方式">
          <button
            v-for="(label, sort) in { latest: '最新', hot: '热门', unanswered: '等你回答' }"
            :key="sort"
            class="forum-tab"
            :class="{ active: filters.sort === sort }"
            :aria-pressed="filters.sort === sort"
            @click="navigate({ sort, page: 1 })"
          >
            {{ label }}
          </button>
        </div>
        <span class="muted">{{ total }} 个话题</span>
        <div class="forum-view-switch" role="group" aria-label="话题显示方式">
          <button
            v-for="(label, value) in { list: '列表', grid: '网格' }"
            :key="value"
            type="button"
            :class="{ active: viewMode === value }"
            :aria-pressed="viewMode === value"
            :aria-label="`${label}视图`"
            aria-controls="forum-feed"
            @click="changeViewMode(value)"
          >
            <svg
              viewBox="0 0 20 20"
              width="16"
              height="16"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <template v-if="value === 'grid'">
                <rect x="3" y="3" width="5" height="5" />
                <rect x="12" y="3" width="5" height="5" />
                <rect x="3" y="12" width="5" height="5" />
                <rect x="12" y="12" width="5" height="5" />
              </template>
              <path v-else d="M3 4h3v3H3zM9 5.5h8M3 13h3v3H3zM9 14.5h8" />
            </svg>
            {{ label }}
          </button>
        </div>
      </div>
      <div
        id="forum-feed"
        class="forum-feed"
        :data-loading="loading && posts.length ? 'true' : undefined"
        :aria-busy="loading"
        tabindex="-1"
      >
        <div
          v-if="loading"
          :class="posts.length ? 'forum-feed-refresh' : 'forum-loading'"
          role="status"
        >
          <span class="spinner"></span>正在加载社区话题…
        </div>
        <div v-if="posts.length" class="forum-feed-posts" :class="`forum-feed-posts-${viewMode}`">
          <PostCard v-for="post in posts" :key="post.id" :post="post" :return-to="listAddress" />
        </div>
        <div v-if="!loading && !posts.length" class="forum-empty">
          <h3>{{ error ? '话题加载失败' : '这里还没有话题' }}</h3>
          <p>{{ error || '来发布第一个讨论，开启社区交流吧。' }}</p>
          <button v-if="error" class="btn" @click="load">重试</button>
        </div>
      </div>
      <p v-if="error && posts.length" role="alert">
        {{ error }} <button class="btn" @click="load()">重试</button>
      </p>
      <Pager
        :page="page"
        :total="total"
        :size="12"
        :busy="loading"
        @change="navigate({ page: $event })"
      />
    </section>
    <aside class="forum-rail forum-right-rail" aria-label="热门话题与社区公约">
      <section class="forum-rail-card">
        <div class="forum-side-title">热门话题 <span>↗</span></div>
        <div class="hot-topic-list">
          <RouterLink
            v-for="(post, i) in hot"
            :key="post.id"
            :to="{ path: '/post.html', query: { id: post.id, from: listAddress } }"
            ><span>{{ String(i + 1).padStart(2, '0') }}</span
            ><b>{{ post.title }}</b
            ><small>{{ post.comments_count || 0 }} 条讨论</small></RouterLink
          >
          <p v-if="!hot.length" class="muted">还没有热门话题</p>
        </div>
      </section>
      <section class="forum-rail-card forum-community-note">
        <div class="forum-side-title">社区公约</div>
        <p>
          友善交流，清楚描述问题，分享自己的尝试。题解请注明来源，一起维护适合每位同学学习的讨论氛围。
        </p>
        <RouterLink to="/compose.html">分享你的思路 →</RouterLink>
      </section>
      <footer class="forum-footer">ACM Forever · 为计量 ACMer 的学习与交流而建</footer>
    </aside>
  </main>
</template>
