<script setup>
import { ref, computed } from 'vue';
import { profileFields, normalized } from '../../lib/member-profiles.js';
const props = defineProps({ record: Object, current: Object });
const emit = defineEmits(['resolve', 'close']);
const fields = computed(() =>
  Object.keys(profileFields).filter(
    (key) =>
      Object.hasOwn(props.record.changes, key) ||
      normalized(props.record.base[key]) !== normalized(props.current[key]),
  ),
);
const choices = ref(
  Object.fromEntries(
    fields.value.map((key) => [
      key,
      normalized(props.record.base[key]) === normalized(props.current[key]) &&
      Object.hasOwn(props.record.changes, key)
        ? 'mine'
        : 'server',
    ]),
  ),
);
function resolve() {
  emit(
    'resolve',
    Object.fromEntries(
      fields.value.map((key) => [
        key,
        choices.value[key] === 'mine'
          ? (props.record.changes[key] ?? props.record.base[key])
          : props.current[key],
      ]),
    ),
  );
}
</script>
<template>
  <section class="admin-panel profile-conflict" aria-label="资料冲突核对">
    <h3>核对资料变化 · {{ record.qq_id }}</h3>
    <p>逐字段选择，确认后生成基于当前资料的待保存草稿。再次保存 OJ 时需要重新确认。</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>字段</th>
            <th>原始值</th>
            <th>服务端当前值</th>
            <th>我的草稿</th>
            <th>采用</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in fields" :key="key">
            <th>{{ profileFields[key] }}</th>
            <td>{{ record.base[key] || '—' }}</td>
            <td>{{ current[key] || '—' }}</td>
            <td>{{ record.changes[key] ?? record.base[key] ?? '—' }}</td>
            <td>
              <label
                ><input
                  v-model="choices[key]"
                  type="radio"
                  :name="'merge-' + record.qq_id + '-' + key"
                  value="server"
                />服务端</label
              ><label
                ><input
                  v-model="choices[key]"
                  type="radio"
                  :name="'merge-' + record.qq_id + '-' + key"
                  value="mine"
                />我的草稿</label
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="chips">
      <button class="btn primary" @click="resolve">确认选择，保留为草稿</button
      ><button class="btn" @click="emit('close')">稍后核对</button>
    </div>
  </section>
</template>
<style scoped>
.profile-conflict {
  border: 1px solid var(--accent);
  margin: 16px 0;
}
.profile-conflict label {
  display: flex;
  gap: 6px;
  align-items: center;
  white-space: nowrap;
}
.profile-conflict table {
  min-width: 650px;
}
.profile-conflict input {
  width: 16px;
  min-width: 16px;
  height: 16px;
}
</style>
