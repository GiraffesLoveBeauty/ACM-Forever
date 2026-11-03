<script setup>
import { ref, watch, onBeforeUnmount } from 'vue';
import { date, notify } from '../../lib/api.js';
const props = defineProps({
  credentials: { type: Array, default: () => [] },
  missing: { type: Number, default: 0 },
});
let revision = 0;
onBeforeUnmount(() => {
  ++revision;
  fallback.value = '';
});
const visible = ref(false),
  fallback = ref('');
watch(
  () => props.credentials,
  () => {
    ++revision;
    fallback.value = '';
    visible.value = false;
  },
);
function text() {
  return [
    'QQ\t昵称\t初始密码\t有效至',
    ...props.credentials.map((r) =>
      [r.qq_id, r.name, r.temporary_password, date(r.expires_at)].join('\t'),
    ),
  ].join('\r\n');
}
async function copy() {
  const current = revision,
    content = text();
  try {
    await navigator.clipboard.writeText(content);
    notify('已复制含初始密码的凭据，请妥善转交。');
  } catch {
    if (current === revision) fallback.value = content;
  }
}
function download() {
  const url = URL.createObjectURL(
    new Blob(['\ufeff' + text()], { type: 'text/plain;charset=utf-8' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = 'account-import-credentials.txt';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
</script>
<template>
  <section
    v-if="credentials.length || missing"
    class="admin-panel import-results"
    aria-labelledby="import-results-title"
  >
    <h3 id="import-results-title">初始凭据领取</h3>
    <p v-if="missing" role="status">
      {{ missing }}
      个账号已创建，但本页未领取其初始密码。服务端不重放密码；请先核对账号，再到“账号管理”明确重新发放，原密码会失效。
    </p>
    <template v-if="credentials.length"
      ><p>
        本页已领取
        {{ credentials.length }} 份。离开或刷新后清除，请及时转交。下载文件含初始密码，请妥善保管。
      </p>
      <div class="credential-actions">
        <button type="button" class="btn" :aria-pressed="visible" @click="visible = !visible">
          {{ visible ? '隐藏初始密码' : '显示初始密码' }}</button
        ><button type="button" class="btn" @click="copy">复制已领取凭据</button
        ><button type="button" class="btn" @click="download">下载凭据文本（含初始密码）</button>
      </div>
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>QQ / 昵称</th>
              <th>初始密码</th>
              <th>有效至</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in credentials" :key="row.row_id">
              <td>{{ row.qq_id }}<br />{{ row.name }}</td>
              <td>
                <input
                  :type="visible ? 'text' : 'password'"
                  :value="row.temporary_password"
                  :aria-label="`${row.qq_id} 的初始密码`"
                  readonly
                  autocomplete="off"
                />
              </td>
              <td>{{ date(row.expires_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <label v-if="fallback"
        >自动复制失败，请手动复制以下内容<textarea
          :value="fallback"
          readonly
          rows="6"
          aria-label="手动复制初始凭据"
        ></textarea></label
    ></template>
  </section>
</template>
<style scoped>
.import-results {
  margin-top: 20px;
  min-width: 0;
}
.credential-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}
table {
  min-width: 560px;
}
input {
  width: 25ch;
  font-family: monospace;
}
textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
}
</style>
