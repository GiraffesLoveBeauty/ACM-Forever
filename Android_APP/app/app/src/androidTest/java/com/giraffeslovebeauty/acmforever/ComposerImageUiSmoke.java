package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
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

/** Hold the real image POST while navigating the actual editor; no production traffic. */
final class ComposerImageUiSmoke {
    private static final String HASH="0123456789abcdef0123456789abcdef",BODY="Submitted body";
    private final Instrumentation test;
    private final AcmApplication app;
    private final boolean failUpload;
    private final AtomicInteger uploads=new AtomicInteger();
    private MainActivity activity;
    private Uri image;
    private volatile Gate gate;
    private volatile boolean multipartValid;
    private ComposerImageUiSmoke(Instrumentation test,boolean failUpload){this.test=test;this.failUpload=failUpload;app=(AcmApplication)test.getTargetContext().getApplicationContext();}
    static void run(Instrumentation test,boolean failUpload){new ComposerImageUiSmoke(test,failUpload).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;ApiClient api=app.api();String origin=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"image.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            SharedPreferences.Editor setup=prefs.edit().putString("api_base_url","https://image.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false);
            for(String key:saved.keySet())if(key.startsWith("cloud_recovery_v021_"))setup.remove(key);setup.commit();
            api.setBaseUrl("https://image.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            createImage();activity=(MainActivity)test.startActivitySync(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("cloud_draft_id",11));
            await(()->body()!=null&&BODY.contentEquals(body().getText()),"original draft loaded");

            holdUpload();leave();main(()->show("compose"));
            await(()->body()!=null&&!body().isEnabled()&&BODY.contentEquals(body().getText()),"returned editor disabled until upload completes");
            EditText returned=body();main(()->returned.setSelection(4));gate.release.countDown();
            await(()->!busy()&&body()==returned&&body().isEnabled(),"upload completion enables reentered editor");
            assertControls();check(BODY.contentEquals(returned.getText())&&returned.getSelectionStart()==4,"no wrong-editor image insertion or cursor reset");
            check(BODY.equals(app.drafts().state().body),"original model retained");
            main(()->returned.setText("Editing works after upload"));check("Editing works after upload".equals(app.drafts().state().body),"restored editor updates shared draft");

            loadOriginal();holdUpload();main(()->{try{app.drafts().load(draft(22,"Different draft","Different body"));}catch(Exception e){throw new AssertionError(e);}invoke("refreshComposer",new Class<?>[0]);});
            await(()->body()!=null&&!body().isEnabled()&&"Different body".contentEquals(body().getText()),"new draft waits for old upload");
            gate.release.countDown();await(()->!busy()&&body()!=null&&body().isEnabled(),"old upload completion enables different draft");
            assertControls();check(app.drafts().state().id==22&&"Different body".equals(app.drafts().state().body),"old upload cannot modify a different draft");

            loadOriginal();holdUpload();leave();gate.release.countDown();await(()->!busy(),"upload completes while another page is visible");
            main(()->check("problems".equals(field("screen"))&&findText("进入题库")!=null,"upload does not force navigation"));

            loadOriginal();EditText original=body();main(()->original.setSelection(5));holdUpload();gate.release.countDown();
            await(()->!busy(),"upload completes in original editor");assertControls();
            main(()->check(body()==original,"upload preserves original editor instance"));
            if(failUpload){check(BODY.contentEquals(original.getText()),"failed upload retains body");await(()->findPrefix("上传图片失败")!=null,"failure uses red action notice");}
            else{String inserted=ForumImages.markdown("/api/forum/images/"+HASH);check((BODY.substring(0,5)+inserted+BODY.substring(5)).contentEquals(original.getText()),"successful upload inserts once at original cursor");check(multipartValid,"actual WebP multipart with Cookie and CSRF");}
            check(uploads.get()==4,"each explicit selection uploads once with no replay");
            output.putString("stream","PASS: image upload "+(failUpload?"failure":"success")+" -> leave/return restores controls without replacing body/cursor; different draft protected; other page retained; original editor behavior preserved; four selections -> four POSTs.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\n");}
        finally{
            Gate held=gate;if(held!=null)held.release.countDown();if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});
            if(image!=null)app.getContentResolver().delete(image,null,null);try{api.logout();}catch(Exception ignored){}
            SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){String key=entry.getKey();Object value=entry.getValue();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);else if(value instanceof Set){Set<String> strings=new HashSet<>();for(Object item:(Set<?>)value)strings.add((String)item);restore.putStringSet(key,strings);}}restore.commit();api.setBaseUrl(origin);AppAppearance.load(app);
        }
        test.finish(result,output);
    }
    private void createImage()throws Exception{
        ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,"acm-held-upload.png");values.put(MediaStore.Images.Media.MIME_TYPE,"image/png");image=app.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);check(image!=null,"local fixture image created");
        Bitmap bitmap=Bitmap.createBitmap(60,40,Bitmap.Config.ARGB_8888);bitmap.eraseColor(0xff4477bb);try(OutputStream out=app.getContentResolver().openOutputStream(image)){check(bitmap.compress(Bitmap.CompressFormat.PNG,100,out),"PNG fixture encoded");}finally{bitmap.recycle();}
    }
    private void holdUpload()throws Exception{
        gate=new Gate();AtomicInteger picks=new AtomicInteger();Instrumentation.ActivityMonitor picker=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction())){picks.incrementAndGet();return new Instrumentation.ActivityResult(Activity.RESULT_OK,new Intent().setData(image));}return null;}};
        test.addMonitor(picker);try{main(()->{View button=find(activity.getWindow().getDecorView(),v->"插入发帖图片".contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));check(button!=null&&button.isEnabled(),"image button enabled");button.performClick();});check(picks.get()==1,"system picker invoked once");}finally{test.removeMonitor(picker);}
        check(gate.entered.await(5,TimeUnit.SECONDS),"image POST is held");
    }
    private void leave()throws Exception{main(()->show("problems"));await(()->findText("进入题库")!=null,"left upload without waiting for server");check(gate.release.getCount()==1,"response remains held");}
    private void loadOriginal()throws Exception{main(()->{try{app.drafts().load(draft(11,"Submitted title",BODY));}catch(Exception e){throw new AssertionError(e);}if("compose".equals(field("screen")))invoke("refreshComposer",new Class<?>[0]);else show("compose");});await(()->!busy()&&body()!=null&&body().isEnabled()&&BODY.contentEquals(body().getText()),"next original editor ready");}
    private void assertControls(){main(()->{check(body()!=null&&body().isEnabled(),"body enabled");for(String text:new String[]{"提交审核","保存草稿","插入图片"}){View button=findText(text);check(button!=null&&button.isEnabled(),text+" enabled");}});}
    private static JSONObject draft(int id,String title,String body)throws Exception{return new JSONObject().put("id",id).put("category_id",1).put("edit_version",1).put("title",title).put("body",body);}
    private void show(String screen){invoke("show",new Class<?>[]{String.class},screen);}
    private void invoke(String name,Class<?>[] types,Object...args){try{java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod(name,types);method.setAccessible(true);method.invoke(activity,args);}catch(Exception e){throw new AssertionError(e);}}
    private Object field(String name){try{java.lang.reflect.Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);return field.get(activity);}catch(Exception e){throw new AssertionError(e);}}
    private boolean busy(){return Boolean.TRUE.equals(field("composeBusy"));}
    private EditText body(){return (EditText)find(activity.getWindow().getDecorView(),v->v instanceof EditText&&"发帖正文输入".contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private View findText(String text){return find(activity.getWindow().getDecorView(),v->v instanceof TextView&&text.contentEquals(((TextView)v).getText()));}
    private View findPrefix(String text){return find(activity.getWindow().getDecorView(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith(text));}
    private View find(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View found=find(((ViewGroup)view).getChildAt(i),match);if(found!=null)return found;}return null;}
    private void main(Runnable action){AtomicReference<Throwable> error=new AtomicReference<>();test.runOnMainSync(()->{try{action.run();}catch(Throwable e){error.set(e);}});if(error.get()!=null)throw new AssertionError(error.get());}
    private void await(BooleanSupplier ready,String reason)throws Exception{long end=SystemClock.uptimeMillis()+7000;while(SystemClock.uptimeMillis()<end){boolean[] value={false};main(()->value[0]=ready.getAsBoolean());if(value[0])return;Thread.sleep(40);}throw new AssertionError(reason);}
    private static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private static final class Gate{final CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);}
    private final class Fixture extends HttpURLConnection{
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();private boolean held;
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public OutputStream getOutputStream(){return sent;}
        public int getResponseCode()throws IOException{
            if(url.getPath().equals("/api/forum/images")&&!held){held=true;uploads.incrementAndGet();Gate selected=gate;selected.entered.countDown();try{if(!selected.release.await(30,TimeUnit.SECONDS))throw new IOException("upload fixture timeout");}catch(InterruptedException e){throw new IOException(e);}}
            return url.getPath().equals("/api/forum/images")?(failUpload?500:201):200;
        }
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=image-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{\"message\":\"Synthetic upload failure\"}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(response().toString().getBytes(StandardCharsets.UTF_8));}catch(Exception e){throw new IOException(e);}}
        private Object response()throws Exception{
            String path=url.getPath();
            if(path.equals("/api/auth/me"))return new JSONObject().put("authenticated",true).put("csrf_token","image-fixture-csrf").put("qq_id","90000001").put("role","member");
            if(path.equals("/api/mobile/v1/capabilities"))return new JSONObject().put("api_version",1).put("features",new JSONObject());
            if(path.equals("/api/forum/categories"))return new JSONArray().put(new JSONObject().put("id",1).put("name","Fixture category"));
            if(path.equals("/api/forum/drafts/11")&&"GET".equals(getRequestMethod()))return draft(11,"Submitted title",BODY);
            if(path.startsWith("/api/forum/drafts")&&sent.size()>0)return new JSONObject(new String(sent.toByteArray(),StandardCharsets.UTF_8)).put("id",path.endsWith("/11")?11:path.endsWith("/22")?22:99).put("edit_version",1);
            if(path.equals("/api/forum/images")){String multipart=sent.toString("ISO-8859-1");multipartValid=String.valueOf(getRequestProperty("Cookie")).contains("image-fixture")&&"image-fixture-csrf".equals(getRequestProperty("X-CSRF-Token"))&&multipart.contains("name=\"image\"")&&multipart.contains("Content-Type: image/webp")&&multipart.contains("WEBP");return new JSONObject().put("url","/api/forum/images/"+HASH);}
            if(path.equals("/api/forum/posts"))return new JSONObject().put("rows",new JSONArray()).put("total",0);
            return new JSONObject();
        }
    }
}
