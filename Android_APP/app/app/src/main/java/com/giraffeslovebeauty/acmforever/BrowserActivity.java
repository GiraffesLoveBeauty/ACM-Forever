package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.net.URI;

/** In-app page for confirmed HTTPS links; it has no JavaScript bridge to app data. */
public final class BrowserActivity extends Activity {
    private WebView web;
    private TextView address;
    private LinearLayout errorPanel;

    static String checkedUrl(String value) {
        try {
            URI uri = new URI(value == null ? "" : value.trim());
            String host = uri.getHost();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null || uri.getUserInfo() != null
                    || host.equalsIgnoreCase("localhost") || host.endsWith(".local")
                    || host.equals("127.0.0.1") || host.equals("::1")) {
                throw new IllegalArgumentException("只支持公开的 HTTPS 网页链接。");
            }
            return uri.toString();
        } catch (java.net.URISyntaxException e) {
            throw new IllegalArgumentException("链接格式无效。", e);
        }
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        String url;
        try { url = checkedUrl(getIntent().getStringExtra("url")); }
        catch (Exception e) { finish(); return; }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        if (Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                view.setPadding(0, bars.top, 0, bars.bottom);
                return insets;
            });
        } else root.setFitsSystemWindows(true);
        setContentView(root);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(12, 5, 12, 5);
        root.addView(header, new LinearLayout.LayoutParams(-1, dp(56)));
        Button back = new Button(this);
        back.setText("返回");
        back.setOnClickListener(view -> onBackPressed());
        header.addView(back, new LinearLayout.LayoutParams(-2, -1));
        address = new TextView(this);
        address.setTextColor(Color.rgb(22, 52, 50));
        address.setTextSize(12);
        address.setSingleLine(true);
        address.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
        address.setText(url);
        header.addView(address, new LinearLayout.LayoutParams(0, -2, 1));
        Button refresh = new Button(this);
        refresh.setText("刷新");
        refresh.setOnClickListener(view -> { errorPanel.setVisibility(View.GONE); web.setVisibility(View.VISIBLE); web.reload(); });
        header.addView(refresh, new LinearLayout.LayoutParams(-2, -1));
        Button external = new Button(this);
        external.setText("浏览器");
        external.setOnClickListener(view -> {
            try {
                String current = checkedUrl(web.getUrl());
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(current)));
            } catch (ActivityNotFoundException e) {
                android.widget.Toast.makeText(this, "找不到可用的浏览器。", android.widget.Toast.LENGTH_SHORT).show();
            } catch (IllegalArgumentException ignored) { }
        });
        header.addView(external, new LinearLayout.LayoutParams(-2, -1));

        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setAllowFileAccessFromFileURLs(false);
        web.getSettings().setAllowUniversalAccessFromFileURLs(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        if (Build.VERSION.SDK_INT >= 26) web.getSettings().setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String currentUrl, android.graphics.Bitmap icon) {
                errorPanel.setVisibility(View.GONE); web.setVisibility(View.VISIBLE);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                try {
                    String next = checkedUrl(request.getUrl().toString());
                    address.setText(next);
                    return false;
                } catch (Exception e) { return true; }
            }
            @Override public void onPageFinished(WebView view, String currentUrl) {
                try { address.setText(checkedUrl(currentUrl)); }
                catch (Exception ignored) { }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, android.webkit.WebResourceError error) {
                if (!request.isForMainFrame()) return;
                android.net.ConnectivityManager manager = (android.net.ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
                android.net.NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
                boolean online = capabilities != null && capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET);
                showError(!online ? "无网络" : error.getErrorCode() == ERROR_TIMEOUT ? "请求超时" : "网页加载失败");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
                if (request.isForMainFrame()) showError(response.getStatusCode() >= 500 ? "服务器异常" : "网页请求失败");
            }
            @Override public void onReceivedSslError(WebView view, android.webkit.SslErrorHandler handler, android.net.http.SslError error) {
                handler.cancel(); showError("安全连接失败");
            }
        });
        android.widget.FrameLayout region = new android.widget.FrameLayout(this);
        root.addView(region, new LinearLayout.LayoutParams(-1, 0, 1));
        region.addView(web, new android.widget.FrameLayout.LayoutParams(-1, -1));
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL); errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setBackgroundColor(Color.rgb(255, 244, 244)); errorPanel.setVisibility(View.GONE);
        region.addView(errorPanel, new android.widget.FrameLayout.LayoutParams(-1, -1));
        web.loadUrl(url);
    }

    private void showError(String reason) {
        web.setVisibility(View.INVISIBLE); errorPanel.removeAllViews();
        TextView title = new TextView(this); title.setText(reason); title.setTextSize(18);
        title.setTextColor(Color.rgb(183, 35, 35)); errorPanel.addView(title);
        Button retry = new Button(this); retry.setText("重试");
        retry.setOnClickListener(view -> { errorPanel.setVisibility(View.GONE); web.setVisibility(View.VISIBLE); web.reload(); });
        errorPanel.addView(retry); errorPanel.setVisibility(View.VISIBLE);
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (web != null) { web.stopLoading(); web.destroy(); web = null; }
        super.onDestroy();
    }
}
