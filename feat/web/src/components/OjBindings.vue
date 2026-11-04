<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { useRequests, date } from '../lib/api.js';
const props = defineProps({ bindings: { type: Array, default: () => [] } });
const emit = defineEmits(['refresh']);
const request = useRequests();
const selected = ref(null),
  mode = ref('verify'),
  account = ref(''),
  password = ref(''),
  confirmed = ref(false),
  challenge = ref(null),
  busy = ref(false),
  message = ref(''),
  error = ref('');
const verifying = computed(() => ['verify', 'verify-current'].includes(mode.value));
const verifyingCurrent = computed(
  () =>
    verifying.value &&
    (challenge.value
      ? sameAccount(challenge.value.account, selected.value?.account)
      : mode.value === 'verify-current'),
);
function sameAccount(first, second) {
  return Boolean(first && second) && first.toLowerCase() === second.toLowerCase();
}
function needsCurrentVerification(binding) {
  return (
    binding.self_service &&
    binding.account &&
    binding.provenance?.source === 'admin_import' &&
    !binding.provenance.owner_verified_at
  );
}
function close() {
  selected.value = null;
  password.value = '';
  confirmed.value = false;
  challenge.value = null;
  account.value = '';
}
function open(binding, action) {
  close();
  selected.value = binding;
  mode.value = action;
  const pending = binding.verification;
  const pendingCurrent = sameAccount(pending?.account, binding.account);
  challenge.value =
    ['verify', 'verify-current'].includes(action) &&
    (action === 'verify-current') === pendingCurrent
      ? pending
      : null;
  account.value = challenge.value?.account || (action === 'verify-current' ? binding.account : '');
  message.value = '';
  error.value = '';
}
async function perform(action, body = {}, method = 'POST') {
  if (busy.value || !selected.value) return;
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    const data = await request(
      '/me/bindings/' + selected.value.platform + (action ? '/' + action : ''),
      { method, body, timeoutMs: 25000 },
      'binding-write',
    );
    if (action === 'verification') {
      challenge.value = data;
      account.value = data.account;
    } else {
      message.value = data.message;
      close();
    }
    password.value = '';
    emit('refresh');
  } catch (e) {
    password.value = '';
    if (e.name !== 'AbortError') error.value = e.message;
  } finally {
    busy.value = false;
  }
}
function confirmBinding() {
  perform('confirm', {
    verification_id: challenge.value.verification_id,
    password: password.value,
    confirmed: confirmed.value,
    current_account: selected.value.account,
  });
}
function removeBinding() {
  perform(
    '',
    {
      password: password.value,
      confirmed: confirmed.value,
      current_account: selected.value.account,
    },
    'DELETE',
  );
}
watch(
  () => props.bindings,
  (bindings) => {
    if (
      selected.value &&
      bindings.find((item) => item.platform === selected.value.platform)?.account !==
        selected.value.account
    )
      close();
  },
);
onBeforeUnmount(close);
</script>
<template>
  <section class="community-panel oj-bindings" aria-labelledby="oj-bindings-heading">
    <div class="panel-heading">
      <h2 id="oj-bindings-heading">OJ 绑定与同步</h2>
      <button class="btn" :disabled="busy" @click="emit('refresh')">刷新状态</button>
    </div>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p class="muted">
      绑定核验只需修改 OJ 的公开资料，不需要 OJ 登录密码。改绑验证失败时保留原账号与数据。
    </p>
    <div class="profile-binding-grid">
      <div v-for="binding in bindings" :key="binding.platform" class="card">
        <h3>
          {{ binding.label }} ·
          {{ { unbound: '未绑定', pending: '待验证', bound: '已绑定' }[binding.binding_status] }}
        </h3>
        <b>{{ binding.account || '尚未绑定 OJ 账号' }}</b>
        <p>{{ binding.message }}</p>
        <small>最近成功同步：{{ date(binding.last_success_at) }}</small>
        <div class="chips">
          <button
            v-if="needsCurrentVerification(binding)"
            class="btn"
            :disabled="busy"
            @click="open(binding, 'verify-current')"
          >
            核验当前账号
          </button>
          <button
            v-if="binding.self_service"
            class="btn"
            :disabled="busy"
            @click="open(binding, 'verify')"
          >
            {{
              binding.verification && !sameAccount(binding.verification.account, binding.account)
                ? '继续验证 / 重新申请'
                : binding.account
                  ? '改绑账号'
                  : '绑定账号'
            }}
          </button>
          <template v-if="binding.account"
            ><button class="btn" :disabled="busy" @click="open(binding, 'unbind')">解绑</button
            ><button
              class="btn"
              :disabled="busy || ['queued', 'running'].includes(binding.sync_status)"
              @click="open(binding, 'sync')"
            >
              同步记录
            </button></template
          >
        </div>
        <p v-if="binding.provenance?.source === 'admin_import'" class="muted">
          管理员导入录入，尚未完成本人归属核验；同步状态与归属核验分别记录。
        </p>
        <p v-else-if="binding.provenance?.source === 'member_verified'" class="muted">
          已通过本人归属核验。
        </p>
        <p v-if="!binding.self_service" class="muted">
          该平台的网页归属验证尚未开放，绑定或改绑请联系管理员。
        </p>
      </div>
    </div>
    <section v-if="selected" class="card" aria-labelledby="binding-operation-heading">
      <h3 id="binding-operation-heading">
        {{ selected.label }} ·
        {{
          {
            verify: verifyingCurrent
              ? '核验当前账号'
              : selected.account
                ? '验证新账号'
                : '首次绑定',
            'verify-current': '核验当前账号',
            unbind: '确认解绑',
            sync: '同步本人记录',
          }[mode]
        }}
      </h3>
      <button class="btn" :disabled="busy" @click="close">取消</button>
      <template v-if="verifying">
        <p v-if="verifyingCurrent" role="note">
          仅核验当前账号的本人归属，保留现有绑定、AC、提交证据和训练挑战；核验成功后按现有流程同步记录。
        </p>
        <form @submit.prevent="perform('verification', { account })">
          <label
            >{{ mode === 'verify-current' ? '当前账号' : '新账号'
            }}<input
              v-model.trim="account"
              :readonly="mode === 'verify-current'"
              required
              maxlength="64"
              autocomplete="off" /></label
          ><button class="btn primary" :disabled="busy">
            {{ busy ? '处理中…' : '申请验证码' }}
          </button>
        </form>
        <div v-if="challenge">
          <p>
            请将验证码 <code>{{ challenge.code }}</code> 保存到 Codeforces 设置的 First
            name（名字）或 Organization（组织），然后确认验证。
          </p>
          <p>
            目标账号：{{ challenge.account }} · 有效至
            {{ date(challenge.expires_at) }}。重新申请将使旧验证失效。
          </p>
        </div>
      </template>
      <template v-if="mode === 'unbind' || (verifying && selected.account && challenge)">
        <p v-if="!verifyingCurrent" role="note">
          当前账号：{{ selected.account }}。解绑或成功改绑会清理该平台的
          AC、提交证据及同步状态，并结束该平台进行中的训练挑战；收藏与历史学习资料保留，其他平台不受影响。
        </p>
        <label
          >当前登录密码<input
            v-model="password"
            type="password"
            autocomplete="current-password"
            maxlength="256"
        /></label>
        <label
          ><input v-model="confirmed" type="checkbox" />{{
            verifyingCurrent ? '我确认核验当前账号的归属' : '我已确认平台、账号和以上数据影响'
          }}</label
        >
      </template>
      <button
        v-if="verifying && challenge"
        class="btn primary"
        :disabled="busy || (Boolean(selected.account) && (!password || !confirmed))"
        @click="confirmBinding"
      >
        {{ busy ? '验证中…' : verifyingCurrent ? '确认核验' : '确认验证并绑定' }}
      </button>
      <button
        v-if="mode === 'unbind'"
        class="btn primary"
        :disabled="busy || !password || !confirmed"
        @click="removeBinding"
      >
        确认解绑
      </button>
      <template v-if="mode === 'sync'"
        ><p>仅同步本人 {{ selected.label }} 记录。已有记录在失败时保留。</p>
        <button class="btn primary" :disabled="busy" @click="perform('sync')">
          开始同步
        </button></template
      >
    </section>
  </section>
</template>
