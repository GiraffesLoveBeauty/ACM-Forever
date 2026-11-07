package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Bitmap;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.*;

/** Local-only transport: exercise real settings and image recovery without production data. */
final class RecoverySettingsUiSmoke {
    private final Instrumentation test;
    private final Context context;
    private Activity activity;
    private volatile boolean failing=true, invalid;
    private final AtomicInteger images=new AtomicInteger(), manifests=new AtomicInteger();
    private byte[] png;
    private RecoverySettingsUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new RecoverySettingsUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)context.getApplicationContext();ApiClient api=app.api();String original=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        File working=new File(context.getCacheDir(),"acm-statement-recovery-test.pdf");
        File cachedPackage=new File(new File(context.getCacheDir(),"updates"),"verified-recoverytest.apk");
        try{
            Bitmap bitmap=Bitmap.createBitmap(8,8,Bitmap.Config.ARGB_8888);ByteArrayOutputStream image=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,image);bitmap.recycle();png=image.toByteArray();
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"recovery.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://recovery.test.invalid").putString("app_update_url","https://recovery.test.invalid/update.json").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).putString("remembered_account","storage-preserve-test").apply();
            api.setBaseUrl("https://recovery.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Password!");
            activity=open(HelpActivity.class);await(()->has("统一帮助与问题反馈在QQ群里直接提"),"local help");check(has("数据与权限说明"),"data information");screenshot("recovery-help.png");finishPage();
            Files.write(working,new byte[]{1,2,3});app.pdfFiles().save("recovery-test",working);
            activity=open(StorageActivity.class);await(()->contains("内容缓存约"),"storage accounting");
            check(has("缓存占用查看")&&has("已下载安装包"),"three storage sections");
            click("清理临时文件");click("确认清理");await(()->has("临时缓存已清理"),"temporary cleanup");
            check(working.exists(),"active PDF working copy retained");check("storage-preserve-test".equals(prefs.getString("remembered_account","")),"account setting retained");
            check(!app.pdfFiles().copyTo("recovery-test",new File(context.getCacheDir(),"unused-copy.pdf")),"PDF cache cleared");
            screenshot("recovery-storage.png");finishPage();
            cachedPackage.getParentFile().mkdirs();Files.write(cachedPackage,new byte[]{1,2,3});
            activity=test.startActivitySync(new Intent(context,UpdateActivity.class).putExtra("manage_downloads",true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            check(manifests.get()==0,"package manager does not automatically check update");
            click("清理已下载安装包");click("确认清理");await(()->!cachedPackage.exists(),"package deleted");check(working.exists(),"document not deleted by package cleanup");finishPage();
            openImage("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");await(()->has("API连接失败"),"image failure warning");check(has("重新读取图片"),"image retry entry");
            failing=false;click("重新读取图片");await(()->has("双指缩放 · 拖动查看"),"manual image retry");await(()->has("重连成功"),"green reconnect");
            Thread.sleep(3300);check(!shown("重连成功"),"success closes after three seconds");finishPage();
            failing=true;openImage("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");await(()->has("API连接失败"),"second failure warning");
            clickDescription("关闭API连接失败提示");check(!shown("API连接失败"),"warning manually closed");
            failing=false;await(()->has("双指缩放 · 拖动查看"),"auto retry continues after dismiss");finishPage();
            invalid=true;int before=images.get();openImage("cccccccccccccccccccccccccccccccc");await(()->has("不支持的图片格式"),"invalid image format");
            Thread.sleep(10500);check(images.get()==before+1,"invalid format does not auto retry");check(!shown("API连接失败"),"invalid format is not network error");
            invalid=false;click("重新读取图片");await(()->has("双指缩放 · 拖动查看"),"manual recovery from invalid format");finishPage();
            api.logout();Instrumentation.ActivityMonitor monitor=test.addMonitor(MainActivity.class.getName(),null,false);
            try{activity=open(StorageActivity.class);Activity login=test.waitForMonitorWithTimeout(monitor,10000);check(login!=null,"storage requires login");activity=login;await(()->has("账号登录"),"login gate");}finally{test.removeMonitor(monitor);}
            output.putString("stream","PASS: local help/data information; three storage sections; safe cleanup preserves account/working PDF; package management skips update check; manual and automatic image recovery; warning dismiss keeps retries; success hides in 3s; format errors do not loop; login gate.\n");result=Activity.RESULT_OK;
        }catch(Throwable e){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));try{screenshot("recovery-failure.png");}catch(Exception ignored){}}
        finally{
            finishPage();working.delete();cachedPackage.delete();try{api.logout();}catch(Exception ignored){}api.setBaseUrl(original);
            SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> e:saved.entrySet()){Object v=e.getValue();String k=e.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);}edit.apply();
        }
        test.finish(result,output);
    }
    private Activity open(Class<?> page){return test.startActivitySync(new Intent(context,page).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
    private void openImage(String id){activity=test.startActivitySync(new Intent(context,ImagePreviewActivity.class).putExtra("url","https://recovery.test.invalid/api/forum/images/"+id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
    private void finishPage(){if(activity!=null){Activity current=activity;main(()->{ModalDialogs.close(current);current.finish();});test.waitForIdleSync();activity=null;}}
    private void main(Runnable work){test.runOnMainSync(work);}
    private View walk(View view,Predicate<View> predicate){if(predicate.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),predicate);if(found!=null)return found;}}return null;}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog d=ref==null?null:(AlertDialog)ref.get();if(d!=null&&d.isShowing())return d.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View find(String value){return walk(decor(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private boolean has(String value){boolean[] found={false};main(()->found[0]=find(value)!=null);return found[0];}
    private boolean contains(String value){boolean[] found={false};main(()->found[0]=walk(decor(),v->v instanceof TextView&&((TextView)v).getText().toString().contains(value))!=null);return found[0];}
    private boolean shown(String value){boolean[] found={false};main(()->{View v=find(value);found[0]=v!=null&&v.isShown();});return found[0];}
    private void click(String text){main(()->{View view=walk(decor(),v->v instanceof Button&&text.contentEquals(((Button)v).getText()));check(view!=null&&view.isEnabled(),"click "+text);view.performClick();});test.waitForIdleSync();}
    private void clickDescription(String text){main(()->{View view=walk(decor(),v->text.equals(v.getContentDescription()));check(view!=null,"click "+text);view.performClick();});}
    private void await(BooleanSupplier condition,String title)throws Exception{long end=SystemClock.uptimeMillis()+20000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(80);}throw new AssertionError("Timeout: "+title);}
    private void screenshot(String name)throws Exception{
        // View construction/idle does not imply that Android's cold-start splash has gone.
        long until=SystemClock.uptimeMillis()+8000;
        do{
            test.waitForIdleSync();Thread.sleep(250);Bitmap b=test.getUiAutomation().takeScreenshot();
            if(b==null)continue;int ink=0;
            for(int y=b.getHeight()/8;y<b.getHeight()*7/8;y+=8)for(int x=16;x<b.getWidth()-16;x+=8){int color=b.getPixel(x,y);if(android.graphics.Color.red(color)<150&&android.graphics.Color.green(color)<150&&android.graphics.Color.blue(color)<150)ink++;}
            if(ink>30){try(OutputStream out=new FileOutputStream(new File(context.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}finally{b.recycle();}return;}
            b.recycle();
        }while(SystemClock.uptimeMillis()<until);
        throw new AssertionError("Page has not visibly drawn: "+name);
    }
    private static void check(boolean value,String title){if(!value)throw new AssertionError(title);}
    private static final class Files{static void write(File file,byte[] bytes)throws IOException{try(OutputStream out=new FileOutputStream(file)){out.write(bytes);}}}
    private final class Fixture extends HttpURLConnection{
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public int getResponseCode(){if(url.getPath().contains("/images/")){images.incrementAndGet();return failing?503:200;}return 200;}
        public String getContentType(){return invalid?"text/plain":"image/png";}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=recovery-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getInputStream(){String path=url.getPath();if(path.contains("/images/"))return new ByteArrayInputStream(png);if(path.endsWith("update.json"))manifests.incrementAndGet();String json=path.endsWith("/me")?"{\"authenticated\":true,\"csrf_token\":\"synthetic\",\"role\":\"member\",\"qq_id\":\"90000001\"}":"{}";return new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8));}
    }
}
