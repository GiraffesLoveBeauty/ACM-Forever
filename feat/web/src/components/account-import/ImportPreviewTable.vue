<script setup>
import { computed, ref, watch } from 'vue';
const props = defineProps({
  rows: { type: Array, default: () => [] },
  selected: { type: Set, default: () => new Set() },
  locked: Boolean,
});
const emit = defineEmits(['select']);
const filter = ref('all'),
  page = ref(1);
const actionLabels = {
  create_member_and_account: '新建并开户',
  create_web_account_only: '仅补开户',
  skipped_existing: '已有账号',
  blocked_inactive: '账号已停用',
  blocked_closed: '账号已注销',
};
const stateLabels = {
  ready: '待确认',
  created: '已创建',
  conflict: '状态冲突',
  invalid: '字段错误',
  skipped: '已跳过',
  blocked: '不能导入',
  cancelled: '已取消',
  retryable: '待重试',
};
const filtered = computed(() =>
  props.rows.filter(
    (row) =>
      filter.value === 'all' ||
      (filter.value === 'ready'
        ? row.can_submit
        : filter.value === 'skipped'
          ? ['skipped', 'blocked', 'cancelled'].includes(row.status)
          : row.status === filter.value),
  ),
);
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / 20)));
const visible = computed(() => filtered.value.slice((page.value - 1) * 20, page.value * 20));
watch(filter, () => {
  page.value = 1;
});
watch(pages, (value) => {
  page.value = Math.min(page.value, value);
});
</script>
<template>
  <section aria-label="逐行预检与执行结果">
    <div class="preview-toolbar">
      <label
        >显示
        <select v-model="filter">
          <option value="all">全部行</option>
          <option value="ready">可执行</option>
          <option value="invalid">错误</option>
          <option value="skipped">已跳过 / 阻断</option>
          <option value="created">已创建</option>
          <option value="conflict">冲突</option>
        </select></label
      ><span>共 {{ filtered.length }} 行</span
      ><template v-if="!locked"
        ><button
          type="button"
          class="btn"
          @click="
            emit(
              'select',
              visible.filter((r) => r.can_submit).map((r) => r.row_id),
              true,
            )
          "
        >
          选中本页可执行行</button
        ><button type="button" class="btn" @click="emit('select', [...selected], false)">
          清空选择（{{ selected.size }}）
        </button></template
      >
    </div>
    <div class="admin-table-wrap" tabindex="0" aria-label="可横向滚动的预检表格">
      <table class="admin-table">
        <thead>
          <tr>
            <th>选择</th>
            <th>Excel 行</th>
            <th>QQ / 昵称</th>
            <th>拟执行动作</th>
            <th>状态与说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in visible" :key="row.row_id">
            <td>
              <input
                type="checkbox"
                :aria-label="`选择 Excel 第 ${row.excel_row_number} 行`"
                :checked="selected.has(row.row_id)"
                :disabled="locked || !row.can_submit"
                @change="emit('select', [row.row_id], $event.target.checked)"
              />
            </td>
            <td>{{ row.excel_row_number }}</td>
            <td>
              <span>{{ row.qq_id || '已匿名化' }}</span
              ><br /><strong>{{ row.name }}</strong>
            </td>
            <td>{{ actionLabels[row.action] || row.action }}</td>
            <td>
              <strong>{{ stateLabels[row.status] || row.status }}</strong>
              <p v-for="(text, i) in row.errors" :key="`e${i}`" class="row-error">{{ text }}</p>
              <p v-for="(text, i) in row.warnings" :key="`w${i}`">{{ text }}</p>
              <p v-if="row.ignored_fields.length">忽略：{{ row.ignored_fields.join('、') }}</p>
              <details v-if="Object.keys(row.bindings || {}).length">
                <summary>将录入的 OJ</summary>
                <p v-for="(account, field) in row.bindings" :key="field">
                  {{ field }}：{{ account }}
                </p>
              </details>
            </td>
          </tr>
          <tr v-if="!visible.length">
            <td colspan="5">此筛选下没有记录。</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="preview-pages">
      <button type="button" class="btn" :disabled="page <= 1" @click="page--">上一页</button
      ><span>第 {{ page }} / {{ pages }} 页 · 每页 20 行</span
      ><button type="button" class="btn" :disabled="page >= pages" @click="page++">下一页</button>
    </div>
  </section>
</template>
<style scoped>
.preview-toolbar,
.preview-pages {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}
table {
  min-width: 660px;
}
td {
  vertical-align: top;
}
td p {
  margin: 5px 0;
  overflow-wrap: anywhere;
  max-width: 360px;
  font-size: 0.86rem;
}
.row-error {
  color: var(--error-color, #a44537);
}
.preview-pages {
  justify-content: flex-end;
}
</style>
