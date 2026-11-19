<script setup>
import { ref, watch } from 'vue';
const props = defineProps({ problem: Object, taskVersion: Number, disabled: Boolean });
const emit = defineEmits(['review']);
const reason = ref('');
watch(
  () => props.problem.can_reset_binding,
  () => {
    reason.value = '';
  },
  { immediate: true },
);
function submit() {
  emit('review', {
    problem_id: props.problem.id,
    version: props.problem.progress_version,
    task_version: props.taskVersion,
    decision: 'reset_binding',
    reason: reason.value.trim(),
  });
}
</script>
<template>
  <form class="tt-panel tt-stack" @submit.prevent="submit">
    <h4>{{ problem.problem_id }} · 管理员核验</h4>
    <p class="tt-caption">
      审核原因会展示给成员，操作保留记录。洛谷按历史 AC 判断完成，不判断按期或逾期。
    </p>
    <label class="tt-field"
      ><span>处理方式</span>
      <span>使用当前绑定重新核验历史 AC；已完成的成绩保留。</span>
    </label>
    <label class="tt-field"
      ><span>公开审核原因</span>
      <textarea
        v-model="reason"
        required
        maxlength="500"
        :disabled="disabled"
        placeholder="填写核验依据；重新绑定会清除本题尚未计入完成的旧证据。"
      ></textarea>
    </label>
    <button class="btn" :disabled="disabled || !reason.trim()">
      保存 {{ problem.problem_id }} 核验结果
    </button>
  </form>
</template>
