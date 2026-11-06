package com.giraffeslovebeauty.acmforever;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;

/** Self-service uses the same ownership proof and destructive-operation checks as Web. */
public final class OjBindingsActivity extends MobilePageActivity {
    private long owner;
    private String platform = "", mode = "details", candidate = "", expectedAccount;
    private OjBindingState binding;
    private OjBindingState.Pending challenge;
    private EditText accountInput, passwordInput;
    private CheckBox confirmation;
    private final java.util.List<View> controls = new java.util.ArrayList<>();

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); createPage("OJ 账号绑定"); owner = api.sessionGeneration();
        String initial = getIntent().getStringExtra("platform");
        if (OjBindingState.known(initial)) platform = initial;
        if (saved != null && saved.getLong("binding_owner", -1) == owner) {
            platform = saved.getString("binding_platform", ""); mode = saved.getString("binding_mode", "details");
            candidate = saved.getString("binding_candidate", ""); expectedAccount = saved.getString("binding_expected");
        }
        if (!platform.isEmpty() && !OjBindingState.known(platform)) platform = "";
        load();
    }

    private void load() {
        resetPage(platform.isEmpty() ? "OJ 账号绑定" : PlatformAssets.name(platform) + " · 账号绑定");
        accountInput = null; passwordInput = null; confirmation = null; controls.clear();
        if (!validOwner()) { error(card(body), new ApiClient.ApiException(401, "请返回并重新登录。", false)); return; }
        LinearLayout slot = card(body); slot.addView(text("正在读取绑定状态…", 14));
        read(() -> {
            synchronized (api) {
                if (!validOwner()) throw new ApiClient.ApiException(401, "登录账号已切换", false);
                return api.getObject("/api/me/profile");
            }
        }, slot, false, value -> {
            if (!validOwner()) return;
            JSONObject profile = (JSONObject) value;
            if (platform.isEmpty()) renderList(slot, profile);
            else {
                OjBindingState fresh = OjBindingState.fromProfile(profile, platform, System.currentTimeMillis() / 1000);
                if (accountInput != null) candidate = accountInput.getText().toString().trim();
                if (expectedAccount != null && !expectedAccount.equals(fresh.account)) {
                    mode = "details"; candidate = ""; challenge = null;
                    notice.show("绑定状态已变化", new IllegalArgumentException("请核对当前账号后重新操作。"));
                }
                if (challenge != null && (fresh.pending == null || !challenge.id.equals(fresh.pending.id))) challenge = null;
                binding = fresh; expectedAccount = fresh.account;
                renderDetail(slot);
            }
        });
    }

    private boolean validOwner() { return owner == api.sessionGeneration() && api.isLoggedIn() && !api.requiresPasswordChange(); }

    private void renderList(LinearLayout slot, JSONObject profile) {
        slot.addView(text("绑定你的刷题账号", 20));
        slot.addView(text("归属验证只需修改 OJ 公开资料，不需要提供 OJ 登录密码。", 14));
        for (String id : OjBindingState.PLATFORMS) {
            OjBindingState state = OjBindingState.fromProfile(profile, id, System.currentTimeMillis() / 1000);
            LinearLayout box = card(slot), line = row(); box.addView(line);
            ImageView logo = new ImageView(this); logo.setImageDrawable(PlatformAssets.logo(this, id));
            line.addView(logo, new LinearLayout.LayoutParams(dp(38), dp(38)));
            TextView label = text(PlatformAssets.name(id), 17); line.addView(label, new LinearLayout.LayoutParams(0, -2, 1));
            box.addView(text(state.bound() ? state.account : "未绑定", 16));
            Button action = button(state.bound() ? "修改" : "绑定", () -> select(id));
            action.setContentDescription(PlatformAssets.name(id) + (state.bound() ? "修改绑定" : "绑定账号")); box.addView(action);
            if (!state.available) box.addView(text(state.message, 13));
        }
    }

    private void select(String id) {
        platform = id; mode = "details"; candidate = ""; expectedAccount = null; challenge = null; load();
    }

    private Button action(LinearLayout parent, String name, Runnable work) {
        Button button = button(name, work); controls.add(button); parent.addView(button); return button;
    }

    private void renderDetail(LinearLayout slot) {
        controls.clear(); accountInput = null; passwordInput = null; confirmation = null;
        slot.addView(text(PlatformAssets.name(platform), 21));
        slot.addView(text(binding.bound() ? "当前账号：" + binding.account : "尚未绑定账号", 17));
        if (!binding.available) { slot.addView(text(binding.message, 14)); return; }
        slot.addView(text(binding.message, 14));
        if (binding.lastSuccess > 0) slot.addView(text("最近成功同步：" + new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.CHINA)
                .format(new java.util.Date(binding.lastSuccess * 1000)), 12));
        if (!binding.selfService) slot.addView(text("该平台尚未开放本人归属验证。绑定或改绑请到网页端或联系管理员；已绑定账号可在下方解绑。", 14));
        if ("details".equals(mode)) {
            if (binding.bound()) {
                if (binding.needsOwnership) action(slot, "核验当前账号", () -> edit("verify-current"));
                if (binding.selfService) action(slot, "改绑账号", () -> edit("verify"));
                action(slot, "解绑账号", () -> edit("unbind"));
                Button sync = action(slot, "同步记录", this::sync);
                sync.setEnabled(!"queued".equals(binding.syncStatus) && !"running".equals(binding.syncStatus));
                action(slot, "刷新状态", this::load); return;
            }
            if (!binding.selfService) return;
            mode = "verify";
        }
        if ("unbind".equals(mode)) {
            destructiveFields(slot, false);
            action(slot, "确认解绑", this::unbind);
        } else {
            boolean current = "verify-current".equals(mode);
            slot.addView(text(current ? "核验当前账号" : binding.bound() ? "验证新账号" : "首次绑定", 17));
            accountInput = input(slot, current ? "当前 OJ 账号" : "OJ 账号标识", current ? binding.account : candidate);
            accountInput.setSaveEnabled(false); accountInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(64)});
            accountInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            accountInput.setEnabled(!current); controls.add(accountInput);
            if (current) slot.addView(text("仅核验当前账号归属，保留现有 AC、提交证据和训练挑战。", 14));
            action(slot, "申请验证码", this::requestVerification);
            // Restored challenges come from the authenticated server summary, never instance state.
            OjBindingState.Pending pending = binding.pending;
            if (challenge == null && pending != null && (current == OjBindingState.sameAccount(pending.account, binding.account))) {
                if (candidate.isEmpty() || OjBindingState.sameAccount(candidate, pending.account)) challenge = pending;
            }
            if (challenge != null) {
                candidate = challenge.account; accountInput.setText(candidate);
                slot.addView(text("目标账号：" + challenge.account, 15));
                TextView code = text(challenge.code, 22); code.setTextIsSelectable(true); slot.addView(code);
                action(slot, "复制验证码", () -> ((ClipboardManager) getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("OJ 归属验证码", challenge.code)));
                slot.addView(text("将验证码保存到 Codeforces 设置的 First name（名字）或 Organization（组织），保存后返回这里确认。", 14));
                slot.addView(text("有效至 " + new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.CHINA).format(new java.util.Date(challenge.expiresAt * 1000)) + "，重新申请将使旧验证失效。", 12));
                if (binding.bound()) destructiveFields(slot, OjBindingState.sameAccount(challenge.account, binding.account));
                action(slot, current ? "确认核验" : "确认验证并绑定", this::confirm);
            }
        }
        action(slot, "返回账号操作", () -> { mode = "details"; candidate = ""; challenge = null; load(); });
        AppAppearance.paintFields(slot);
    }

    private void edit(String action) {
        mode = action; candidate = "verify-current".equals(action) ? binding.account : ""; challenge = null; load();
    }

    private void destructiveFields(LinearLayout parent, boolean current) {
        parent.addView(text(current ? "请使用当前 ACMForever 登录密码确认归属核验。"
                : "解绑或成功改绑将清理该平台 AC、提交证据、同步状态，并结束进行中的训练挑战。收藏与历史学习资料保留，其他平台不受影响。", 14));
        passwordInput = input(parent, "当前 ACMForever 登录密码", "");
        passwordInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        passwordInput.setSaveEnabled(false); passwordInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(256)}); controls.add(passwordInput);
        confirmation = new CheckBox(this); confirmation.setText(current ? "我确认核验当前账号的归属" : "我已确认平台、账号和以上数据影响");
        confirmation.setSaveEnabled(false); parent.addView(confirmation); controls.add(confirmation);
    }

    private String password() { return passwordInput == null ? "" : passwordInput.getText().toString(); }
    private boolean confirmed() { return confirmation != null && confirmation.isChecked(); }

    private void requestVerification() {
        try {
            candidate = accountInput.getText().toString().trim();
            JSONObject payload = binding.verificationBody(candidate);
            perform("POST", "verification", payload, result -> { challenge = new OjBindingState.Pending(result); candidate = challenge.account; load(); });
        } catch (Exception e) { notice.show("申请验证", e); }
    }
    private void confirm() {
        try {
            if (!OjBindingState.sameAccount(candidate, accountInput.getText().toString().trim())) throw new IllegalArgumentException("目标账号已修改，请重新申请验证码。");
            perform("POST", "confirm", binding.confirmationBody(challenge, password(), confirmed(), System.currentTimeMillis() / 1000), this::completed);
        } catch (Exception e) { notice.show("确认绑定", e); }
    }
    private void unbind() {
        try { perform("DELETE", "", binding.unbindBody(password(), confirmed()), this::completed); }
        catch (Exception e) { notice.show("确认解绑", e); }
    }
    private void sync() { perform("POST", "sync", new JSONObject(), this::completed); }
    private void completed(JSONObject result) { mode = "details"; candidate = ""; challenge = null; expectedAccount = null; load(); }

    private interface Result { void show(JSONObject result) throws Exception; }
    private void perform(String method, String action, JSONObject payload, Result done) {
        if (writing || !validOwner() || binding == null) return;
        writing = true; notice.hide(); int token = serial; String path = binding.path(action);
        for (View control : controls) control.setEnabled(false);
        if (passwordInput != null) passwordInput.setText("");
        if (confirmation != null) confirmation.setChecked(false);
        io.execute(() -> {
            JSONObject result = null; Exception failure = null;
            try {
                synchronized (api) {
                    if (!validOwner()) throw new ApiClient.ApiException(401, "登录账号已切换，请返回重新登录。", false);
                    result = api.writeObject(method, path, payload);
                }
            } catch (Exception e) { failure = e; }
            JSONObject response = result; Exception issue = failure;
            runOnUiThread(() -> {
                writing = false;
                if (isDestroyed() || token != serial) return;
                for (View control : controls) control.setEnabled(true);
                if (accountInput != null && "verify-current".equals(mode)) accountInput.setEnabled(false);
                if (!validOwner()) { load(); return; }
                if (issue != null) {
                    Exception visible = issue;
                    if (issue instanceof ApiClient.ApiException) {
                        ApiClient.ApiException error = (ApiClient.ApiException) issue;
                        if (error.details != null && "invalid_password".equals(error.details.optString("code")))
                            visible = new IllegalArgumentException(error.getMessage());
                    }
                    notice.show("账号绑定操作", visible);
                }
                else try { done.show(response); } catch (Exception e) { notice.show("处理结果", e); }
            });
        });
    }

    @Override public void onBackPressed() {
        if (writing) { notice.show("正在处理", new IllegalArgumentException("请等待本次操作结束后返回，避免重复提交。")); return; }
        if (!platform.isEmpty() && !OjBindingState.known(getIntent().getStringExtra("platform"))) {
            platform = ""; mode = "details"; candidate = ""; challenge = null; expectedAccount = null; load();
        } else super.onBackPressed();
    }
    @Override protected void onResume() {
        super.onResume(); if (api != null && !validOwner()) { challenge = null; candidate = ""; load(); }
    }
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out); out.putLong("binding_owner", owner); out.putString("binding_platform", platform);
        out.putString("binding_mode", writing ? "details" : mode); out.putString("binding_expected", expectedAccount);
        out.putString("binding_candidate", writing ? "" : accountInput == null ? candidate : accountInput.getText().toString().trim());
        // No passwords, confirmation checkbox, CSRF or challenge codes in saved state.
    }
}
