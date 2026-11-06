package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;

/** Strict, non-cacheable account-closure contract. A logged-out session is not a receipt. */
final class AccountClosure {
    static final String POLICY = "closure-v2";
    static final String CONSEQUENCES = "注销即时生效且不可恢复。账户信息、站内私有刷题/训练记录、源码、收藏、云端草稿与平台绑定会被删除。已发布的话题、评论、Wiki 历史和公共引用图片会保留，作者显示为已注销用户。不会删除外部 OJ 账号或退出 QQ 群。";
    static final class Ticket {
        final String origin, account, requestId, token, policy, notice, blocker;
        final long epoch, expires;
        final boolean canClose;
        Ticket(String origin, String account, JSONObject preview) throws Exception {
            this.origin = ApiClient.checkedBaseUrl(origin); this.account = account;
            requestId = preview.getString("request_id"); token = preview.getString("receipt_token");
            policy = preview.getString("policy_version"); epoch = preview.getLong("account_epoch"); expires = preview.getLong("receipt_expires_at");
            if (this.origin.isEmpty() || account.isEmpty() || !requestId.matches("[a-f0-9]{32}") || !token.matches("[A-Za-z0-9_-]{32,128}") || !POLICY.equals(policy) || epoch < 1)
                throw new IllegalArgumentException("注销预览格式或规则版本不支持，请到网页端处理。");
            canClose = preview.getBoolean("can_close");
            JSONObject retention = preview.optJSONObject("retention_notice");
            notice = retention == null ? "" : retention.optString("text");
            if (notice.isEmpty()) throw new IllegalArgumentException("服务器未提供完整注销后果，请到网页端处理。");
            JSONArray blockers = preview.optJSONArray("blockers"); StringBuilder messages = new StringBuilder();
            if (blockers != null) for (int i = 0; i < blockers.length(); i++) {
                if (i > 0) messages.append('\n'); messages.append(blockers.getJSONObject(i).optString("message", "暂时无法注销。"));
            }
            blocker = messages.toString();
        }
        boolean expired(long now) { return now >= expires; }
        JSONObject body(String password, long now) throws Exception {
            if (!canClose) throw new IllegalArgumentException(blocker.isEmpty() ? "暂时无法注销。" : blocker);
            if (expired(now)) throw new IllegalArgumentException("注销预览已过期，请重新打开。");
            if (password == null || password.isEmpty() || password.length() > 256) throw new IllegalArgumentException("请输入当前 ACMForever 登录密码。");
            return new JSONObject().put("current_password", password).put("confirm_text", "注销账号")
                    .put("policy_version", policy).put("expected_account_epoch", epoch);
        }
        JSONObject saved() throws Exception {
            return new JSONObject().put("origin", origin).put("account", account).put("preview", new JSONObject()
                    .put("request_id", requestId).put("receipt_token", token).put("policy_version", policy)
                    .put("account_epoch", epoch).put("receipt_expires_at", expires).put("can_close", canClose)
                    .put("retention_notice", new JSONObject().put("text", notice)));
        }
        static Ticket restore(String text) throws Exception {
            JSONObject saved = new JSONObject(text); return new Ticket(saved.getString("origin"), saved.getString("account"), saved.getJSONObject("preview"));
        }
        boolean closed(JSONObject result) throws Exception {
            if (!requestId.equals(result.getString("request_id")) || !policy.equals(result.getString("policy_version")))
                throw new IllegalArgumentException("注销回执不匹配，不能确认结果。");
            String status = result.getString("status"); long committed = result.optLong("committed_at");
            if ("closed".equals(status) && committed > 0) return true;
            if ("pending".equals(status) && committed == 0) return false;
            throw new IllegalArgumentException("注销回执状态无效，不能确认结果。");
        }
    }
    static boolean disabled(Exception failure) { return "FEATURE_DISABLED".equals(code(failure)); }
    static String code(Exception failure) {
        if (!(failure instanceof ApiClient.ApiException)) return "";
        JSONObject details = ((ApiClient.ApiException) failure).details; return details == null ? "" : details.optString("code");
    }
    // Only explicit pre-commit refusals are safe to leave. Other errors require a receipt read.
    static boolean refused(Exception failure) {
        return rateLimited(failure) || authenticationRequired(failure) || java.util.Arrays.asList("FEATURE_DISABLED", "ROLE_HANDOVER_REQUIRED", "LAST_ROOT_PROTECTED", "REAUTH_FAILED", "ACCOUNT_CHANGED", "POLICY_CHANGED", "CSRF_INVALID", "INVALID_REQUEST", "MUST_CHANGE_PASSWORD").contains(code(failure));
    }
    static boolean rateLimited(Exception failure) {
        // The closure API emits this response before its commit transaction. Bare 429s are ambiguous.
        return failure instanceof ApiClient.ApiException && ((ApiClient.ApiException) failure).status == 429 && "RATE_LIMITED".equals(code(failure));
    }
    static boolean authenticationRequired(Exception failure) {
        // Only the closure POST's explicit business response proves authentication failed before commit.
        return failure instanceof ApiClient.ApiException && ((ApiClient.ApiException) failure).status == 401 && "AUTH_REQUIRED".equals(code(failure));
    }
}
