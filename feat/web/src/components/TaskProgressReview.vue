<script setup>
import { ref, watch } from 'vue';
const props = defineProps({ problem: Object, taskVersion: Number, disabled: Boolean });
const emit = defineEmits(['review']);
const decision = ref('on_time');
const reason = ref('');
watch(
  () => props.problem.can_reset_binding,
  (reset) => {
    decision.value = reset ? 'reset_binding' : 'on_time';
    reason.value = '';
  },
  { immediate: true },
);
function submit() {
  emit('review', {
    problem_id: props.problem.id,
    version: props.problem.progress_version,
    task_version: props.taskVersion,
    decision: decision.value,
    reason: reason.value.trim(),
  });
}
</script>
<template>
  <form class="tt-panel tt-stack" @submit.prevent="submit">
    <h4>{{ problem.problem_id }} · 管理员核验</h4>
    <p class="tt-caption">审核原因会展示给成员，操作保留记录。审核不会生成实际提交时间。</p>
    <label class="tt-field"
      ><span>处理方式</span>
      <select v-model="decision" :disabled="disabled">
        <template v-if="problem.can_reset_binding"
          ><option value="reset_binding">使用当前绑定重新建立核验起点</option></template
        >
        <template v-else>
          <option value="on_time">确认按期完成</option>
          <option value="late">确认逾期完成</option>
          <option v-if="problem.review" value="clear">撤销人工决定，恢复快照判定</option>
        </template>
      </select>
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
