package com.giraffeslovebeauty.acmforever;

import android.os.Handler;
import android.os.Looper;
import java.lang.ref.WeakReference;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** Process-owned one-shot submission. Rotation only reattaches; recovery only reads receipts. */
final class AccountClosureFlow {
    enum Phase { IDLE, CHECKING, READY, SUBMITTING, UNCERTAIN, CLOSED, DISABLED, BLOCKED, ERROR }
    static final class State {
        final Phase phase; final AccountClosure.Ticket ticket; final String message;
        State(Phase phase, AccountClosure.Ticket ticket, String message) { this.phase = phase; this.ticket = ticket; this.message = message; }
        boolean busy() { return phase == Phase.CHECKING || phase == Phase.SUBMITTING; }
    }
    private final AcmApplication app;
    private final ApiClient api;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private WeakReference<Runnable> observer = new WeakReference<>(null);
    private volatile State state = new State(Phase.IDLE, null, "");
    private long owner;
    private boolean initialized;
    private final Runnable poll = this::query;

    AccountClosureFlow(AcmApplication app) { this.app = app; api = app.api(); }
    State state() { return state; }
    void attach(Runnable callback) { observer = new WeakReference<>(callback); callback.run(); }
    void detach(Runnable callback) { if (observer.get() == callback) { observer.clear(); main.removeCallbacks(poll); } }
    private void update(Phase phase, AccountClosure.Ticket ticket, String message) {
        state = new State(phase, ticket, message);
        main.post(() -> { Runnable callback = observer.get(); if (callback != null) callback.run();
            if (state.phase == Phase.UNCERTAIN && observer.get() != null && !state.ticket.expired(now())) { main.removeCallbacks(poll); main.postDelayed(poll, 5000); }
        });
    }
    private long now() { return System.currentTimeMillis() / 1000; }
    void enter() {
        if (state.busy()) return;
        if (state.phase == Phase.UNCERTAIN) { query(); return; }
        if (state.phase == Phase.CLOSED) return;
        owner = api.sessionGeneration();
        update(Phase.CHECKING, null, "正在检查注销开关…");
        io.execute(() -> {
            try {
                if (!initialized) {
                    String saved = app.vault().readClosure();
                    if (!saved.isEmpty()) {
                        AccountClosure.Ticket restored = AccountClosure.Ticket.restore(saved);
                        initialized = true; readReceipt(restored); return;
                    }
                    initialized = true;
                }
                synchronized (api) {
                    requireOwner(); JSONObject session = api.refreshSession(); requireOwner();
                    if (!session.optBoolean("account_closure_enabled")) { update(Phase.DISABLED, null, "注销窗口关闭"); return; }
                    AccountClosure.Ticket ticket = new AccountClosure.Ticket(api.getBaseUrl(), api.accountKey(), api.closurePreview(owner));
                    update(Phase.READY, ticket, "");
                }
            } catch (Exception e) { update(AccountClosure.disabled(e) ? Phase.DISABLED : Phase.ERROR, null, AccountClosure.disabled(e) ? "注销窗口关闭" : message(e)); }
        });
    }
    private void requireOwner() {
        if (owner != api.sessionGeneration() || !api.isLoggedIn()) throw new IllegalStateException("登录账号已切换，请返回重新登录。");
    }
    void submit(String password) {
        State before = state; if (before.phase != Phase.READY) return;
        AccountClosure.Ticket ticket = before.ticket;
        update(Phase.SUBMITTING, ticket, "正在验证并提交注销…");
        io.execute(() -> {
            boolean mayHaveSubmitted = false;
            try {
                synchronized (api) {
                    requireOwner(); JSONObject session = api.refreshSession(); requireOwner();
                    if (!session.optBoolean("account_closure_enabled")) { update(Phase.DISABLED, null, "注销窗口关闭"); return; }
                    if (api.isAdministrator()) { update(Phase.BLOCKED, null, "管理员无法执行注销，需要先交接权限、降为普通成员。"); return; }
                    JSONObject body = ticket.body(password, now());
                    if (!app.vault().saveClosure(ticket.saved().toString())) throw new IllegalStateException("无法安全保存注销回执，本次未提交，请稍后重试。");
                    mayHaveSubmitted = true;
                    JSONObject result = api.closeAccount(owner, ticket, body);
                    if (ticket.closed(result)) { complete(ticket); return; }
                }
                readReceipt(ticket);
            } catch (Exception e) {
                if (mayHaveSubmitted && !AccountClosure.refused(e)) { readReceipt(ticket); return; }
                if (mayHaveSubmitted) app.vault().clearClosure();
                if (AccountClosure.disabled(e)) update(Phase.DISABLED, null, "注销窗口关闭");
                else if ("ROLE_HANDOVER_REQUIRED".equals(AccountClosure.code(e)) || "LAST_ROOT_PROTECTED".equals(AccountClosure.code(e))) update(Phase.BLOCKED, null, "管理员无法执行注销，需要先交接权限、降为普通成员。");
                else if ("REAUTH_FAILED".equals(AccountClosure.code(e))) update(Phase.READY, ticket, "当前密码不正确，请重新输入。");
                else if (AccountClosure.rateLimited(e)) update(Phase.ERROR, null, "注销请求过于频繁，本次未执行注销。请稍后重新检查。");
                else if (AccountClosure.authenticationRequired(e)) update(Phase.ERROR, null, "登录已失效，本次未执行注销。请返回重新登录后重新检查。");
                else update(Phase.ERROR, null, message(e));
            }
        });
    }
    private static String message(Exception error) {
        if (!(error instanceof ApiClient.ApiException) && error instanceof IllegalArgumentException) return error.getMessage();
        if (!(error instanceof ApiClient.ApiException) && error instanceof IllegalStateException) return error.getMessage();
        return FailureState.title(error);
    }
    void query() {
        State before = state; if (before.phase != Phase.UNCERTAIN) return;
        main.removeCallbacks(poll); update(Phase.CHECKING, before.ticket, "正在查询注销回执…"); io.execute(() -> readReceipt(before.ticket));
    }
    private void readReceipt(AccountClosure.Ticket ticket) {
        try {
            if (ticket.expired(now())) { update(Phase.UNCERTAIN, ticket, "回执已过期，无法确认注销结果。请到网页端或联系管理员核对；不会重新提交注销。"); return; }
            if (ticket.closed(api.closureReceipt(ticket))) { complete(ticket); return; }
            update(Phase.UNCERTAIN, ticket, "服务器尚未确认注销成功，正在等待回执。请勿重复提交。");
        } catch (Exception e) { update(Phase.UNCERTAIN, ticket, "注销结果暂未确认：" + FailureState.title(e) + "。仅查询回执，不会重复提交注销。"); }
    }
    private void complete(AccountClosure.Ticket ticket) {
        synchronized (api) {
            if (api.forgetClosedAccount(ticket)) {
                app.vault().forgetClosedAccount(ticket.origin, ticket.account);
                TrainingReminder.disable(app);
            }
        }
        // Persisted receipt survives process death on this page, so the farewell is recoverable.
        update(Phase.CLOSED, ticket, "感谢你的陪伴，我们会加油的，祝你天天开心");
    }
    void acknowledge() {
        if (state.phase != Phase.CLOSED) return;
        io.execute(() -> { app.vault().clearClosure(); update(Phase.IDLE, null, ""); });
    }
}
