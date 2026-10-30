<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth, useRequests } from '../lib/api.js';
import { downloadMarkdown } from '../lib/wiki.js';
import MarkdownView from '../components/MarkdownView.vue';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const nav = ref(),
  detail = ref(),
  article = ref(),
  results = ref(),
  error = ref(''),
  busy = ref(false),
  search = ref(''),
  drawer = ref(false),
  tocOpen = ref(false),
  headings = ref([]),
  active = ref(''),
  histories = ref([]),
  showHistory = ref(false),
  downloadError = ref('');
const tops = computed(() => nav.value?.categories.filter((c) => c.parent_id == null) || []);
const activeTop = computed(() => article.value?.path[0]?.id || detail.value?.path[0]?.id || null);
const queryText = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''));
const canManage = computed(() => auth.authenticated && ['admin', 'root'].includes(auth.role));
let revision = 0,
  timer,
  downloadController;
function go(query = {}) {
  drawer.value = false;
  router.push({ path: '/wiki.html', query });
}
function find() {
  clearTimeout(timer);
  timer = setTimeout(() => go(search.value.trim() ? { q: search.value.trim() } : {}), 300);
}
async function load() {
  const current = ++revision;
  busy.value = true;
  error.value = '';
  headings.value = [];
  histories.value = [];
  showHistory.value = false;
  search.value = queryText.value;
  try {
    const navigation = await request('/wiki/navigation', {}, 'wiki-navigation');
    if (current !== revision) return;
    nav.value = navigation;
    let nextArticle = null,
      nextDetail = null,
      nextResults = null;
    if (route.query.slug) {
      const slug = encodeURIComponent(String(route.query.slug));
      const suffix = /^\d+$/.test(String(route.query.revision || ''))
        ? '/revisions/' + route.query.revision
        : '';
      nextArticle = await request('/wiki/pages/' + slug + suffix, {}, 'wiki-content');
    } else if (queryText.value) {
      nextResults = await request(
        '/wiki/search?' + new URLSearchParams({ q: queryText.value, page: route.query.page || 1 }),
        {},
        'wiki-content',
      );
    } else {
      const category = route.query.category || navigation.default_category_id || tops.value[0]?.id;
      if (category) {
        nextDetail = await request(
          '/wiki/categories/' + encodeURIComponent(category),
          {},
          'wiki-content',
        );
        if (nextDetail.category.parent_id != null)
          nextResults = await request(
            '/wiki/pages?' +
              new URLSearchParams({ category_id: category, page: route.query.page || 1 }),
            {},
            'wiki-list',
          );
      }
    }
    if (current !== revision) return;
    article.value = nextArticle;
    detail.value = nextDetail;
    results.value = nextResults;
    document.title = `${nextArticle?.title || nextDetail?.category.name || 'Wiki'} · ACM Forever`;
  } catch (e) {
    if (current === revision && e.name !== 'AbortError')
      error.value =
        e.status === 404 ? '内容或分类不存在、已调整或尚未公开，请重新选择分类。' : e.message;
  } finally {
    if (current === revision) busy.value = false;
  }
}
async function history() {
  try {
    histories.value = await request(
      '/wiki/pages/' + encodeURIComponent(article.value.slug) + '/revisions',
      {},
      'wiki-history',
    );
    showHistory.value = !showHistory.value;
  } catch (e) {
    downloadError.value = e.message;
  }
}
async function download() {
  try {
    downloadController?.abort();
    downloadController = new AbortController();
    const q = route.query.revision
      ? '?revision_id=' + encodeURIComponent(route.query.revision)
      : '';
    await downloadMarkdown(
      '/api/wiki/pages/' + encodeURIComponent(article.value.slug) + '/markdown' + q,
      downloadController.signal,
    );
    downloadError.value = '';
  } catch (e) {
    if (e.name !== 'AbortError') downloadError.value = e.message;
  }
}
function pages(page) {
  go({ ...route.query, page });
}
watch(
  () => [
    route.query.category,
    route.query.slug,
    route.query.q,
    route.query.page,
    route.query.revision,
  ],
  load,
  { immediate: true },
);
onBeforeUnmount(() => {
  revision++;
  clearTimeout(timer);
  downloadController?.abort();
});
</script>
<template>
  <main class="wiki-shell community-main">
    <header class="wiki-hero">
      <div>
        <span class="panel-eyebrow">ACM FOREVER / KNOWLEDGE HANDBOOK</span>
        <h1>Wiki · 知识手册</h1>
        <p>把算法、工具与实验室经验，整理成随时可查的知识。</p>
      </div>
      <RouterLink v-if="canManage" class="btn" to="/admin.html?section=wiki&tab=categories"
        >管理 Wiki</RouterLink
      >
    </header>
    <form
      class="wiki-search"
      role="search"
      @submit.prevent="go(search.trim() ? { q: search.trim() } : {})"
    >
      <label class="sr-only" for="wiki-search">搜索知识</label
      ><input
        id="wiki-search"
        v-model="search"
        maxlength="100"
        placeholder="搜索标题、DSU 等别名、标签或正文…"
        @input="find"
      /><button class="btn primary">搜索</button
      ><button
        type="button"
        class="btn wiki-drawer-toggle"
        :aria-expanded="drawer"
        @click="drawer = !drawer"
      >
        分类导航
      </button>
    </form>
    <div class="wiki-layout" :class="{ 'with-article': article }">
      <aside class="wiki-categories" :class="{ open: drawer }" aria-label="Wiki 大类导航">
        <h2>知识分类</h2>
        <button
          v-for="top in tops"
          :key="top.id"
          class="wiki-category"
          :class="{ active: activeTop === top.id }"
          @click="go({ category: top.id })"
        >
          {{ top.name }}<span>↗</span>
        </button>
        <p v-if="nav && !tops.length" class="muted">Wiki 正在建设中</p>
      </aside>
      <section class="wiki-content" :aria-busy="busy">
        <p v-if="busy" role="status">正在加载 Wiki…</p>
        <div v-if="error" class="card" role="alert">
          <p>{{ error }}</p>
          <button class="btn" @click="load">重试</button
          ><button class="btn" @click="go()">返回 Wiki</button>
        </div>
        <template v-if="!busy || article || detail || results">
          <nav class="wiki-breadcrumb" aria-label="面包屑">
            <RouterLink to="/wiki.html">Wiki</RouterLink
            ><template v-for="c in article?.path || detail?.path || []" :key="c.id"
              ><span>/</span
              ><RouterLink :to="{ path: '/wiki.html', query: { category: c.id } }">{{
                c.name
              }}</RouterLink></template
            ><template v-if="article"
              ><span>/</span><span>{{ article.title }}</span></template
            >
          </nav>
          <template v-if="article">
            <div class="wiki-article-heading">
              <span class="panel-eyebrow">KNOWLEDGE / {{ article.tags.join(' · ') }}</span>
              <h1>{{ article.title }}</h1>
              <p>{{ article.summary }}</p>
              <p class="muted">
                维护者 {{ article.maintainer }} · 更新于
                {{ new Date(article.published_at * 1000).toLocaleDateString('zh-CN')
                }}<template v-if="route.query.revision"> · 正在查看历史版本</template>
              </p>
              <div class="chips">
                <button class="btn" @click="download">下载 MD</button
                ><button class="btn" @click="history">公开版本历史</button
                ><button
                  class="btn wiki-toc-toggle"
                  :aria-expanded="tocOpen"
                  @click="tocOpen = !tocOpen"
                >
                  文章目录</button
                ><RouterLink
                  v-if="route.query.revision"
                  class="btn"
                  :to="{ path: '/wiki.html', query: { slug: article.slug } }"
                  >阅读当前版本</RouterLink
                >
              </div>
              <p v-if="downloadError" role="alert">{{ downloadError }}</p>
              <ul v-if="showHistory">
                <li v-for="r in histories" :key="r.id">
                  <RouterLink
                    :to="{ path: '/wiki.html', query: { slug: article.slug, revision: r.id } }"
                    >{{ r.title }} ·
                    {{ new Date(r.published_at * 1000).toLocaleString('zh-CN') }}</RouterLink
                  >
                </li>
              </ul>
            </div>
            <MarkdownView
              :key="article.id"
              :source="article.body"
              @toc="headings = $event"
              @active="active = $event"
            />
            <section v-if="article.exercises.length" class="card">
              <h2>关联练习</h2>
              <p v-for="e in article.exercises" :key="e.url">
                <a
                  :href="e.url"
                  :target="e.url.startsWith('/') ? undefined : '_blank'"
                  rel="noopener noreferrer"
                  >{{ e.label }} ↗</a
                >
              </p>
            </section>
            <footer class="wiki-source">
              <p v-if="article.source">来源：{{ article.source }}</p>
              <p v-if="article.license">许可：{{ article.license }}</p>
            </footer>
          </template>
          <template v-else-if="queryText"
            ><h1>搜索“{{ queryText }}”</h1>
            <p class="muted">找到 {{ results?.total || 0 }} 篇已发布文章</p></template
          >
          <template v-else-if="detail"
            ><h1>{{ detail.category.name }}</h1>
            <p>{{ detail.category.description }}</p>
            <div v-if="detail.category.parent_id == null" class="wiki-cards">
              <RouterLink
                v-for="child in detail.children"
                :key="child.id"
                class="wiki-subcategory card"
                :to="{ path: '/wiki.html', query: { category: child.id } }"
                ><span class="panel-eyebrow">SECTION</span>
                <h2>{{ child.name }} ↗</h2>
                <p>{{ child.description || '打开分类，探索更多知识。' }}</p>
                <small>{{ child.published_count }} 篇已发布文章</small></RouterLink
              >
            </div>
            <p v-if="detail.category.parent_id == null && !detail.children.length">
              该分类内容正在整理。
            </p></template
          >
          <template v-if="results && !article"
            ><div class="wiki-article-list">
              <RouterLink
                v-for="item in results.items"
                :key="item.slug"
                class="wiki-article-card"
                :to="{ path: '/wiki.html', query: { slug: item.slug } }"
                ><small>{{ item.parent_name }} / {{ item.category_name }}</small>
                <h2>{{ item.title }} <span>↗</span></h2>
                <p>{{ item.summary || item.excerpt }}</p>
                <small
                  >{{ item.tags.join(' · ') }} ·
                  {{ new Date(item.updated_at * 1000).toLocaleDateString('zh-CN') }}</small
                ></RouterLink
              >
              <p v-if="!results.items.length">
                {{
                  queryText ? '没有匹配的已发布文章，请调整关键词或浏览分类。' : '暂无已发布内容。'
                }}
              </p>
            </div>
            <Pager
              :page="Number(route.query.page) || 1"
              :total="results.total"
              :size="20"
              :busy="busy"
              @change="pages"
          /></template>
          <div v-if="nav && !tops.length && !article && !queryText" class="card">
            <h2>Wiki 正在建设中</h2>
            <p>知识内容正在整理，请稍后再来。</p>
          </div>
        </template>
      </section>
      <aside v-if="article" class="wiki-toc" :class="{ open: tocOpen }" aria-label="文章目录">
        <h2>本篇目录</h2>
        <RouterLink
          v-for="heading in headings"
          :key="heading.id"
          :class="{ active: active === heading.id, nested: heading.level > 2 }"
          :to="{ path: '/wiki.html', query: route.query, hash: '#' + heading.id }"
          >{{ heading.title }}</RouterLink
        >
      </aside>
    </div>
  </main>
</template>
