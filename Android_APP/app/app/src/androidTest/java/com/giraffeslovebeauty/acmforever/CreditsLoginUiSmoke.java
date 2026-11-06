package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Bitmap;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.*;

/** Synthetic transport only in the test APK; no production writes or GitHub traffic. */
final class CreditsLoginUiSmoke {
    private final Instrumentation test;
    private final Context context;
    private Activity activity;
    private CreditsLoginUiSmoke(Instrumentation test) { this.test=test;context=test.getTargetContext(); }
    static void run(Instrumentation test) { new CreditsLoginUiSmoke(test).run(); }
    private void run() {
        main(()->{}); Bundle output=new Bundle(); int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();ApiClient api=app.api();String original=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try {
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"credits.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://credits.test.invalid").putString("app_update_url","https://credits.test.invalid/update.json").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();
            api.setBaseUrl("https://credits.test.invalid");api.setNetworkAvailable(()->true);api.logout();
            activity=test.startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            await(()->has("账号登录"),"signed out login"); assertLocked();
            for(Class<?> page:Arrays.asList(AboutActivity.class,SearchActivity.class,UpdateActivity.class,AppearanceActivity.class,WebFeaturesActivity.class)) {
                Instrumentation.ActivityMonitor monitor=test.addMonitor(MainActivity.class.getName(),null,false);
                try {
                    Activity from=activity;main(()->from.startActivity(new Intent(context,page)));
                    Activity login=test.waitForMonitorWithTimeout(monitor,10000);check(login!=null,"redirect from "+page.getSimpleName());activity=login;
                    await(()->has("账号登录"),"redirect login");assertLocked();
                } finally { test.removeMonitor(monitor); }
            }
            screenshot("login-gate-v0222.png");
            api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent(context,AboutActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            await(()->has("特别鸣谢"),"about credits");
            main(()->{check(findText("@MiaoJJ13445")!=null,"maintainer shown");check(findText("@Setsuna-Yukirin")!=null,"review requester thanked");check(findText("@chatgpt-codex-connector[bot]")!=null,"review bot distinguished");check(countImages(activity.getWindow().getDecorView())>=12,"offline participant avatars loaded");});
            screenshot("about-credits-v0222.png");
            activity=test.startActivitySync(new Intent(context,UpdateActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            await(()->has("已是最新版本"),"update check still works");main(()->{View confirm=findText("确认");if(confirm!=null)confirm.performClick();});
            main(()->{
                View current=findDescription("更新记录 0.2.22"),previous=findDescription("更新记录 0.2.21");
                check(current!=null&&previous!=null,"current and historical cards");
                check(walk(current,v->v instanceof TextView&&((TextView)v).getText().toString().contains("待评审与发布"))!=null,"current does not invent review");
                check(countImages(previous)>=4,"historical owner, requester, reviewer and publisher avatars");
                check(walk(previous,v->v instanceof TextView&&"@Setsuna-Yukirin".contentEquals(((TextView)v).getText()))!=null,"historical requester");
            });
            screenshot("update-credits-v0222.png");
            Activity old=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(UpdateActivity.class.getName(),null,false);
            try{main(old::recreate);activity=test.waitForMonitorWithTimeout(monitor,10000);check(activity!=null,"update page recreated");await(()->has("@MiaoJJ13445"),"credits survive recreation");}finally{test.removeMonitor(monitor);}
            monitor=test.addMonitor(MainActivity.class.getName(),null,false);
            try{api.logout();Activity login=test.waitForMonitorWithTimeout(monitor,10000);check(login!=null,"logout from child returns to login");activity=login;await(()->has("账号登录"),"signed out after child");assertLocked();}finally{test.removeMonitor(monitor);}
            output.putString("stream","PASS: signed-out login only; About/Search/Update/Appearance/Wiki direct entry redirects; no navigation/settings/search entry; offline credits and avatars; historical roles distinguished; current review pending; check updates; recreation; logout from child clears navigation.\n");result=Activity.RESULT_OK;
        } catch(Throwable e) {output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));try{screenshot("credits-login-failure-v0222.png");}catch(Exception ignored){}}
        finally {
            if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});
            try{api.logout();}catch(Exception ignored){}api.setBaseUrl(original);
            SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);}edit.apply();
        }
        test.finish(result,output);
    }
    private void assertLocked(){main(()->{View root=activity.getWindow().getDecorView();check(walk(root,v->v.isShown()&&"常用工具".equals(v.getContentDescription()))==null,"tools hidden");check(walk(root,v->v.isShown()&&"进入账号设置".equals(v.getContentDescription()))==null,"header hidden");check(walk(root,v->v.isShown()&&v instanceof TextView&&Arrays.asList("检查更新","个性化设置","搜索设置","特别鸣谢").contains(((TextView)v).getText().toString()))==null,"other content inaccessible");});}
    private int countImages(View v){int count=v instanceof ImageView&&((ImageView)v).getDrawable() instanceof android.graphics.drawable.BitmapDrawable?1:0;if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++)count+=countImages(g.getChildAt(i));}return count;}
    private View walk(View v,Predicate<View> predicate){if(predicate.test(v))return v;if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){View found=walk(g.getChildAt(i),predicate);if(found!=null)return found;}}return null;}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog dialog=ref==null?null:(AlertDialog)ref.get();if(dialog!=null&&dialog.isShowing())return dialog.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View findText(String value){return walk(decor(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private View findDescription(String value){return walk(decor(),v->value.equals(v.getContentDescription()));}
    private boolean has(String value){boolean[] found={false};main(()->found[0]=findText(value)!=null);return found[0];}
    private void main(Runnable work){test.runOnMainSync(work);}
    private void await(BooleanSupplier condition,String title)throws Exception{long end=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(70);}throw new AssertionError("Timeout: "+title);}
    private void screenshot(String name)throws Exception{test.waitForIdleSync();Thread.sleep(250);Bitmap b=test.getUiAutomation().takeScreenshot();if(b!=null){try(OutputStream out=new FileOutputStream(new File(context.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}}
    private static void check(boolean value,String title){if(!value)throw new AssertionError(title);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public int getResponseCode(){return 200;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=credits-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getInputStream()throws IOException{
            String body="{}";String path=url.getPath();
            if(path.equals("/api/auth/me"))body="{\"authenticated\":true,\"csrf_token\":\"synthetic\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            if(path.endsWith("update.json"))try{body=new org.json.JSONObject().put("packageName",context.getPackageName()).put("versionCode",36).put("versionName","0.2.22").put("apkUrl","https://credits.test.invalid/test.apk").put("sha256",String.join("",Collections.nCopies(64,"a"))).put("sizeBytes",1024).put("minSdk",26).put("channel","debug").put("notes","Synthetic update").toString();}catch(Exception e){throw new IOException(e);}
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
        }
    }
}
