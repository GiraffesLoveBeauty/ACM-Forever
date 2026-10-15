package com.giraffeslovebeauty.acmforever;

import android.annotation.SuppressLint;
import android.content.Context;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import org.json.JSONObject;

/** Local, sanitized reader with no application bridge or shared login cookies. */
final class ContentView extends WebView {
    @SuppressLint("SetJavaScriptEnabled")
    ContentView(Context context, String source, boolean html, java.util.function.Consumer<String> openLink) {
        super(context);
        setBackgroundColor(android.graphics.Color.TRANSPARENT);
        getSettings().setJavaScriptEnabled(true);
        getSettings().setAllowFileAccess(false);
        getSettings().setAllowContentAccess(false);
        getSettings().setAllowFileAccessFromFileURLs(false);
        getSettings().setAllowUniversalAccessFromFileURLs(false);
        getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(this, false);
        setLayoutParams(new LinearLayout.LayoutParams(-1, dp(120)));
        setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if ("https".equals(request.getUrl().getScheme())) openLink.accept(request.getUrl().toString());
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("file:///android_asset/reader/") || url.startsWith("https://")) return null;
                return new WebResourceResponse("text/plain", "UTF-8", new java.io.ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!"file:///android_asset/reader/index.html".equals(url)) return;
                evaluateJavascript("renderContent(" + JSONObject.quote(source) + "," + JSONObject.quote(html ? "html" : "markdown") + ")", ignored -> resize());
                postDelayed(() -> resize(), 600);
                postDelayed(() -> resize(), 1800);
            }
        });
        loadUrl("file:///android_asset/reader/index.html");
    }
    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private void resize() {
        if (getParent() == null) return;
        evaluateJavascript("Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)", value -> {
            try {
                int height = Math.max(dp(100), dp(Float.parseFloat(value)));
                if (getLayoutParams().height != height) { getLayoutParams().height = height; requestLayout(); }
            } catch (NumberFormatException ignored) { }
        });
    }
    @Override protected void onDetachedFromWindow() {
        stopLoading(); super.onDetachedFromWindow(); destroy();
    }
}
