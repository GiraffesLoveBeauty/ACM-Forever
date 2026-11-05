package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Color;
import android.net.Uri;
import android.webkit.*;
import org.json.JSONObject;
import java.io.*;

/** Executes only bundled official Vue/CSS/SVG. No native JS bridge or network capability. */
final class OfficialThemeView extends WebView {
    private static final String ORIGIN="https://appassets.androidplatform.net",PREFIX="/themes/renderer/";
    private final String scene;private String applied="";private boolean loaded;
    OfficialThemeView(Context c){this(c,"background");}
    OfficialThemeView(Context c,String scene){
        super(c);this.scene=scene;setBackgroundColor(Color.TRANSPARENT);setHorizontalScrollBarEnabled(false);setVerticalScrollBarEnabled(false);
        setContentDescription("官方主题原始素材 "+scene);setImportantForAccessibility("background".equals(scene)?IMPORTANT_FOR_ACCESSIBILITY_NO:IMPORTANT_FOR_ACCESSIBILITY_AUTO);
        getSettings().setJavaScriptEnabled(true);getSettings().setAllowFileAccess(false);getSettings().setAllowContentAccess(false);getSettings().setDomStorageEnabled(false);getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);getSettings().setBlockNetworkLoads(true);
        setWebViewClient(new WebViewClient(){
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                Uri uri=request.getUrl();String path=uri.getPath();
                if("https".equals(uri.getScheme())&&"appassets.androidplatform.net".equals(uri.getHost())&&path!=null&&path.startsWith(PREFIX)&&!path.contains("..")&&"GET".equals(request.getMethod()))try{
                    String type=path.endsWith(".js")?"text/javascript":path.endsWith(".css")?"text/css":path.endsWith(".svg")?"image/svg+xml":path.endsWith(".woff2")?"font/woff2":path.endsWith(".html")?"text/html":"application/octet-stream";
                    return new WebResourceResponse(type,"UTF-8",getContext().getAssets().open(path.substring(1)));
                }catch(IOException ignored){}
                return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",java.util.Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return true;}
            @Override public void onPageFinished(WebView view,String url){if((ORIGIN+PREFIX+"index.html").equals(url)){loaded=true;refresh();}}
        });
        loadUrl(ORIGIN+PREFIX+"index.html");
    }
    @Override public boolean onTouchEvent(android.view.MotionEvent event){return !"background".equals(scene)&&!"banner-background".equals(scene)&&super.onTouchEvent(event);}
    static boolean background(Context c){android.content.SharedPreferences p=AppAppearance.prefs(c);return "web".equals(p.getString("theme_source","acm"))&&"solid".equals(p.getString("bg_mode","solid"))&&"theme".equals(p.getString("bg_source","custom"));}
    void refresh(){
        if(!loaded)return;try{
            android.content.SharedPreferences prefs=AppAppearance.prefs(getContext());JSONObject selected=AppAppearance.findPreset(getContext(),prefs.getString("theme_preset","industrial"));boolean dark=prefs.getBoolean("theme_dark",false);
            String config=new JSONObject().put("scene",scene).put("design",selected.optString("design_template","original")).put("dark",dark).put("profile",WebThemes.profile(selected,dark)).toString();if(!config.equals(applied)){applied=config;evaluateJavascript("window.applyTheme("+config+")",null);}
        }catch(Exception ignored){}
    }
    @Override protected void onDetachedFromWindow(){super.onDetachedFromWindow();stopLoading();destroy();}
}
