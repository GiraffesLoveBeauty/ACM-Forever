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
import java.util.function.BooleanSupplier;

/** Actual editor navigation while the submit POST is held; no production requests. */
final class ComposerSubmitUiSmoke {
    private final Instrumentation test;
    private final AcmApplication app;
    private MainActivity activity;
    private volatile Gate gate;
    private final AtomicInteger submits=new AtomicInteger();
    private ComposerSubmitUiSmoke(Instrumentation test){this.test=test;app=(AcmApplication)test.getTargetContext().getApplicationContext();}
    static void run(Instrumentation test){new ComposerSubmitUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;ApiClient api=app.api();String origin=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"submit.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            SharedPreferences.Editor setup=prefs.edit().putString("api_base_url","https://submit.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false);
            for(String key:saved.keySet())if(key.startsWith("cloud_recovery_v021_"))setup.remove(key);setup.commit();
            api.setBaseUrl("https://submit.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=(MainActivity)test.startActivitySync(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("cloud_draft_id",11));
            await(()->body()!=null&&"Submitted body".contentEquals(body().getText()),"original draft loaded");

            holdSubmit();main(()->show("problems"));await(()->findText("进入题库")!=null,"left while POST held");main(()->show("compose"));
            await(()->body()!=null&&!body().isEnabled()&&"Submitted body".contentEquals(body().getText()),"returned editor waits for submit result");
            check(gate.release.getCount()==1,"POST has not returned");gate.release.countDown();
            await(()->body()!=null&&body().isEnabled()&&body().length()==0&&app.drafts().state().id==0,"successful submit clears and enables reentered editor");
            main(()->body().setText("New body after submit"));check("New body after submit".equals(app.drafts().state().body),"reentered controls edit the current cleared model");

            loadOriginal();holdSubmit();main(()->show("problems"));
            main(()->{try{app.drafts().load(draft(22,"New draft","New draft body"));}catch(Exception e){throw new AssertionError(e);}refreshEditor();show("compose");});
            await(()->body()!=null&&"New draft body".contentEquals(body().getText()),"new draft is visible while old submit pending");
            gate.release.countDown();await(()->body()!=null&&body().isEnabled()&&"New draft body".contentEquals(body().getText()),"late success preserves and enables different draft");
            check(app.drafts().state().id==22,"old submit cannot clear new draft ID");

            loadOriginal();holdSubmit();long oldGeneration=app.drafts().generation();
            main(()->{CloudDrafts.State current=app.drafts().state();check(app.drafts().update(current.generation,current.category,current.title,"Newer input from another editor"),"same draft receives newer input");});
            gate.release.countDown();await(()->body()!=null&&body().isEnabled()&&"Newer input from another editor".contentEquals(body().getText()),"late success preserves newer text");
            check(app.drafts().generation()!=oldGeneration&&app.drafts().state().id!=11,"newer text is moved out of submitted draft");
            check(submits.get()==3,"one submit per explicit action");
            output.putString("stream","PASS: real submit POST held -> leave -> return -> success clears and enables editor; different draft ID and newer input survive late success; each action submits once.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\n");}
        finally{
            Gate held=gate;if(held!=null)held.release.countDown();if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});
            try{api.logout();}catch(Exception ignored){}
            SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){String key=entry.getKey();Object value=entry.getValue();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);}restore.commit();api.setBaseUrl(origin);AppAppearance.load(app);
        }
        test.finish(result,output);
    }
    private void holdSubmit()throws Exception{
        gate=new Gate();main(()->{View submit=findText("提交审核");check(submit!=null&&submit.isEnabled(),"submit enabled");submit.performClick();});
        check(gate.entered.await(5,TimeUnit.SECONDS),"POST is held");
    }
    private void loadOriginal()throws Exception{
        main(()->{try{app.drafts().load(draft(11,"Submitted title","Submitted body"));}catch(Exception e){throw new AssertionError(e);}refreshEditor();});
        await(()->body()!=null&&body().isEnabled()&&"Submitted body".contentEquals(body().getText()),"next scenario editor ready");
    }
    private static JSONObject draft(int id,String title,String body)throws Exception{return new JSONObject().put("id",id).put("category_id",1).put("edit_version",1).put("title",title).put("body",body);}
    private void show(String screen){invoke("show",new Class<?>[]{String.class},screen);}
    private void refreshEditor(){invoke("refreshComposer",new Class<?>[0]);}
    private void invoke(String name,Class<?>[] types,Object...args){try{java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod(name,types);method.setAccessible(true);method.invoke(activity,args);}catch(Exception e){throw new AssertionError(e);}}
    private EditText body(){return (EditText)find(activity.getWindow().getDecorView(),v->v instanceof EditText&&"发帖正文输入".contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private View findText(String text){return find(activity.getWindow().getDecorView(),v->v instanceof TextView&&text.contentEquals(((TextView)v).getText()));}
    private View find(View view,java.util.function.Predicate<View> condition){if(condition.test(view))return view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View result=find(((ViewGroup)view).getChildAt(i),condition);if(result!=null)return result;}return null;}
    private void main(Runnable action){AtomicReference<Throwable> error=new AtomicReference<>();test.runOnMainSync(()->{try{action.run();}catch(Throwable e){error.set(e);}});if(error.get()!=null)throw new AssertionError(error.get());}
    private void await(BooleanSupplier ready,String reason)throws Exception{long end=SystemClock.uptimeMillis()+6500;while(SystemClock.uptimeMillis()<end){boolean[] value={false};main(()->value[0]=ready.getAsBoolean());if(value[0])return;Thread.sleep(40);}throw new AssertionError(reason);}
    private static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private static final class Gate{final CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);}
    private final class Fixture extends HttpURLConnection{
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();private boolean held;
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public OutputStream getOutputStream(){return sent;}
        public int getResponseCode()throws IOException{
            if(url.getPath().endsWith("/submit")&&!held){held=true;submits.incrementAndGet();Gate selected=gate;if(selected==null)throw new IOException("missing submit gate");selected.entered.countDown();try{if(!selected.release.await(30,TimeUnit.SECONDS))throw new IOException("submit fixture timeout");}catch(InterruptedException e){throw new IOException(e);}}
            return 200;
        }
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=submit-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(response().toString().getBytes(StandardCharsets.UTF_8));}catch(Exception e){throw new IOException(e);}}
        private Object response()throws Exception{
            String path=url.getPath();
            if(path.equals("/api/auth/me"))return new JSONObject().put("authenticated",true).put("csrf_token","submit-fixture-csrf").put("qq_id","90000001").put("role","member");
            if(path.equals("/api/mobile/v1/capabilities"))return new JSONObject().put("api_version",1).put("features",new JSONObject());
            if(path.equals("/api/forum/categories"))return new JSONArray().put(new JSONObject().put("id",1).put("name","Fixture category"));
            if(path.endsWith("/submit"))return new JSONObject().put("id",88);
            if(path.equals("/api/forum/drafts/11"))return draft(11,"Submitted title","Submitted body");
            if(path.equals("/api/forum/drafts")&&"POST".equals(getRequestMethod()))return new JSONObject(new String(sent.toByteArray(),StandardCharsets.UTF_8)).put("id",99).put("edit_version",1);
            if(path.equals("/api/forum/posts"))return new JSONObject().put("rows",new JSONArray()).put("total",0);
            return new JSONObject();
        }
    }
}
