package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Synthetic transport only. Exercise real UI navigation while an HTTPS request waits 30s. */
final class NetworkReadUiSmoke {
    private final Instrumentation test;
    private final AcmApplication app;
    private MainActivity activity;
    private volatile Gate gate;
    private final Map<String,AtomicInteger> counts=new ConcurrentHashMap<>();
    private final ExecutorService workers=Executors.newFixedThreadPool(3);
    private volatile boolean noStore;
    private volatile String csrf="fixture-csrf";
    private final AtomicInteger bytes=new AtomicInteger(),conditional=new AtomicInteger();
    private long navigationMs;
    private NetworkReadUiSmoke(Instrumentation test){this.test=test;app=(AcmApplication)test.getTargetContext().getApplicationContext();}
    static void run(Instrumentation test){new NetworkReadUiSmoke(test).run();}
    private void run(){Bundle output=new Bundle();int outcome=Activity.RESULT_CANCELED;
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!url.getHost().endsWith(".test.invalid"))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            AppAppearance.prefs(app).edit().putString("api_base_url","https://network.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).commit();
            ApiClient api=app.api();api.setBaseUrl("https://network.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=(MainActivity)test.startActivitySync(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            await(()->has("Network post"),"forum ready");
            gate=new Gate("/api/mobile/v1/leaderboard");main(()->show("rank"));check(gate.entered.await(5,TimeUnit.SECONDS),"rank request held");
            long start=SystemClock.uptimeMillis();main(()->show("problems"));await(()->has("进入题库"),"navigation completes before network");navigationMs=SystemClock.uptimeMillis()-start;
            check(navigationMs<1800,"navigation must not wait for 30s request");check(gate.release.getCount()==1,"server has not replied");
            await(()->gate.cancelled.get(),"old page GET disconnected");gate.release.countDown();gate=null;
            Gate shared=new Gate("/api/shared");gate=shared;
            Future<JSONObject> first=workers.submit(()->api.getObject(shared.path));check(shared.entered.await(3,TimeUnit.SECONDS),"shared read started");
            Future<JSONObject> second=workers.submit(()->api.getObject(shared.path));Thread.sleep(200);shared.release.countDown();
            JSONObject a=first.get(3,TimeUnit.SECONDS),b=second.get(3,TimeUnit.SECONDS);a.put("value","mutated");check(b.optString("value").equals("read"),"each reader gets an independent JSON copy");check(count(shared.path)==1,"one wire request for two concurrent reads");gate=null;
            api.getObject("/api/me/problems?page=1");check(cached(api,"/api/me/problems?page=1"),"problem cache seeded");
            api.postAction(7,"like","",0);check(cached(api,"/api/me/problems?page=1"),"like preserves unrelated problem cache");
            try{api.writeObject("POST","/api/write-fail",new JSONObject());throw new AssertionError("expected 500");}catch(ApiClient.ApiException expected){check(expected.status==500,"write failure");}Thread.sleep(150);check(count("/api/write-fail")==1,"writes never automatically retry");
            JSONObject wiki=api.getObject("/api/wiki/pages");int before=bytes.get();JSONObject unchanged=api.getObject("/api/wiki/pages");check(wiki.toString().equals(unchanged.toString())&&conditional.get()==1&&bytes.get()==before,"304 preserves representation with zero body bytes");
            noStore=true;api.getObject("/api/wiki/no-store");api.getObject("/api/wiki/no-store");check(conditional.get()==1,"no-store never sends a validator");noStore=false;
            try(ApiClient.OwnerScope ignored=api.bind(api.sessionGeneration())){csrf="refreshed-fixture-csrf";api.refreshSession();api.writeObject("POST","/api/check-csrf",new JSONObject());}
            Gate stale=new Gate("/api/late401");gate=stale;Future<?> old=workers.submit(()->{try{api.getObject(stale.path);throw new AssertionError("old response accepted");}catch(ApiClient.ApiException expected){return null;}catch(Exception e){throw new CompletionException(e);}});check(stale.entered.await(3,TimeUnit.SECONDS),"old account response held");
            long stateStart=SystemClock.uptimeMillis();main(()->api.setBaseUrl("https://new.test.invalid"));check(SystemClock.uptimeMillis()-stateStart<1000,"state lock never waits for network");api.login("90000002","Synthetic-Test!");long generation=api.sessionGeneration();stale.release.countDown();old.get(3,TimeUnit.SECONDS);check(api.isLoggedIn()&&generation==api.sessionGeneration(),"late old 401 cannot clear new session");gate=null;
            output.putString("stream","PASS: 30s held network navigation="+navigationMs+"ms; obsolete GET cancelled; 2 concurrent reads -> 1 request; JSON copies independent; like retains problem cache; writes=1; ETag304=0 body bytes; no-store respected; late401 cannot clear new session.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\ncounts="+counts+"\n");}
        finally{Gate pending=gate;if(pending!=null)pending.release.countDown();workers.shutdownNow();if(activity!=null)main(()->activity.finish());}test.finish(outcome,output);
    }
    private int count(String path){AtomicInteger n=counts.get(path);return n==null?0:n.get();}
    private boolean cached(ApiClient api,String path)throws Exception{api.beginReplay();try{api.get(path);return api.replayReady();}catch(ApiClient.CacheMissException ignored){return false;}finally{api.endReplay();}}
    private static final class Gate {final String path;final CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);final AtomicBoolean cancelled=new AtomicBoolean();Gate(String path){this.path=path;}}
    private void main(Runnable action){AtomicReference<Throwable> failure=new AtomicReference<>();test.runOnMainSync(()->{try{action.run();}catch(Throwable e){failure.set(e);}});if(failure.get()!=null)throw new AssertionError(failure.get());}
    private void show(String screen){try{java.lang.reflect.Method m=MainActivity.class.getDeclaredMethod("show",String.class);m.setAccessible(true);m.invoke(activity,screen);}catch(Exception e){throw new AssertionError(e);}}
    private boolean has(String text){boolean[] found={false};main(()->found[0]=find(activity.getWindow().getDecorView(),text));return found[0];}
    private boolean find(View view,String text){if(view instanceof TextView&&text.contentEquals(((TextView)view).getText()))return true;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)if(find(((ViewGroup)view).getChildAt(i),text))return true;return false;}
    private void await(java.util.function.BooleanSupplier check,String label)throws Exception{long end=SystemClock.uptimeMillis()+5000;while(SystemClock.uptimeMillis()<end){if(check.getAsBoolean())return;Thread.sleep(40);}throw new AssertionError(label);}
    private static void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection {
        private boolean counted,held;private Gate selected;
        Fixture(URL url){super(url);}public void connect(){}public boolean usingProxy(){return false;}
        public void disconnect(){if(selected!=null){selected.cancelled.set(true);}}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public int getResponseCode()throws IOException{
            if(!counted){counts.computeIfAbsent(url.getPath(),k->new AtomicInteger()).incrementAndGet();counted=true;}
            if(!held){held=true;selected=gate;if(selected!=null&&selected.path.equals(url.getPath())){selected.entered.countDown();long end=SystemClock.uptimeMillis()+30000;while(selected.release.getCount()>0&&!selected.cancelled.get()&&SystemClock.uptimeMillis()<end)try{Thread.sleep(20);}catch(InterruptedException e){throw new IOException(e);}if(selected.cancelled.get())throw new IOException("cancelled");}else selected=null;}
            if(url.getPath().equals("/api/late401"))return 401;
            if(url.getPath().equals("/api/write-fail"))return 500;
            if(url.getPath().equals("/api/check-csrf")&&!csrf.equals(getRequestProperty("X-CSRF-Token")))return 403;
            if(url.getPath().equals("/api/wiki/pages")&&getRequestProperty("If-None-Match")!=null){if(held&&conditional.get()==0)conditional.incrementAndGet();return 304;}
            return 200;
        }
        public String getHeaderField(String key){if("Cache-Control".equalsIgnoreCase(key))return url.getPath().startsWith("/api/wiki/")&&!noStore?"public, max-age=0, must-revalidate":"no-store";if("ETag".equalsIgnoreCase(key)&&url.getPath().startsWith("/api/wiki/"))return "\"fixture-etag\"";return null;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=network-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{\"message\":\"synthetic failure\"}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{try{byte[] data=response().toString().getBytes(StandardCharsets.UTF_8);bytes.addAndGet(data.length);return new ByteArrayInputStream(data);}catch(Exception e){throw new IOException(e);}}
        private Object response()throws Exception{
            String path=url.getPath();if(path.equals("/api/auth/me"))return new JSONObject().put("authenticated",true).put("csrf_token",csrf).put("qq_id","90000001").put("role","member");
            if(path.equals("/api/mobile/v1/capabilities"))return new JSONObject().put("api_version",1).put("features",new JSONObject().put("public_member_ids",true));
            if(path.endsWith("/forum/posts"))return new JSONObject().put("rows",new JSONArray().put(new JSONObject().put("id",7).put("title","Network post").put("excerpt","plain text"))).put("total",1).put("page_size",2);
            if(path.endsWith("/leaderboard"))return new JSONObject().put("rows",new JSONArray()).put("total",0).put("positive_only",true);
            if(path.equals("/api/forum/categories"))return new JSONArray().put(new JSONObject().put("id",1).put("name","Fixture"));
            if(path.equals("/api/me/profile"))return new JSONObject().put("user",new JSONObject().put("name","Fixture"));
            if(path.equals("/api/me/problems"))return new JSONObject().put("items",new JSONArray()).put("total",0);
            return new JSONObject().put("value","read").put("active",true);
        }
    }
}
