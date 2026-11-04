package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;

/** Test APK only: real Activity recreation with a synthetic document picker result. */
final class MarkdownImportUiSmoke {
    private final Instrumentation test;private final Context context;private Activity activity;private ApiClient api;
    private final ArrayList<Activity> opened=new ArrayList<>();
    private static final AtomicInteger writes=new AtomicInteger();
    private static volatile String savedBody="",account="90000001";
    private MarkdownImportUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new MarkdownImportUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> before=new HashMap<>(prefs.getAll());
        File file=new File(context.getCacheDir(),"review-import.md");
        try{
            writes.set(0);savedBody="";account="90000001";
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"imports.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://imports.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();api.setBaseUrl("https://imports.test.invalid");api.setNetworkAvailable(()->true);api.login(account,"Synthetic-Test!");
            try(FileOutputStream stream=new FileOutputStream(file)){stream.write("# Imported after recreation\nSynthetic Markdown body".getBytes(StandardCharsets.UTF_8));}
            activity=test.startActivitySync(new Intent().setClassName(context,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("cloud_draft_id",11));opened.add(activity);
            await(()->body()!=null&&"Original draft body".contentEquals(body().getText()),"initial draft loaded");
            choose();recreate();deliver(file);
            await(()->body()!=null&&body().getText().toString().startsWith("# Imported after recreation"),"Markdown imports after real Activity recreation");
            await(()->savedBody.startsWith("# Imported after recreation")&&!app.drafts().state().dirty,"import autosaves to original draft");check(app.drafts().state().id==11,"import keeps original draft ID");
            choose();recreate();main(()->app.drafts().load(draft(22,"Other draft body")));int count=writes.get();deliver(file);
            await(()->findPrefix("导入失败")!=null,"changed draft is rejected after recreation");check(app.drafts().state().id==22&&"Other draft body".equals(app.drafts().state().body),"late import cannot overwrite new draft");Thread.sleep(1100);check(writes.get()==count,"rejected draft import sends no write");
            await(()->body()!=null&&"Other draft body".contentEquals(body().getText()),"editor refreshes to current draft");
            choose();recreate();api.logout();account="90000002";api.login(account,"Synthetic-Test!");main(()->{app.drafts().bind(api.getBaseUrl()+"/"+api.accountKey(),api.sessionGeneration());app.drafts().load(draft(33,"Other account body"));});count=writes.get();deliver(file);
            await(()->findPrefix("导入失败")!=null,"changed account is rejected after recreation");check(app.drafts().state().id==33&&"Other account body".equals(app.drafts().state().body),"late import cannot overwrite new account draft");Thread.sleep(1100);check(writes.get()==count,"rejected account import sends no write");
            output.putString("stream","PASS: document selection -> real Activity recreation -> synthetic result imports/autosaves to original draft; changed draft/account results rejected without writes, and no credentials stored in instance state.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));}
        finally{
            for(int i=opened.size()-1;i>=0;i--){Activity item=opened.get(i);main(()->{ModalDialogs.close(item);item.finish();});}
            try{api.logout();}catch(Exception ignored){}file.delete();
            SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:before.entrySet()){String key=entry.getKey();Object value=entry.getValue();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);}restore.apply();api.setBaseUrl(base);AppAppearance.load(context);
        }
        test.finish(result,output);
    }
    private void choose(){AtomicInteger hits=new AtomicInteger();Instrumentation.ActivityMonitor picker=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction())){check("text/*".equals(intent.getType()),"text document picker");hits.incrementAndGet();return new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);}return null;}};test.addMonitor(picker);try{click("导入 .md");check(hits.get()==1,"document picker requested once");}finally{test.removeMonitor(picker);}}
    private void recreate()throws Exception{
        Activity previous=activity;Application app=previous.getApplication();AtomicReference<Activity> next=new AtomicReference<>();
        Application.ActivityLifecycleCallbacks callback=new Application.ActivityLifecycleCallbacks(){public void onActivityCreated(Activity a,Bundle state){if(a instanceof MainActivity&&a!=previous)next.set(a);}public void onActivityStarted(Activity a){}public void onActivityResumed(Activity a){}public void onActivityPaused(Activity a){}public void onActivityStopped(Activity a){}public void onActivitySaveInstanceState(Activity a,Bundle b){check(!b.containsKey("csrf_token")&&!b.containsKey("password"),"instance state has no credentials");}public void onActivityDestroyed(Activity a){}};
        app.registerActivityLifecycleCallbacks(callback);try{main(previous::recreate);await(()->next.get()!=null&&previous.isDestroyed(),"real editor Activity recreated");activity=next.get();opened.add(activity);await(()->body()!=null,"recreated editor ready");}finally{app.unregisterActivityLifecycleCallbacks(callback);}
    }
    private void deliver(File file){main(()->((MainActivity)activity).onActivityResult(42,Activity.RESULT_OK,new Intent().setData(Uri.fromFile(file))));}
    private static JSONObject draft(int id,String body){try{return new JSONObject().put("id",id).put("category_id",1).put("title","Import test title").put("body",body).put("edit_version",1);}catch(JSONException e){throw new AssertionError(e);}}
    private View walk(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private EditText body(){return (EditText)walk(activity.getWindow().getDecorView(),v->"发帖正文输入".contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private View findPrefix(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith(value));}
    private void click(String value){main(()->{View found=walk(activity.getWindow().getDecorView(),v->v instanceof Button&&value.contentEquals(((Button)v).getText()));check(found!=null,"button exists: "+value);found.performClick();});test.waitForIdleSync();}
    private void main(Runnable work){Throwable[] error={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+7000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0]){test.waitForIdleSync();return;}Thread.sleep(70);}throw new AssertionError(label);}
    private void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private static final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return sent;}
        public int getResponseCode(){return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=imports-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(response().getBytes(StandardCharsets.UTF_8));}catch(JSONException e){throw new IOException(e);}}
        private String response()throws JSONException{String path=url.getPath();if(path.equals("/api/auth/me"))return new JSONObject().put("authenticated",true).put("csrf_token","test-only").put("role","member").put("qq_id",account).toString();if(path.equals("/api/forum/categories"))return "[{\"id\":1,\"name\":\"测试分类\"}]";if(path.matches("/api/forum/drafts/(11|22|33)")){int id=Integer.parseInt(path.substring(path.lastIndexOf('/')+1));if("PUT".equals(getRequestMethod())){savedBody=new JSONObject(new String(sent.toByteArray(),StandardCharsets.UTF_8)).getString("body");writes.incrementAndGet();return draft(id,savedBody).toString();}return draft(id,"Original draft body").toString();}if(path.equals("/api/forum/posts"))return "{\"rows\":[],\"total\":0}";return "{}";}
    }
}
