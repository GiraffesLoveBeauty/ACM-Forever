package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

/** Test-only metadata transport and photo selection. Never bundled into the main APK. */
final class LocalSettingsUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;
    private volatile int response=200;private volatile long version;private final AtomicInteger requests=new AtomicInteger();
    private LocalSettingsUiSmoke(Instrumentation test){this.test=test;app=test.getTargetContext();}
    static void run(Instrumentation test){new LocalSettingsUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> before=new HashMap<>(prefs.getAll());ApiClient api=((AcmApplication)app.getApplicationContext()).api();String original=api.getBaseUrl();File cover=new File(app.getFilesDir(),"profile-cover.jpg");byte[] savedCover=null;File photo=new File(app.getCacheDir(),"crop-input.png");
        try{
            if(cover.isFile())try(InputStream in=new FileInputStream(cover)){savedCover=in.readAllBytes();}
            prefs.edit().putString("api_base_url","https://updates.test.invalid").putBoolean("app_update_automatic",false).putBoolean("app_update_wifi_download",false).putString("app_update_url","https://updates.test.invalid/update.json").apply();api.setBaseUrl("https://updates.test.invalid");
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"updates.test.invalid".equals(url.getHost()))throw new IOException("External traffic blocked");return new Fixture(url);}}:null);
            galleryAndCrop(photo,prefs);
            activity=test.startActivitySync(new Intent().setClassName(app,UpdateActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            AppUpdates updates=((AcmApplication)app.getApplicationContext()).updates();version=updates.currentVersion();
            releaseHistory(updates.currentName());
            main(()->{find("检查更新").performClick();find("检查更新").performClick();});await(()->has("已是最新版本"),8000,"current release dialog");check(requests.get()==1,"repeated check creates one request");click("确认");check(has("已是最新版"),"current release status retained");
            response=302;int redirectsBefore=requests.get();click("检查更新");await(()->has("已是最新版本"),8000,"HTTPS redirected manifest");click("确认");check(has("已是最新版")&&requests.get()==redirectsBefore+2,"HTTPS redirect follows once");
            response=404;click("检查更新");await(()->has("无API接口"),8000,"missing release API");check(!has("已是最新版"),"missing API is not current version");
            response=200;version=updates.currentVersion()+1;click("检查更新");await(()->has("下载安装包"),8000,"new release confirmation");click("取消更新");await(()->find("更新 0.2.9 版本")!=null,8000,"new release action");check(!has("无API接口"),"successful retry clears failure");screenshot("update-v028.png");
            version=updates.currentVersion();click("启动时自动检查更新");await(()->!updates.busy(),8000,"automatic check");main(()->check(prefs.getBoolean("app_update_automatic",false),"automatic choice persists"));
            main(()->{check(find("仅 Wi-Fi 自动下载新版")==null,"Wi-Fi auto download removed");find("启动时自动检查更新").performClick();check(!updates.automatic(),"disable automatic persists");});
            UriChecks();output.putString("stream","PASS: offline bundled release list and current/historical details, duplicate detail taps reuse one window, back preserves list scroll, no network while reading history; system photo picker, free crop and local save, update deduplication, latest/new/404 states, retry and automatic-check option, no Wi-Fi auto-download control, provider traversal rejected.\n");result=Activity.RESULT_OK;
        }catch(Throwable e){
            String diagnostics="";try{AppUpdates u=((AcmApplication)app.getApplicationContext()).updates();diagnostics="\nUpdate status: "+u.status()+"; source="+u.endpoint()+"; requests="+requests.get();screenshot("settings-failure-v028.png");}catch(Exception ignored){}
            output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e)+diagnostics);
        }
        finally{
            if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});photo.delete();ProfileCover.clear(app);
            if(savedCover!=null)try(FileOutputStream out=new FileOutputStream(cover)){out.write(savedCover);}catch(IOException ignored){}
            SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> item:before.entrySet()){Object value=item.getValue();if(value instanceof String)edit.putString(item.getKey(),(String)value);else if(value instanceof Boolean)edit.putBoolean(item.getKey(),(Boolean)value);else if(value instanceof Integer)edit.putInt(item.getKey(),(Integer)value);else if(value instanceof Long)edit.putLong(item.getKey(),(Long)value);else if(value instanceof Float)edit.putFloat(item.getKey(),(Float)value);}edit.apply();AppAppearance.load(app);api.setBaseUrl(original);
        }test.finish(result,output);
    }
    private void releaseHistory(String current)throws Exception{
        int before=requests.get();response=0;
        main(()->{check(find("更新日志与说明")!=null,"history section exists");check(find("v"+current+" · 当前版本")!=null,"installed release marked");});
        for(String version:new String[]{current,"0.1.0"}){
            int[] position={0};View[] dialog={null};
            main(()->{
                View open=description("查看 v"+version+" 更新说明");check(open!=null,"version is listed: "+version);
                open.requestRectangleOnScreen(new Rect(0,0,open.getWidth(),open.getHeight()),true);
            });test.waitForIdleSync();Thread.sleep(350);
            screenshot("release-list-"+version+".png");
            main(()->{
                ScrollView list=(ScrollView)walk(activity.getWindow().getDecorView(),v->v instanceof ScrollView);position[0]=list.getScrollY();
                View open=description("查看 v"+version+" 更新说明");open.performClick();dialog[0]=decor();open.performClick();
                check(decor()==dialog[0]&&dialog[0]!=activity.getWindow().getDecorView(),"duplicate detail reuses one dialog");
                TextView details=(TextView)description("版本更新详情 "+version);check(details!=null&&details.getText().toString().contains("更新日志")&&details.getText().toString().contains("更新说明"),"full notes rendered");
                check(details.getBackground()!=null,"notes have themed reading surface");
            });screenshot("release-details-"+version+".png");
            main(()->{FrameLayout frame=(FrameLayout)walk(decor(),v->"system_bar_surface".equals(v.getTag()));check(frame!=null&&frame.getChildAt(0).getTop()>0,"details inset below system time area");});
            test.sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);test.waitForIdleSync();
            main(()->{check(!ModalDialogs.isShowing(activity),"back dismisses details");ScrollView list=(ScrollView)walk(activity.getWindow().getDecorView(),v->v instanceof ScrollView);check(list.getScrollY()==position[0],"list scroll preserved");});
        }
        check(requests.get()==before,"offline history sends no requests");response=200;
        main(()->((ScrollView)walk(activity.getWindow().getDecorView(),v->v instanceof ScrollView)).scrollTo(0,0));
    }
    private void galleryAndCrop(File photo,SharedPreferences prefs)throws Exception{
        Bitmap input=Bitmap.createBitmap(1200,900,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(input);Paint paint=new Paint();paint.setColor(Color.RED);canvas.drawRect(0,0,600,900,paint);paint.setColor(Color.BLUE);canvas.drawRect(600,0,1200,900,paint);try(FileOutputStream out=new FileOutputStream(photo)){input.compress(Bitmap.CompressFormat.PNG,100,out);}input.recycle();
        activity=test.startActivitySync(new Intent().setClassName(app,OptionalTestClasses.type("AdvancedAppearanceActivity").getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));click("背景选择");Activity appearance=activity;
        AtomicInteger picks=new AtomicInteger();Instrumentation.ActivityMonitor picker=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(android.provider.MediaStore.ACTION_PICK_IMAGES.equals(intent.getAction())||Intent.ACTION_PICK.equals(intent.getAction())){picks.incrementAndGet();return new Instrumentation.ActivityResult(Activity.RESULT_OK,new Intent().setData(android.net.Uri.fromFile(photo)));}if(Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction()))throw new AssertionError("background opened file manager");return null;}};
        Instrumentation.ActivityMonitor cropMonitor=test.addMonitor(OptionalTestClasses.type("BackgroundCropActivity").getName(),null,false);test.addMonitor(picker);
        try{click("选择本机图片");Activity cropped=test.waitForMonitorWithTimeout(cropMonitor,8000);check(cropped!=null,"picker opens crop page");activity=cropped;await(()->find("使用此背景")!=null&&find("使用此背景").isEnabled(),8000,"crop image loaded");check(picks.get()==1,"photo picker invoked once");
            main(()->{View view=description("背景裁剪区域，拖动图片、双指缩放或拖动裁剪框边角");RectF before=(RectF)OptionalTestClasses.call(view,"frame",new Class<?>[0]);drag(view,before.right,before.bottom,before.right-40,before.bottom-50);RectF after=(RectF)OptionalTestClasses.call(view,"frame",new Class<?>[0]);check(after.width()<before.width()&&after.height()<before.height(),"crop frame freely resizes");drag(view,after.centerX(),after.centerY(),after.centerX()+30,after.centerY()+25);float[] selected=(float[])OptionalTestClasses.call(view,"selection",new Class<?>[0]);check(selected[0]>=-.1&&selected[1]>=-.1&&selected[2]<=1200.1&&selected[3]<=900.1,"panning keeps crop inside image");Bitmap out=(Bitmap)OptionalTestClasses.call(view,"export",new Class<?>[0]);check(out.getWidth()>0&&out.getHeight()>0&&out.getWidth()<1200,"export uses selected region");out.recycle();});screenshot("background-crop-v028.png");click("使用此背景");await(()->"image".equals(prefs.getString("bg_mode",""))&&ProfileCover.exists(app),8000,"cropped background stored");activity=appearance;main(()->activity.finish());
        }finally{test.removeMonitor(picker);test.removeMonitor(cropMonitor);}
    }
    private void UriChecks()throws Exception{boolean rejected=false;try{app.getContentResolver().openFileDescriptor(android.net.Uri.parse("content://"+app.getPackageName()+".updates/../private.apk"),"r");}catch(FileNotFoundException e){rejected=true;}check(rejected,"update provider rejects traversal");}
    private void drag(View view,float x,float y,float a,float b){long t=SystemClock.uptimeMillis();for(int i=0;i<3;i++){MotionEvent event=MotionEvent.obtain(t,t+i*30,i==0?MotionEvent.ACTION_DOWN:i==1?MotionEvent.ACTION_MOVE:MotionEvent.ACTION_UP,i==0?x:a,i==0?y:b,0);view.dispatchTouchEvent(event);event.recycle();}}
    private void screenshot(String name)throws Exception{test.waitForIdleSync();Thread.sleep(350);Bitmap b=test.getUiAutomation().takeScreenshot();if(b!=null){try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}}
    private void main(Runnable work){test.runOnMainSync(work);}
    private View walk(View view,java.util.function.Predicate<View> predicate){if(predicate.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),predicate);if(found!=null)return found;}}return null;}
    private View decor(){try{java.lang.reflect.Field field=ModalDialogs.class.getDeclaredField("visible");field.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)field.get(null)).get(activity);AlertDialog dialog=ref==null?null:(AlertDialog)ref.get();if(dialog!=null&&dialog.isShowing())return dialog.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View find(String text){return walk(decor(),v->v instanceof TextView&&text.contentEquals(((TextView)v).getText()));}
    private View description(String text){return walk(decor(),v->text.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private boolean has(String text){final boolean[] found={false};main(()->found[0]=find(text)!=null);return found[0];}
    private void click(String label){main(()->{View view=find(label);check(view!=null&&view.isEnabled(),"control available: "+label);view.performClick();});}
    private void await(BooleanSupplier condition,long timeout,String label)throws Exception{long end=SystemClock.uptimeMillis()+timeout;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(60);}throw new AssertionError("Timeout: "+label);}
    private void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        @Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}
        @Override public int getResponseCode(){requests.incrementAndGet();try{Thread.sleep(120);}catch(InterruptedException e){Thread.currentThread().interrupt();}return url.getPath().equals("/redirected.json")?200:response;}
        @Override public String getHeaderField(String name){return "Location".equalsIgnoreCase(name)?"/redirected.json":null;}
        @Override public InputStream getInputStream()throws IOException{try{return new ByteArrayInputStream(new JSONObject().put("packageName",app.getPackageName()).put("versionCode",version).put("versionName",version>((AcmApplication)app.getApplicationContext()).updates().currentVersion()?"0.2.9":"0.2.8").put("apkUrl","https://updates.test.invalid/new.apk").put("sha256",new String(new char[64]).replace('\0','a')).put("sizeBytes",2048).put("minSdk",26).put("notes","测试版本说明").toString().getBytes(StandardCharsets.UTF_8));}catch(Exception e){throw new IOException(e);}}
    }
}
