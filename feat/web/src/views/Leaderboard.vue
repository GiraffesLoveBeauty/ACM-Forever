<script setup>
import { ref, reactive, watch, onMounted } from 'vue';
import { useRequests, avatar, showError, notify } from '../lib/api.js';
import CommunityArt from '../components/CommunityArt.vue';
const request = useRequests(),
  rows = ref([]),
  total = ref(0),
  page = ref(1),
  loading = ref(false),
  search = ref('');
const platforms = {
  codeforces: 'Codeforces',
  luogu: '洛谷',
  nowcoder: '牛客',
  atcoder: 'AtCoder',
  cjlu: '校 OJ',
};
const filters = reactive({
  days: '7',
  sort: 'total_count',
  search: '',
  page_size: 20,
  platforms: Object.keys(platforms),
});
async function load(reset = false) {
  if (reset) page.value = 1;
  loading.value = true;
  try {
    const data = await request(
      '/community/leaderboard?' +
        new URLSearchParams({
          ...filters,
          platforms: filters.platforms.join(','),
          page: page.value,
        }),
      {},
      'rank',
    );
    rows.value = data.rows;
    total.value = data.total;
    page.value = data.page;
    loading.value = false;
  } catch (e) {
    if (e.name !== 'AbortError') {
      loading.value = false;
      showError(e);
    }
  }
}
function platformToggle(value) {
  if (filters.platforms.includes(value)) {
    if (filters.platforms.length === 1) {
      notify('至少选择一个平台');
      return;
    }
    filters.platforms = filters.platforms.filter((p) => p !== value);
  } else filters.platforms.push(value);
}
watch(filters, () => load(true));
onMounted(() => load());
</script>
<template>
  <main class="community-main leaderboard-main">
    <section class="community-page-heading leaderboard-heading">
      <div>
        <h1>社区排行榜</h1>
        <p>各平台去重 AC 题数，仅展示公开昵称与统计。</p>
      </div>
      <CommunityArt />
    </section>
    <section class="community-panel leaderboard-panel">
      <div class="leaderboard-toolbar">
        <form class="rank-search" @submit.prevent="filters.search = search.trim()">
          <span>⌕</span
          ><input v-model="search" type="search" placeholder="按公开昵称或身份搜索" /><button>
            查找
          </button>
        </form>
        <div class="rank-selects">
          <label
            >统计区间<select v-model="filters.days">
              <option
                v-for="(label, value) in {
                  7: '近 7 日',
                  30: '近 30 日',
                  90: '近 90 日',
                  365: '近 1 年',
                  all: '生涯',
                }"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select></label
          ><label
            >排序方式<select v-model="filters.sort">
              <option value="total_count">总 AC 数</option>
              <option
                v-for="(label, key) in {
                  cf: 'Codeforces',
                  luogu: '洛谷',
                  nowcoder: '牛客',
                  atcoder: 'AtCoder',
                  cjlu: '校 OJ',
                }"
                :key="key"
                :value="`${key}_count`"
              >
                {{ label }}
              </option>
            </select></label
          ><label
            >每页显示<select v-model="filters.page_size">
              <option v-for="size in [10, 20, 50, 100]" :key="size" :value="size">
                {{ size }} 人
              </option>
            </select></label
          >
        </div>
        <div class="rank-platforms">
          <div class="rank-platforms-label">计入总 AC 的平台</div>
          <div class="oj-filters">
            <label v-for="(label, key) in platforms" :key="key" class="oj-filter"
              ><input
                type="checkbox"
                :checked="filters.platforms.includes(key)"
                @change="platformToggle(key)"
              /><span>{{ label }}</span></label
            >
          </div>
        </div>
      </div>
      <div class="leaderboard-summary">
        <b>{{ loading ? '正在加载排行榜…' : `共 ${total} 名成员` }}</b
        ><span class="muted">按平台去重统计</span>
      </div>
      <div class="community-table-wrap" :aria-busy="loading">
        <table class="community-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>成员</th>
              <th v-for="label in platforms" :key="label">{{ label }}</th>
              <th>总题数</th>
              <th>身份</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(user, i) in rows" :key="`${page}-${i}`">
              <td>
                <span class="rank-number" :class="page === 1 && i < 3 ? `rank-top-${i + 1}` : ''">{{
                  (page - 1) * filters.page_size + i + 1
                }}</span>
              </td>
              <td>
                <span class="rank-member-cell"
                  ><img class="rank-avatar" :src="avatar(user.avatar_url)" alt="成员头像" /><b
                    class="rank-member-name"
                    >{{ user.name }}</b
                  ></span
                >
              </td>
              <td v-for="key in ['cf', 'luogu', 'nowcoder', 'atcoder', 'cjlu']" :key="key">
                {{ user[`${key}_count`] || 0 }}
              </td>
              <td>
                <b class="rank-total">{{ user.total_count || 0 }}</b>
              </td>
              <td>{{ user.status || '—' }}</td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="9" class="empty">{{ loading ? '正在加载…' : '暂无符合条件的成员' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="leaderboard-pagination">
        <button
          class="btn"
          :disabled="loading || page <= 1"
          @click="
            page--;
            load();
          "
        >
          ← 上一页</button
        ><span>第 {{ page }} / {{ Math.max(1, Math.ceil(total / filters.page_size)) }} 页</span
        ><button
          class="btn"
          :disabled="loading || page * filters.page_size >= total"
          @click="
            page++;
            load();
          "
        >
          下一页 →
        </button>
      </div>
    </section>
    <p class="leaderboard-footnote">排行榜根据已同步的 OJ 通过记录统计；题数按平台与题号去重。</p>
  </main>
</template>
