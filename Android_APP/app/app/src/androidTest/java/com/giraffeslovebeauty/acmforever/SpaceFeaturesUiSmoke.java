package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Synthetic test transport is isolated to the test APK; no production credentials or data. */
final class SpaceFeaturesUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;private volatile boolean offline;
    private final AtomicInteger requests=new AtomicInteger();
    private SpaceFeaturesUiSmoke(Instrumentation t){test=t;app=t.getTargetContext();}
    static void run(Instrumentation t){new SpaceFeaturesUiSmoke(t).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> saved=new HashMap<>(prefs.getAll());ApiClient api=((AcmApplication)app.getApplicationContext()).api();String base=api.getBaseUrl();
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"space.test.invalid".equals(url.getHost()))throw new IOException("External access blocked");return new Fixture(url);}}:null);
            prefs.edit().clear().putString("api_base_url","https://space.test.invalid").putString("theme_source","web").putString("theme_preset","phase").putBoolean("theme_dark",true).putInt("module_transparency",2).putString("bg_mode","solid").putString("bg_source","theme").apply();api.setBaseUrl("https://space.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            open(ClubActivity.class,"page","checkin");await(()->find("设置每日提醒时间")!=null,5000,"checkin page");click("设置每日提醒时间");await(()->description("提醒小时")!=null,2000,"text time fields");
            main(()->{check(walk(decor(),v->v instanceof TimePicker)==null,"no wheel or clock time picker");EditText h=(EditText)description("提醒小时");check(h.getCurrentTextColor()==MobileStyle.TEXT,"time input follows dark theme");h.setText("25");});click("保存");main(()->check(((EditText)description("提醒小时")).getError()!=null,"invalid hour rejected"));
            main(()->{((EditText)description("提醒小时")).setText("21");((EditText)description("提醒分钟")).setText("35");((CheckBox)find("通知提醒")).setChecked(false);});shot("training-reminder-v029.png");click("保存");check(prefs.getInt("reminder_hour",0)==21&&prefs.getInt("reminder_minute",0)==35&&!prefs.getBoolean("training_reminder",true),"time saved without enabling notifications");
            if(Build.VERSION.SDK_INT>=33)test.getUiAutomation().grantRuntimePermission(app.getPackageName(),android.Manifest.permission.POST_NOTIFICATIONS);
            main(()->((CheckBox)find("通知提醒")).performClick());check(prefs.getBoolean("training_reminder",false)&&TrainingReminder.notificationsAllowed(app),"notification permission enables local daily reminder");main(()->((CheckBox)find("通知提醒")).performClick());check(!prefs.getBoolean("training_reminder",true),"notification reminder can be disabled");
            open(SpaceActivity.class,"kind","posts");await(()->find("测试投稿")!=null,5000,"own topic cards");check(description("我的话题条目 61")!=null,"posts card structure");click("未通过");await(()->find("测试投稿")==null,2000,"local state filter");click("全部");shot("space-posts-v029.png");
            open(SpaceActivity.class,"kind","bookmarks");await(()->find("测试收藏")!=null,5000,"bookmark cards");shot("space-bookmarks-v029.png");
            offline=true;open(SpaceActivity.class,"kind","drafts");await(()->find("API连接失败")!=null,4000,"uncached button shows connection failure");shot("space-offline-v029.png");
            offline=false;await(()->find("测试草稿")!=null,14000,"read automatically reconnects");await(()->find("重连成功")!=null,2000,"green reconnect notice");Thread.sleep(3300);main(()->check(!find("重连成功").isShown(),"reconnect closes after three seconds"));shot("space-drafts-v029.png");
            offline=true;open(SpaceActivity.class,"kind","drafts");await(()->find("测试草稿")!=null,2000,"cached drafts visible offline");offline=false;
            open(MainActivity.class,null,null);await(()->description("个人中心")!=null,5000,"main shell");main(()->{View plus=description("常用工具");check(((android.graphics.drawable.GradientDrawable)plus.getBackground()).getColor().getDefaultColor()==MobileStyle.ACCENT,"top plus uses theme background");});clickDescription("个人中心");await(()->find("最近 AC 测试题")!=null,5000,"recent AC record");click("最近 AC 测试题");await(()->find("题面内跳验证")!=null,5000,"AC opens native statement");check(walk(decor(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith("输入"))!=null,"native samples present");shot("recent-ac-native-v029.png");
            result.putString("stream","PASS: typed reminder time/dark colours/validation/notification permission and opt-in/out; three private card pages; no-cache failure, cached reopen, automatic reconnect/3s close; themed plus and recent AC native statement/samples.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable e){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));try{shot("space-failure-v029.png");}catch(Exception ignored){}}
        finally{
            if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});try{api.logout();}catch(Exception ignored){}SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);}edit.apply();api.setBaseUrl(base);AppAppearance.load(app);
        }test.finish(outcome,result);
    }
    private void open(Class<?> cls,String key,String value){if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});Intent intent=new Intent().setClassName(app,cls.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);if(key!=null)intent.putExtra(key,value);activity=test.startActivitySync(intent);}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog d=ref==null?null:(AlertDialog)ref.get();if(d!=null&&d.isShowing())return d.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View walk(View v,java.util.function.Predicate<View> match){if(match.test(v))return v;if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){View found=walk(g.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String s){return walk(decor(),v->v instanceof TextView&&s.contentEquals(((TextView)v).getText()));}
    private View description(String s){return walk(decor(),v->s.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void main(Runnable r){final Throwable[] error={null};test.runOnMainSync(()->{try{r.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void click(String s){main(()->{View v=find(s);check(v!=null,"button "+s);v.performClick();});}
    private void clickDescription(String s){main(()->{View v=description(s);check(v!=null,"control "+s);v.performClick();});}
    private void await(java.util.function.BooleanSupplier ready,long ms,String label)throws Exception{long until=SystemClock.uptimeMillis()+ms;while(SystemClock.uptimeMillis()<until){final boolean[] ok={false};main(()->ok[0]=ready.getAsBoolean());if(ok[0])return;Thread.sleep(60);}throw new AssertionError(label);}
    private void shot(String name)throws IOException{test.waitForIdleSync();try{Thread.sleep(450);}catch(InterruptedException e){Thread.currentThread().interrupt();}Bitmap b=test.getUiAutomation().takeScreenshot();if(b!=null){try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}}
    private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        @Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}
        @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=space-fixture; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public int getResponseCode()throws IOException{requests.incrementAndGet();if(offline)throw new ConnectException("synthetic connection unavailable");return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}
        @Override public InputStream getInputStream(){String p=url.getPath(),body="{}";
            if(p.endsWith("/auth/me"))body="{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            else if(p.endsWith("/categories"))body="[{\"id\":1,\"name\":\"求助\",\"slug\":\"help\"}]";
            else if(p.endsWith("/me/profile"))body="{\"user\":{\"name\":\"Isolated member\",\"qq_id\":\"90000001\"},\"platform_counts\":{\"codeforces\":1},\"total_count\":1,\"recent_ac\":[{\"platform\":\"codeforces\",\"problem_id\":\"1A\",\"problem_name\":\"最近 AC 测试题\",\"submit_time\":1793740000}]}";
            else if(p.endsWith("/me/problems/codeforces/1A"))body="{\"platform\":\"codeforces\",\"problem_id\":\"1A\",\"problem_name\":\"题面内跳验证\",\"content_available\":true,\"statement_text\":\"Test statement\",\"samples\":[{\"input\":\"1\",\"output\":\"1\"}]}";
            else if(p.endsWith("/mine/posts"))body="[{\"id\":61,\"title\":\"测试投稿\",\"category_name\":\"求助\",\"status\":\"published\",\"created_at\":1793740000}]";
            else if(p.endsWith("/mine/bookmarks"))body="[{\"id\":62,\"title\":\"测试收藏\",\"author_name\":\"成员\",\"category_name\":\"题解\",\"created_at\":1793740000}]";
            else if(p.endsWith("/drafts"))body="[{\"id\":63,\"title\":\"测试草稿\",\"category_name\":\"讨论\",\"updated_at\":1793740000}]";
            else if(p.endsWith("/forum/posts"))body="{\"rows\":[],\"total\":0}";
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));}
    }
}
