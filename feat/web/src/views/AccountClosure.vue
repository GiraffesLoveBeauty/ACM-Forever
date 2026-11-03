<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { api, auth, initializeAuth, finishAccountClosure } from '../lib/api.js';
import { readClosure, rememberClosure, closureLabels } from '../lib/account-closure.js';
const preview = ref(null),
  password = ref(''),
  confirmation = ref(''),
  acknowledged = ref(false);
const phase = ref('loading'),
  busy = ref(false),
  message = ref(''),
  result = ref(null);
const controller = new AbortController();
let disposed = false;
let previewOwner = null;
const canSubmit = computed(
  () =>
    preview.value?.can_close &&
    auth.authenticated &&
    acknowledged.value &&
    confirmation.value === '注销账号' &&
    password.value.length > 0 &&
    !busy.value,
);
const entries = (counts) => Object.entries(counts || {}).filter(([, count]) => count > 0);
function applyResult(data) {
  if (data.status !== 'closed') {
    phase.value = 'unknown';
    message.value =
      '服务端尚未记录注销完成。请稍后用回执再次查询；仍登录时可重新输入密码，使用同一请求重试。';
    return;
  }
  result.value = data;
  phase.value = 'closed';
  password.value = '';
  confirmation.value = '';
  // A receipt from an earlier visit must not log out a different account that
  // signed in later. The original owner is held only in this view's memory.
  if (
    !auth.authenticated ||
    (previewOwner &&
      auth.qq_id === previewOwner.qq_id &&
      (auth.account_epoch ?? 1) === previewOwner.account_epoch)
  )
    finishAccountClosure();
}
async function loadPreview() {
  if (busy.value) return;
  busy.value = true;
  message.value = '';
  try {
    preview.value = await api('/me/account-closure/preview', { signal: controller.signal });
    previewOwner = { qq_id: auth.qq_id, account_epoch: preview.value.account_epoch };
    rememberClosure(preview.value);
    phase.value = 'ready';
  } catch (error) {
    if (!disposed) {
      phase.value = 'unavailable';
      message.value = error.message;
    }
  } finally {
    busy.value = false;
  }
}
async function checkReceipt() {
  if (busy.value || !preview.value) return;
  busy.value = true;
  message.value = '';
  try {
    const data = await api('/account-closures/' + preview.value.request_id, {
      headers: { 'X-Closure-Receipt': preview.value.receipt_token },
      signal: controller.signal,
    });
    applyResult(data);
  } catch (error) {
    if (!disposed) {
      phase.value = 'unknown';
      message.value =
        error.status === 404
          ? '回执不存在或已过期，暂时无法确认注销结果。请联系平台维护者核查，不能以未登录判断注销成功。'
          : '结果待确认：' + error.message + ' 请保留本标签页后再次查询。';
    }
  } finally {
    busy.value = false;
  }
}
async function submit() {
  if (!canSubmit.value) return;
  busy.value = true;
  message.value = '';
  rememberClosure(preview.value, true);
  const body = {
    current_password: password.value,
    confirm_text: confirmation.value,
    policy_version: preview.value.policy_version,
    expected_account_epoch: preview.value.account_epoch,
  };
  password.value = '';
  try {
    const data = await api('/me/account-closure', {
      method: 'POST',
      body,
      headers: {
        'Idempotency-Key': preview.value.request_id,
        'X-Closure-Receipt': preview.value.receipt_token,
      },
      signal: controller.signal,
      timeoutMs: 20000,
    });
    applyResult(data);
  } catch (error) {
    if (disposed) return;
    if (!error.status || error.status >= 500 || error.status === 401) {
      phase.value = 'unknown';
      message.value = '结果待确认。请求可能已经提交，请使用回执查询；退出登录不代表注销成功。';
    } else {
      phase.value = 'ready';
      message.value = error.message;
      if (
        [
          'ACCOUNT_CHANGED',
          'POLICY_CHANGED',
          'ROLE_HANDOVER_REQUIRED',
          'LAST_ROOT_PROTECTED',
        ].includes(error.code)
      )
        preview.value.can_close = false;
    }
  } finally {
    body.current_password = '';
    busy.value = false;
  }
}
onMounted(async () => {
  const saved = readClosure();
  try {
    await initializeAuth();
  } catch {
    /* A receipt does not need login. */
  }
  if (disposed) return;
  if (saved?.submitted) {
    preview.value = saved.preview;
    phase.value = 'unknown';
    await checkReceipt();
  } else if (auth.authenticated && auth.account_closure_enabled) await loadPreview();
  else {
    phase.value = 'unavailable';
    message.value = auth.authenticated
      ? '账号注销暂未开放。'
      : '请先登录本人账号；已有回执只在提交时使用的标签页内查询。';
  }
});
onBeforeUnmount(() => {
  disposed = true;
  password.value = '';
  controller.abort();
});
</script>
<template>
  <main class="community-main closure-page">
    <nav class="closure-breadcrumb" aria-label="面包屑">
      <RouterLink to="/home.html">个人中心</RouterLink><span> / 注销账号</span>
    </nav>
    <section class="community-panel closure-card">
      <span class="closure-eyebrow">账号安全</span>
      <h1>
        {{ phase === 'closed' ? '账号已注销' : phase === 'unknown' ? '结果待确认' : '注销账号' }}
      </h1>
      <p v-if="phase === 'loading'" role="status">正在读取账号状态与数据影响…</p>
      <template v-else-if="phase === 'closed'">
        <p role="status">服务端已确认注销成功，旧登录、绑定和私有数据已撤销。</p>
        <p>
          公共内容保留，作者统一显示为“已注销用户”。同一 QQ
          可由管理员创建全新账号，旧数据不会恢复或继承。
        </p>
        <p>
          资源清理：{{
            {
              pending: '已撤销访问，文件排队清理中',
              completed: '已完成',
              attention_required: '已撤销访问，部分文件等待维护者处理',
            }[result?.cleanup_state] || '查询中'
          }}
        </p>
        <p class="closure-caption">
          回执仅用于查询本次结果，有效期 24 小时。关闭本标签页后可能无法再次查询。
        </p>
        <button
          v-if="result?.cleanup_state !== 'completed'"
          class="btn"
          :disabled="busy"
          @click="checkReceipt"
        >
          刷新资源清理状态
        </button>
        <RouterLink class="btn primary" to="/index.html">返回社区</RouterLink>
      </template>
      <template v-else>
        <p v-if="message" class="closure-message" role="alert">{{ message }}</p>
        <template v-if="preview">
          <div class="closure-warning">
            <strong>提交后立即生效，不可恢复</strong>
            <p>{{ preview.retention_notice?.text }}</p>
          </div>
          <div class="closure-impact">
            <section>
              <h2>将删除的私有数据</h2>
              <dl>
                <template v-for="[key, count] in entries(preview.delete_counts)" :key="key"
                  ><dt>{{ closureLabels[key] || key }}</dt>
                  <dd>{{ count }}</dd></template
                >
              </dl>
              <p v-if="!entries(preview.delete_counts).length">暂无相关私有记录。</p>
            </section>
            <section>
              <h2>继续保留的公共内容</h2>
              <dl>
                <template v-for="[key, count] in entries(preview.retain_counts)" :key="key"
                  ><dt>{{ closureLabels[key] || key }}</dt>
                  <dd>{{ count }}</dd></template
                >
              </dl>
              <p>保留最小账号墓碑与必要受限引用；外部 OJ 账号和 QQ 群成员关系不受影响。</p>
            </section>
          </div>
          <ul v-if="preview.blockers?.length" class="closure-message">
            <li v-for="blocker in preview.blockers" :key="blocker.code">{{ blocker.message }}</li>
          </ul>
          <form
            v-if="preview.can_close && auth.authenticated"
            class="closure-form"
            @submit.prevent="submit"
          >
            <label
              >当前密码<input
                v-model="password"
                type="password"
                autocomplete="current-password"
                maxlength="256"
                :disabled="busy"
                required
            /></label>
            <label class="closure-check"
              ><input v-model="acknowledged" type="checkbox" :disabled="busy" /><span
                >我已了解删除及保留范围，确认操作不可恢复，同一 QQ
                可重新开户，新账号不继承旧数据。</span
              ></label
            >
            <label
              >请输入“注销账号”确认<input
                v-model="confirmation"
                autocomplete="off"
                maxlength="4"
                :disabled="busy"
                required
            /></label>
            <button class="btn closure-danger" type="submit" :disabled="!canSubmit">
              {{ busy ? '正在确认结果…' : '永久注销账号' }}
            </button>
          </form>
          <button
            v-if="phase === 'unknown'"
            class="btn primary"
            :disabled="busy"
            @click="checkReceipt"
          >
            {{ busy ? '正在查询…' : '用回执查询结果' }}
          </button>
          <button
            v-if="phase === 'ready' && !preview.can_close"
            class="btn"
            :disabled="busy"
            @click="loadPreview"
          >
            重新检查注销条件
          </button>
        </template>
        <div class="closure-links">
          <RouterLink v-if="auth.authenticated" class="btn" to="/home.html">返回个人中心</RouterLink
          ><RouterLink v-else class="btn" to="/login.html?next=/account-closure.html"
            >登录本人账号</RouterLink
          ><RouterLink class="btn" to="/index.html">返回社区</RouterLink>
        </div>
      </template>
    </section>
  </main>
</template>
<style scoped>
.closure-page {
  max-width: 960px;
  padding-bottom: 40px;
}
.closure-breadcrumb {
  margin: 24px 0 14px;
  opacity: 0.8;
}
.closure-card {
  padding: clamp(20px, 4vw, 40px);
  overflow-wrap: anywhere;
}
.closure-eyebrow {
  font-size: 12px;
  letter-spacing: 0.14em;
  opacity: 0.65;
}
.closure-card h1 {
  margin: 10px 0 20px;
}
.closure-card p {
  line-height: 1.8;
}
.closure-warning {
  border: 1px solid #bd754955;
  border-left: 3px solid #bd7549;
  padding: 16px 20px;
  margin: 24px 0;
  background: #bd75490b;
}
.closure-warning strong {
  color: #bd7549;
}
.closure-impact {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin: 24px 0;
}
.closure-impact h2 {
  font-size: 17px;
}
.closure-impact dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  font-size: 14px;
}
.closure-impact dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.closure-form {
  display: grid;
  gap: 20px;
  border-top: 1px solid #8883;
  padding-top: 24px;
}
.closure-form label {
  display: grid;
  gap: 8px;
}
.closure-form input:not([type='checkbox']) {
  width: 100%;
  max-width: 400px;
  min-height: 44px;
  padding: 10px 12px;
  color: inherit;
  background: transparent;
  border: 1px solid #8886;
  border-radius: 6px;
  box-sizing: border-box;
}
.closure-form .closure-check {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  line-height: 1.6;
}
.closure-check input {
  margin-top: 4px;
  width: 18px;
  height: 18px;
  max-width: 18px;
  min-width: 18px;
  min-height: 18px;
  flex: 0 0 18px;
}
.closure-check span {
  flex: 1;
  min-width: 0;
}
.closure-danger {
  justify-self: start;
  background: #b83c32;
  color: #fff;
  border-color: #b83c32;
  min-height: 44px;
}
.closure-danger:disabled {
  opacity: 0.5;
}
.closure-message {
  padding: 12px 16px;
  background: #bd754915;
  line-height: 1.7;
}
.closure-caption {
  font-size: 13px;
  opacity: 0.75;
}
.closure-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}
@media (max-width: 600px) {
  .closure-impact {
    grid-template-columns: 1fr;
    gap: 14px;
  }
  .closure-danger {
    width: 100%;
  }
}
</style>
