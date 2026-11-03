<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, auth, useRequests } from '../lib/api.js';
import { createWikiNavigationLoader, peekWikiNavigation } from '../lib/wiki-navigation.js';
import { downloadMarkdown } from '../lib/wiki.js';
import { markdown } from '../lib/markdown.js';
import WikiCategoryNav from '../components/WikiCategoryNav.vue';
import MarkdownView from '../components/MarkdownView.vue';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  router = useRouter(),
  request = useRequests();
const navigationLoader = createWikiNavigationLoader(request);
const nav = ref(peekWikiNavigation()),
  navigationBusy = ref(false),
  navigationError = ref(''),
  renderedContentKey = ref(''),
  detail = ref(),
  article = ref(),
  results = ref(),
  error = ref(''),
  busy = ref(false),
  search = ref(''),
  drawer = ref(),
  tocOpen = ref(false),
  headings = ref([]),
  active = ref(''),
  histories = ref([]),
  showHistory = ref(false),
  downloadError = ref(''),
  topics = ref(),
  suggestions = ref(),
  searchOpen = ref(false),
  searchBusy = ref(false),
  searchError = ref('');
const tops = computed(() => nav.value?.categories.filter((c) => c.parent_id == null) || []);
const activeTop = computed(() => article.value?.path[0]?.id || detail.value?.path[0]?.id || null);
const queryText = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''));
const canManage = computed(() => auth.authenticated && ['admin', 'root'].includes(auth.role));
const isTop = computed(
  () =>
    detail.value?.category.parent_id == null &&
    !!detail.value &&
    !article.value &&
    !queryText.value,
);
const articleTab = computed(() => (route.query.tab === 'practice' ? 'practice' : 'read'));
let revision = 0,
  timer,
  suggestionRevision = 0,
  downloadController,
  contentController,
  navigationRevision = 0,
  disposed = false;
function closeSearch() {
  clearTimeout(timer);
  suggestionRevision++;
  searchOpen.value = false;
  searchBusy.value = false;
}
function go(query = {}) {
  if (drawer.value?.open) drawer.value.close();
  closeSearch();
  router.push({ path: '/wiki.html', query });
}
function find() {
  clearTimeout(timer);
  const q = search.value.trim(),
    current = ++suggestionRevision;
  suggestions.value = undefined;
  searchError.value = '';
  searchOpen.value = !!q;
  searchBusy.value = !!q;
  if (!q) return;
  timer = setTimeout(async () => {
    try {
      const data = await request(
        '/wiki/search?' + new URLSearchParams({ q, page_size: 6 }),
        {},
        'wiki-suggestions',
      );
      if (current === suggestionRevision) suggestions.value = data;
    } catch (e) {
      if (current === suggestionRevision && e.name !== 'AbortError') searchError.value = e.message;
    } finally {
      if (current === suggestionRevision) searchBusy.value = false;
    }
  }, 250);
}
function searchKeys(event) {
  if (event.isComposing || event.keyCode === 229) return;
  if (event.key === 'Escape') closeSearch();
  if (!searchOpen.value) return;
  const links = [...event.currentTarget.querySelectorAll('.wiki-search-results a')];
  if (['ArrowDown', 'ArrowUp'].includes(event.key) && links.length) {
    event.preventDefault();
    const index = links.indexOf(document.activeElement);
    const next =
      event.key === 'ArrowDown'
        ? (index + 1) % links.length
        : index <= 0
          ? links.length - 1
          : index - 1;
    links[next].focus();
  }
  if (
    event.key === 'Enter' &&
    event.target.tagName === 'INPUT' &&
    suggestions.value?.items.length &&
    !searchBusy.value
  ) {
    event.preventDefault();
    go({ slug: suggestions.value.items[0].slug });
  }
}
function searchBlur(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) closeSearch();
}
const contentKey = computed(() =>
  JSON.stringify([
    route.query.category,
    route.query.slug,
    queryText.value,
    route.query.page,
    route.query.revision,
  ]),
);
const staleContent = computed(
  () =>
    !!(article.value || detail.value || results.value) &&
    renderedContentKey.value !== contentKey.value,
);
async function ensureNavigation(force = false) {
  const current = ++navigationRevision;
  navigationBusy.value = !peekWikiNavigation() || force;
  navigationError.value = '';
  try {
    let data;
    try {
      data = await navigationLoader.load(force);
    } catch (e) {
      if (e.codeName !== 'wiki_navigation_invalidated' || disposed) throw e;
      data = await navigationLoader.load(true);
    }
    if (!disposed && current === navigationRevision) nav.value = data;
    return data;
  } catch (e) {
    if (!disposed && current === navigationRevision && e.name !== 'AbortError')
      navigationError.value = e.message;
    throw e;
  } finally {
    if (!disposed && current === navigationRevision) navigationBusy.value = false;
  }
}
function refreshNavigationIfStale() {
  if (!document.hidden && !peekWikiNavigation() && !navigationBusy.value)
    ensureNavigation().catch(() => {});
}
function retryNavigation() {
  if (route.query.slug || queryText.value) ensureNavigation(true).catch(() => {});
  else load(true);
}
function categoryDetail(navigation, id) {
  const category = navigation.categories.find((c) => String(c.id) === String(id));
  if (!category) return null;
  const parent = navigation.categories.find((c) => c.id === category.parent_id);
  return {
    category,
    path: category.parent_id == null ? [category] : [parent, category].filter(Boolean),
    children: navigation.categories.filter((c) => c.parent_id === category.id),
  };
}
async function load(forceNavigation = false) {
  const current = ++revision;
  const targetKey = contentKey.value;
  const target = { ...route.query, q: queryText.value };
  downloadController?.abort();
  contentController?.abort();
  const controller = new AbortController();
  contentController = controller;
  busy.value = true;
  error.value = '';
  downloadError.value = '';
  histories.value = [];
  showHistory.value = false;
  tocOpen.value = false;
  closeSearch();
  search.value = target.q;
  // Start navigation independently. A directory failure must never block an article/search.
  const navigationPromise = ensureNavigation(forceNavigation === true);
  navigationPromise.catch(() => {});
  const content = (path) => api(path, { signal: controller.signal });
  try {
    let nextArticle = null,
      nextDetail = null,
      nextResults = null;
    if (target.slug) {
      const slug = encodeURIComponent(String(target.slug));
      const suffix = /^\d+$/.test(String(target.revision || ''))
        ? '/revisions/' + target.revision
        : '';
      nextArticle = await content('/wiki/pages/' + slug + suffix);
    } else if (target.q) {
      nextResults = await content(
        '/wiki/search?' +
          new URLSearchParams({
            q: target.q,
            page: target.page || 1,
          }),
      );
    } else {
      let navigation = await navigationPromise;
      if (current !== revision) return;
      const id =
        target.category ||
        navigation.default_category_id ||
        navigation.categories.find((c) => c.parent_id == null)?.id;
      if (id) {
        nextDetail = categoryDetail(navigation, id);
        if (!nextDetail) {
          navigation = await ensureNavigation(true);
          if (current !== revision) return;
          nextDetail = categoryDetail(navigation, id);
        }
        if (!nextDetail) throw Object.assign(Error('分类不存在或已调整。'), { status: 404 });
        nextResults = await content(
          '/wiki/pages?' +
            new URLSearchParams({
              category_id: id,
              page: nextDetail.category.parent_id == null ? 1 : target.page || 1,
              page_size: nextDetail.category.parent_id == null ? 3 : 20,
            }),
        );
      }
    }
    if (current !== revision) return;
    if (article.value?.body !== nextArticle?.body) headings.value = [];
    article.value = nextArticle;
    detail.value = nextDetail;
    results.value = nextResults;
    renderedContentKey.value = targetKey;
    document.title = `${nextArticle?.title || nextDetail?.category.name || 'Wiki'} · ACM Forever`;
  } catch (e) {
    if (current === revision && e.name !== 'AbortError') {
      error.value =
        e.status === 404 ? '内容或分类不存在、已调整或尚未公开，请重新选择分类。' : e.message;
      if (e.status === 404) {
        article.value = detail.value = results.value = null;
        headings.value = [];
        renderedContentKey.value = '';
        document.title = 'Wiki · ACM Forever';
      }
    }
  } finally {
    if (current === revision) busy.value = false;
  }
}
async function history() {
  const current = revision;
  try {
    const data = await request(
      '/wiki/pages/' + encodeURIComponent(article.value.slug) + '/revisions',
      {},
      'wiki-history',
    );
    if (current !== revision) return;
    histories.value = data;
    showHistory.value = !showHistory.value;
  } catch (e) {
    if (current === revision && e.name !== 'AbortError') downloadError.value = e.message;
  }
}
async function download() {
  const current = revision;
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
    if (current === revision) downloadError.value = '';
  } catch (e) {
    if (current === revision && e.name !== 'AbortError') downloadError.value = e.message;
  }
}
function excerpt(item) {
  if (item.summary) return item.summary;
  const node = document.createElement('div');
  node.innerHTML = markdown(item.excerpt || '');
  return node.textContent.replace(/\s+/g, ' ').trim();
}
function explore() {
  topics.value?.scrollIntoView({
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    block: 'start',
  });
  topics.value?.focus({ preventScroll: true });
}
watch(
  [
    () => route.query.category,
    () => route.query.slug,
    () => route.query.q,
    () => route.query.page,
    () => route.query.revision,
  ],
  load,
  { immediate: true },
);
watch(() => route.fullPath, closeSearch);
onMounted(() => {
  window.addEventListener('focus', refreshNavigationIfStale);
  document.addEventListener('visibilitychange', refreshNavigationIfStale);
});
onBeforeUnmount(() => {
  disposed = true;
  navigationRevision++;
  navigationLoader.dispose();
  contentController?.abort();
  window.removeEventListener('focus', refreshNavigationIfStale);
  document.removeEventListener('visibilitychange', refreshNavigationIfStale);
  revision++;
  closeSearch();
  downloadController?.abort();
});
</script>
<template>
  <main class="wiki-shell community-main">
    <div class="wiki-utility">
      <span class="wiki-kicker">WIKI / KNOWLEDGE BASE</span>
      <form
        class="wiki-search"
        role="search"
        @submit.prevent="go(search.trim() ? { q: search.trim() } : {})"
        @keydown="searchKeys"
        @focusout="searchBlur"
      >
        <label class="wiki-search-box"
          ><svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            aria-hidden="true"
          >
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="m16 16 5 5" />
          </svg>
          <span class="sr-only">搜索知识</span
          ><input
            id="wiki-search"
            v-model="search"
            type="search"
            maxlength="100"
            autocomplete="off"
            placeholder="搜索条目、算法或别名"
            :aria-expanded="searchOpen"
            aria-controls="wiki-search-results"
            @input="find"
            @focus="search.trim() && find()"
          />
        </label>
        <button class="btn" type="submit">搜索</button>
        <div
          v-if="searchOpen"
          id="wiki-search-results"
          class="wiki-search-results"
          aria-label="搜索建议"
        >
          <p v-if="searchBusy" role="status">正在搜索…</p>
          <p v-else-if="searchError" role="alert">{{ searchError }}</p>
          <template v-else-if="suggestions">
            <RouterLink
              v-for="item in suggestions.items"
              :key="item.slug"
              :to="{ path: '/wiki.html', query: { slug: item.slug } }"
              ><strong>{{ item.title }}</strong
              ><small>{{ item.parent_name }} / {{ item.category_name }}</small></RouterLink
            >
            <p v-if="!suggestions.items.length">没有匹配条目，试试算法名称或别名。</p>
            <button v-if="suggestions.total" type="submit" class="wiki-search-all">
              查看全部 {{ suggestions.total }} 个结果 →
            </button>
          </template>
        </div>
      </form>
      <RouterLink
        v-if="canManage"
        class="btn wiki-manage-link"
        to="/admin.html?section=wiki&tab=categories"
        >管理 Wiki</RouterLink
      >
    </div>
    <button
      type="button"
      class="btn wiki-drawer-toggle"
      aria-haspopup="dialog"
      aria-controls="wiki-nav-drawer"
      @click="drawer.showModal()"
    >
      ☰ 大类导航
    </button>
    <dialog id="wiki-nav-drawer" ref="drawer" class="wiki-nav-dialog" @click.self="drawer.close()">
      <div class="wiki-dialog-heading">
        <strong>知识分类</strong
        ><button type="button" class="btn" autofocus @click="drawer.close()">关闭导航</button>
      </div>
      <WikiCategoryNav
        :categories="nav?.categories || []"
        :active-id="activeTop"
        :busy="navigationBusy"
        :error="navigationError"
        @retry="retryNavigation"
        @select="go({ category: $event })"
      />
    </dialog>
    <div class="wiki-layout" :class="{ 'with-article': article }">
      <WikiCategoryNav
        :categories="nav?.categories || []"
        :active-id="activeTop"
        :busy="navigationBusy"
        :error="navigationError"
        @retry="retryNavigation"
        @select="go({ category: $event })"
      />
      <section class="wiki-content" :aria-busy="busy">
        <p v-if="busy" role="status">正在加载 Wiki…</p>
        <p v-if="staleContent" class="muted" role="status">
          {{
            busy
              ? '正在加载当前地址，下面暂时显示上次内容。'
              : '当前地址尚未加载成功，下面为上次成功内容。'
          }}
        </p>
        <div v-if="error" class="card wiki-feedback" role="alert">
          <p>{{ error }}</p>
          <div class="chips">
            <button class="btn" @click="load">重试</button
            ><button class="btn" @click="go()">返回 Wiki</button>
          </div>
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
              ><span>/</span><span aria-current="page">{{ article.title }}</span></template
            >
          </nav>
          <div v-if="article" class="wiki-reader-layout" :inert="staleContent || undefined">
            <div class="wiki-reader-main">
              <header class="wiki-article-heading">
                <span class="wiki-kicker"
                  >{{ article.path[1]?.name
                  }}<template v-if="article.aliases?.length">
                    / {{ article.aliases[0] }}</template
                  ></span
                >
                <h1>{{ article.title }}</h1>
                <p class="wiki-article-summary">{{ article.summary }}</p>
                <p class="wiki-meta">
                  已发布<template v-if="route.query.revision"> · 历史版本</template
                  ><span>维护者 {{ article.maintainer }}</span
                  ><span>{{
                    new Date(article.published_at * 1000).toLocaleDateString('zh-CN')
                  }}</span>
                </p>
                <div class="chips wiki-reader-tools">
                  <button class="btn" @click="download">下载 MD</button
                  ><button class="btn" :aria-expanded="showHistory" @click="history">
                    公开版本历史</button
                  ><button
                    class="btn wiki-toc-toggle"
                    :aria-expanded="tocOpen"
                    aria-controls="wiki-article-toc"
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
                <ul v-if="showHistory" class="wiki-public-history">
                  <li v-for="r in histories" :key="r.id">
                    <RouterLink
                      :to="{ path: '/wiki.html', query: { slug: article.slug, revision: r.id } }"
                      >{{ r.title }} ·
                      {{ new Date(r.published_at * 1000).toLocaleString('zh-CN') }}</RouterLink
                    >
                  </li>
                  <li v-if="!histories.length">暂无可查看的公开版本。</li>
                </ul>
              </header>
              <nav class="wiki-reading-tabs" aria-label="文章内容">
                <RouterLink
                  :class="{ active: articleTab === 'read' }"
                  :aria-current="articleTab === 'read' ? 'page' : undefined"
                  :to="{ path: '/wiki.html', query: { ...route.query, tab: undefined } }"
                  >阅读讲解</RouterLink
                ><RouterLink
                  :class="{ active: articleTab === 'practice' }"
                  :aria-current="articleTab === 'practice' ? 'page' : undefined"
                  :to="{ path: '/wiki.html', query: { ...route.query, tab: 'practice' } }"
                  >关联练习<span v-if="article.exercises.length">
                    {{ article.exercises.length }}</span
                  ></RouterLink
                >
              </nav>
              <div v-show="articleTab === 'read'">
                <MarkdownView
                  :key="article.id"
                  :source="article.body"
                  @toc="headings = $event"
                  @active="active = $event"
                />
              </div>
              <section v-if="articleTab === 'practice'" class="wiki-practice">
                <h2>关联练习</h2>
                <a
                  v-for="e in article.exercises"
                  :key="e.url"
                  class="wiki-practice-link"
                  :href="e.url"
                  :target="e.url.startsWith('/') ? undefined : '_blank'"
                  rel="noopener noreferrer"
                  ><span>{{ e.label }}</span
                  ><span aria-hidden="true">↗</span></a
                >
                <div v-if="!article.exercises.length" class="wiki-empty">
                  <strong>暂无关联练习</strong>
                  <p>此条目可先阅读讲解，练习资源由维护者逐步补充。</p>
                </div>
              </section>
              <footer class="wiki-source">
                <p v-if="article.source">来源：{{ article.source }}</p>
                <p v-if="article.license">许可：{{ article.license }}</p>
                <RouterLink :to="{ path: '/wiki.html', query: { category: article.path[1]?.id } }"
                  >返回{{ article.path[1]?.name }}</RouterLink
                >
              </footer>
            </div>
            <aside
              id="wiki-article-toc"
              class="wiki-toc"
              :class="{ open: tocOpen }"
              aria-label="文章目录"
            >
              <h2>本页内容</h2>
              <template v-if="articleTab === 'read'"
                ><RouterLink
                  v-for="heading in headings"
                  :key="heading.id"
                  :class="{ active: active === heading.id, nested: heading.level > 2 }"
                  :aria-current="active === heading.id ? 'location' : undefined"
                  :to="{ path: '/wiki.html', query: route.query, hash: '#' + heading.id }"
                  >{{ heading.title }}</RouterLink
                >
                <p v-if="!headings.length" class="muted">本文暂无章节目录</p></template
              >
              <p v-else>关联练习</p>
              <div class="wiki-reading-info">
                <h2>当前分类</h2>
                <RouterLink
                  v-for="c in article.path"
                  :key="c.id"
                  :to="{ path: '/wiki.html', query: { category: c.id } }"
                  >{{ c.name }}</RouterLink
                ><template v-if="article.tags.length"
                  ><h2>条目标签</h2>
                  <p>{{ article.tags.join(' · ') }}</p></template
                >
              </div>
            </aside>
          </div>
          <template v-else-if="queryText"
            ><div class="wiki-page-heading">
              <span class="wiki-kicker">WIKI / SEARCH</span>
              <h1>搜索“{{ queryText }}”</h1>
              <p class="muted">找到 {{ results?.total || 0 }} 篇已发布文章</p>
            </div></template
          >
          <template v-else-if="detail">
            <template v-if="isTop"
              ><section class="wiki-hero">
                <span class="wiki-kicker">ACM FOREVER / {{ detail.category.name }}</span>
                <h1>把想明白的事，<br />写成找得到的知识。</h1>
                <p>{{ detail.category.description || '按小类查阅条目，把知识用到实践中。' }}</p>
                <div class="chips">
                  <RouterLink
                    v-if="results?.items.length"
                    class="btn primary"
                    :to="{ path: '/wiki.html', query: { slug: results.items[0].slug } }"
                    >开始阅读 →</RouterLink
                  ><button class="btn" @click="explore">探索小类</button>
                </div>
                <div class="wiki-hero-foot">
                  <span>{{ detail.children.map((c) => c.name).join(' / ') || '等待添加小类' }}</span
                  ><span>查得到 · 读得懂 · 用得上</span>
                </div>
              </section>
              <section ref="topics" class="wiki-topics" tabindex="-1">
                <div class="wiki-section-heading">
                  <h2>按小类探索</h2>
                  <small>{{ detail.category.name }} · {{ detail.children.length }} 个小类</small>
                </div>
                <div class="wiki-cards">
                  <RouterLink
                    v-for="(child, index) in detail.children"
                    :key="child.id"
                    class="wiki-subcategory"
                    :to="{ path: '/wiki.html', query: { category: child.id } }"
                    ><span class="wiki-topic-index">{{ String(index + 1).padStart(2, '0') }}</span
                    ><span
                      ><strong>{{ child.name }}</strong
                      ><small>{{ child.description || '查看此小类下的文章' }}</small></span
                    ><small class="wiki-topic-count"
                      >{{ child.published_count }} 篇</small
                    ></RouterLink
                  >
                </div>
                <div v-if="!detail.children.length" class="wiki-empty">
                  <strong>还没有小类</strong>
                  <p>这里会展示此大类下的知识分类。</p>
                </div>
              </section>
              <section class="wiki-start-reading">
                <div class="wiki-section-heading">
                  <h2>开始阅读</h2>
                  <small>{{ detail.category.name }}中的近期更新</small>
                </div>
                <div class="wiki-article-list">
                  <RouterLink
                    v-for="item in results?.items || []"
                    :key="item.slug"
                    class="wiki-reading-row"
                    :to="{ path: '/wiki.html', query: { slug: item.slug } }"
                    ><span
                      ><strong>{{ item.title }}</strong
                      ><small>{{ excerpt(item) }}</small
                      ><small>{{ item.parent_name }} / {{ item.category_name }}</small></span
                    ><span aria-hidden="true">↗</span></RouterLink
                  >
                  <p v-if="!results?.items.length" class="wiki-empty">
                    知识内容正在整理，稍后再来看看。
                  </p>
                </div>
              </section>
            </template>
            <div v-else class="wiki-page-heading">
              <span class="wiki-kicker">{{ detail.path[0]?.name }} / 小类</span>
              <h1>{{ detail.category.name }}</h1>
              <p>{{ detail.category.description || '此小类下的全部知识条目。' }}</p>
              <small class="muted">{{ results?.total || 0 }} 篇文章</small>
            </div>
          </template>
          <template v-if="results && !article && !isTop"
            ><div class="wiki-article-list">
              <RouterLink
                v-for="item in results.items"
                :key="item.slug"
                class="wiki-article-card wiki-reading-row"
                :to="{ path: '/wiki.html', query: { slug: item.slug } }"
                ><span
                  ><strong>{{ item.title }}</strong
                  ><small>{{ excerpt(item) }}</small
                  ><small
                    >{{ item.parent_name }} / {{ item.category_name }} ·
                    {{ item.tags.join(' · ') }} ·
                    {{ new Date(item.updated_at * 1000).toLocaleDateString('zh-CN') }}</small
                  ></span
                ><span aria-hidden="true">↗</span></RouterLink
              >
              <p v-if="!results.items.length" class="wiki-empty">
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
              @change="go({ ...route.query, page: $event })"
          /></template>
          <div v-if="nav && !tops.length && !article && !queryText" class="wiki-empty">
            <h2>Wiki 正在建设中</h2>
            <p>知识内容正在整理，请稍后再来。</p>
          </div>
        </template>
      </section>
    </div>
    <footer class="wiki-site-footer">
      <span>ACM FOREVER / WIKI</span><span>分类清晰，知识可达。</span>
    </footer>
  </main>
</template>
