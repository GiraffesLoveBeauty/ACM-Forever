package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.Bundle;
import android.provider.MediaStore;
import android.net.Uri;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Synthetic transport only; verifies image attachment and the account-owned header loader. */
final class CommunityUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;private ApiClient api;
    private static final String HASH="0123456789abcdef0123456789abcdef";
    private static byte[] png;private static volatile String avatar="/uploads/avatars/first.png",savedBody="";
    private static volatile boolean failUpload,uploadCookie,uploadCsrf,uploadField;
    private static final AtomicInteger uploads=new AtomicInteger();private Uri image;
    private CommunityUiSmoke(Instrumentation test){this.test=test;app=test.getTargetContext();}
    static void run(Instrumentation test){new CommunityUiSmoke(test).run();}
    private void run(){Bundle output=new Bundle();int outcome=Activity.RESULT_CANCELED;api=((AcmApplication)app.getApplicationContext()).api();String base=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> settings=new HashMap<>(prefs.getAll());
        java.util.concurrent.atomic.AtomicBoolean completed=new java.util.concurrent.atomic.AtomicBoolean();Thread watchdog=new Thread(()->{try{Thread.sleep(40000);if(completed.get())return;StringBuilder dump=new StringBuilder("FAIL: community verification timeout\n");for(Map.Entry<Thread,StackTraceElement[]> entry:Thread.getAllStackTraces().entrySet()){dump.append(entry.getKey().getName()).append('\n');for(StackTraceElement frame:entry.getValue())dump.append("  ").append(frame).append('\n');}Bundle failure=new Bundle();failure.putString("stream",dump.toString());failure.putBoolean("passed",false);test.finish(Activity.RESULT_CANCELED,failure);}catch(InterruptedException ignored){}},"community-test-watchdog");watchdog.setDaemon(true);watchdog.start();
        try{
            Bitmap bitmap=Bitmap.createBitmap(60,40,Bitmap.Config.ARGB_8888);bitmap.eraseColor(0xff4477bb);ByteArrayOutputStream bytes=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes);bitmap.recycle();png=bytes.toByteArray();
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"community.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden in this test");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://community.test.invalid").putBoolean("auto_login",false).apply();api.setBaseUrl("https://community.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent().setClassName(app,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            await(()->desc("筛选社区话题")!=null,6000,"forum");click("排名");click("主页");await(()->avatar.equals(desc("进入账号设置").getTag()),6000,"avatar survives fast tab changes before visiting account/profile");
            main(()->{View code=desc("猫娘代码标志"),copy=desc("社区横幅文字"),art=desc("网页同款最短路径图谱");int[] a=new int[2],b=new int[2],c=new int[2];code.getLocationOnScreen(a);art.getLocationOnScreen(b);copy.getLocationOnScreen(c);check(a[1]<b[1]&&a[0]+code.getWidth()>=b[0]+art.getWidth()-3,"code mark upper right");check(c[0]+copy.getWidth()<=b[0],"copy never overlaps graph");GraphArtView graph=(GraphArtView)art;float scale=Math.min(graph.getWidth()/400f,graph.getHeight()/300f);float x=(graph.getWidth()-400*scale)/2+177*scale,y=(graph.getHeight()-300*scale)/2+47*scale;long time=android.os.SystemClock.uptimeMillis();MotionEvent down=MotionEvent.obtain(time,time,MotionEvent.ACTION_DOWN,x,y,0),up=MotionEvent.obtain(time,time+50,MotionEvent.ACTION_UP,x,y,0);graph.dispatchTouchEvent(down);graph.dispatchTouchEvent(up);down.recycle();up.recycle();check(graph.target()==2&&graph.status().contains("权重 11"),"touch computes a new route");});screenshot("forum-v027.png");
            main(()->{check(desc("放大探索图谱")==null,"explore button removed");desc("网页同款最短路径图谱").performLongClick();check(ModalDialogs.isShowing(activity),"long press opens expanded graph");});screenshot("graph-v027.png");main(()->ModalDialogs.close(activity));
            avatar="/uploads/avatars/second.png";api.refreshSession();click("排名");click("主页");await(()->avatar.equals(desc("进入账号设置").getTag()),5000,"changed avatar refreshes from home");
            compose();comments();codeBlocks();
            api.logout();main(()->activity.onBackPressed());api.login("90000001","Synthetic-Test!");main(()->activity.onBackPressed());
            output.putBoolean("passed",true);output.putString("stream","PASS: fast-tab and changed-avatar updates, touch-driven shortest paths and expanded graph, composer/comment previews, system photo selection, WebP multipart image/CSRF/Cookie, Markdown insertion plus cloud autosave, upload failure preserves editor and text.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable e){output.putBoolean("passed",false);output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));}
        finally{if(image!=null)app.getContentResolver().delete(image,null,null);if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});try{api.logout();}catch(Exception ignored){}SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> entry:settings.entrySet()){String key=entry.getKey();Object v=entry.getValue();if(v instanceof String)restore.putString(key,(String)v);else if(v instanceof Boolean)restore.putBoolean(key,(Boolean)v);else if(v instanceof Integer)restore.putInt(key,(Integer)v);else if(v instanceof Long)restore.putLong(key,(Long)v);else if(v instanceof Float)restore.putFloat(key,(Float)v);}restore.apply();api.setBaseUrl(base);AppAppearance.load(app);}
        completed.set(true);watchdog.interrupt();test.finish(outcome,output);
    }
    private void compose()throws Exception{
        ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,"acm-ui-smoke.png");values.put(MediaStore.Images.Media.MIME_TYPE,"image/png");image=app.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);check(image!=null,"test image created");try(OutputStream out=app.getContentResolver().openOutputStream(image)){out.write(png);}
        click("发帖");await(()->desc("发帖正文输入")!=null,6000,"compose editor");View editor=desc("发帖正文输入");main(()->((EditText)editor).setText("Image attachment **preview**"));
        pick();await(()->((EditText)desc("发帖正文输入")).getText().toString().contains("![图片](/api/forum/images/"+HASH+")"),6000,"Markdown image inserted");check(editor==desc("发帖正文输入"),"image insert does not rebuild editor");check(uploadCookie&&uploadCsrf&&uploadField,"multipart uses image field and authenticated session");await(()->savedBody.contains(HASH),6000,"attachment auto-saved to cloud");
        click("预览发帖正文");main(()->check(ModalDialogs.isShowing(activity),"post preview opens"));screenshot("post-preview-v027.png");main(()->ModalDialogs.close(activity));
        String before=((EditText)editor).getText().toString();failUpload=true;int count=uploads.get();pick();await(()->uploads.get()>count&&findPrefix("上传图片失败")!=null,6000,"failed upload red banner");main(()->check(editor==desc("发帖正文输入")&&before.equals(((EditText)editor).getText().toString()),"failed attachment retains all input"));failUpload=false;screenshot("image-failure-v027.png");
    }
    private void pick(){AtomicInteger hits=new AtomicInteger();Instrumentation.ActivityMonitor picker=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction())){hits.incrementAndGet();return new Instrumentation.ActivityResult(Activity.RESULT_OK,new Intent().setData(image));}return null;}};test.addMonitor(picker);try{click("插入发帖图片");check(hits.get()==1,"system photo picker invoked once");}finally{test.removeMonitor(picker);}}
    private void comments()throws Exception{
        main(()->activity.finish());activity=test.startActivitySync(new Intent().setClassName(app,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK).putExtra("club_post_id",8));await(()->desc("预览评论")!=null,6000,"comment preview button");click("预览评论");main(()->check(ModalDialogs.isShowing(activity),"comment preview opens without submitting"));main(()->ModalDialogs.close(activity));
    }
    private void codeBlocks()throws Exception{
        final ContentView[] reader={null};StringBuilder longLine=new StringBuilder();for(int i=0;i<100;i++)longLine.append("long_code_");String markdown="正文中的 `inline code`。\n\n```cpp\nint main() {\n\tconst char* text = \""+longLine+"\";\n\treturn 0;\n}\n```\n\n> 引用中的代码：\n>\n> ```cpp\n> int x = 1;\n> ```\n\n代码框后的中文正文。";
        main(()->{ScrollView scroll=new ScrollView(activity);LinearLayout panel=new LinearLayout(activity);panel.setPadding(24,24,24,24);panel.setOrientation(1);panel.setBackgroundColor(MobileStyle.PANEL);reader[0]=new ContentView(activity,markdown,false,url->{});panel.addView(reader[0]);scroll.addView(panel);activity.setContentView(scroll);});
        java.util.concurrent.atomic.AtomicBoolean passed=new java.util.concurrent.atomic.AtomicBoolean();
        await(()->{reader[0].evaluateJavascript("(()=>{const a=document.getElementById('article'),ps=[...document.querySelectorAll('pre')];if(ps.length!==2)return false;const r=a.getBoundingClientRect(),w=document.documentElement.clientWidth;const aligned=ps.every(p=>{const b=p.getBoundingClientRect(),c=getComputedStyle(p);return b.left>=r.left-1&&b.right<=r.right+1&&c.whiteSpace==='pre'&&c.textAlign==='left'&&c.tabSize==='4';});const p=ps[0];p.scrollLeft=80;return aligned&&p.scrollLeft>0&&document.documentElement.scrollWidth<=w+1&&p.querySelector('code').textContent.includes('\\tconst char*');})()",value->passed.set("true".equals(value)));return passed.get();},6000,"code frames align and long lines scroll internally without expanding body");screenshot("code-block-v027.png");
    }
    private void main(Runnable work){test.runOnMainSync(work);}
    private View walk(View view,java.util.function.Predicate<View> match){if(view.getVisibility()!=View.VISIBLE)return null;if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View v=walk(group.getChildAt(i),match);if(v!=null)return v;}}return null;}
    private View desc(String value){return walk(activity.getWindow().getDecorView(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private View findPrefix(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith(value));}
    private void click(String value){main(()->{View view=desc(value);if(view==null)view=walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));check(view!=null,"control "+value);view.performClick();});test.waitForIdleSync();}
    private void await(java.util.function.BooleanSupplier ready,long timeout,String message)throws Exception{long end=System.currentTimeMillis()+timeout;while(System.currentTimeMillis()<end){boolean[] ok={false};main(()->ok[0]=ready.getAsBoolean());if(ok[0])return;Thread.sleep(80);}throw new AssertionError(message);}
    private void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private void screenshot(String name)throws Exception{Thread.sleep(200);Bitmap b=test.getUiAutomation().takeScreenshot();try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}finally{b.recycle();}}
    private static final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return sent;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=community-fixture; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public int getResponseCode(){if(url.getPath().equals("/api/mobile/v1/capabilities"))return 404;if(url.getPath().equals("/api/forum/images")){uploads.incrementAndGet();return failUpload?500:201;}return 200;}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{\"message\":\"Synthetic upload failure\"}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream()throws IOException{String path=url.getPath();if(path.startsWith("/uploads/avatars/")||path.startsWith("/api/forum/images/")){if(path.contains("first"))try{Thread.sleep(500);}catch(InterruptedException ignored){}return new ByteArrayInputStream(png);}String body="{}";
            if(path.endsWith("/auth/me"))body="{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\",\"avatar_url\":\""+avatar+"\"}";
            else if(path.equals("/api/forum/images")){String multipart=sent.toString("ISO-8859-1");uploadCookie=String.valueOf(getRequestProperty("Cookie")).contains("community-fixture");uploadCsrf="test-only".equals(getRequestProperty("X-CSRF-Token"));uploadField=multipart.contains("name=\"image\"")&&multipart.contains("Content-Type: image/webp")&&multipart.contains("WEBP");body="{\"url\":\"/api/forum/images/"+HASH+"\"}";}
            else if(path.equals("/api/forum/categories"))body="[{\"id\":1,\"name\":\"求助\",\"slug\":\"help\"}]";
            else if(path.equals("/api/forum/posts/8"))body="{\"id\":8,\"title\":\"Comment test\",\"body\":\"# Markdown\",\"comments\":[]}";
            else if(path.startsWith("/api/forum/drafts")&&sent.size()>0){try{savedBody=new JSONObject(sent.toString("UTF-8")).optString("body");}catch(JSONException e){throw new IOException(e);}body="{\"id\":70,\"edit_version\":1}";}
            else if(path.equals("/api/forum/posts")||path.equals("/api/community/leaderboard"))body="{\"rows\":[],\"total\":0,\"page\":1}";
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));}
    }
}
