<script setup>
import { ref, reactive, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useRequests, external, showError, notify } from '../lib/api.js';
import { useParams } from '../lib/admin.js';
import Pager from '../components/Pager.vue';
const route = useRoute(),
  update = useParams(),
  request = useRequests(),
  search = ref(route.query.search || ''),
  data = ref(),
  detail = ref(),
  form = reactive({});
const fields = {
  name: '昵称',
  real_name: '真实姓名',
  school: '学校',
  status: '身份 / 年级',
  cf_handle: 'Codeforces',
  luogu_id: '洛谷',
  nowcoder_id: '牛客',
  atcoder_handle: 'AtCoder',
  cjlu_username: '校 OJ',
};
async function load() {
  detail.value = null;
  data.value = null;
  try {
    if (route.query.qq_id) {
      detail.value = await request(
        '/member/' + encodeURIComponent(route.query.qq_id),
        {},
        'members',
      );
      for (const key of Object.keys(fields)) form[key] = detail.value.user[key] || '';
    } else {
      search.value = route.query.search || '';
      data.value = await request(
        '/admin/members?' +
          new URLSearchParams({
            search: route.query.search || '',
            page: route.query.page || 1,
            page_size: 20,
          }),
        {},
        'members',
      );
    }
  } catch (e) {
    showError(e);
  }
}
async function save() {
  const bindings = ['cf_handle', 'luogu_id', 'nowcoder_id', 'atcoder_handle', 'cjlu_username'];
  const changed = bindings.filter(
    (key) =>
      String(form[key] || '')
        .trim()
        .toLowerCase() !==
      String(detail.value.user[key] || '')
        .trim()
        .toLowerCase(),
  );
  if (
    changed.length &&
    !confirm(
      '确认修改该成员的 OJ 绑定？受影响平台的 AC、提交证据与同步状态将被清理，进行中的挑战将结束；收藏与历史资料保留。\n' +
        changed
          .map(
            (key) =>
              `${fields[key]}：${detail.value.user[key] || '未绑定'} → ${form[key] || '解绑'}`,
          )
          .join('\n'),
    )
  )
    return;
  const expected_bindings = Object.fromEntries(
    bindings.map((key) => [key, detail.value.user[key] || '']),
  );
  const binding_versions = Object.fromEntries(
    ['codeforces', 'luogu', 'nowcoder', 'atcoder', 'cjlu'].map((platform) => [
      platform,
      detail.value.user[
        platform === 'codeforces' ? 'cf_binding_version' : platform + '_binding_version'
      ] || 0,
    ]),
  );
  try {
    const result = await request('/user', {
      method: 'PUT',
      body: {
        qq_id: route.query.qq_id,
        ...form,
        confirm_bindings: changed.length > 0,
        expected_bindings,
        binding_versions,
      },
    });
    notify(result.message || '成员资料已保存');
    await load();
  } catch (e) {
    showError(e);
  }
}
watch(() => route.query, load, { immediate: true });
</script>
<template>
  <template v-if="!route.query.qq_id"
    ><section class="admin-panel">
      <form class="filters" @submit.prevent="update({ search: search.trim(), page: 1 })">
        <label
          >搜索成员<input
            v-model="search"
            type="search"
            placeholder="QQ、昵称、身份、学校或 OJ 账号" /></label
        ><button class="btn primary">搜索</button>
      </form>
      <p class="muted">共 {{ data?.total || 0 }} 位成员</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>成员</th>
              <th>QQ</th>
              <th>学校 / 身份</th>
              <th>OJ 账号</th>
              <th>Web 角色</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in data?.items || []" :key="row.qq_id">
              <td>{{ row.name }}</td>
              <td>{{ row.qq_id }}</td>
              <td>{{ row.school }}<br />{{ row.status }}</td>
              <td>
                {{
                  row.cf_handle || row.luogu_id || row.atcoder_handle || row.nowcoder_id || '未绑定'
                }}
              </td>
              <td>{{ row.role || '未开通' }}</td>
              <td><button class="btn" @click="update({ qq_id: row.qq_id })">查看资料</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager
        :page="Number(data?.page || 1)"
        :total="data?.total || 0"
        @change="(page) => update({ page })"
      /></section></template
  ><template v-else
    ><button class="btn" @click="update({ qq_id: null })">← 返回成员列表</button
    ><template v-if="detail"
      ><section class="admin-panel">
        <h2>{{ detail.user.name }} · {{ route.query.qq_id }}</h2>
        <p>Web 角色：{{ detail.permissions?.role || '未开通' }}</p>
        <form @submit.prevent="save">
          <div class="admin-create-grid">
            <label v-for="(label, key) in fields" :key="key"
              >{{ label }}<input v-model="form[key]"
            /></label>
          </div>
          <p class="muted">OJ 账号变更后会清理旧账号提交证据并重新同步；历史学习资料保留存档。</p>
          <button class="btn primary">保存资料与绑定</button>
        </form>
      </section>
      <section class="admin-panel">
        <h2>平台统计</h2>
        <div class="chips">
          <span v-for="(count, platform) in detail.platform_counts" :key="platform" class="chip"
            >{{ platform }} · {{ count }} 题</span
          >
        </div>
        <p>
          CF Rating {{ detail.cf?.rating ?? '—' }} · AtCoder Rating
          {{ detail.atcoder?.rating ?? '—' }} · 挑战 Rating {{ detail.challenge_rating ?? '—' }}
        </p>
      </section>
      <section class="admin-panel">
        <h2>最近 AC 摘要</h2>
        <article v-for="(row, i) in detail.recent_ac" :key="i" class="list-item">
          <span
            ><b>{{ row.problem_name || row.problem_id }}</b
            ><br />{{ row.platform }} · {{ row.problem_rating || '未知' }}</span
          ><a
            v-if="row.problem_url"
            class="btn"
            :href="external(row.problem_url)"
            target="_blank"
            rel="noopener"
            >打开题目</a
          >
        </article>
      </section></template
    ></template
  >
</template>
