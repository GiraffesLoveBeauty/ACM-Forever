package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;

/** User-confirmed APK update from a project-controlled HTTPS server. */
final class UpdateManager {
    private final Activity activity;
    private final ExecutorService io;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private long downloadId = -1;
    private Uri pendingApk;
    private boolean waitingForInstallPermission = false;
    private String expectedSha256 = "";
    private boolean closed = false;
    private boolean checking;
    private AlertDialog checkingDialog;
    private long expectedVersion;
    private boolean verifying;
    private AlertDialog updatePrompt;

    UpdateManager(Activity activity, ExecutorService io) {
        this.activity = activity;
        this.io = io;
    }

    static String checkedManifestUrl(String value) {
        String raw = value == null ? "" : value.trim();
        if (raw.isEmpty()) return "";
        return checkedHttpsUrl(raw);
    }

    private static String checkedHttpsUrl(String value) {
        try {
            URI uri = new URI(value);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getFragment() != null) {
                throw new IllegalArgumentException("版本清单与 APK 必须使用 HTTPS 地址。");
            }
            return uri.toString();
        } catch (java.net.URISyntaxException e) {
            throw new IllegalArgumentException("更新地址格式无效。", e);
        }
    }

    void check(String manifestUrl) {
        if (checking || closed || updatePrompt != null) return;
        if (verifying || pendingApk != null) { notice("正在处理已下载的更新。"); return; }
        if (downloadId != -1) { notice("已有更新正在下载。"); return; }
        String address;
        try { address = checkedManifestUrl(manifestUrl); }
        catch (Exception e) { notice(e.getMessage()); return; }
        if (!networkAvailable()) { showFailure("无网络"); return; }
        if (address.isEmpty()) { showFailure("无API接口"); return; }
        checking = true;
        checkingDialog = new ModalDialogs.Builder(activity).setTitle("检查更新").setMessage("正在检查新版本…").setCancelable(false).show();
        io.execute(() -> {
            try {
                if (!networkAvailable()) throw new ApiClient.NoNetworkException();
                URL url = new URL(address);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(15000);
                connection.setInstanceFollowRedirects(false);
                connection.setRequestProperty("Accept", "application/json");
                String body;
                try {
                    int status = connection.getResponseCode();
                    if (status != 200) throw new ApiClient.ApiException(status, "版本清单HTTP " + status, false);
                    try (InputStream stream = connection.getInputStream()) {
                        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                        byte[] chunk = new byte[4096];
                        int count;
                        while ((count = stream.read(chunk)) != -1) {
                            if (buffer.size() + count > 32768) throw new IllegalStateException("版本清单过大。");
                            buffer.write(chunk, 0, count);
                        }
                        body = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                    }
                } finally { connection.disconnect(); }
                JSONObject manifest = new JSONObject(body);
                String packageName = manifest.getString("packageName");
                if (!activity.getPackageName().equals(packageName)) throw new IllegalStateException("更新包名与当前 App 不一致。");
                long versionCode = manifest.getLong("versionCode");
                String versionName = manifest.getString("versionName");
                if (versionCode < 1 || !versionName.matches("[0-9]+\\.[0-9]+(?:\\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?")) throw new IllegalStateException("更新版本无效。");
                String apkUrl = checkedHttpsUrl(manifest.getString("apkUrl"));
                String sha = manifest.getString("sha256").toLowerCase(Locale.ROOT);
                if (!sha.matches("[0-9a-f]{64}")) throw new IllegalStateException("版本清单缺少有效 SHA-256。");
                long current = Build.VERSION.SDK_INT >= 28
                        ? activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).getLongVersionCode()
                        : activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionCode;
                if (versionCode <= current) { ui.post(() -> { finishCheck(); notice("已是最新版"); }); return; }
                String notes = manifest.optString("notes", "本次更新没有附加说明。");
                ui.post(() -> {
                    if (closed) return;
                    finishCheck();
                    updatePrompt = new ModalDialogs.Builder(activity).setTitle("发现新版本 " + versionName)
                            .setMessage(notes + "\n\n将下载 APK 并由安卓系统安装器完成更新。")
                            .setNegativeButton("稍后", null)
                            .setPositiveButton("更新" + versionName + "版本", (dialog, which) -> startDownload(apkUrl, sha, versionCode))
                            .create();
                    updatePrompt.setOnDismissListener(dialog -> updatePrompt = null);
                    ModalDialogs.show(updatePrompt);
                });
            } catch (Exception e) { ui.post(() -> { finishCheck(); showFailure(!networkAvailable() ? "无网络" : FailureState.title(e)); }); }
        });
    }

    private void startDownload(String apkUrl, String sha, long versionCode) {
        if (closed || verifying || pendingApk != null) return;
        if (downloadId != -1) { notice("已有更新正在下载。"); return; }
        try {
            expectedSha256 = sha;
            expectedVersion = versionCode;
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(apkUrl));
            request.setTitle("ACMforever 更新 " + versionCode);
            request.setDescription("下载完成后会校验文件并请求安装确认");
            request.setMimeType("application/vnd.android.package-archive");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalFilesDir(activity, Environment.DIRECTORY_DOWNLOADS,
                    "acmforever-" + versionCode + "-" + System.currentTimeMillis() + ".apk");
            DownloadManager manager = (DownloadManager) activity.getSystemService(Context.DOWNLOAD_SERVICE);
            downloadId = manager.enqueue(request);
            notice("已开始下载。进度可在系统通知中查看。");
            ui.postDelayed(this::pollDownload, 1000);
        } catch (Exception e) { downloadId = -1; notice("下载启动失败：" + e.getMessage()); }
    }

    private void pollDownload() {
        if (closed || downloadId == -1) return;
        DownloadManager manager = (DownloadManager) activity.getSystemService(Context.DOWNLOAD_SERVICE);
        DownloadManager.Query query = new DownloadManager.Query().setFilterById(downloadId);
        try (Cursor cursor = manager.query(query)) {
            if (cursor == null || !cursor.moveToFirst()) { downloadId = -1; notice("下载任务不存在。"); return; }
            int status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
            if (status == DownloadManager.STATUS_SUCCESSFUL) {
                Uri uri = manager.getUriForDownloadedFile(downloadId);
                downloadId = -1;
                if (uri == null) { notice("下载完成但找不到 APK。"); return; }
                verifyAndInstall(uri);
            } else if (status == DownloadManager.STATUS_FAILED) {
                downloadId = -1;
                showFailure(!networkAvailable() ? "无网络" : "APK下载失败");
            } else ui.postDelayed(this::pollDownload, 1000);
        } catch (Exception e) { downloadId = -1; notice("下载状态读取失败：" + e.getMessage()); }
    }

    private void verifyAndInstall(Uri apk) {
        verifying = true;
        final String sha = expectedSha256;
        final long version = expectedVersion;
        io.execute(() -> {
            java.io.File verified = null;
            try {
                java.io.File directory = new java.io.File(activity.getCacheDir(), "updates");
                if (!directory.isDirectory() && !directory.mkdirs()) throw new IllegalStateException("无法创建更新缓存。");
                verified = java.io.File.createTempFile("verified-", ".apk", directory);
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                try (InputStream stream = activity.getContentResolver().openInputStream(apk);
                     java.io.FileOutputStream output = new java.io.FileOutputStream(verified)) {
                    if (stream == null) throw new IllegalStateException("无法读取已下载的 APK。");
                    byte[] buffer = new byte[8192];
                    int count;
                    while ((count = stream.read(buffer)) != -1) { digest.update(buffer, 0, count); output.write(buffer, 0, count); }
                }
                StringBuilder actual = new StringBuilder();
                for (byte b : digest.digest()) actual.append(String.format(Locale.ROOT, "%02x", b & 0xff));
                if (!actual.toString().equals(sha)) throw new IllegalStateException("SHA-256 不匹配，安装已取消。");
                {
                    android.content.pm.PackageManager pm = activity.getPackageManager();
                    int flags = Build.VERSION.SDK_INT >= 28 ? android.content.pm.PackageManager.GET_SIGNING_CERTIFICATES : android.content.pm.PackageManager.GET_SIGNATURES;
                    android.content.pm.PackageInfo candidate = pm.getPackageArchiveInfo(verified.getAbsolutePath(), flags);
                    android.content.pm.PackageInfo installed = pm.getPackageInfo(activity.getPackageName(), flags);
                    if (candidate == null || !activity.getPackageName().equals(candidate.packageName)
                            || (Build.VERSION.SDK_INT >= 28 ? candidate.getLongVersionCode() : candidate.versionCode) != version)
                        throw new IllegalStateException("APK 的实际包名或版本与更新信息不符。");
                    android.content.pm.Signature[] next = Build.VERSION.SDK_INT >= 28 ? candidate.signingInfo.getApkContentsSigners() : candidate.signatures;
                    android.content.pm.Signature[] current = Build.VERSION.SDK_INT >= 28 ? installed.signingInfo.getApkContentsSigners() : installed.signatures;
                    if (next == null || current == null || next.length != current.length
                            || !new java.util.HashSet<>(java.util.Arrays.asList(next)).equals(new java.util.HashSet<>(java.util.Arrays.asList(current))))
                        throw new IllegalStateException("更新 APK 签名不匹配。");
                }
                final Uri privateApk = Uri.parse("content://" + activity.getPackageName() + ".updates/" + verified.getName());
                ui.post(() -> {
                    verifying = false;
                    if (closed) return;
                    pendingApk = privateApk;
                    requestInstall();
                });
            } catch (Exception e) { if (verified != null) verified.delete(); ui.post(() -> { verifying = false; notice("APK 校验失败：" + e.getMessage()); }); }
        });
    }

    private void requestInstall() {
        if (pendingApk == null || closed) return;
        if (!activity.getPackageManager().canRequestPackageInstalls()) {
            waitingForInstallPermission = true;
            new ModalDialogs.Builder(activity).setTitle("允许安装更新")
                    .setMessage("安卓需要你为本 App 允许安装未知应用。授权后仍会显示系统安装确认页。")
                    .setNegativeButton("取消", (dialog, which) -> { waitingForInstallPermission = false; pendingApk = null; })
                    .setPositiveButton("打开设置", (dialog, which) -> {
                        Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:" + activity.getPackageName()));
                        activity.startActivity(settings);
                    }).show();
            return;
        }
        waitingForInstallPermission = false;
        Intent install = new Intent(Intent.ACTION_VIEW);
        install.setDataAndType(pendingApk, "application/vnd.android.package-archive");
        install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try { activity.startActivity(install); pendingApk = null; }
        catch (Exception e) { notice("无法启动系统安装器：" + e.getMessage()); }
    }

    void resumePendingInstall() {
        if (waitingForInstallPermission && pendingApk != null && activity.getPackageManager().canRequestPackageInstalls()) {
            requestInstall();
        }
    }

    private void finishCheck() { checking = false; if (checkingDialog != null) { checkingDialog.dismiss(); checkingDialog = null; } }
    void close() { closed = true; finishCheck(); if(updatePrompt != null) updatePrompt.dismiss(); ui.removeCallbacksAndMessages(null); }

    private void notice(String message) {
        if (closed || activity.isFinishing()) return;
        new ModalDialogs.Builder(activity).setMessage(message).setPositiveButton("知道了", null).show();
    }

    private boolean networkAvailable() {
        android.net.ConnectivityManager manager = (android.net.ConnectivityManager) activity.getSystemService(Context.CONNECTIVITY_SERVICE);
        android.net.NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    private void showFailure(String reason) {
        if (closed || activity.isFinishing()) return;
        android.widget.LinearLayout panel = new android.widget.LinearLayout(activity);
        panel.setOrientation(android.widget.LinearLayout.VERTICAL); panel.setGravity(android.view.Gravity.CENTER);
        panel.setMinimumHeight(Math.round(180 * activity.getResources().getDisplayMetrics().density));
        panel.setBackgroundColor(android.graphics.Color.rgb(255, 244, 244));
        android.widget.TextView text = new android.widget.TextView(activity);
        text.setText(reason); text.setTextSize(16); text.setTextColor(android.graphics.Color.rgb(183, 35, 35));
        panel.addView(text);
        new ModalDialogs.Builder(activity).setView(panel).setPositiveButton("关闭", null).show();
    }
}
