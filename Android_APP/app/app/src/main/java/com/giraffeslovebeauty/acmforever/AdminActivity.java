package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.JsResult;
import android.webkit.JsPromptResult;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Local-only management UI, reusing the Web modules through an authenticated API boundary. */
public final class AdminActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private static ApiClient session;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final java.util.concurrent.atomic.AtomicInteger queued = new java.util.concurrent.atomic.AtomicInteger();
    private WebView web;
    private ApiClient api;
    private volatile boolean closed;
    private String documentText;
    private android.webkit.ValueCallback<Uri[]> fileChoice;

    static void open(Activity activity, ApiClient api) {
        if(session!=null)return;
        if (!api.isAdministrator() || api.requiresPasswordChange()) return;
        session = api;
        activity.startActivity(new Intent(activity, AdminActivity.class));
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state); api = session;
        if (api == null || !api.isAdministrator() || api.requiresPasswordChange()) { finish(); return; }
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setFitsSystemWindows(true);
        root.setBackgroundColor(android.graphics.Color.rgb(237,243,239)); setContentView(root);
        Button back = new Button(this); back.setText("返回账号设置"); back.setOnClickListener(v -> onBackPressed()); root.addView(back);
        web = new WebView(this); root.addView(web, new LinearLayout.LayoutParams(-1,0,1));
        web.getSettings().setJavaScriptEnabled(true); web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false); web.getSettings().setAllowContentAccess(true);
        web.getSettings().setAllowFileAccessFromFileURLs(false); web.getSettings().setAllowUniversalAccessFromFileURLs(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.getSettings().setSupportMultipleWindows(false);
        android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.addJavascriptInterface(new Bridge(),"AcmAdminNative");
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri=request.getUrl();
                if ("https".equals(uri.getScheme()) && "appassets.androidplatform.net".equals(uri.getHost()) && uri.getPort()==-1
                        && "GET".equals(request.getMethod()) && uri.getPath()!=null && uri.getPath().matches("/admin/[A-Za-z0-9_./-]+") && !uri.getPath().contains("..")) {
                    try {
                        String path=uri.getPath().substring(1), mime=path.endsWith(".js")?"application/javascript":path.endsWith(".css")?"text/css":path.endsWith(".html")?"text/html":"application/octet-stream";
                        return new WebResourceResponse(mime,"UTF-8",200,"OK",java.util.Collections.singletonMap("Cache-Control","no-store"),getAssets().open(path));
                    } catch (Exception ignored) { }
                }
                return new WebResourceResponse("text/plain","UTF-8",403,"Forbidden",java.util.Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // No remote document or iframe is ever loaded with the native interface present.
                if (request.isForMainFrame() && request.hasGesture()) openExternal(request.getUrl().toString());
                return true;
            }
            @Override public void onReceivedSslError(WebView view,android.webkit.SslErrorHandler handler,android.net.http.SslError error) { handler.cancel(); }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onJsAlert(WebView view,String url,String message,JsResult result) {
                if(ModalDialogs.isShowing(AdminActivity.this)){result.cancel();return true;}
                new ModalDialogs.Builder(AdminActivity.this).setMessage(message).setPositiveButton("知道了",(d,w)->result.confirm()).setOnCancelListener(d->result.cancel()).show(); return true;
            }
            @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result) {
                if(ModalDialogs.isShowing(AdminActivity.this)){result.cancel();return true;}
                new ModalDialogs.Builder(AdminActivity.this).setMessage(message).setPositiveButton("确认",(d,w)->result.confirm()).setNegativeButton("取消",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show(); return true;
            }
            @Override public boolean onJsPrompt(WebView view,String url,String message,String initial,JsPromptResult result) {
                if(ModalDialogs.isShowing(AdminActivity.this)){result.cancel();return true;}
                EditText input=new EditText(AdminActivity.this); input.setText(initial);
                if(message.contains("密码"))input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
                new ModalDialogs.Builder(AdminActivity.this).setMessage(message).setView(input).setPositiveButton("确认",(d,w)->result.confirm(input.getText().toString())).setNegativeButton("取消",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show(); return true;
            }
            @Override public boolean onShowFileChooser(WebView view,android.webkit.ValueCallback<Uri[]> callback,FileChooserParams params) {
                if(fileChoice!=null){callback.onReceiveValue(null);return true;}fileChoice=callback;
                try { Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(intent,92); }
                catch(Exception e){fileChoice=null;callback.onReceiveValue(null);}return true;
            }
        });
        web.loadUrl(ORIGIN+"/admin/index.html");
    }

    private final class Bridge {
        @JavascriptInterface public void request(String id,String method,String path,String body) {
            if(closed||id==null||!id.matches("[0-9]{1,12}"))return;
            if(queued.incrementAndGet()>16){queued.decrementAndGet();respond(id,0,null,"请求过于频繁");return;}
            worker.execute(()->{
                try {
                    if(closed)return;
                    if(body==null||body.length()>1024*1024)throw new IllegalArgumentException("请求过大");
                    Object value=api.adminRequest(method,path,body.isEmpty()?null:new JSONObject(body));
                    respond(id,200,value,"");
                }catch(Exception e){respond(id,e instanceof ApiClient.ApiException?((ApiClient.ApiException)e).status:0,e instanceof ApiClient.ApiException?((ApiClient.ApiException)e).details:null,FailureState.title(e));}
                finally{queued.decrementAndGet();}
            });
        }
        @JavascriptInterface public void close() { runOnUiThread(()->finish()); }
        @JavascriptInterface public void copyText(String text) {
            if(closed||text==null||text.length()>1024*1024)return;
            runOnUiThread(()->((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(android.content.ClipData.newPlainText("ACMforever",text)));
        }
        @JavascriptInterface public void saveDocument(String name,String text) {
            if(closed||text==null||text.length()>1024*1024||name==null||!name.matches("[A-Za-z0-9_-]+\\.(csv|json)"))return;
            runOnUiThread(()->{
                if(documentText!=null)return;documentText=text;
                Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(name.endsWith(".csv")?"text/csv":"application/json").putExtra(Intent.EXTRA_TITLE,name);
                try{startActivityForResult(intent,91);}catch(Exception e){documentText=null;notice("无法打开保存文件窗口");}
            });
        }
    }
    private void respond(String id,int status,Object data,String title) {
        try {
            JSONObject result=new JSONObject().put("status",status).put("data",data==null?new JSONObject().put("message",title):data).put("title",title);
            runOnUiThread(()->{if(!closed&&web!=null)web.evaluateJavascript("window.__acmAdminResponse("+JSONObject.quote(id)+","+result+")",null);});
        }catch(Exception ignored){ }
    }
    private void openExternal(String value) {
        try{
            String checked=BrowserActivity.checkedUrl(value);
            if(checked.startsWith(ORIGIN))return;
            new ModalDialogs.Builder(this).setTitle("打开外部网页").setMessage(checked).setNegativeButton("取消",null).setPositiveButton("打开",(d,w)->startActivity(new Intent(this,BrowserActivity.class).putExtra("url",checked))).show();
        }catch(Exception ignored){ }
    }
    private void notice(String value){if(!closed)new ModalDialogs.Builder(this).setMessage(value).setPositiveButton("知道了",null).show();}
    @Override protected void onActivityResult(int code,int result,Intent data) {
        super.onActivityResult(code,result,data);
        if(code==92&&fileChoice!=null){fileChoice.onReceiveValue(result==RESULT_OK&&data!=null&&data.getData()!=null?new Uri[]{data.getData()}:null);fileChoice=null;return;}
        if(code!=91)return;
        String text=documentText;documentText=null;
        if(result!=RESULT_OK||data==null||data.getData()==null||text==null)return;
        Uri destination=data.getData();
        worker.execute(()->{try(java.io.OutputStream out=getContentResolver().openOutputStream(destination)){
            if(out==null)throw new java.io.IOException();out.write(text.getBytes(StandardCharsets.UTF_8));runOnUiThread(()->notice("已保存"));
        }catch(Exception e){runOnUiThread(()->notice("保存失败"));}});
    }
    @Override public void onBackPressed(){if(web!=null)web.evaluateJavascript("Promise.resolve(window.__acmAdminCanLeave?.()??true).then(ok=>{if(ok)AcmAdminNative.close()})",null);else super.onBackPressed();}
    @Override protected void onDestroy(){ModalDialogs.close(this);closed=true;documentText=null;if(fileChoice!=null)fileChoice.onReceiveValue(null);worker.shutdownNow();if(web!=null){web.removeJavascriptInterface("AcmAdminNative");web.stopLoading();web.destroy();web=null;}if(isFinishing())session=null;super.onDestroy();}
}
