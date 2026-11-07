package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.view.View;
import android.webkit.*;
import android.widget.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Page-scoped image recovery. Only connection failures are automatically retried. */
public final class ImagePreviewActivity extends Activity {
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private WebView viewer;
    private TextView status;
    private Button retry;
    private PageRefresh refresh;
    private ApiClient api;
    private long owner;
    private String address;
    private boolean dead, busy, loaded;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); AppAppearance.load(this); AppAppearance.window(this);
        api = ((AcmApplication)getApplication()).api(); owner = api.sessionGeneration();
        address = getIntent().getStringExtra("url");
        LinearLayout root = new SpacedLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setFitsSystemWindows(true); root.setPadding(dp(12), dp(12), dp(12), dp(12));
        root.setBackgroundColor(MobileStyle.PANEL); AppAppearance.content(this, root);
        Button back = new Button(this); back.setText("返回"); MobileStyle.button(back, false);
        back.setOnClickListener(v -> finish()); root.addView(back);
        refresh = new PageRefresh(this, root, 1); configureRefresh();
        status = new TextView(this); status.setTextColor(MobileStyle.TEXT);
        status.setPadding(dp(12), dp(12), dp(12), dp(12)); root.addView(status);
        retry = new Button(this); retry.setText("重新读取图片"); MobileStyle.button(retry, true);
        retry.setOnClickListener(v -> refresh.refreshNow()); retry.setVisibility(View.GONE); root.addView(retry);
        viewer = new WebView(this); viewer.setBackgroundColor(MobileStyle.PANEL);
        viewer.setContentDescription("图片，支持双指缩放和拖动");
        viewer.getSettings().setJavaScriptEnabled(false); viewer.getSettings().setAllowFileAccess(false);
        viewer.getSettings().setAllowContentAccess(false); viewer.getSettings().setBuiltInZoomControls(true);
        viewer.getSettings().setDisplayZoomControls(false); viewer.getSettings().setUseWideViewPort(true);
        viewer.getSettings().setLoadWithOverviewMode(true);
        viewer.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return true; }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return new WebResourceResponse("text/plain", "UTF-8", new java.io.ByteArrayInputStream(new byte[0]));
            }
        });
        root.addView(viewer, new LinearLayout.LayoutParams(-1, 0, 1)); read();
    }
    private int dp(int value) { return MobileStyle.dp(this, value); }
    private void configureRefresh() {
        refresh.reset(1); refresh.userAction(); refresh.register(1, this::read);
        if (loaded) refresh.cached(1);
    }
    private void read() {
        if (dead || busy || !api.isLoggedIn() || owner != api.sessionGeneration()) return;
        busy = true; retry.setEnabled(false); refresh.start(1);
        if (!loaded) status.setText("正在读取图片…");
        io.execute(() -> {
            String html = null; Exception issue = null;
            try {
                ApiClient.Media data;
                synchronized (api) {
                    if (owner != api.sessionGeneration()) throw new ApiClient.ApiException(401, "登录账号已变化", false);
                    data = api.communityMedia(address);
                }
                BitmapFactory.Options bounds = new BitmapFactory.Options(); bounds.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(data.bytes, 0, data.bytes.length, bounds);
                if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || (long)bounds.outWidth * bounds.outHeight > 16000000L) {
                    api.discardCommunityMedia(address);
                    throw new ApiClient.MediaFormatException("图片尺寸或内容不支持");
                }
                html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                    + "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">"
                    + "<style>body{margin:0}img{width:100%;height:auto}</style></head><body><img alt='社区图片' src='data:"
                    + data.mime + ";base64," + android.util.Base64.encodeToString(data.bytes, android.util.Base64.NO_WRAP)
                    + "'></body></html>";
            } catch (Exception e) { issue = e; }
            String image = html; Exception failure = issue;
            runOnUiThread(() -> {
                if (dead) return;
                if (owner != api.sessionGeneration() || !api.isLoggedIn()) { finish(); return; }
                busy = false; retry.setEnabled(true);
                if (failure == null) {
                    loaded = true; refresh.cached(1); retry.setVisibility(View.GONE);
                    status.setText("双指缩放 · 拖动查看"); status.setTextColor(MobileStyle.TEXT);
                    status.setBackgroundColor(android.graphics.Color.TRANSPARENT);
                    viewer.loadDataWithBaseURL(null, image, "text/html", "UTF-8", null);
                    refresh.finish(1);
                } else {
                    String reason = FailureState.title(failure);
                    if (PageRefresh.isConnectionFailure(reason)) {
                        refresh.failure(reason); refresh.finish(1);
                    } else configureRefresh();
                    status.setText(failure instanceof ApiClient.MediaFormatException ? failure.getMessage() : reason);
                    status.setTextColor(ErrorModule.ink()); ErrorModule.style(status); retry.setVisibility(View.VISIBLE);
                }
            });
        });
    }
    @Override protected void onResume() {
        super.onResume();
        if (api != null && (owner != api.sessionGeneration() || !api.isLoggedIn())) finish();
    }
    @Override protected void onDestroy() {
        dead = true; if (refresh != null) refresh.close(); io.shutdownNow();
        if (viewer != null) {
            viewer.stopLoading();
            if (viewer.getParent() instanceof android.view.ViewGroup) ((android.view.ViewGroup)viewer.getParent()).removeView(viewer);
            viewer.destroy();
        }
        super.onDestroy();
    }
}
