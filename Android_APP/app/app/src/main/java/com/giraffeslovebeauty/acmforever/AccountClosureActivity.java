package com.giraffeslovebeauty.acmforever;

import android.app.AlertDialog;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.widget.*;

/** Only the backend receipt can unlock the farewell page. No password survives recreation. */
public final class AccountClosureActivity extends MobilePageActivity {
    private AccountClosureFlow flow;
    private AccountClosureFlow.State shown;
    private final Runnable changed = this::render;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); createPage("账户注销"); flow = ((AcmApplication) getApplication()).closure();
        // Recreated Activities reattach to the pending process-owned operation.
        if (state == null || flow.state().phase == AccountClosureFlow.Phase.IDLE) flow.enter();
        flow.attach(changed);
    }
    private void render() {
        if (isFinishing() || isDestroyed() || flow == null) return;
        AccountClosureFlow.State state = flow.state(); if (shown == state) return; shown = state;
        ModalDialogs.close(this); resetPage("账户注销"); writing = state.busy();
        LinearLayout panel = card(body);
        if (state.phase == AccountClosureFlow.Phase.CLOSED) {
            panel.addView(text(state.message, 21)); panel.addView(text("注销成功", 16));
            panel.addView(text("原账号登录已清理。已发布公共内容按服务器规则保留；外部 OJ 账号不受影响。", 13));
            Button back = button("返回登陆界面", () -> { flow.acknowledge(); setResult(RESULT_OK); finish(); });
            MobileStyle.button(back, true); panel.addView(back);
            new ModalDialogs.Builder(this).setTitle("注销成功").setView(farewell()).show(); return;
        }
        panel.addView(text(state.message.isEmpty() ? "请仔细阅读注销后果。" : state.message, 16));
        if (state.busy()) { panel.addView(new CodingCatView(this), new LinearLayout.LayoutParams(-1, dp(160))); return; }
        if (state.phase == AccountClosureFlow.Phase.READY) {
            panel.addView(button("查看注销后果", this::confirmation)); confirmation();
        } else if (state.phase == AccountClosureFlow.Phase.UNCERTAIN) {
            panel.addView(text("不会将退出登录或网络错误当作注销成功；保留的加密回执可在重新进入此页面时继续查询。", 13));
            panel.addView(button("查询注销结果", flow::query));
        } else if (state.phase != AccountClosureFlow.Phase.IDLE) {
            panel.addView(button("重新检查", flow::enter));
            new ModalDialogs.Builder(this).setTitle(state.phase == AccountClosureFlow.Phase.DISABLED ? "注销窗口关闭" : "暂时无法注销")
                    .setMessage(state.message).setPositiveButton("知道了", (d, w) -> {}).show();
        }
    }
    private LinearLayout farewell() {
        LinearLayout box = column(); box.addView(text("感谢你的陪伴，我们会加油的，祝你天天开心", 19));
        TextView success = text("注销成功", 15); success.setGravity(Gravity.CENTER); box.addView(success);
        Button back = button("返回登陆界面", () -> {});
        // The normal page helper blocks actions while a modal is visible; this button belongs to it.
        back.setOnClickListener(v -> { if (back.isEnabled()) { back.setEnabled(false); flow.acknowledge(); setResult(RESULT_OK); finish(); } });
        MobileStyle.button(back, true); box.addView(back); return box;
    }
    private void confirmation() {
        AccountClosureFlow.State state = flow.state(); if (state.phase != AccountClosureFlow.Phase.READY || ModalDialogs.isShowing(this)) return;
        LinearLayout box = column();
        box.addView(text("账户信息：站内私有刷题记录、收藏、草稿等私有数据会被删除。", 15));
        box.addView(text(state.ticket.notice, 13));
        box.addView(new CryingCatView(this), new LinearLayout.LayoutParams(-1, dp(118)));
        EditText password = null;
        if (state.ticket.canClose) {
            password = input(box, "当前 ACMForever 登录密码", ""); password.setSaveEnabled(false);
            password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
            password.setFilters(new InputFilter[]{new InputFilter.LengthFilter(256)});
        }
        if (!state.message.isEmpty()) { TextView error = text(state.message, 14); error.setTextColor(ErrorModule.ink()); box.addView(error); }
        Button close = button("狠心注销", () -> {}), cancel = button("点错了喵", () -> {});
        MobileStyle.button(cancel, true); MobileStyle.flat(close); close.setBackgroundTintList(null);
        close.setBackground(MobileStyle.panel(this, 0x80e5484d, 12, 0)); close.setTextColor(MobileStyle.TEXT);
        equalButtons(box, close, cancel);
        AlertDialog dialog = new ModalDialogs.Builder(this).setTitle("真的要注销吗？").setView(box).show();
        EditText credential = password;
        cancel.setOnClickListener(v -> dialog.dismiss());
        close.setOnClickListener(v -> {
            if (!close.isEnabled() || flow.state().phase != AccountClosureFlow.Phase.READY) return;
            String value = credential == null ? "" : credential.getText().toString();
            close.setEnabled(false); cancel.setEnabled(false); if (credential != null) credential.setText("");
            dialog.dismiss(); flow.submit(value);
        });
    }
    @Override protected void onResume() { super.onResume(); if (flow != null) { flow.attach(changed); if (flow.state().phase == AccountClosureFlow.Phase.UNCERTAIN) flow.query(); } }
    @Override protected void onPause() { if (flow != null) flow.detach(changed); super.onPause(); }
    @Override protected void onDestroy() { if (flow != null) flow.detach(changed); super.onDestroy(); }
    @Override public void onBackPressed() {
        if (flow != null && flow.state().busy()) { notice.show("正在处理", new IllegalArgumentException("请等待服务器返回，避免重复提交。")); return; }
        if (flow != null && flow.state().phase == AccountClosureFlow.Phase.CLOSED) { flow.acknowledge(); setResult(RESULT_OK); finish(); return; }
        super.onBackPressed();
    }
}
