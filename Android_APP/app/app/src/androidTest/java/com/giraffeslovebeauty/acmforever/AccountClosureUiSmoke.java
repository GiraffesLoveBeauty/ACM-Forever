package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.*;

/** Test APK only; synthetic transport forbids all production traffic and real account deletion. */
final class AccountClosureUiSmoke {
    private final Instrumentation test;
    private final Context context;
    private ApiClient api; private AcmApplication app; private Activity activity;
    private final List<Activity> pages = new ArrayList<>();
    private volatile boolean enabled, authenticated = true, closed, pending, loseResponse, wrongPassword, delay, rateLimited, receiptRateLimited;
    private volatile String role = "member", account = "90000001";
    private volatile long epoch = 1;
    private volatile int posts, previews, receipts;
    private String requestId = "", receiptToken = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFG";
    private AccountClosureUiSmoke(Instrumentation test) { this.test = test; context = test.getTargetContext(); }
    static void run(Instrumentation test) { new AccountClosureUiSmoke(test).run(); }
    private void run() {
        Bundle output = new Bundle(); int status = Activity.RESULT_CANCELED;
        main(() -> {}); app = (AcmApplication) context.getApplicationContext(); api = app.api(); String base = api.getBaseUrl();
        SharedPreferences prefs = AppAppearance.prefs(context); Map<String, ?> before = new HashMap<>(prefs.getAll());
        try {
            URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
                protected URLConnection openConnection(URL url) throws IOException {
                    if (!"closure.test.invalid".equals(url.getHost())) throw new IOException("External traffic forbidden"); return new Fixture(url);
                }
            } : null);
            prefs.edit().putBoolean("auto_login", false).putBoolean("app_update_automatic", false).apply(); app.vault().clearClosure();
            api.setBaseUrl("https://closure.test.invalid"); api.setNetworkAvailable(() -> true); login("90000001", 1);
            activity = open(MainActivity.class); showAccount(); await(() -> has("账户注销"), "account closure entry");
            main(() -> {
                View a = find("退出登录"), b = find("账户注销"); check(a != null && b != null, "both account actions exist");
                int[] pa = new int[2], pb = new int[2]; a.getLocationOnScreen(pa); b.getLocationOnScreen(pb); check(pb[1] > pa[1], "closure below logout");
            });
            Activity parent = activity; activity = follow(() -> click("账户注销")); await(() -> has("注销窗口关闭"), "feature switch closed");
            check(previews == 0 && posts == 0, "disabled switch makes no preview or submit"); finish(); activity = parent;

            enabled = true; activity = open(AccountClosureActivity.class); await(() -> has("真的要注销吗？"), "confirmation modal");
            await(() -> description("哭泣的猫娘") != null, "crying cat illustration");
            main(() -> {
                View close = find("狠心注销"), cancel = find("点错了喵"); check(close.getWidth() == cancel.getWidth() && close.getHeight() == cancel.getHeight(), "equal decision buttons");
                android.graphics.drawable.GradientDrawable fill = (android.graphics.drawable.GradientDrawable) close.getBackground();
                check(android.graphics.Color.alpha(fill.getColor().getDefaultColor()) == 128, "destructive button half-transparent red");
                EditText password = input(); password.requestFocus(); check(password.onCheckIsTextEditor(), "password editor accepts keyboard");
            }); progress("confirmation and buttons checked"); screenshot("closure-confirm.png");
            click("点错了喵"); check(posts == 0, "cancel never submits"); finish();

            role = "admin"; activity = open(AccountClosureActivity.class); await(() -> has("狠心注销"), "administrator still sees consequences");
            click("狠心注销"); await(() -> has("需要先交接权限"), "administrator prevented"); check(posts == 0, "administrator makes no deletion write"); finish();
            role = "member"; activity = open(AccountClosureActivity.class); await(() -> has("狠心注销"), "member confirmation");
            role = "root"; edit("Test-Password!"); click("狠心注销"); await(() -> has("需要先交接权限"), "fresh role revalidation"); check(posts == 0, "changed administrator blocked before POST"); finish();

            role = "member"; activity = open(AccountClosureActivity.class); await(() -> input() != null, "password required");
            rateLimited = true; int ratePosts = posts, rateReads = receipts; String refusedRequest = requestId;
            edit("Test-Password!"); click("狠心注销"); await(() -> has("本次未执行注销") && app.closure().state().phase == AccountClosureFlow.Phase.ERROR, "submit rate limit is a known refusal");
            check(posts == ratePosts + 1 && receipts == rateReads, "rate limit does not start receipt polling or repeat POST");
            check(app.vault().readClosure().isEmpty() && api.isLoggedIn() && !closed, "rate refusal clears saved receipt and preserves account");
            recreate(); await(() -> has("本次未执行注销"), "rate refusal survives rotation without uncertain state");
            check(posts == ratePosts + 1 && app.vault().readClosure().isEmpty(), "rotation never restores refused receipt or resubmits");
            click("知道了"); rateLimited = false; click("重新检查"); await(() -> input() != null, "manual recheck available after rate limit lifts");
            check(!requestId.equals(refusedRequest) && input().length() == 0 && posts == ratePosts + 1, "recheck creates fresh preview without POST or saved password");
            finish(); resetController(); activity = open(AccountClosureActivity.class); await(() -> input() != null, "fresh controller does not restore refused receipt");
            check(posts == ratePosts + 1 && receipts == rateReads && app.vault().readClosure().isEmpty(), "restart after refusal stays out of receipt recovery");
            progress("rate-limit refusal, rotation, manual recheck and controller restart checked");
            wrongPassword = true; edit("Incorrect-Password!"); click("狠心注销"); await(() -> has("当前密码不正确") && input() != null, "wrong password is not success");
            check(input().length() == 0 && api.isLoggedIn(), "password cleared and original session retained"); wrongPassword = false;
            edit("Test-Password!"); recreate(); await(() -> input() != null, "confirmation survives rotation"); check(input().length() == 0, "password not in instance state");
            prefs.edit().putString("remembered_account", account).putBoolean("auto_login", true).apply();
            check(app.vault().savePassword(api.getBaseUrl(), account, "Test-Password!"), "synthetic opt-in password saved for cleanup test");
            int count = posts; final int inFlight = count + 1; edit("Test-Password!"); delay = true; click("狠心注销");
            await(() -> posts == inFlight, "one in-flight submission"); recreate(); await(() -> has("注销成功"), "success after submit rotation"); delay = false;
            check(posts == count + 1 && !api.isLoggedIn(), "rotation never resubmits; success clears session immediately");
            check(!prefs.getBoolean("auto_login", false) && !prefs.getBoolean("save_password", false), "credentials disabled after closure");
            progress("success, password cleanup and rotation checked"); screenshot("closure-success.png"); click("返回登陆界面"); await(() -> app.closure().state().phase == AccountClosureFlow.Phase.IDLE, "success acknowledged");
            activity = parent; showAccount(); await(() -> has("登录"), "parent account renders login"); check(!has("账户注销"), "logged out account has no closure entry");

            login("90000001", 2); loseResponse = true; closed = false; activity = open(AccountClosureActivity.class); await(() -> input() != null, "lost-response confirmation");
            count = posts; edit("Test-Password!"); click("狠心注销"); await(() -> has("注销成功"), "lost POST response recovered by receipt");
            check(posts == count + 1 && receipts > 0, "only one write with receipt recovery"); click("返回登陆界面"); await(() -> app.closure().state().phase == AccountClosureFlow.Phase.IDLE, "recovery acknowledged"); loseResponse = false;

            login("90000001", 3); closed = false; pending = true; loseResponse = true; activity = open(AccountClosureActivity.class); await(() -> input() != null, "pending confirmation");
            count = posts; edit("Test-Password!"); click("狠心注销"); await(() -> has("尚未确认注销成功"), "pending receipt truthful");
            check(app.closure().state().phase == AccountClosureFlow.Phase.UNCERTAIN && posts == count + 1, "pending receipt not success and no repeated write");
            String saved = app.vault().readClosure(); check(!saved.contains("Test-Password!") && !prefs.getString("closure_cipher", "").contains(receiptToken), "only encrypted receipt persisted");
            recreate(); await(() -> has("尚未确认注销成功"), "rotation recovers pending read"); check(posts == count + 1, "pending rotate never POSTs");
            receiptRateLimited = true; click("查询注销结果"); await(() -> has("请求过于频繁") && app.closure().state().phase == AccountClosureFlow.Phase.UNCERTAIN, "receipt rate limit remains uncertain");
            check(saved.equals(app.vault().readClosure()) && posts == count + 1, "receipt throttle retains encrypted recovery and never resubmits"); receiptRateLimited = false;
            // Simulate loss of the in-memory controller; recover from the encrypted on-device receipt.
            finish(); resetController();
            activity = open(AccountClosureActivity.class); await(() -> has("尚未确认注销成功"), "persistent recovery"); check(posts == count + 1, "persistent recovery only reads");
            login("90000001", 4); pending = false; closed = true; click("查询注销结果"); await(() -> has("注销成功"), "old result displayed");
            check(api.isLoggedIn() && "90000001".equals(api.accountKey()), "new account epoch preserved by old receipt");
            click("返回登陆界面"); await(() -> app.closure().state().phase == AccountClosureFlow.Phase.IDLE, "old receipt acknowledged");
            check(api.isLoggedIn(), "return never logs out replacement account");
            output.putString("stream", "PASS: entry below logout; fresh feature switch; consequences and crying cat; equal 50% red/theme actions; cancel; admin/root and role-change blocks; current password/CSRF/idempotency/receipt/epoch contract; submit RATE_LIMITED clears receipt with manual recheck after rotation/restart, no polling or auto-POST; wrong password; rotation without password or duplicate POST; confirmed success clears credentials; parent login; lost-response receipt recovery; pending truthful; receipt RATE_LIMITED retains recovery; encrypted receipt process-controller recovery; anonymous receipt headers; newer account epoch protected.\n"); status = Activity.RESULT_OK;
        } catch (Throwable e) {
            StringBuilder visible = new StringBuilder(); if (activity != null) main(() -> walk(decor(), v -> { if (v instanceof TextView && !(v instanceof EditText)) visible.append(((TextView) v).getText()).append(" | "); return false; }));
            output.putString("stream", "FAIL: " + android.util.Log.getStackTraceString(e) + "\nUI: " + visible + "\nCounts: posts=" + posts + " previews=" + previews + " receipts=" + receipts);
        } finally {
            for (int i = pages.size() - 1; i >= 0; i--) { Activity page = pages.get(i); main(() -> { ModalDialogs.close(page); page.finish(); }); }
            app.vault().clearClosure(); try { api.logout(); } catch (Exception ignored) {} api.setBaseUrl(base);
            SharedPreferences.Editor restore = prefs.edit().clear();
            for (Map.Entry<String, ?> e : before.entrySet()) { Object v = e.getValue(); String k = e.getKey(); if (v instanceof String) restore.putString(k, (String) v); else if (v instanceof Boolean) restore.putBoolean(k, (Boolean) v); else if (v instanceof Integer) restore.putInt(k, (Integer) v); else if (v instanceof Long) restore.putLong(k, (Long) v); else if (v instanceof Float) restore.putFloat(k, (Float) v); }
            restore.apply(); AppAppearance.load(context);
        }
        test.finish(status, output);
    }
    private void login(String who, long generation) throws Exception { authenticated = true; account = who; epoch = generation; api.login(who, "Test-Password!"); }
    private void resetController() throws Exception { java.lang.reflect.Field field = AcmApplication.class.getDeclaredField("closure"); field.setAccessible(true); field.set(app, new AccountClosureFlow(app)); }
    private void progress(String step) { Bundle message = new Bundle(); message.putString("stream", "STEP: " + step + "\n"); test.sendStatus(1, message); }
    private Activity open(Class<?> type) { Activity page = test.startActivitySync(new Intent(context, type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); pages.add(page); return page; }
    private Activity follow(Runnable work) { Instrumentation.ActivityMonitor monitor = test.addMonitor(AccountClosureActivity.class.getName(), null, false); try { work.run(); Activity page = test.waitForMonitorWithTimeout(monitor, 8000); check(page != null, "closure Activity started"); pages.add(page); return page; } finally { test.removeMonitor(monitor); } }
    private void recreate() { Activity old = activity; activity = follow(() -> main(old::recreate)); }
    private void finish() { main(() -> { ModalDialogs.close(activity); activity.finish(); }); test.waitForIdleSync(); }
    private View decor() { WeakReferenceHolder holder = new WeakReferenceHolder(); main(() -> { try { java.lang.reflect.Field f = ModalDialogs.class.getDeclaredField("visible"); f.setAccessible(true); Object ref = ((Map<?, ?>) f.get(null)).get(activity); AlertDialog dialog = ref instanceof java.lang.ref.WeakReference ? (AlertDialog) ((java.lang.ref.WeakReference<?>) ref).get() : null; holder.view = dialog != null && dialog.isShowing() ? dialog.getWindow().getDecorView() : activity.getWindow().getDecorView(); } catch (Exception e) { throw new AssertionError(e); } }); return holder.view; }
    private static final class WeakReferenceHolder { View view; }
    private View walk(View view, Predicate<View> match) { if (view.getVisibility() != View.VISIBLE) return null; if (match.test(view)) return view; if (view instanceof ViewGroup) { ViewGroup group = (ViewGroup) view; for (int i = 0; i < group.getChildCount(); i++) { View found = walk(group.getChildAt(i), match); if (found != null) return found; } } return null; }
    private View find(String value) { return walk(decor(), v -> v instanceof TextView && value.contentEquals(((TextView) v).getText())); }
    private View description(String value) { return walk(decor(), v -> value.contentEquals(v.getContentDescription() == null ? "" : v.getContentDescription())); }
    private boolean has(String value) { return walk(decor(), v -> v instanceof TextView && !(v instanceof EditText) && ((TextView) v).getText().toString().contains(value)) != null; }
    private EditText input() { return (EditText) walk(decor(), v -> v instanceof EditText); }
    private void edit(String text) { main(() -> { check(input() != null, "current password input"); input().setText(text); }); }
    private void click(String name) { main(() -> { View v = find(name); while (v != null && !v.isClickable() && v.getParent() instanceof View) v = (View) v.getParent(); check(v != null && v.isEnabled(), "button " + name); v.performClick(); }); test.waitForIdleSync(); }
    private void main(Runnable work) { if (Looper.myLooper() == Looper.getMainLooper()) { work.run(); return; } Throwable[] failure = {null}; test.runOnMainSync(() -> { try { work.run(); } catch (Throwable e) { failure[0] = e; } }); if (failure[0] != null) throw new AssertionError(failure[0]); }
    private void await(BooleanSupplier ready, String name) throws Exception { long until = SystemClock.uptimeMillis() + 15000; while (SystemClock.uptimeMillis() < until) { test.waitForIdleSync(); boolean[] done = {false}; main(() -> done[0] = ready.getAsBoolean()); if (done[0]) return; Thread.sleep(80); } throw new AssertionError("Timeout: " + name); }
    private void showAccount() { main(() -> { try { java.lang.reflect.Method method = MainActivity.class.getDeclaredMethod("show", String.class); method.setAccessible(true); method.invoke(activity, "account"); } catch (Exception e) { throw new AssertionError(e); } }); }
    private void screenshot(String name) throws Exception {
        // Render the real window hierarchy on the UI thread for a deterministic preview.
        android.graphics.Bitmap[] image = {null}; main(() -> { View view = decor(); image[0] = android.graphics.Bitmap.createBitmap(view.getWidth(), view.getHeight(), android.graphics.Bitmap.Config.ARGB_8888); view.draw(new android.graphics.Canvas(image[0])); });
        try (FileOutputStream file = new FileOutputStream(new File(context.getExternalFilesDir(null), name))) { image[0].compress(android.graphics.Bitmap.CompressFormat.PNG, 100, file); } finally { image[0].recycle(); }
    }
    private static void check(boolean ok, String name) { if (!ok) throw new AssertionError(name); }
    private final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream(); private String response; private int code = 200;
        Fixture(URL url) { super(url); } public void connect() {} public void disconnect() {} public boolean usingProxy() { return false; }
        public OutputStream getOutputStream() { return bytes; }
        public int getResponseCode() throws IOException { prepare(); return code; }
        public Map<String, List<String>> getHeaderFields() { return url.getPath().equals("/api/auth/login") ? Collections.singletonMap("Set-Cookie", Collections.singletonList("session=closure-fixture; Path=/; Secure; HttpOnly; Max-Age=600")) : Collections.emptyMap(); }
        public InputStream getErrorStream() { return stream(response); }
        public InputStream getInputStream() throws IOException { prepare(); return stream(response); }
        private InputStream stream(String value) { return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8)); }
        private void prepare() throws IOException {
            if (response != null) return;
            String path = url.getPath();
            try {
                if (path.equals("/api/auth/login") || path.equals("/api/auth/logout")) { response = "{\"success\":true}"; return; }
                if (path.equals("/api/auth/me")) { response = new JSONObject().put("authenticated", authenticated).put("csrf_token", "closure-csrf").put("qq_id", account).put("role", role).put("account_epoch", epoch).put("account_closure_enabled", enabled).toString(); return; }
                if (path.equals("/api/me/account-closure/preview")) {
                    check(enabled, "disabled server never previewed"); requestId = String.format(java.util.Locale.ROOT, "%032x", ++previews);
                    response = new JSONObject().put("request_id", requestId).put("receipt_token", receiptToken).put("account_epoch", epoch)
                            .put("policy_version", "closure-v2").put("receipt_expires_at", System.currentTimeMillis() / 1000 + 86400).put("can_close", "member".equals(role))
                            .put("retention_notice", new JSONObject().put("text", "注销即时生效且不可恢复。删除站内私有训练记录、源码、收藏、云端草稿与平台绑定；已发布的话题、评论、Wiki 历史和公共引用图片继续保留，作者显示为已注销用户。不会删除外部 OJ 账号或退出 QQ 群。审计保留180天，备份最长保留30天。"))
                            .put("blockers", new JSONArray()).toString(); return;
                }
                if (path.equals("/api/me/account-closure")) {
                    posts++; check("POST".equals(getRequestMethod()), "closure verb");
                    check("closure-csrf".equals(getRequestProperty("X-CSRF-Token")), "closure CSRF");
                    check(requestId.equals(getRequestProperty("Idempotency-Key")) && receiptToken.equals(getRequestProperty("X-Closure-Receipt")), "preview-bound secret headers");
                    JSONObject body = new JSONObject(bytes.toString("UTF-8")); check(body.length() == 4 && "注销账号".equals(body.getString("confirm_text")) && body.getLong("expected_account_epoch") == epoch && "closure-v2".equals(body.getString("policy_version")), "exact account intent");
                    if (rateLimited) { code = 429; response = "{\"code\":\"RATE_LIMITED\",\"message\":\"操作过于频繁，请稍后再试。\"}"; return; }
                    if (wrongPassword) { code = 403; response = "{\"code\":\"REAUTH_FAILED\",\"message\":\"当前密码不正确。\"}"; return; }
                    check("Test-Password!".equals(body.getString("current_password")), "current password");
                    if (delay) Thread.sleep(1800);
                    if (!pending) { closed = true; authenticated = false; }
                    response = receipt(); if (loseResponse) throw new java.net.SocketTimeoutException("Synthetic lost POST response"); return;
                }
                if (path.startsWith("/api/account-closures/")) {
                    receipts++; check(receiptToken.equals(getRequestProperty("X-Closure-Receipt")), "secret receipt header");
                    check(getRequestProperty("Cookie") == null && getRequestProperty("X-CSRF-Token") == null, "receipt has no unrelated account credentials");
                    if (receiptRateLimited) { code = 429; response = "{\"code\":\"RATE_LIMITED\",\"message\":\"操作过于频繁，请稍后再试。\"}"; return; }
                    response = receipt(); return;
                }
                if (path.equals("/api/me/profile")) { response = "{\"user\":{\"name\":\"Synthetic member\"},\"platform_counts\":{},\"recent_ac\":[],\"bindings\":[]}"; return; }
                if (path.equals("/api/mobile/v1/capabilities")) { response = "{\"api_version\":1,\"features\":{}}"; return; }
                response = path.equals("/api/forum/posts") ? "{\"rows\":[],\"total\":0}" : "[]";
            } catch (IOException e) { throw e; } catch (Exception e) { throw new IOException(e); }
        }
        private String receipt() throws Exception { return new JSONObject().put("request_id", requestId).put("policy_version", "closure-v2").put("status", closed ? "closed" : "pending").put("committed_at", closed ? System.currentTimeMillis() / 1000 : 0).put("cleanup_state", closed ? "pending" : "not_started").toString(); }
    }
}
