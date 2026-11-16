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
import org.json.*;

/** Intercepts every HTTPS request inside the test process; never calls a public host. */
final class GiteeUpdatesUiSmoke {
    private final Instrumentation test;private final Context context;private AppUpdates updates;private ApiClient api;
    private final AtomicInteger primary=new AtomicInteger(),fallback=new AtomicInteger(),manifestFallback=new AtomicInteger();
    private volatile boolean primaryFails,artifactFails;private long code;private String version;private final byte[] payload="synthetic module bytes; never installed".getBytes(StandardCharsets.UTF_8);
    private Activity activity;
    private GiteeUpdatesUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new GiteeUpdatesUiSmoke(test).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;
        SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();AppUpdates old=app.updates();File downloaded=new File(context.getCacheDir(),"gitee-smoke.bin");
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL u)throws IOException{return new Fixture(u);}}:null);
            api.setBaseUrl("https://gitee-updates.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            prefs.edit().remove("app_update_url").remove("app_update_manifest").remove("app_update_source").remove("app_update_download").remove("app_update_verified").putBoolean("app_update_automatic",false).commit();
            updates=new AppUpdates(context,api,()->true);java.lang.reflect.Field owner=AcmApplication.class.getDeclaredField("updates");owner.setAccessible(true);owner.set(app,updates);code=updates.currentVersion()+1;version=updates.currentName();
            check(updates.endpoint().equals(UpdateSources.GITEE_LATEST),"Gitee is default");
            main(()->updates.check(true));waitDone();check(updates.available()&&manifestFallback.get()==0,"newer Gitee result avoids GitHub: "+updates.status());
            primaryFails=true;main(()->updates.check(true));waitDone();check(updates.available()&&updates.sourceStatus().contains("最近成功来源：GitHub"),"Gitee outage falls back to GitHub");
            primaryFails=false;code=updates.currentVersion();main(()->updates.check(true));waitDone();check(updates.error().isEmpty()&&updates.sourceStatus().contains("最近成功来源：Gitee"),"matching versions prefer Gitee");
            activity=test.startActivitySync(new Intent(context,UpdateActivity.class).putExtra("manage_downloads",true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));test.waitForIdleSync();
            main(()->check(walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&((TextView)v).getText().toString().contains("优先 Gitee，不可用时尝试 GitHub"))!=null,"update page displays priority"));
            ModuleSpec spec=new ModuleSpec("cat-art",UpdateSources.asset(version,"module-cat-art.acmpack",true),ModuleFiles.hex(java.security.MessageDigest.getInstance("SHA-256").digest(payload)),"assets",payload.length,(int)code);
            ModuleNetwork.download(spec,downloaded,n->{},()->false);check(Arrays.equals(payload,java.nio.file.Files.readAllBytes(downloaded.toPath())),"Gitee redirect downloads exact module bytes");downloaded.delete();
            artifactFails=true;int before=fallback.get();ModuleNetwork.download(spec,downloaded,n->{},()->false);check(fallback.get()>before&&Arrays.equals(payload,java.nio.file.Files.readAllBytes(downloaded.toPath())),"module failure retries exact GitHub artifact");downloaded.delete();
            before=fallback.get();try{ModuleNetwork.download(spec,downloaded,n->{},()->true);throw new AssertionError("cancellation accepted");}catch(IOException expected){}check(fallback.get()==before&&!downloaded.exists(),"cancel does not launch fallback or retain partial file");
            main(()->updates.source("https://gitee-updates.test.invalid/custom.json"));main(()->updates.check(true));waitDone();check(updates.error().isEmpty()&&updates.endpoint().contains("custom.json"),"custom source preserved");
            result.putString("stream","PASS: Gitee-first default, valid newer primary skips GitHub, metadata outage falls back, current version source label, real update page displays priority, Gitee CDN redirect and exact module bytes, module network fallback, cancellation cleanup, explicit custom source. All HTTPS traffic intercepted.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable failure){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure));}
        finally{
            if(updates!=null)main(updates::cancelDownload);if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});downloaded.delete();
            try{api.logout();}catch(Exception ignored){}api.setBaseUrl(base);
            try{java.lang.reflect.Field f=AcmApplication.class.getDeclaredField("updates");f.setAccessible(true);f.set(app,old);}catch(Exception ignored){}
            SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> item:saved.entrySet()){Object v=item.getValue();String k=item.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);else if(v instanceof Set)edit.putStringSet(k,new HashSet<>((Set<String>)v));}edit.commit();
        }
        test.finish(outcome,result);
    }
    private void main(Runnable job){test.runOnMainSync(job);}
    private void waitDone()throws Exception{long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=!updates.busy());if(done[0])return;Thread.sleep(60);}throw new AssertionError("update timeout");}
    private static View walk(View v,java.util.function.Predicate<View> predicate){if(predicate.test(v))return v;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++){View found=walk(((ViewGroup)v).getChildAt(i),predicate);if(found!=null)return found;}return null;}
    private static void check(boolean yes,String label){if(!yes)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL u){super(u);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic-gitee; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public int getResponseCode()throws IOException{
            if(url.getHost().equals("gitee.com")){primary.incrementAndGet();if(primaryFails||artifactFails&&url.getPath().endsWith(".acmpack"))throw new IOException("synthetic Gitee outage");if(url.getPath().endsWith(".acmpack"))return 302;return 200;}
            if(url.getHost().equals("github.com")){fallback.incrementAndGet();if(url.toString().equals(UpdateSources.GITHUB_LATEST))manifestFallback.incrementAndGet();return 200;}
            if(url.getHost().equals("foruda.gitee.com")||url.getHost().equals("gitee-updates.test.invalid"))return 200;
            throw new IOException("External traffic forbidden");
        }
        public String getHeaderField(String name){return "Location".equals(name)?"https://foruda.gitee.com/attach_file/synthetic/module-cat-art.acmpack":null;}
        public InputStream getInputStream()throws IOException{
            try{
                if(url.getPath().endsWith(".acmpack"))return new ByteArrayInputStream(payload);
                JSONObject body=new JSONObject();
                if(url.toString().equals(UpdateSources.GITEE_LATEST))body.put("tag_name","v"+version).put("prerelease",false);
                else if(url.getPath().endsWith("update.json")||url.getPath().endsWith("custom.json")){boolean gitee=url.getHost().equals("gitee.com");body.put("packageName",context.getPackageName()).put("versionCode",code).put("versionName",version).put("schemaVersion",2).put("distribution","release").put("apkUrl",UpdateSources.asset(version,"acmforever-"+version+".apk",gitee)).put("sha256",String.join("",Collections.nCopies(64,"a"))).put("modulesUrl",UpdateSources.asset(version,"modules.json",gitee));}
                else if(url.getPath().endsWith("modules.json")){JSONArray rows=new JSONArray();for(String id:ModuleSpec.IDS)rows.put(new JSONObject().put("id",id).put("kind",ModuleSpec.nativeModule(id)?"native":"assets").put("url",UpdateSources.asset(version,ModuleSpec.filename(id),url.getHost().equals("gitee.com"))).put("sizeBytes",payload.length).put("sha256",ModuleFiles.hex(java.security.MessageDigest.getInstance("SHA-256").digest(payload))));body.put("schemaVersion",1).put("versionCode",code).put("versionName",version).put("modules",rows);}
                else if(url.getPath().endsWith("/me"))body.put("authenticated",true).put("csrf_token","synthetic").put("role","member").put("qq_id","90000001");
                return new ByteArrayInputStream(body.toString().getBytes(StandardCharsets.UTF_8));
            }catch(Exception e){throw new IOException(e);}
        }
    }
}
