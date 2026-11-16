package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.content.pm.ApplicationInfo;
import android.os.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.json.JSONObject;

/** Upgrade persistence and private download checks with synthetic HTTPS transport only. */
final class ReleaseChannelsUiSmoke {
    private static final String ORIGIN="https://channels.test.invalid",ACCOUNT="90000001",PASSWORD="Synthetic-Only!";
    static void run(Instrumentation test,String mode){
        test.runOnMainSync(()->{}); // Application startup must finish before replacing test preferences.
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        Context context=test.getTargetContext();SharedPreferences prefs=AppAppearance.prefs(context);
        try{
            if(mode.equals("seedrelease")){
                check(context.getPackageManager().getPackageInfo(context.getPackageName(),0).versionName.equals("0.2.30"),"seed original published APK");
                check(prefs.edit().putString("remembered_account",ACCOUNT).putBoolean("remember_account",true).putBoolean("auto_login",false)
                    .putString("api_base_url",ORIGIN).putInt("theme_primary",0xff4488cc).putInt("module_transparency",2)
                    .putString("search_history","[\"upgrade-proof\"]").commit(),"seed preferences");
                check(new SessionVault(prefs).savePassword(ORIGIN,ACCOUNT,PASSWORD),"seed Android Keystore password");
                check(prefs.edit().commit(),"flush asynchronous password preferences before package replacement");
                check(PASSWORD.equals(new SessionVault(prefs).readPassword(ORIGIN,ACCOUNT)),"seed encrypted password readable");
                try(FileOutputStream out=new FileOutputStream(new File(context.getFilesDir(),"migration-proof.bin"))){out.write(new byte[]{1,7,9,3});}
                seedModules(test,context);
                legacyUpdateManifest(test,context,prefs);
            }else if(mode.equals("verifymigration")||mode.equals("verifylegacyreturn")||mode.equals("verifypreview")){
                String expected=mode.equals("verifylegacyreturn")?"0.2.30":new JSONObject(readManifest(test)).getString("versionName");
                check(context.getPackageManager().getPackageInfo(context.getPackageName(),0).versionName.equals(expected),"expected covering version installed");
                if(!mode.equals("verifylegacyreturn"))check((context.getApplicationInfo().flags&ApplicationInfo.FLAG_DEBUGGABLE)==0,"preview and formal APKs are not debuggable");
                check(ACCOUNT.equals(prefs.getString("remembered_account","")),"account retained");
                boolean savedPassword=prefs.getBoolean("save_password",false),cipherPresent=prefs.contains("password_cipher");
                check(PASSWORD.equals(new SessionVault(prefs).readPassword(ORIGIN,ACCOUNT)),"encrypted password and Keystore key retained; saved="+savedPassword+", cipher="+cipherPresent);
                check(prefs.getInt("theme_primary",0)==0xff4488cc&&prefs.getInt("module_transparency",0)==2,"appearance retained");
                check(prefs.getString("search_history","").contains("upgrade-proof"),"history retained");
                try(FileInputStream in=new FileInputStream(new File(context.getFilesDir(),"migration-proof.bin"))){check(Arrays.equals(in.readAllBytes(),new byte[]{1,7,9,3}),"private files retained");}
                for(String id:ModuleSpec.IDS)check(ModuleHealth.verify(context,id).intact,"previously downloaded module preserved: "+id);
                if(mode.equals("verifypreview"))publicReturn(test,context);
            }else{
                privateDownload(test,context);
            }
            output.putString("stream","PASS: "+mode+"; "+(mode.equals("releasechannels")?"member denied; admin preview download; real APK hash/package/signature/revision checked; provider read only; logout invalidates private download":"same-package covering switch preserves account, encrypted password, theme, history and files; preview disables automatic checking")+".\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\n");}
        test.finish(result,output);
    }
    private static void publicReturn(Instrumentation test,Context context)throws Exception{
        check(AppDistribution.installed(context).preview,"preview metadata installed");
        byte[] old;
        try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/acm-old-fixture.apk");InputStream in=new FileInputStream(fd.getFileDescriptor())){old=in.readAllBytes();}
        StringBuilder hash=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(old))hash.append(String.format(Locale.ROOT,"%02x",b&255));
        JSONObject metadata=new JSONObject().put("packageName",context.getPackageName()).put("versionName","0.2.30").put("versionCode",44).put("minSdk",26)
            .put("channel","debug").put("sizeBytes",old.length).put("sha256",hash.toString()).put("apkUrl",ORIGIN+"/stable.apk");
        int[] calls={0};URL.setURLStreamHandlerFactory(protocol->!"https".equals(protocol)?null:new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{
            if(!url.toString().equals(ORIGIN+"/update.json"))throw new IOException("External traffic forbidden");
            return new HttpURLConnection(url){public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public int getResponseCode(){calls[0]++;return 200;}public InputStream getInputStream(){return new ByteArrayInputStream(metadata.toString().getBytes(StandardCharsets.UTF_8));}};
        }});
        AppAppearance.prefs(context).edit().putBoolean("app_update_automatic",true).putString("app_update_url",ORIGIN+"/update.json").commit();
        AppUpdates[] track={null};test.runOnMainSync(()->{track[0]=new AppUpdates(context,((AcmApplication)context.getApplicationContext()).api(),()->true);check(!track[0].automatic(),"preview suppresses saved automatic option");track[0].maybeCheck();track[0].check(false);});
        Thread.sleep(200);check(calls[0]==0,"no automatic manifest request in preview");
        test.runOnMainSync(()->track[0].check(true));await(test,()->!track[0].busy());check(track[0].available(),"manual stable return available at equal versionCode: "+track[0].status());
        File file=new File(context.getCacheDir(),"stable-return-probe.apk");try(FileOutputStream out=new FileOutputStream(file)){out.write(old);}
        try{track[0].validatePackage(file,new UpdateManifest(metadata,context.getPackageName()));}finally{file.delete();}
    }
    private static void legacyUpdateManifest(Instrumentation test,Context context,SharedPreferences prefs)throws Exception{
        byte[] manifest=readManifest(test).getBytes(StandardCharsets.UTF_8);
        JSONObject value=new JSONObject(new String(manifest,StandardCharsets.UTF_8));
        check(value.getLong("versionCode")==45&&"release".equals(value.getString("distribution"))&&!value.has("channel"),"real formal manifest enables legacy migration");
        URL.setURLStreamHandlerFactory(protocol->!"https".equals(protocol)?null:new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{
            if(!url.getHost().equals("channels.test.invalid"))throw new IOException("External traffic forbidden");
            return new HttpURLConnection(url){
                public void connect(){} public void disconnect(){} public boolean usingProxy(){return false;}
                public int getResponseCode(){return 200;}
                public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
                public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic-migration; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
                public InputStream getInputStream(){return new ByteArrayInputStream(url.getPath().equals("/update.json")?manifest:(url.getPath().endsWith("/me")?"{\"authenticated\":true,\"csrf_token\":\"synthetic\",\"role\":\"member\",\"qq_id\":\"90000001\"}":"{}").getBytes(StandardCharsets.UTF_8));}
            };
        }});
        prefs.edit().putString("app_update_url",ORIGIN+"/update.json").commit();
        ApiClient api=((AcmApplication)context.getApplicationContext()).api();api.setBaseUrl(ORIGIN);api.setNetworkAvailable(()->true);api.login(ACCOUNT,PASSWORD);
        AppUpdates[] controller={null};
        test.runOnMainSync(()->{controller[0]=new AppUpdates(context,api,()->true);controller[0].check(true);});
        await(test,()->!controller[0].busy());
        check(controller[0].available()&&controller[0].error().isEmpty(),"published 0.2.30 accepts real next public update manifest: "+controller[0].status());
    }
    private static String readManifest(Instrumentation test)throws Exception{
        try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/acm-formal-manifest.json");InputStream in=new FileInputStream(fd.getFileDescriptor())){return new String(in.readAllBytes(),StandardCharsets.UTF_8);}
    }
    private static void seedModules(Instrumentation test,Context context)throws Exception{
        byte[] bytes;try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/acm-old-modules.json");InputStream in=new FileInputStream(fd.getFileDescriptor())){bytes=in.readAllBytes();}
        Map<String,ModuleSpec> catalog=ModuleSpec.parse(new JSONObject(new String(bytes,StandardCharsets.UTF_8)),44,"0.2.30");
        File root=ModuleStore.root(context,44);root.mkdirs();try(FileOutputStream out=new FileOutputStream(new File(root,"catalog.json"))){out.write(bytes);}
        for(String id:ModuleSpec.IDS){
            ModuleSpec spec=catalog.get(id);File archive=ModuleStore.archive(context,id,44);
            check(archive.getParentFile().isDirectory()||archive.getParentFile().mkdirs(),"create fixture module download directory");
            try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/old-"+ModuleSpec.filename(id));InputStream in=new FileInputStream(fd.getFileDescriptor());FileOutputStream out=new FileOutputStream(archive)){in.transferTo(out);}
            ModuleFiles.verify(archive,spec,ModuleStore.trusted(context));
            if(!ModuleSpec.nativeModule(id))ModuleStore.installAssets(context,spec);
            ModuleStore.acquired(context,id);check(ModuleHealth.verify(context,id).intact,"old published module seeded: "+id);
        }
    }
    private static void privateDownload(Instrumentation test,Context context)throws Exception{
        byte[] apk;
        try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/acm-admin-fixture.apk");InputStream in=new FileInputStream(fd.getFileDescriptor())){apk=in.readAllBytes();}
        check(apk.length>100000,"test fixture is real admin APK");
        File probe=new File(context.getCacheDir(),"admin-archive-probe.apk");
        try(FileOutputStream out=new FileOutputStream(probe)){out.write(apk);}
        android.content.pm.PackageInfo parsed=context.getPackageManager().getPackageArchiveInfo(probe.getAbsolutePath(),android.content.pm.PackageManager.GET_SIGNING_CERTIFICATES);
        check(parsed!=null&&!ApkManifest.debuggable(context.getPackageManager(),probe,parsed),"real preview archive is not debuggable");
        AppDistribution distribution=AppDistribution.archive(context.getPackageManager().getPackageArchiveInfo(probe.getAbsolutePath(),android.content.pm.PackageManager.GET_META_DATA));probe.delete();
        android.content.pm.PackageInfo formal=context.getPackageManager().getPackageArchiveInfo(context.getApplicationInfo().sourceDir,0);
        check(formal!=null&&!ApkManifest.debuggable(context.getPackageManager(),new File(context.getApplicationInfo().sourceDir),formal),"real formal archive is not debuggable");
        StringBuilder hash=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(apk))hash.append(String.format(Locale.ROOT,"%02x",b&255));
        String previewTag="v"+parsed.versionName+"-preview."+distribution.revision;
        JSONObject metadata=new JSONObject().put("packageName",context.getPackageName()).put("distribution","preview")
            .put("versionName",parsed.versionName).put("versionCode",parsed.getLongVersionCode()).put("releaseVersionCode",distribution.releaseCode).put("previewRevision",distribution.revision).put("previewTag",previewTag).put("minSdk",26).put("sizeBytes",apk.length).put("sha256",hash.toString())
            .put("apkPath","/api/admin/android/releases/"+previewTag+"/apk").put("notes","Synthetic transport, real local APK");
        Map<String,byte[]> moduleBytes=new HashMap<>();JSONObject moduleCatalog;
        try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/acm-preview-modules.json");InputStream in=new FileInputStream(fd.getFileDescriptor())){moduleCatalog=new JSONObject(new String(in.readAllBytes(),StandardCharsets.UTF_8));}
        metadata.put("modulesPath","/api/admin/android/releases/"+previewTag+"/modules").put("moduleCatalog",moduleCatalog);
        for(String id:ModuleSpec.IDS){String name=ModuleSpec.filename(id);try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/"+name);InputStream in=new FileInputStream(fd.getFileDescriptor())){moduleBytes.put(name,in.readAllBytes());}}
        String[] role={"member"};boolean[] cookie={false},empty={false};
        URL.setURLStreamHandlerFactory(protocol->!"https".equals(protocol)?null:new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{
            if(!url.getHost().equals("channels.test.invalid"))throw new IOException("External traffic forbidden");
            return new HttpURLConnection(url){
                @Override public void connect(){} @Override public void disconnect(){} @Override public boolean usingProxy(){return false;}
                @Override public int getResponseCode(){return 200;}
                @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
                @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
                @Override public long getContentLengthLong(){String name=url.getPath().substring(url.getPath().lastIndexOf('/')+1);return moduleBytes.containsKey(name)?moduleBytes.get(name).length:url.getPath().endsWith("/apk")?apk.length:-1;}
                @Override public InputStream getInputStream()throws IOException{
                    String path=url.getPath();
                    if(path.endsWith("/apk")){cookie[0]=getRequestProperty("Cookie")!=null;check(!getInstanceFollowRedirects(),"private download does not redirect cookie");return new ByteArrayInputStream(apk);}
                    if(path.contains("/assets/")){String name=path.substring(path.lastIndexOf('/')+1);check(getRequestProperty("Cookie")!=null&&!getInstanceFollowRedirects(),"private module uses Cookie without redirects");if(!moduleBytes.containsKey(name))throw new IOException("Unknown fixture module");return new ByteArrayInputStream(moduleBytes.get(name));}
                    try{return new ByteArrayInputStream((path.endsWith("/latest")?(empty[0]?"{\"available\":false}":metadata.toString()):path.endsWith("/me")?new JSONObject().put("authenticated",true).put("csrf_token","synthetic").put("role",role[0]).put("qq_id",ACCOUNT).toString():"{}").getBytes(StandardCharsets.UTF_8));}catch(Exception e){throw new IOException(e);}
                }
            };
        }});
        AcmApplication app=(AcmApplication)context.getApplicationContext();ApiClient api=app.api();api.setBaseUrl(ORIGIN);api.setNetworkAvailable(()->true);api.login(ACCOUNT,PASSWORD);
        boolean denied=false;try{api.adminRelease();}catch(ApiClient.ApiException e){denied=e.status==403;}check(denied,"member cannot request private metadata");
        role[0]="admin";api.refreshSession();test.waitForIdleSync();AppUpdates[] track={null};test.runOnMainSync(()->track[0]=new AppUpdates(context,api,()->true,true));
        AppUpdates updates=track[0];java.lang.reflect.Field controller=AcmApplication.class.getDeclaredField("adminUpdates");controller.setAccessible(true);controller.set(app,updates);
        test.runOnMainSync(()->updates.check(true));await(test,()->!updates.busy());check(updates.available(),"admin metadata available: "+updates.status());
        test.runOnMainSync(updates::download);await(test,()->!updates.busy());check(updates.ready()&&updates.error().isEmpty()&&cookie[0],"private APK verified and cookie sent; state="+updates.status()+", cookie="+cookie[0]);
        Map<String,ModuleSpec> specs=ModuleNetwork.catalog(context,UpdateManifest.administrator(metadata,ORIGIN));
        for(String id:ModuleSpec.IDS){ModuleSpec spec=specs.get(id);check(spec.downloadUrls().size()==1&&spec.url.startsWith(ORIGIN+"/api/admin/android/releases/"+previewTag+"/assets/"),"private modules have no anonymous fallback");
            File target=new File(context.getCacheDir(),"private-"+ModuleSpec.filename(id));try{ModuleNetwork.download(context,spec,target,n->{},()->false);ModuleFiles.verify(target,spec,ModuleStore.trusted(context));}finally{target.delete();}}
        File cancelled=new File(context.getCacheDir(),"cancelled-preview-module.bin");boolean stopped=false;
        try{ModuleNetwork.download(context,specs.get("cat-art"),cancelled,n->{},()->true);}catch(IOException expected){stopped=true;}finally{cancelled.delete();}check(stopped,"private module cancellation is honored");
        java.lang.reflect.Field field=AppUpdates.class.getDeclaredField("verifiedName");field.setAccessible(true);String name=(String)field.get(updates);
        android.net.Uri uri=android.net.Uri.parse("content://"+context.getPackageName()+".updates/"+name);
        try(InputStream in=context.getContentResolver().openInputStream(uri)){check(in.read()>=0,"verified provider readable");}
        boolean readOnly=false;try(ParcelFileDescriptor fd=context.getContentResolver().openFileDescriptor(uri,"w")){}catch(FileNotFoundException e){readOnly=true;}check(readOnly,"installer provider is read only");
        Activity parent=test.startActivitySync(new Intent(context,UpdateActivity.class).putExtra("manage_downloads",true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        Instrumentation.ActivityMonitor monitor=test.addMonitor(UpdateActivity.class.getName(),null,false);
        Activity child=null;
        try{
            test.runOnMainSync(()->{android.view.View button=find(parent.getWindow().getDecorView(),"待发布测试版");check(button!=null,"update page has admin-only preview entry");button.performClick();button.performClick();});
            child=test.waitForMonitorWithTimeout(monitor,8000);
            check(child!=null&&child!=parent&&child.getIntent().getBooleanExtra("admin_distribution",false),"admin update opens a distinct child page");
            test.waitForIdleSync();check(monitor.getHits()==1,"repeated admin entry taps open one page");
            Activity active=child;test.runOnMainSync(()->check(find(active.getWindow().getDecorView(),"启动时自动检查更新")==null,"preview entry only checks manually"));
            installerOwnership(test,context,app,updates,active);
            Activity opened=child;test.runOnMainSync(opened::finish);test.waitForIdleSync();
            check(!parent.isFinishing()&&!parent.isDestroyed(),"return preserves formal update parent");
        }finally{test.removeMonitor(monitor);Activity opened=child;test.runOnMainSync(()->{if(opened!=null)opened.finish();parent.finish();});}
        String staleReceipt=updates.installReceipt();
        api.logout();test.waitForIdleSync();check(!updates.ready(),"logout clears private ready state");
        callback(test,context,staleReceipt,android.content.pm.PackageInstaller.STATUS_PENDING_USER_ACTION,new Intent(context,UpdateActivity.class));
        test.waitForIdleSync();check(!updates.awaitingModuleInstall(),"old private confirmation cannot survive logout");
        AppUpdates restarted=new AppUpdates(context,api,()->true,true);check(!restarted.ownsInstallReceipt(staleReceipt),"process restart cannot reuse private installer authority");
        boolean blocked=false;try(InputStream in=context.getContentResolver().openInputStream(uri)){}catch(FileNotFoundException e){blocked=true;}check(blocked,"logged-out provider cannot serve debug APK");
        empty[0]=true;api.login(ACCOUNT,PASSWORD);test.waitForIdleSync();test.runOnMainSync(()->updates.check(true));await(test,()->!updates.busy());
        check(!updates.available()&&updates.error().isEmpty()&&updates.status().equals("暂无待发布测试版"),"released preview disappears as valid empty result");
    }
    private static void installerOwnership(Instrumentation test,Context context,AcmApplication app,AppUpdates updates,Activity page)throws Exception{
        check(!ModuleStore.installedNativeChecked(context).isEmpty(),"real preview installer fixture includes native splits");
        check(context.getPackageManager().canRequestPackageInstalls(),"isolated emulator explicitly permits system install request");
        AppUpdates formal=app.updates();check(!formal.awaitingModuleInstall(),"formal controller initially detached");
        test.runOnMainSync(()->updates.install(page));
        await(test,()->updates.awaitingModuleInstall()||!updates.error().isEmpty());
        check(updates.awaitingModuleInstall()&&updates.error().isEmpty(),"real PackageInstaller pending action reaches preview controller: "+updates.status());
        check(!formal.awaitingModuleInstall()&&formal.error().isEmpty(),"preview confirmation never enters detached formal controller");
        long end=SystemClock.uptimeMillis()+10000;boolean systemVisible=false;
        while(SystemClock.uptimeMillis()<end){android.view.accessibility.AccessibilityNodeInfo window=test.getUiAutomation().getRootInActiveWindow();
            if(window!=null&&window.getPackageName()!=null&&window.getPackageName().toString().contains("packageinstaller")){systemVisible=true;break;}Thread.sleep(100);}
        check(systemVisible,"actual system package installer confirmation displayed from preview page");
        try(ParcelFileDescriptor ignored=test.getUiAutomation().executeShellCommand("input keyevent KEYCODE_BACK")){Thread.sleep(300);}
        await(test,()->!updates.awaitingModuleInstall()&&!updates.error().isEmpty());
        check(updates.error().contains("取消")&&formal.error().isEmpty(),"real system cancellation updates preview only");
        test.runOnMainSync(updates::dismissError);
        callback(test,context,updates.installReceipt(),android.content.pm.PackageInstaller.STATUS_FAILURE,null);test.waitForIdleSync();
        check(updates.error().contains("系统安装失败")&&formal.error().isEmpty(),"failure callback also preserves controller ownership");
        test.runOnMainSync(updates::dismissError);
        callback(test,context,"app-update",android.content.pm.PackageInstaller.STATUS_FAILURE_ABORTED,null);test.waitForIdleSync();
        check(formal.error().contains("取消")&&updates.error().isEmpty(),"legacy formal receipt remains supported");test.runOnMainSync(formal::dismissError);
    }
    private static void callback(Instrumentation test,Context context,String receipt,int status,Intent confirmation)throws Exception{
        int session=190001;context.getSharedPreferences("module_installs",0).edit().putString("session_"+session,receipt).commit();
        Intent result=new Intent().putExtra(android.content.pm.PackageInstaller.EXTRA_SESSION_ID,session).putExtra(android.content.pm.PackageInstaller.EXTRA_STATUS,status).putExtra(android.content.pm.PackageInstaller.EXTRA_STATUS_MESSAGE,"Synthetic callback boundary");
        if(confirmation!=null)result.putExtra(Intent.EXTRA_INTENT,confirmation);
        test.runOnMainSync(()->new ModuleInstallReceiver().onReceive(context,result));
    }
    private static android.view.View find(android.view.View view,String label){
        if(view instanceof android.widget.TextView&&label.contentEquals(((android.widget.TextView)view).getText()))return view;
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++){android.view.View found=find(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }
    private static void await(Instrumentation test,java.util.function.BooleanSupplier condition)throws Exception{long end=SystemClock.uptimeMillis()+20000;while(SystemClock.uptimeMillis()<end){boolean[] done={false};test.runOnMainSync(()->done[0]=condition.getAsBoolean());if(done[0])return;Thread.sleep(50);}throw new AssertionError("update timeout");}
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
}
