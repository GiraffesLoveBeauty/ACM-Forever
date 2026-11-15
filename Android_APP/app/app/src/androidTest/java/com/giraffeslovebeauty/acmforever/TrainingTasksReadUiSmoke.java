package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import org.json.*;

/** PR143 regression: real cache/live callbacks, slow HTTPS, and retained Activity scroll state. */
final class TrainingTasksReadUiSmoke {
    private final Instrumentation test;
    private final AcmApplication app;
    private final String scenario;
    private final AtomicInteger started=new AtomicInteger(),finished=new AtomicInteger();
    private final List<Activity> opened=new ArrayList<>();
    private TrainingTasksActivity activity;
    private volatile long delay;

    private TrainingTasksReadUiSmoke(Instrumentation t,String value){test=t;app=(AcmApplication)t.getTargetContext().getApplicationContext();scenario=value;}
    static void run(Instrumentation t,String scenario){new TrainingTasksReadUiSmoke(t,scenario).run();}

    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
                protected URLConnection openConnection(URL u)throws IOException{
                    if(!u.getHost().equals("training-read.test.invalid"))throw new IOException("External test traffic forbidden");
                    return new Fixture(u);
                }
            }:null);
            AppAppearance.prefs(app).edit().putString("api_base_url","https://training-read.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).commit();
            app.api().setBaseUrl("https://training-read.test.invalid");app.api().setNetworkAvailable(()->true);app.api().login("90000001","Synthetic!Only42");
            activity=(TrainingTasksActivity)test.startActivitySync(new Intent(app,TrainingTasksActivity.class).putExtra("task_id",7L).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));opened.add(activity);
            await(()->finished.get()==1&&ui(()->activity.refresh.canRefresh()),"initial detail live response");test.waitForIdleSync();
            if("slow".equals(scenario))slow();else scroll();
            result.putString("stream","PASS: training detail "+scenario+", live GETs="+finished.get()+"\n");outcome=Activity.RESULT_OK;
        }catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\nGET started="+started.get()+", finished="+finished.get()+"\n");}
        finally{for(Activity a:opened)main(()->{ModalDialogs.close(a);a.finish();});}
        test.finish(outcome,result);
    }

    private void slow()throws Exception{
        delay=4200;
        int[] revision={0};main(()->{render();revision[0]=activity.serial;});
        await(()->started.get()==2,"slow GET after queued cache replay");
        Thread.sleep(3400);
        check(ui(()->activity.serial==revision[0]),"cached queued detail must not invalidate a >3s live GET");
        await(()->finished.get()==2&&ui(()->activity.refresh.canRefresh()),"slow queued response accepted");
        // A pull-to-refresh may start while the previous successful response's timer is pending.
        main(()->activity.refresh.refreshNow());await(()->started.get()==3,"manual refresh before pending poll");
        Thread.sleep(3400);
        check(ui(()->activity.serial==revision[0]),"pending poll must not invalidate an in-flight manual refresh");
        await(()->finished.get()==3&&ui(()->activity.refresh.canRefresh()&&hasText(activity.getWindow().getDecorView(),"同步状态：同步完成")),"slow completed state accepted");
        check(ui(()->{View v=find(activity.getWindow().getDecorView(),"刷新进度");return v!=null&&v.isEnabled();}),"completed response enables progress refresh");
        Thread.sleep(3400);check(started.get()==3,"completed state must stop polling");
    }

    private void scroll()throws Exception{
        delay=1200;
        main(()->activity.scroll.scrollTo(0,460));test.waitForIdleSync();
        check(ui(()->activity.scroll.getScrollY()==460),"fixture must have enough content to scroll");
        main(this::render);await(()->started.get()==2,"cache shown before live GET");test.waitForIdleSync();
        check(ui(()->activity.scroll.getScrollY()==460),"cache callback restores saved reading position");
        main(()->activity.scroll.scrollTo(0,720));test.waitForIdleSync();
        await(()->finished.get()==2&&ui(()->activity.refresh.canRefresh()),"live response after cached detail");test.waitForIdleSync();
        check(ui(()->activity.scroll.getScrollY()==720),"live callback must retain reading done since the cache callback");

        // Use the real OJ child page, then return to the same detail Activity.
        Instrumentation.ActivityMonitor monitor=test.addMonitor(OjBindingsActivity.class.getName(),null,false);
        Activity child;
        try{
            main(()->{View v=find(activity.getWindow().getDecorView(),"查看 / 绑定 OJ 账号");check(v!=null,"OJ binding entry");v.performClick();});
            child=test.waitForMonitorWithTimeout(monitor,8000);check(child!=null,"OJ binding page opened");opened.add(child);
        }finally{test.removeMonitor(monitor);}
        main(child::onBackPressed);
        await(()->started.get()==3,"live detail read on return from OJ bindings");test.waitForIdleSync();
        check(ui(()->activity.scroll.getScrollY()==720),"return cache callback keeps previous reading position");
        await(()->finished.get()==3&&ui(()->activity.refresh.canRefresh()),"live response on return");test.waitForIdleSync();
        check(ui(()->activity.scroll.getScrollY()==720),"return live callback keeps previous reading position");
    }

    private void render(){try{java.lang.reflect.Method m=TrainingTasksActivity.class.getDeclaredMethod("render");m.setAccessible(true);m.invoke(activity);}catch(Exception e){throw new AssertionError(e);}}
    private void main(Runnable work){Throwable[] failure={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){failure[0]=e;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private boolean ui(BooleanSupplier condition){boolean[] result={false};main(()->result[0]=condition.getAsBoolean());return result[0];}
    private View find(View view,String label){if(view instanceof TextView&&label.contentEquals(((TextView)view).getText()))return view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View found=find(((ViewGroup)view).getChildAt(i),label);if(found!=null)return found;}return null;}
    private boolean hasText(View view,String label){return find(view,label)!=null;}
    private void await(BooleanSupplier condition,String what)throws Exception{long end=SystemClock.uptimeMillis()+18000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(50);}throw new AssertionError("Timeout: "+what);}
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}

    private JSONObject task(int request)throws Exception{
        JSONArray problems=new JSONArray();for(int i=0;i<24;i++)problems.put(new JSONObject().put("platform","codeforces").put("problem_id","cf_"+(1843+i)+"A").put("problem_name","Reading fixture "+i).put("problem_rating",800).put("tags",new JSONArray().put("math")).put("verification","coverage_missing").put("status","pending"));
        return new JSONObject().put("id",7).put("title","Training read fixture").put("state","published").put("phase","active").put("rule","period_ac").put("problems",problems)
            .put("refresh",new JSONObject().put("status","slow".equals(scenario)&&request<3?"queued":"completed"));
    }

    private final class Fixture extends HttpURLConnection {
        Fixture(URL u){super(u);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public int getResponseCode(){return 200;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=read-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public InputStream getInputStream()throws IOException{
            try{
                String path=url.getPath();JSONObject value=new JSONObject();
                if(path.equals("/api/auth/me"))value.put("authenticated",true).put("csrf_token","read-test-csrf").put("qq_id","90000001").put("role","member");
                else if(path.equals("/api/me/training-tasks/7")){
                    check("GET".equals(getRequestMethod()),"detail polling is read-only");long wait=delay;int request=started.incrementAndGet();if(wait>0)Thread.sleep(wait);value=task(request);finished.incrementAndGet();
                }else if(path.equals("/api/me/profile"))value.put("user",new JSONObject().put("name","Read fixture"));
                else if(!path.equals("/api/auth/login"))throw new IOException("Unexpected endpoint: "+path);
                return new ByteArrayInputStream(value.toString().getBytes(StandardCharsets.UTF_8));
            }catch(Exception failure){throw new IOException(failure);}
        }
    }
}
