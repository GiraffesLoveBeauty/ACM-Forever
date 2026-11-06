package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;

/** Member-only binding state. A zero AC count says nothing about account ownership. */
final class OjBindingState {
    static final String[] PLATFORMS = {"codeforces", "luogu", "atcoder", "nowcoder", "cjlu"};
    private static final String[] FIELDS = {"cf_handle", "luogu_id", "atcoder_handle", "nowcoder_id", "cjlu_username"};
    final String platform, account, message, syncStatus;
    final boolean available, selfService, needsOwnership;
    final long lastSuccess;
    final Pending pending;

    static final class Pending {
        final String account, id, code;
        final long expiresAt;
        Pending(JSONObject json) {
            account = clean(json, "account"); id = clean(json, "verification_id");
            code = clean(json, "code"); expiresAt = json.optLong("expires_at");
        }
        boolean valid(long now) { return !account.isEmpty() && !id.isEmpty() && !code.isEmpty() && expiresAt > now; }
    }

    private OjBindingState(String platform, JSONObject entry, String fallback, long now) {
        this.platform = platform; available = entry != null;
        account = available ? clean(entry, "account") : fallback;
        selfService = available && entry.optBoolean("self_service", false);
        message = available ? clean(entry, "message") : "无API接口：服务器未提供绑定操作状态，请到网页端或联系管理员。";
        syncStatus = available ? clean(entry, "sync_status") : "";
        lastSuccess = available ? entry.optLong("last_success_at") : 0;
        JSONObject provenance = available ? entry.optJSONObject("provenance") : null;
        needsOwnership = selfService && bound() && provenance != null
                && "admin_import".equals(provenance.optString("source")) && provenance.optLong("owner_verified_at") == 0;
        JSONObject verification = available ? entry.optJSONObject("verification") : null;
        Pending candidate = verification == null ? null : new Pending(verification);
        pending = candidate != null && candidate.valid(now) ? candidate : null;
    }

    static OjBindingState fromProfile(JSONObject profile, String platform, long now) {
        int index = index(platform);
        JSONArray bindings = profile == null ? null : profile.optJSONArray("bindings");
        JSONObject entry = null;
        if (bindings != null) for (int i = 0; i < bindings.length(); i++) {
            JSONObject item = bindings.optJSONObject(i);
            if (item != null && platform.equals(item.optString("platform"))) { entry = item; break; }
        }
        JSONObject user = profile == null ? null : profile.optJSONObject("user");
        if (user == null) user = profile;
        return new OjBindingState(platform, entry, clean(user, FIELDS[index]), now);
    }

    static boolean known(String platform) {
        for (String item : PLATFORMS) if (item.equals(platform)) return true;
        return false;
    }
    private static int index(String platform) {
        for (int i = 0; i < PLATFORMS.length; i++) if (PLATFORMS[i].equals(platform)) return i;
        throw new IllegalArgumentException("不支持的平台");
    }
    private static String clean(JSONObject json, String field) {
        return json == null || json.isNull(field) ? "" : json.optString(field, "").trim();
    }
    boolean bound() { return !account.isEmpty(); }
    String path(String action) {
        if (!java.util.Arrays.asList("", "verification", "confirm", "sync").contains(action))
            throw new IllegalArgumentException("不支持的绑定操作");
        return "/api/me/bindings/" + platform + (action.isEmpty() ? "" : "/" + action);
    }
    static boolean sameAccount(String a, String b) { return a != null && b != null && a.equalsIgnoreCase(b); }
    JSONObject verificationBody(String candidate) throws Exception {
        if (!selfService) throw new IllegalArgumentException("该平台尚未开放自助绑定或改绑，请联系管理员。");
        String value = candidate.trim();
        if (!value.matches("[A-Za-z0-9_.-]{1,64}")) throw new IllegalArgumentException("请输入1至64位账号标识，不要填写网址或密码。");
        if (sameAccount(account, value) && !needsOwnership) throw new IllegalArgumentException("该账号已经绑定，无需重复绑定。");
        return new JSONObject().put("account", value);
    }
    JSONObject confirmationBody(Pending challenge, String selectedAccount, String password, boolean confirmed, long now) throws Exception {
        if (!selfService || challenge == null || !challenge.valid(now)) throw new IllegalArgumentException("验证已过期，请重新申请验证码。");
        if (!sameAccount(challenge.account, selectedAccount == null ? null : selectedAccount.trim()))
            throw new IllegalArgumentException("目标账号已修改，请重新申请验证码。");
        JSONObject result = credentials(password, confirmed);
        return result.put("verification_id", challenge.id);
    }
    JSONObject unbindBody(String password, boolean confirmed) throws Exception {
        if (!available || !bound()) throw new IllegalArgumentException("该平台尚未绑定账号，或服务器未提供绑定状态。");
        return credentials(password, confirmed);
    }
    private JSONObject credentials(String password, boolean confirmed) throws Exception {
        if (bound() && (password.isEmpty() || password.length() > 256 || !confirmed))
            throw new IllegalArgumentException("请填写当前 ACMForever 登录密码，并勾选确认。");
        JSONObject result = new JSONObject().put("current_account", account).put("confirmed", confirmed);
        if (bound()) result.put("password", password);
        return result;
    }
}
