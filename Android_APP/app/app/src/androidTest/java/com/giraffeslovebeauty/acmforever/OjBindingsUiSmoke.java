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

/** Test APK only: exercise real binding pages against synthetic authenticated responses. */
final class OjBindingsUiSmoke {
    private final Instrumentation test;
    private final Context context;
    private ApiClient api;
    private Activity activity;
    private final List<Activity> pages = new ArrayList<>();
    private final List<String> requests = Collections.synchronizedList(new ArrayList<>());
    private volatile String account = "", target = "", proof = "", sync = "never";
    private volatile int writes;
    private volatile boolean rejectConfirmation, verificationUnavailable;
    private OjBindingsUiSmoke(Instrumentation test) { this.test = test; context = test.getTargetContext(); }
    static void run(Instrumentation test) { new OjBindingsUiSmoke(test).run(); }

    private void run() {
        Bundle output = new Bundle(); int status = Activity.RESULT_CANCELED;
        main(() -> { }); // Wait until Application.onCreate has configured the shared client.
        AcmApplication app = (AcmApplication) context.getApplicationContext(); api = app.api(); String base = api.getBaseUrl();
        SharedPreferences prefs = AppAppearance.prefs(context); Map<String, ?> before = new HashMap<>(prefs.getAll());
        try {
            URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
                protected URLConnection openConnection(URL url) throws IOException {
                    if (!"bindings.test.invalid".equals(url.getHost())) throw new IOException("External traffic forbidden");
                    return new Fixture(url);
                }
            } : null);
            prefs.edit().putBoolean("auto_login", false).putBoolean("app_update_automatic", false).apply();
            api.setBaseUrl("https://bindings.test.invalid"); api.setNetworkAvailable(() -> true); api.login("90000001", "Synthetic-Test!");
            activity = open(MainActivity.class, new Intent()); show("mine");
            await(() -> has("各平台通过题数"), "own public profile"); clickDescription("切换平台 Codeforces");
            await(() -> description("Codeforces绑定账号") != null, "unbound count replaced by bind button");
            Activity parent = activity;
            activity = follow(OjBindingsActivity.class, () -> clickDescription("Codeforces绑定账号"));
            await(() -> has("申请验证码"), "native binding form");
            edit("OJ 账号标识", "FirstHandle"); click("申请验证码");
            await(() -> has("确认验证并绑定"), "proof instructions"); check(input("当前 ACMForever 登录密码") == null, "first binding asks for no password");
            int proofWrites = writes; String originalProof = proof;
            edit("OJ 账号标识", "bad/name"); click("申请验证码"); await(() -> has("不要填写网址或密码"), "new target fails local validation");
            click("确认验证并绑定"); await(() -> has("目标账号已修改"), "old proof cannot confirm an invalid changed target");
            check(writes == proofWrites && account.isEmpty() && originalProof.equals(proof), "invalid reapplication never binds old proof target");
            edit("OJ 账号标识", "OtherHandle"); verificationUnavailable = true; click("申请验证码");
            await(() -> has("请求超时"), "new verification fails before server receives it"); verificationUnavailable = false;
            click("确认验证并绑定"); await(() -> has("目标账号已修改"), "old proof cannot confirm changed target after transport failure");
            check(writes == proofWrites && account.isEmpty() && originalProof.equals(proof), "failed reapplication preserves original proof without binding another account");
            edit("OJ 账号标识", " FirstHandle ");
            screenshot("oj-bindings-proof.png");
            click("确认验证并绑定"); await(() -> has("当前账号：FirstHandle"), "first bind saved");
            main(activity::onBackPressed); activity = parent;
            await(() -> activity.hasWindowFocus() && description("Codeforces绑定账号") == null && has("累计通过题数") && has("0"), "returned profile refreshes bound zero AC and hides bind");
            show("account"); await(() -> has("OJ 账号绑定"), "account entrance");
            parent = activity; activity = follow(OjBindingsActivity.class, () -> click("OJ 账号绑定"));
            await(() -> description("Codeforces修改绑定") != null && has("FirstHandle"), "bound username and modify action");
            screenshot("oj-bindings-list.png");
            clickDescription("Codeforces修改绑定"); await(() -> has("改绑账号"), "modify opens platform actions");
            click("改绑账号"); await(() -> has("申请验证码"), "replace form");
            edit("OJ 账号标识", "SecondHandle"); click("申请验证码"); await(() -> has("确认验证并绑定"), "replace proof");
            int beforeWrite = writes; click("确认验证并绑定"); check(writes == beforeWrite, "replacement cannot skip password and confirmation");
            edit("当前 ACMForever 登录密码", "Synthetic-Test!"); checked(true);
            recreate(); await(() -> has("确认验证并绑定"), "pending proof restored from server");
            main(() -> { check(input("当前 ACMForever 登录密码").length() == 0, "password not restored"); CheckBox box = (CheckBox) walk(decor(), v -> v instanceof CheckBox); check(!box.isChecked(), "destructive checkbox not restored"); });
            rejectConfirmation = true; edit("当前 ACMForever 登录密码", "Synthetic-Test!"); checked(true); click("确认验证并绑定");
            await(() -> has("公开资料中未找到验证码"), "server rejection visible"); check("FirstHandle".equals(account), "failed verification keeps prior binding");
            rejectConfirmation = false; edit("当前 ACMForever 登录密码", "Synthetic-Test!"); checked(true); click("确认验证并绑定");
            await(() -> has("当前账号：SecondHandle"), "replace success"); click("同步记录"); await(() -> has("同步已排队"), "manual sync uses existing endpoint");
            click("解绑账号"); await(() -> has("确认解绑"), "unbind form"); beforeWrite = writes;
            edit("当前 ACMForever 登录密码", "Synthetic-Test!"); click("确认解绑"); check(writes == beforeWrite, "unbind needs explicit checkbox");
            checked(true); click("确认解绑"); await(() -> has("尚未绑定账号") && has("申请验证码"), "unbind returns to bind form");
            main(activity::onBackPressed); await(() -> description("洛谷绑定账号") != null, "back to list");
            clickDescription("洛谷绑定账号"); await(() -> has("该平台尚未开放本人归属验证"), "unsupported platform tells truth");
            check(!has("申请验证码"), "no fabricated platform ownership flow");
            api.logout(); main(() -> { test.callActivityOnPause(activity); test.callActivityOnResume(activity); });
            await(() -> has("登录已失效") || has("请返回并重新登录") || has("无访问权限"), "session loss removes private controls");
            check(!has("申请验证码") && !has("确认解绑"), "old account cannot write after logout");
            output.putString("stream", "PASS: real profile bind CTA; no CTA for bound zero-AC; account settings username/modify; changed verification target blocked after local validation and pre-server transport failures; original proof target can still bind when explicitly selected; CF first bind, rebind with current password and explicit confirmation; pending proof restored after Activity recreation without password/checkbox; failed proof retains old account; CSRF and expected-account payloads; manual sync; confirmed unbind; unsupported-platform explanation; session-loss guard; return refresh.\n");
            status = Activity.RESULT_OK;
        } catch (Throwable failure) {
            StringBuilder visible = new StringBuilder();
            if (activity != null) main(() -> walk(decor(), v -> { if (v instanceof TextView) visible.append(((TextView) v).getText()).append(" | "); return false; }));
            try { if (activity != null) screenshot("oj-bindings-failure.png"); } catch (Exception ignored) { }
            output.putString("stream", "FAIL: " + android.util.Log.getStackTraceString(failure) + "\nUI: " + visible + "\nRequests: " + requests);
        }
        finally {
            for (int i = pages.size() - 1; i >= 0; i--) { Activity page = pages.get(i); main(() -> { ModalDialogs.close(page); page.finish(); }); }
            try { api.logout(); } catch (Exception ignored) { }
            api.setBaseUrl(base);
            SharedPreferences.Editor restore = prefs.edit().clear();
            for (Map.Entry<String, ?> entry : before.entrySet()) { Object v = entry.getValue(); String k = entry.getKey();
                if (v instanceof String) restore.putString(k, (String) v); else if (v instanceof Boolean) restore.putBoolean(k, (Boolean) v);
                else if (v instanceof Integer) restore.putInt(k, (Integer) v); else if (v instanceof Long) restore.putLong(k, (Long) v); else if (v instanceof Float) restore.putFloat(k, (Float) v);
            }
            restore.apply(); AppAppearance.load(context);
        }
        test.finish(status, output);
    }
    private Activity open(Class<?> type, Intent intent) {
        Activity page = test.startActivitySync(intent.setClass(context, type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); pages.add(page); return page;
    }
    private Activity follow(Class<?> type, Runnable click) {
        Instrumentation.ActivityMonitor monitor = test.addMonitor(type.getName(), null, false);
        try { click.run(); Activity page = test.waitForMonitorWithTimeout(monitor, 8000); check(page != null, "page opened " + type.getSimpleName()); pages.add(page); return page; }
        finally { test.removeMonitor(monitor); }
    }
    private void recreate() { Activity old = activity; activity = follow(OjBindingsActivity.class, () -> main(old::recreate)); }
    private void screenshot(String name) throws Exception { android.graphics.Bitmap image = test.getUiAutomation().takeScreenshot(); try (FileOutputStream out = new FileOutputStream(new File(context.getExternalFilesDir(null), name))) { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, out); } finally { image.recycle(); } }
    private void show(String screen) { main(() -> { try { java.lang.reflect.Method method = MainActivity.class.getDeclaredMethod("show", String.class); method.setAccessible(true); method.invoke(activity, screen); } catch (Exception e) { throw new AssertionError(e); } }); }
    private View decor() { return activity.getWindow().getDecorView(); }
    private View walk(View view, Predicate<View> match) { if (view.getVisibility() != View.VISIBLE) return null; if (match.test(view)) return view; if (view instanceof ViewGroup) { ViewGroup group = (ViewGroup) view; for (int i = 0; i < group.getChildCount(); i++) { View found = walk(group.getChildAt(i), match); if (found != null) return found; } } return null; }
    private View description(String value) { return walk(decor(), v -> value.contentEquals(v.getContentDescription() == null ? "" : v.getContentDescription())); }
    private EditText input(String hint) { return (EditText) walk(decor(), v -> v instanceof EditText && hint.contentEquals(((EditText) v).getHint())); }
    private boolean has(String value) { return walk(decor(), v -> v instanceof TextView && ((TextView) v).getText().toString().contains(value)) != null; }
    private void edit(String hint, String value) { main(() -> { EditText input = input(hint); check(input != null, "input " + hint); input.setText(value); }); }
    private void checked(boolean value) { main(() -> ((CheckBox) walk(decor(), v -> v instanceof CheckBox)).setChecked(value)); }
    private void click(String value) { main(() -> { View button = walk(decor(), v -> v instanceof TextView && value.contentEquals(((TextView) v).getText())); while (button != null && !button.isClickable() && button.getParent() instanceof View) button = (View) button.getParent(); check(button != null && button.isEnabled(), "button " + value); button.performClick(); }); test.waitForIdleSync(); }
    private void clickDescription(String value) { main(() -> { View view = description(value); check(view != null && view.isEnabled(), "description " + value); view.performClick(); }); test.waitForIdleSync(); }
    private void main(Runnable task) { Throwable[] issue = {null}; test.runOnMainSync(() -> { try { task.run(); } catch (Throwable e) { issue[0] = e; } }); if (issue[0] != null) throw new AssertionError(issue[0]); }
    private void await(BooleanSupplier ready, String label) throws Exception { long until = SystemClock.uptimeMillis() + 10000; while (SystemClock.uptimeMillis() < until) { test.waitForIdleSync(); boolean[] done = {false}; main(() -> done[0] = ready.getAsBoolean()); if (done[0]) return; Thread.sleep(70); } throw new AssertionError("Timeout: " + label); }
    private static void check(boolean ok, String label) { if (!ok) throw new AssertionError(label); }

    private JSONObject pending() throws Exception { return new JSONObject().put("account", target).put("verification_id", proof).put("code", "ACM-TEST-CODE").put("expires_at", System.currentTimeMillis() / 1000 + 600); }
    private JSONObject profile() throws Exception {
        JSONArray bindings = new JSONArray();
        for (String id : OjBindingState.PLATFORMS) {
            boolean cf = "codeforces".equals(id);
            JSONObject entry = new JSONObject().put("platform", id).put("account", cf ? account : "")
                    .put("self_service", cf).put("sync_status", cf ? sync : "never")
                    .put("message", cf && "queued".equals(sync) ? "同步已排队。" : "绑定状态");
            if (cf && !proof.isEmpty()) entry.put("verification", pending()); bindings.put(entry);
        }
        return new JSONObject().put("user", new JSONObject().put("name", "Synthetic member").put("cf_handle", account))
                .put("bindings", bindings).put("platform_counts", new JSONObject()).put("total_count", 0).put("recent_ac", new JSONArray());
    }
    private final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Fixture(URL url) { super(url); } public void connect() { } public void disconnect() { } public boolean usingProxy() { return false; }
        public OutputStream getOutputStream() { return bytes; }
        public int getResponseCode() throws IOException {
            if (verificationUnavailable && url.getPath().endsWith("/verification")) throw new SocketTimeoutException("Synthetic verification request did not reach server");
            return rejectConfirmation && url.getPath().endsWith("/confirm") ? 400 : 200;
        }
        public Map<String, List<String>> getHeaderFields() { return url.getPath().endsWith("/login") ? Collections.singletonMap("Set-Cookie", Collections.singletonList("session=synthetic-binding; Path=/; Secure; HttpOnly; Max-Age=600")) : Collections.emptyMap(); }
        public InputStream getErrorStream() { return stream("{\"message\":\"公开资料中未找到验证码\"}"); }
        public InputStream getInputStream() throws IOException {
            String path = url.getPath();
            requests.add(getRequestMethod() + " " + path);
            try {
                if (path.equals("/api/auth/login") || path.equals("/api/auth/logout")) return stream("{\"success\":true}");
                if (path.equals("/api/auth/me")) return stream("{\"authenticated\":true,\"csrf_token\":\"binding-csrf\",\"qq_id\":\"90000001\",\"role\":\"member\"}");
                if (path.equals("/api/me/profile")) return stream(profile().toString());
                if (path.startsWith("/api/forum/mine/") || path.equals("/api/forum/drafts")) return stream("[]");
                if (path.equals("/api/mobile/v1/capabilities")) return stream("{\"api_version\":1,\"features\":{}}");
                if (path.equals("/api/forum/categories")) return stream("[]");
                if (path.equals("/api/forum/posts")) return stream("{\"rows\":[],\"total\":0}");
                if (path.startsWith("/api/me/bindings/")) {
                    check("binding-csrf".equals(getRequestProperty("X-CSRF-Token")), "binding CSRF"); writes++;
                    JSONObject payload = new JSONObject(bytes.toString("UTF-8"));
                    if (path.endsWith("/verification")) {
                        target = payload.getString("account"); proof = "proof-" + writes; return stream(pending().toString());
                    }
                    if (path.endsWith("/confirm")) {
                        check(proof.equals(payload.getString("verification_id")), "current server proof");
                        if (!account.isEmpty()) check(payload.getBoolean("confirmed") && "Synthetic-Test!".equals(payload.getString("password")) && account.equals(payload.getString("current_account")), "rebind explicit confirmation and expected account");
                        else check(!payload.has("password"), "first bind sends no password");
                        account = target; proof = ""; return stream("{\"success\":true,\"sync_status\":\"queued\"}");
                    }
                    if ("DELETE".equals(getRequestMethod())) {
                        check(payload.getBoolean("confirmed") && "Synthetic-Test!".equals(payload.getString("password")) && account.equals(payload.getString("current_account")), "unbind confirmation and expected account");
                        account = ""; proof = ""; sync = "never"; return stream("{\"success\":true}");
                    }
                    if (path.endsWith("/sync")) { sync = "queued"; return stream("{\"success\":true,\"sync_status\":\"queued\"}"); }
                }
                return stream("{}");
            } catch (Exception e) { throw new IOException(e); }
        }
        private InputStream stream(String value) { return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8)); }
    }
}
