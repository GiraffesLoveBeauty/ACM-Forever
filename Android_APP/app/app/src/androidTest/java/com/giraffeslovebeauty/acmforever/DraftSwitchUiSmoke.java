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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

/** Test APK only: exercise the actual three-Activity draft stack and recorded server writes. */
final class DraftSwitchUiSmoke {
    private final Instrumentation test;private final Context context;private Activity activity;
    private final ArrayList<Activity> opened=new ArrayList<>();
    private static final Map<Integer,JSONObject> records=Collections.synchronizedMap(new HashMap<>());
    private static final AtomicInteger writes=new AtomicInteger();
    private DraftSwitchUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new DraftSwitchUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();ApiClient api=app.api();String base=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try{
            records.clear();records.put(11,draft(11,1,"Draft A title","Draft A original body"));records.put(22,draft(22,2,"Draft B title","Draft B original body"));writes.set(0);
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
                protected URLConnection openConnection(URL url)throws IOException{if(!"draft-switch.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}
            }:null);
            prefs.edit().putString("api_base_url","https://draft-switch.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();
            api.setBaseUrl("https://draft-switch.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent().setClassName(context,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("cloud_draft_id",11));opened.add(activity);
            await(()->body()!=null&&"Draft A original body".contentEquals(body().getText()),"draft A opened");
            Activity original=activity;EditText staleBody=body();
            Instrumentation.ActivityMonitor monitor=test.addMonitor(SpaceActivity.class.getName(),null,false);
            click("云端草稿");Activity space=test.waitForMonitorWithTimeout(monitor,6000);test.removeMonitor(monitor);check(space!=null,"draft list Activity created");activity=space;opened.add(space);
            await(()->description("云端草稿条目 22")!=null,"draft B in real list");
            monitor=test.addMonitor(MainActivity.class.getName(),null,false);
            main(()->{View card=description("云端草稿条目 22");View edit=walk(card,v->v instanceof Button&&"继续编辑".contentEquals(((Button)v).getText()));check(edit!=null,"draft B edit button");edit.performClick();});
            Activity child=test.waitForMonitorWithTimeout(monitor,6000);test.removeMonitor(monitor);check(child!=null&&child!=original,"second editor Activity created");activity=child;opened.add(child);
            await(()->body()!=null&&"Draft B original body".contentEquals(body().getText()),"draft B opened");
            main(()->body().setText("Draft B edited in child"));await(()->"Draft B edited in child".equals(records.get(22).optString("body")),"child autosaves only B");
            main(child::onBackPressed);activity=space;await(space::hasWindowFocus,"back to draft list");click("返回");activity=original;await(original::hasWindowFocus,"back to original editor Activity");
            await(()->body()!=null&&"Draft B edited in child".contentEquals(body().getText()),"resumed editor binds current B body instead of stale A");
            main(()->{check("Draft B title".contentEquals(title().getText()),"resumed editor binds B title");Spinner category=(Spinner)walk(decor(),v->v instanceof Spinner);check("分类 B".equals(category.getSelectedItem().toString()),"resumed editor binds B category");});
            int before=writes.get();main(()->staleBody.setText("STALE A TEXT MUST NEVER SAVE"));Thread.sleep(1200);
            check(writes.get()==before,"detached A text callback cannot schedule a save");
            await(()->body()!=null&&"Draft B edited in child".contentEquals(body().getText()),"stale callback preserves B controls");
            main(()->body().setText("Draft B edited after returning"));await(()->"Draft B edited after returning".equals(records.get(22).optString("body")),"resumed editor autosaves current B");
            check("Draft B title".equals(records.get(22).optString("title"))&&records.get(22).optInt("category_id")==2,"B keeps its title and category");
            check("Draft A title".equals(records.get(11).optString("title"))&&"Draft A original body".equals(records.get(11).optString("body")),"A remains unchanged");
            check(app.drafts().state().id==22&&!app.drafts().state().dirty,"saved ID and editor agree on B");
            output.putString("stream","PASS: real A editor -> cloud list -> second B editor -> back through list to original; B title/body/category rebound, detached A callbacks rejected, only B updated and A unchanged.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));}
        finally{
            for(int i=opened.size()-1;i>=0;i--){Activity item=opened.get(i);main(()->{ModalDialogs.close(item);item.finish();});}
            try{api.logout();}catch(Exception ignored){}
            SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){String key=entry.getKey();Object value=entry.getValue();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);}restore.apply();api.setBaseUrl(base);AppAppearance.load(context);
        }
        test.finish(result,output);
    }
    private static JSONObject draft(int id,int category,String title,String body)throws JSONException{return new JSONObject().put("id",id).put("category_id",category).put("title",title).put("body",body).put("edit_version",1);}
    private View decor(){return activity.getWindow().getDecorView();}
    private View walk(View view,java.util.function.Predicate<View> match){if(view==null)return null;if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View description(String value){return walk(decor(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private EditText body(){return (EditText)description("发帖正文输入");}
    private EditText title(){return (EditText)walk(decor(),v->v instanceof EditText&&"例如：二分答案的边界怎么判断？".equals(String.valueOf(((EditText)v).getHint())));}
    private void click(String value){main(()->{View control=walk(decor(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));check(control!=null,"control exists: "+value);control.performClick();});}
    private void main(Runnable work){final Throwable[] error={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+7000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0]){test.waitForIdleSync();return;}Thread.sleep(70);}throw new AssertionError(label);}
    private void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private static final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public int getResponseCode(){return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}
        public OutputStream getOutputStream(){return sent;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=draft-switch-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(response().getBytes(StandardCharsets.UTF_8));}catch(JSONException e){throw new IOException(e);}}
        private String response()throws JSONException{
            String path=url.getPath();
            if(path.equals("/api/auth/me"))return "{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            if(path.equals("/api/forum/categories"))return "[{\"id\":1,\"name\":\"分类 A\"},{\"id\":2,\"name\":\"分类 B\"}]";
            if(path.equals("/api/forum/drafts")){synchronized(records){return new JSONArray(Arrays.asList(records.get(11),records.get(22))).toString();}}
            if(path.matches("/api/forum/drafts/(11|22)")){
                int id=Integer.parseInt(path.substring(path.lastIndexOf('/')+1));
                synchronized(records){if("PUT".equals(getRequestMethod())){JSONObject value=new JSONObject(new String(sent.toByteArray(),StandardCharsets.UTF_8));JSONObject previous=records.get(id);value.put("id",id).put("edit_version",previous.getInt("edit_version")+1);records.put(id,value);writes.incrementAndGet();}return records.get(id).toString();}
            }
            if(path.equals("/api/forum/posts"))return "{\"rows\":[],\"total\":0}";
            return "{}";
        }
    }
}
