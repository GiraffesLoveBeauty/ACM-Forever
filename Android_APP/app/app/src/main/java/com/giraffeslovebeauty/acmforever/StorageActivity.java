package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.os.Bundle;
import android.os.Environment;
import android.widget.*;

/** Three local storage sections. All accounting and cache deletion run off the UI thread. */
public final class StorageActivity extends MobilePageActivity {
    private TextView usage, result;
    private Button inspect, clean;
    private boolean scanning;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); createPage("存储管理");
        LinearLayout summary = card(body); summary.addView(text("缓存占用查看", 19));
        usage = text("正在计算…", 14); usage.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE); summary.addView(usage);
        inspect = button("重新查看占用", () -> scan(false)); summary.addView(inspect);
        LinearLayout temporary = card(body); temporary.addView(text("清理临时文件", 19));
        temporary.addView(text("清理读取缓存、PDF 缓存和超过 7 天的主题分享副本。正在阅读的 PDF、近期分享文件、账号密码、主题原图及草稿会保留。", 14));
        clean = button("清理临时文件", this::confirmClear); temporary.addView(clean);
        result = text("", 13); result.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE); temporary.addView(result);
        LinearLayout packages = card(body); packages.addView(text("已下载安装包", 19));
        packages.addView(text("查看下载与校验状态、安装新版或删除下载的安装包。下载或校验进行中不能清理安装包。", 14));
        packages.addView(button("管理已下载安装包", () -> {
            opening = true; startActivity(new Intent(this, UpdateActivity.class).putExtra("manage_downloads", true));
        }));
        AppAppearance.paintFields(root);
    }
    @Override protected void onResume() { super.onResume(); if (usage != null) scan(false); }
    private void confirmClear() {
        if (scanning) return;
        new ModalDialogs.Builder(this).setTitle("清理临时文件？")
            .setMessage("保留账号密码、主题背景、草稿、正在阅读的 PDF 和已下载安装包。清理后内容会在下次打开时重新读取。")
            .setNegativeButton("取消", null).setPositiveButton("确认清理", (d, w) -> scan(true)).show();
    }
    private void scan(boolean clear) {
        if (scanning || isDestroyed()) return;
        scanning = true; inspect.setEnabled(false); clean.setEnabled(false);
        io.execute(() -> {
            String info = null; Exception failure = null;
            try {
                AcmApplication app = (AcmApplication)getApplication();
                if (clear) {
                    api.clearReadCaches(); app.pdfFiles().clear();
                    TemporaryStorage.clearExpiredShares(getCacheDir(), System.currentTimeMillis());
                }
                long memory = api.cachedDataBytes();
                long disk = TemporaryStorage.bytes(getCacheDir());
                long downloads = TemporaryStorage.bytes(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS));
                info = "内容缓存约 " + size(memory) + "\n应用临时目录 " + size(disk) + "\n下载目录 " + size(downloads)
                    + "\n内容缓存按数据大小估算，非 App 总内存；临时目录含校验后的安装包，安装包在下方单独管理。";
            } catch (Exception e) { failure = e; }
            String value = info; Exception error = failure;
            runOnUiThread(() -> {
                if (isDestroyed()) return; scanning = false; inspect.setEnabled(true); clean.setEnabled(true);
                if (error != null) { result.setText(error.getMessage()); notice.show("存储管理", error); }
                else { usage.setText(value); if (clear) result.setText("临时缓存已清理"); }
            });
        });
    }
    private String size(long bytes) { return android.text.format.Formatter.formatShortFileSize(this, bytes); }
}
