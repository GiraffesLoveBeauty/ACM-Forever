package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.*;

/** Test transport lives only in the instrumentation APK; system download uses a reserved invalid host. */
final class StartupUpdatesUiSmoke {
    private final Instrumentation test;
    private final Context context;
    private final List<Activity> opened=new ArrayList<>();
    private Activity activity;
    private AppUpdates updates;
    private ApiClient api;
    private final AtomicInteger checks=new AtomicInteger();
    private final CountDownLatch sessionEntered=new CountDownLatch(1),sessionRelease=new CountDownLatch(1);
    private volatile boolean holdSession,sessionRecovered;
    private volatile int response=200;
    private volatile long version;
    private StartupUpdatesUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new StartupUpdatesUiSmoke(test).run();}
    private void run(){
        main(()->{}); // Let Application.onCreate finish before replacing test transport/state.
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"startup-updates.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://startup-updates.test.invalid").remove("app_update_automatic").remove("app_update_attempt").remove("app_update_url").putBoolean("app_update_wifi_download",true).putBoolean("auto_login",false).apply();
            api.setBaseUrl("https://startup-updates.test.invalid");api.setNetworkAvailable(()->true);
            // Keep the synthetic HTTPS transport independent of emulator host connectivity.
            java.util.concurrent.atomic.AtomicBoolean online=new java.util.concurrent.atomic.AtomicBoolean(false);
            updates=new AppUpdates(context,api,online::get);java.lang.reflect.Field updateOwner=AcmApplication.class.getDeclaredField("updates");updateOwner.setAccessible(true);updateOwner.set(app,updates);version=updates.currentVersion()+1;
            check(updates.endpoint().equals(context.getString(R.string.default_update_manifest_url)),"debug updates use GitHub Release independently of business API");
            main(()->updates.source("https://startup-updates.test.invalid/api/mobile/v1/releases/latest?channel=debug"));
            main(()->updates.check(true));await(()->!updates.busy(),"offline check completes");check("无网络".equals(updates.error())&&checks.get()==0,"offline check never calls transport");online.set(true);prefs.edit().remove("app_update_attempt").commit();
            check(updates.automatic(),"automatic check defaults on");check(!prefs.contains("app_update_wifi_download"),"legacy auto-download setting removed");main(()->updates.automatic(false));check(!updates.automatic(),"explicit off respected");prefs.edit().remove("app_update_automatic").apply();
            api.login("90000001","Synthetic-Test!");String session=api.exportSession();api.logout();
            prefs.edit().putBoolean("auto_login",true).apply();check(app.vault().save(api.getBaseUrl(),session),"store test session");
            holdSession=true;sessionRecovered=false;
            activity=open(MainActivity.class);
            check(sessionEntered.await(8,TimeUnit.SECONDS),"startup is restoring session");
            check(checks.get()==0,"step 5 waits for session recovery");
            sessionRelease.countDown();
            await(()->has("下载安装包"),"new version popup after session");
            check(sessionRecovered&&checks.get()==1,"one background update check follows session");
            assertButtons();screenshot("update-offer-v0214.png");
            Activity old=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(MainActivity.class.getName(),null,false);
            try{main(old::recreate);Activity next=test.waitForMonitorWithTimeout(monitor,8000);check(next!=null&&next!=old,"main recreated");activity=next;opened.add(next);await(()->has("下载安装包"),"offer survives rotation");assertButtons();check(checks.get()==1,"rotation does not recheck");}finally{test.removeMonitor(monitor);}
            click("取消更新");main(()->{check(!ModalDialogs.isShowing(activity),"cancel closes offer");updates.startupCheck();updates.startupCheck();});Thread.sleep(300);check(checks.get()==1,"repeat startup does not check again");
            // Explicit download opens the cat page once even if the old button receives two clicks.
            main(()->updates.check(true));await(()->has("下载安装包"),"manual confirmation");
            monitor=test.addMonitor(UpdateDownloadActivity.class.getName(),null,false);
            try{
                main(()->{View download=find("下载安装包");download.performClick();download.performClick();});
                Activity page=test.waitForMonitorWithTimeout(monitor,8000);check(page instanceof UpdateDownloadActivity,"download page opened");Activity home=activity;activity=page;opened.add(page);
                await(()->has("正在下载…"),"cat download heading");main(()->check(walk(decor(),v->v instanceof CodingCatView)!=null,"cat animation present"));screenshot("cat-download-v0214.png");
                check(monitor.getHits()==1,"duplicate tap starts one download screen");
                long task=downloadId();check(task!=-1,"real system task exists");((DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE)).remove(task);
                await(()->has("下载失败"),"removed system download fails visibly");check(updates.error().equals("下载任务不存在，请重新下载。"),"specific download error retained");
                click("重试下载");await(()->has("正在下载…"),"failed download can retry");check(downloadId()!=-1&&downloadId()!=task,"retry creates a new task");
                main(()->updates.cancelDownload());await(()->has("下载已取消"),"cancel state");main(page::finish);activity=home;test.waitForIdleSync();
            }finally{test.removeMonitor(monitor);}
            version=updates.currentVersion();main(()->updates.check(true));await(()->has("已是最新版本"),"latest result popup");screenshot("latest-confirm-v0214.png");click("确认");main(()->check(!ModalDialogs.isShowing(activity),"latest confirmed"));
            response=404;main(()->updates.check(true));await(()->!updates.busy(),"missing endpoint completes");check(updates.error().equals("无API接口"),"missing API reported honestly");main(()->check(!ModalDialogs.isShowing(activity),"failed update leaves home usable"));
            // Failed first checks must not suppress retries for six hours; success is tracked separately.
            response=200;version=updates.currentVersion();prefs.edit().remove("app_update_success").remove("app_update_checked_build").putLong("app_update_attempt",System.currentTimeMillis()-61000).commit();int retryBefore=checks.get();main(updates::maybeCheck);await(()->!updates.busy()&&checks.get()==retryBefore+1,"failed check can retry after short debounce");check(prefs.getLong("app_update_success",0)>0,"successful check persisted independently");main(updates::maybeCheck);Thread.sleep(150);check(checks.get()==retryBefore+1,"successful automatic checks retain six-hour interval");
            activity=open(UpdateActivity.class);await(()->has("已是最新版本"),"opening update page forces a check despite recent successful auto check");check(checks.get()==retryBefore+2,"manual page entry checked once");click("确认");
            output.putString("stream","PASS: default on and saved off; session-before-update startup; one check per process; version/notes and equal buttons with red alpha 50%; popup restored on recreation; cancellation; duplicate download taps open one cat page; real DownloadManager task, visible failure, retry and cancellation; latest-version confirmation; legacy Wi-Fi auto-download removed; missing API releases home; failed-check retry and successful six-hour throttle; update page entry forces a manual check.\n");result=Activity.RESULT_OK;
        }catch(Throwable failure){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure)+"\nChecks="+checks.get()+", recovered="+sessionRecovered+", update="+(updates==null?"not created":updates.status())+"\n");try{screenshot("startup-updates-failure.png");}catch(Exception ignored){}}
        finally{
            sessionRelease.countDown();
            if(updates!=null)main(()->updates.cancelDownload());
            for(int i=opened.size()-1;i>=0;i--){Activity a=opened.get(i);main(()->{ModalDialogs.close(a);a.finish();});}
            try{api.logout();}catch(Exception ignored){}api.setBaseUrl(base);
            SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> item:saved.entrySet()){Object v=item.getValue();if(v instanceof String)edit.putString(item.getKey(),(String)v);else if(v instanceof Boolean)edit.putBoolean(item.getKey(),(Boolean)v);else if(v instanceof Integer)edit.putInt(item.getKey(),(Integer)v);else if(v instanceof Long)edit.putLong(item.getKey(),(Long)v);else if(v instanceof Float)edit.putFloat(item.getKey(),(Float)v);}edit.apply();
        }
        test.finish(result,output);
    }
    private long downloadId()throws Exception{java.lang.reflect.Field f=AppUpdates.class.getDeclaredField("downloadId");f.setAccessible(true);return f.getLong(updates);}
    private void assertButtons(){main(()->{Button yes=(Button)find("下载安装包"),no=(Button)find("取消更新");check(yes!=null&&no!=null,"both actions present");check(find("ACMforever 0.2.15")!=null&&find("更新说明")!=null,"version and notes present in body");check(yes.getWidth()==no.getWidth()&&yes.getHeight()==no.getHeight(),"actions equal size");check(no.getLeft()>yes.getRight(),"buttons separated");check(((GradientDrawable)no.getBackground()).getColor().getDefaultColor()==0x80ff0000,"cancel is red at 50% alpha");Rect visible=new Rect();check(yes.getGlobalVisibleRect(visible)&&visible.height()==yes.getHeight(),"download remains visible below long notes");});}
    private Activity open(Class<?> page){Activity a=test.startActivitySync(new Intent().setClassName(context,page.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));opened.add(a);return a;}
    private void main(Runnable job){test.runOnMainSync(job);}
    private View walk(View v,Predicate<View> predicate){if(predicate.test(v))return v;if(v instanceof ViewGroup){ViewGroup group=(ViewGroup)v;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),predicate);if(found!=null)return found;}}return null;}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog d=ref==null?null:(AlertDialog)ref.get();if(d!=null&&d.isShowing())return d.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View find(String value){return walk(decor(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private boolean has(String value){boolean[] yes={false};main(()->yes[0]=find(value)!=null);return yes[0];}
    private void click(String label){main(()->{View v=find(label);check(v!=null&&v.isEnabled(),"button available: "+label);v.performClick();});test.waitForIdleSync();}
    private void await(BooleanSupplier condition,String label)throws Exception{long end=SystemClock.uptimeMillis()+12000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(60);}throw new AssertionError("Timeout: "+label);}
    private void screenshot(String name)throws Exception{test.waitForIdleSync();Thread.sleep(350);Bitmap b=test.getUiAutomation().takeScreenshot();if(b!=null){try(OutputStream out=new FileOutputStream(new File(context.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}}
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        @Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}
        @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=startup-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public int getResponseCode()throws IOException{
            if(url.getPath().endsWith("/releases/latest")){checks.incrementAndGet();if(!sessionRecovered&&holdSession)throw new IOException("Update ran before session recovery");return response;}
            if(url.getPath().endsWith("/me")&&holdSession){sessionEntered.countDown();try{if(!sessionRelease.await(10,TimeUnit.SECONDS))throw new IOException("Session gate timed out");}catch(InterruptedException e){throw new IOException(e);}sessionRecovered=true;}
            return 200;
        }
        @Override public InputStream getInputStream()throws IOException{
            try{String path=url.getPath(),body="{}";
                if(path.endsWith("/releases/latest"))body=new JSONObject().put("packageName",context.getPackageName()).put("versionCode",version).put("versionName","0.2.15").put("apkUrl","https://downloads.invalid/acmforever-test.apk").put("sha256",String.join("",Collections.nCopies(64,"a"))).put("sizeBytes",2048).put("minSdk",26).put("notes",String.join("\n",Collections.nCopies(30,"仅在测试 APK 中使用的更新说明"))).toString();
                else if(path.endsWith("/me"))body="{\"authenticated\":true,\"csrf_token\":\"synthetic\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
                else if(path.endsWith("/posts"))body="{\"posts\":[],\"total\":0,\"page\":1,\"total_pages\":1}";
                return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
            }catch(Exception e){throw new IOException(e);}
        }
    }
}
