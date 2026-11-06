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
    interface OutlineListener {void changed(WikiOutline outline);void anchor(String id);}
    private final OutlineListener outlineListener;
    private boolean disposed,ready,measuring;
    private final Runnable watchLayout=new Runnable(){public void run(){if(disposed||outlineListener==null)return;if(getWindowVisibility()==VISIBLE)resize();postDelayed(this,1000);}};
    ContentView(Context context, String source, boolean html, java.util.function.Consumer<String> openLink) {
        this(context,source,html,openLink,null);
    }
    @SuppressLint("SetJavaScriptEnabled")
    ContentView(Context context, String source, boolean html, java.util.function.Consumer<String> openLink,OutlineListener outlineListener) {
        super(context);
        this.outlineListener=outlineListener;
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
                if(outlineListener!=null&&"acm-wiki-anchor".equals(request.getUrl().getScheme())){outlineListener.anchor(request.getUrl().getSchemeSpecificPart());return true;}
                if("acm-image".equals(request.getUrl().getScheme())){String address=request.getUrl().getSchemeSpecificPart();ApiClient api=((AcmApplication)context.getApplicationContext()).api();if(api.isCommunityMedia(address))context.startActivity(new android.content.Intent(context,ImagePreviewActivity.class).putExtra("url",address));return true;}
                if ("https".equals(request.getUrl().getScheme())) openLink.accept(request.getUrl().toString());
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                ApiClient api=((AcmApplication)context.getApplicationContext()).api();if(api.isCommunityMedia(url)){try{ApiClient.Media media=api.communityMedia(url);return new WebResourceResponse(media.mime,null,new java.io.ByteArrayInputStream(media.bytes));}catch(Exception e){return new WebResourceResponse("text/plain","UTF-8",new java.io.ByteArrayInputStream(new byte[0]));}}
                if (url.startsWith("file:///android_asset/reader/") || url.startsWith("https://")) return null;
                return new WebResourceResponse("text/plain", "UTF-8", new java.io.ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (disposed||!"file:///android_asset/reader/index.html".equals(url)) return;
                String colors="document.body.style.color='"+css(MobileStyle.TEXT)+"';document.body.style.background='transparent';"+
                        "document.documentElement.style.setProperty('--panel','"+css(MobileStyle.BACKGROUND)+"');"+
                        "document.documentElement.style.setProperty('--line','"+css(MobileStyle.LINE)+"');"+
                        "document.documentElement.style.setProperty('--brand','"+css(MobileStyle.BRAND)+"');"+
                        "document.documentElement.style.setProperty('--muted','"+css(MobileStyle.MUTED)+"');";
                String base=((AcmApplication)context.getApplicationContext()).api().getBaseUrl();
                evaluateJavascript(colors+"renderContent(" + JSONObject.quote(source) + "," + JSONObject.quote(html ? "html" : "markdown") + ","+JSONObject.quote(base)+","+(outlineListener!=null)+")", ignored -> {if(!disposed){ready=true;resize();}});
                postDelayed(() -> resize(), 600);
                postDelayed(() -> resize(), 1800);
            }
        });
        loadUrl("file:///android_asset/reader/index.html");
    }
    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String css(int color){return String.format(java.util.Locale.ROOT,"#%06x",color&0xffffff);}
    private void resize() {
        if (disposed||!ready||measuring||getParent() == null) return;
        measuring=true;
        // Document scrollHeight includes the previous WebView height and can retain a stale
        // oversized code/preview frame. Measure the actual article, including its code boxes.
        evaluateJavascript(outlineListener==null?"Math.ceil(document.getElementById('article').getBoundingClientRect().height)":"AcmReader.layout()", value -> {
            measuring=false;if(disposed)return;
            try {
                WikiOutline outline=outlineListener==null?null:new WikiOutline(new JSONObject(value));
                int height = Math.max(dp(100), dp(outline==null?Float.parseFloat(value):outline.height));
                if (getLayoutParams().height != height) { getLayoutParams().height = height; requestLayout(); }
                if(outline!=null)outlineListener.changed(outline);
            } catch (org.json.JSONException|NumberFormatException ignored) { }
        });
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();if(outlineListener!=null){removeCallbacks(watchLayout);postDelayed(watchLayout,1000);}}
    @Override protected void onDetachedFromWindow() {
        disposed=true;removeCallbacks(watchLayout);
        stopLoading(); super.onDetachedFromWindow(); destroy();
    }
}
