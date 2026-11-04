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
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;

/** Test APK only: hold an actual client request while recreating the real editor. */
final class LifecycleNetworkUiSmoke {
    private final Instrumentation test;private final Context context;private Activity activity;private ApiClient api;
    private final ArrayList<Activity> opened=new ArrayList<>();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private static volatile Gate blocked;
    private static volatile String savedBody="";
    private LifecycleNetworkUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new LifecycleNetworkUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> before=new HashMap<>(prefs.getAll());
        try{
            savedBody="";blocked=null;
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"lifecycle.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://lifecycle.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();api.setBaseUrl("https://lifecycle.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent().setClassName(context,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("cloud_draft_id",11));opened.add(activity);
            await(()->body()!=null&&"Lifecycle draft body".contentEquals(body().getText()),"editor loaded");
            long session=api.sessionGeneration();Gate read=new Gate("/api/lifecycle-test/pending","GET");blocked=read;
            Future<?> request=worker.submit(()->{try{api.getObject(read.path);}catch(Exception e){throw new CompletionException(e);}});
            try{check(read.entered.await(5,TimeUnit.SECONDS),"ordinary request holds client monitor");recreateWhileBlocked(read,"ordinary GET");}finally{read.release.countDown();}
            request.get(5,TimeUnit.SECONDS);blocked=null;
            await(()->body()!=null&&"Lifecycle draft body".contentEquals(body().getText()),"editor restored after read");
            Gate save=new Gate("/api/forum/drafts/11","PUT");blocked=save;
            main(()->body().setText("Lifecycle edited body"));
            try{check(save.entered.await(6,TimeUnit.SECONDS),"CloudDrafts autosave holds client monitor");recreateWhileBlocked(save,"cloud autosave");}finally{save.release.countDown();}
            await(()->"Lifecycle edited body".equals(savedBody)&&!app.drafts().state().dirty,"autosave completes after recreation");blocked=null;
            await(()->body()!=null&&"Lifecycle edited body".contentEquals(body().getText()),"recreated editor keeps current body");
            check(api==app.api()&&api.isLoggedIn()&&session==api.sessionGeneration(),"same client and session retained");check(app.drafts().state().id==11,"autosave keeps the draft ID");
            output.putString("stream","PASS: real Activity recreation resumes and UI heartbeat runs before blocked GET/autosave responses are released; same client/session/draft retained and autosave completes with current body.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));}
        finally{
            Gate gate=blocked;if(gate!=null)gate.release.countDown();blocked=null;
            worker.shutdownNow();
            for(int i=opened.size()-1;i>=0;i--){Activity item=opened.get(i);main(()->{ModalDialogs.close(item);item.finish();});}
            try{api.logout();}catch(Exception ignored){}
            SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:before.entrySet()){String key=entry.getKey();Object value=entry.getValue();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);}restore.apply();api.setBaseUrl(base);AppAppearance.load(context);
        }
        test.finish(result,output);
    }
    private void recreateWhileBlocked(Gate gate,String label)throws Exception{
        Activity previous=activity;Application app=previous.getApplication();AtomicReference<Activity> next=new AtomicReference<>();CountDownLatch resumed=new CountDownLatch(1),heartbeat=new CountDownLatch(1);Handler ui=new Handler(Looper.getMainLooper());
        Application.ActivityLifecycleCallbacks callback=new Application.ActivityLifecycleCallbacks(){public void onActivityCreated(Activity a,Bundle state){if(a instanceof MainActivity&&a!=previous)next.set(a);}public void onActivityResumed(Activity a){if(a==next.get()){resumed.countDown();ui.post(heartbeat::countDown);}}public void onActivityStarted(Activity a){}public void onActivityPaused(Activity a){}public void onActivityStopped(Activity a){}public void onActivitySaveInstanceState(Activity a,Bundle b){}public void onActivityDestroyed(Activity a){}};
        app.registerActivityLifecycleCallbacks(callback);boolean responsive=false,pending=false;
        try{
            ui.post(previous::recreate);
            responsive=resumed.await(3,TimeUnit.SECONDS)&&heartbeat.await(1,TimeUnit.SECONDS);
            pending=gate.release.getCount()==1;
        }finally{
            gate.release.countDown();
            // Release the old build's frozen UI before cleanup and before reporting the assertion.
            check(resumed.await(5,TimeUnit.SECONDS),"editor eventually resumes after release");
            Activity replacement=next.get();if(replacement!=null){activity=replacement;opened.add(replacement);}
            app.unregisterActivityLifecycleCallbacks(callback);
        }
        check(responsive&&pending,label+": Activity resumed and heartbeat ran while response was still blocked");
    }
    private static final class Gate{final String path,method;final CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);Gate(String path,String method){this.path=path;this.method=method;}}
    private View walk(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private EditText body(){return (EditText)walk(activity.getWindow().getDecorView(),v->"发帖正文输入".contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void main(Runnable work){Throwable[] error={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+7000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0]){test.waitForIdleSync();return;}Thread.sleep(70);}throw new AssertionError(label);}
    private void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private static final class Fixture extends HttpURLConnection{
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return sent;}
        public int getResponseCode()throws IOException{Gate gate=blocked;if(gate!=null&&gate.path.equals(url.getPath())&&gate.method.equals(getRequestMethod())){gate.entered.countDown();try{if(!gate.release.await(8,TimeUnit.SECONDS))throw new IOException("Synthetic response not released");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}}return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=lifecycle-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(response().getBytes(StandardCharsets.UTF_8));}catch(JSONException e){throw new IOException(e);}}
        private String response()throws JSONException{String path=url.getPath();if(path.equals("/api/auth/me"))return "{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";if(path.equals("/api/forum/categories"))return "[{\"id\":1,\"name\":\"测试分类\"}]";if(path.equals("/api/forum/drafts/11")){if("PUT".equals(getRequestMethod()))savedBody=new JSONObject(new String(sent.toByteArray(),StandardCharsets.UTF_8)).getString("body");return new JSONObject().put("id",11).put("category_id",1).put("title","Lifecycle draft title").put("body",savedBody.isEmpty()?"Lifecycle draft body":savedBody).put("edit_version",1).toString();}if(path.equals("/api/forum/posts"))return "{\"rows\":[],\"total\":0}";return "{}";}
    }
}
