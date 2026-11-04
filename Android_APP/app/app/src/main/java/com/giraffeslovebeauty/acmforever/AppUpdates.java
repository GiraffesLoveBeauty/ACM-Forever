package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.content.pm.*;
import android.database.Cursor;
import android.net.*;
import android.os.*;
import android.provider.Settings;
import org.json.JSONObject;
import java.io.*;
import java.lang.ref.WeakReference;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

/** Process-owned update state; system downloads survive page changes and process restarts. */
final class AppUpdates {
    private static final String KEY="app_update_";
    private final Context context;
    private final ApiClient api;
    private final SharedPreferences prefs;
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private WeakReference<Activity> owner=new WeakReference<>(null);
    private Runnable listener;
    private UpdateManifest release;
    private String source="",error="",verifiedName="";
    private long downloadId=-1,generation;
    private boolean checking,verifying,installRequested;
    private int progress=-1;
    private long promptedVersion;
    private final Runnable poll=this::pollDownload;

    AppUpdates(Context context,ApiClient api){
        this.context=context.getApplicationContext();this.api=api;prefs=AppAppearance.prefs(context);
        downloadId=prefs.getLong(KEY+"download",-1);verifiedName=prefs.getString(KEY+"verified","");
        try{
            source=endpoint();
            if(source.equals(prefs.getString(KEY+"source",""))){
                String stored=prefs.getString(KEY+"manifest","");
                if(!stored.isEmpty())release=new UpdateManifest(new JSONObject(stored),context.getPackageName());
                if(release!=null&&release.versionCode>currentVersion()){
                    downloadId=prefs.getLong(KEY+"download",-1);verifiedName=prefs.getString(KEY+"verified","");
                    if(!verifiedFile().isFile())verifiedName="";
                }else clearStored();
            }else clearStored();
        }catch(Exception ignored){clearStored();}
    }
    void attach(Activity activity,Runnable changed){owner=new WeakReference<>(activity);listener=changed;syncSource();changed();if(downloadId!=-1&&!verifying){ui.removeCallbacks(poll);ui.post(poll);}}
    void detach(Activity activity){if(owner.get()==activity){owner.clear();listener=null;}}
    private Activity activity(){Activity a=owner.get();return a==null||a.isFinishing()||a.isDestroyed()?null:a;}
    boolean automatic(){return prefs.getBoolean(KEY+"automatic",false);}
    boolean automaticDownload(){return automatic()&&prefs.getBoolean(KEY+"wifi_download",false);}
    void automatic(boolean value){prefs.edit().putBoolean(KEY+"automatic",value).apply();if(!value)prefs.edit().putBoolean(KEY+"wifi_download",false).apply();changed();}
    void automaticDownload(boolean value){prefs.edit().putBoolean(KEY+"wifi_download",value).putBoolean(KEY+"automatic",value||automatic()).apply();changed();}
    void maybeCheck(){if(automatic()&&System.currentTimeMillis()-prefs.getLong(KEY+"attempt",0)>=6*60*60*1000L)check(false);}
    long currentVersion(){try{PackageInfo p=context.getPackageManager().getPackageInfo(context.getPackageName(),0);return Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode;}catch(Exception e){return 0;}}
    String currentName(){try{return context.getPackageManager().getPackageInfo(context.getPackageName(),0).versionName;}catch(Exception e){return "未知";}}
    String endpoint(){
        boolean debug=(context.getApplicationInfo().flags&ApplicationInfo.FLAG_DEBUGGABLE)!=0;
        String configured=prefs.getString(KEY+"url","");
        if(configured.trim().isEmpty()&&!debug)configured=context.getString(R.string.default_update_manifest_url);
        return UpdateManifest.endpoint(api.getBaseUrl(),configured,debug?"debug":"release");
    }
    void source(String value){
        if(busy())throw new IllegalArgumentException("请等待当前检查完成，或先取消下载。");
        String checked=value.trim().isEmpty()?"":UpdateManifest.https(value);
        prefs.edit().putString(KEY+"url",checked).apply();syncSource();changed();
    }
    String customSource(){return prefs.getString(KEY+"url","");}
    private void syncSource(){
        String next;try{next=endpoint();}catch(Exception e){error=e.getMessage();return;}
        if(next.equals(source))return;
        ++generation;cancelDownload();source=next;release=null;error="";checking=false;clearStored();
        prefs.edit().remove(KEY+"attempt").apply();
    }
    boolean busy(){return checking||verifying||downloadId!=-1;}
    boolean downloading(){return downloadId!=-1;}
    boolean ready(){return !verifiedName.isEmpty()&&verifiedFile().isFile();}
    boolean available(){return release!=null&&release.versionCode>currentVersion()&&release.minSdk<=Build.VERSION.SDK_INT;}
    String error(){return error;}
    String status(){
        if(checking)return "正在检查新版本…";
        if(verifying)return "正在校验安装包…";
        if(downloadId!=-1)return progress<0?"正在等待或下载安装包…":"正在下载安装包 · "+progress+"%";
        if(ready())return "新版已下载，等待安装";
        if(!error.isEmpty())return error;
        if(release==null)return "尚未检查更新";
        if(release.versionCode<=currentVersion())return "已是最新版";
        if(release.minSdk>Build.VERSION.SDK_INT)return "新版本需要 Android API "+release.minSdk+" 或更高版本";
        return "发现新版本 "+release.versionName;
    }
    String notes(){return release==null?"":release.notes;}
    String downloadLabel(){return release==null?"下载新版安装包":"更新 "+release.versionName+" 版本";}
    void dismissError(){error="";changed();}
    private void changed(){if(listener!=null&&activity()!=null)listener.run();}
    void check(boolean manual){
        syncSource();if(busy())return;error="";checking=true;changed();
        final long ticket=++generation;final String address=source;
        prefs.edit().putLong(KEY+"attempt",System.currentTimeMillis()).apply();
        io.execute(()->{
            try{
                if(address.isEmpty())throw new ApiClient.UnconfiguredException();
                if(!networkAvailable())throw new ApiClient.NoNetworkException();
                HttpURLConnection connection=openManifest(address);
                UpdateManifest found;
                try{
                    try(InputStream stream=connection.getInputStream();ByteArrayOutputStream bytes=new ByteArrayOutputStream()){
                        byte[] buffer=new byte[4096];int n;
                        while((n=stream.read(buffer))!=-1){if(bytes.size()+n>32768)throw new IllegalArgumentException("版本清单超过 32 KB。");bytes.write(buffer,0,n);}
                        found=new UpdateManifest(new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8)),context.getPackageName());
                    }
                }finally{connection.disconnect();}
                ui.post(()->{
                    if(ticket!=generation)return;checking=false;
                    if(release==null||release.versionCode!=found.versionCode||!release.sha256.equals(found.sha256)){deleteVerified();}
                    release=found;save();changed();
                    if(!manual&&available()){
                        if(automaticDownload())download(true);else prompt();
                    }
                });
            }catch(Exception failure){ui.post(()->{if(ticket!=generation)return;checking=false;error=failure instanceof IllegalArgumentException?failure.getMessage():FailureState.title(failure);changed();});}
        });
    }
    private HttpURLConnection openManifest(String address)throws Exception{
        String next=UpdateManifest.https(address);
        for(int hop=0;hop<=5;hop++){
            HttpURLConnection connection=(HttpURLConnection)new URL(next).openConnection();
            boolean keep=false;
            try{
                connection.setConnectTimeout(10000);connection.setReadTimeout(10000);connection.setInstanceFollowRedirects(false);connection.setRequestProperty("Accept","application/json");
                int status=connection.getResponseCode();
                if(status==200){keep=true;return connection;}
                if(status==301||status==302||status==303||status==307||status==308){
                    if(hop==5)throw new IllegalArgumentException("更新清单重定向次数过多。");
                    next=UpdateManifest.redirected(next,connection.getHeaderField("Location"));
                }else throw new ApiClient.ApiException(status,"版本发布接口 HTTP "+status,false);
            }finally{if(!keep)connection.disconnect();}
        }
        throw new IllegalArgumentException("更新清单重定向次数过多。");
    }
    private void prompt(){
        Activity a=activity();if(a==null||listener!=null||ModalDialogs.isShowing(a)||release==null||promptedVersion==release.versionCode)return;
        promptedVersion=release.versionCode;
        new ModalDialogs.Builder(a).setTitle("发现新版本 "+release.versionName).setMessage(notes()).setNegativeButton("稍后",null)
                .setPositiveButton("查看更新",(d,w)->a.startActivity(new Intent(a,UpdateActivity.class))).show();
    }
    void download(boolean wifiOnly){
        syncSource();if(busy()||!available()||ready())return;
        try{
            DownloadManager.Request request=new DownloadManager.Request(Uri.parse(release.apkUrl));
            request.setTitle("ACMforever "+release.versionName);request.setDescription("下载后校验并由系统确认安装");
            request.setMimeType("application/vnd.android.package-archive");request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            if(wifiOnly){request.setAllowedNetworkTypes(DownloadManager.Request.NETWORK_WIFI);request.setAllowedOverMetered(false);}
            request.setDestinationInExternalFilesDir(context,Environment.DIRECTORY_DOWNLOADS,"acmforever-"+release.versionCode+"-"+System.currentTimeMillis()+".apk");
            downloadId=downloads().enqueue(request);progress=-1;error="";save();changed();ui.removeCallbacks(poll);ui.postDelayed(poll,1000);
        }catch(Exception e){downloadId=-1;fail(e);}
    }
    private DownloadManager downloads(){return (DownloadManager)context.getSystemService(Context.DOWNLOAD_SERVICE);}
    private void pollDownload(){
        if(downloadId==-1||verifying||release==null)return;
        try(Cursor cursor=downloads().query(new DownloadManager.Query().setFilterById(downloadId))){
            if(cursor==null||!cursor.moveToFirst())throw new IOException("下载任务不存在，请重新下载。");
            long total=cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES)),bytes=cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
            if(total>UpdateManifest.MAX_APK_BYTES||bytes>UpdateManifest.MAX_APK_BYTES)throw new IllegalArgumentException("安装包超过大小限制。");
            progress=total>0?(int)Math.min(100,bytes*100/total):-1;changed();
            int status=cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
            if(status==DownloadManager.STATUS_FAILED)throw new IOException("APK 下载失败，系统原因 "+cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON)));
            if(status==DownloadManager.STATUS_SUCCESSFUL){Uri uri=downloads().getUriForDownloadedFile(downloadId);if(uri==null)throw new IOException("找不到下载文件。");verify(uri);}
            else ui.postDelayed(poll,1000);
        }catch(Exception e){cancelDownload();fail(e);}
    }
    private void verify(Uri uri){
        verifying=true;changed();final UpdateManifest expected=release;final long ticket=generation,task=downloadId;
        io.execute(()->{
            File file=null;
            try{
                File folder=new File(context.getCacheDir(),"updates");if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("无法创建更新缓存。");
                file=File.createTempFile("verified-",".apk",folder);MessageDigest digest=MessageDigest.getInstance("SHA-256");long bytes=0;
                try(InputStream in=context.getContentResolver().openInputStream(uri);FileOutputStream out=new FileOutputStream(file)){
                    if(in==null)throw new IOException("无法读取安装包。");byte[] buffer=new byte[16384];int n;
                    while((n=in.read(buffer))!=-1){bytes+=n;if(bytes>UpdateManifest.MAX_APK_BYTES)throw new IllegalArgumentException("安装包超过大小限制。");digest.update(buffer,0,n);out.write(buffer,0,n);}
                }
                StringBuilder hash=new StringBuilder();for(byte b:digest.digest())hash.append(String.format(Locale.ROOT,"%02x",b&255));
                if(!expected.sha256.equals(hash.toString())||(expected.sizeBytes>0&&expected.sizeBytes!=bytes))throw new IllegalArgumentException("安装包校验失败，请重新下载。");
                validatePackage(file,expected);final File verified=file;
                ui.post(()->{
                    if(ticket!=generation){verified.delete();return;}
                    if(task!=-1)downloads().remove(task);downloadId=-1;verifying=false;verifiedName=verified.getName();error="";save();changed();
                });
            }catch(Exception e){if(file!=null)file.delete();ui.post(()->{if(ticket!=generation)return;verifying=false;cancelDownload();fail(e);});}
        });
    }
    void validatePackage(File file,UpdateManifest expected)throws Exception{
        PackageManager pm=context.getPackageManager();int flags=Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo next=pm.getPackageArchiveInfo(file.getAbsolutePath(),flags),installed=pm.getPackageInfo(context.getPackageName(),flags);
        long version=next==null?-1:Build.VERSION.SDK_INT>=28?next.getLongVersionCode():next.versionCode;
        if(next==null||!context.getPackageName().equals(next.packageName)||version!=expected.versionCode||version<=currentVersion())throw new IllegalArgumentException("APK 的包名或版本与更新清单不符。");
        if(next.applicationInfo==null||next.applicationInfo.minSdkVersion>Build.VERSION.SDK_INT)throw new IllegalArgumentException("安装包不支持当前 Android 版本。");
        Signature[] a=Build.VERSION.SDK_INT>=28?(next.signingInfo==null?null:next.signingInfo.getApkContentsSigners()):next.signatures;
        Signature[] b=Build.VERSION.SDK_INT>=28?(installed.signingInfo==null?null:installed.signingInfo.getApkContentsSigners()):installed.signatures;
        if(a==null||b==null||a.length==0||a.length!=b.length||!new HashSet<>(Arrays.asList(a)).equals(new HashSet<>(Arrays.asList(b))))throw new IllegalArgumentException("安装包签名与当前 App 不一致。");
    }
    void install(Activity a){
        if(!ready())return;
        if(!a.getPackageManager().canRequestPackageInstalls()){
            if(ModalDialogs.isShowing(a))return;
            new ModalDialogs.Builder(a).setTitle("允许安装更新").setMessage("打开本 App 的安装权限后，仍由系统确认安装。")
                    .setNegativeButton("取消",null).setPositiveButton("打开设置",(d,w)->{
                        try{installRequested=true;a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+context.getPackageName())));}
                        catch(Exception e){installRequested=false;fail(e);}
                    }).show();return;
        }
        try{
            installRequested=false;Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://"+context.getPackageName()+".updates/"+verifiedName),"application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);a.startActivity(intent);
        }catch(Exception e){fail(e);}
    }
    void resumeInstall(Activity a){if(installRequested){installRequested=false;if(a.getPackageManager().canRequestPackageInstalls())install(a);}}
    void cancelDownload(){++generation;ui.removeCallbacks(poll);if(downloadId!=-1)downloads().remove(downloadId);downloadId=-1;verifying=false;progress=-1;save();changed();}
    private File verifiedFile(){return new File(new File(context.getCacheDir(),"updates"),verifiedName.matches("verified-[A-Za-z0-9_-]+\\.apk")?verifiedName:"missing");}
    private void deleteVerified(){if(!verifiedName.isEmpty())verifiedFile().delete();verifiedName="";}
    private void clearStored(){if(downloadId!=-1)downloads().remove(downloadId);downloadId=-1;deleteVerified();release=null;prefs.edit().remove(KEY+"manifest").remove(KEY+"download").remove(KEY+"verified").remove(KEY+"source").apply();}
    private void save(){SharedPreferences.Editor edit=prefs.edit().putString(KEY+"source",source).putLong(KEY+"download",downloadId).putString(KEY+"verified",verifiedName);if(release!=null)edit.putString(KEY+"manifest",release.json());else edit.remove(KEY+"manifest");edit.apply();}
    private void fail(Exception e){error=e instanceof IllegalArgumentException?e.getMessage():FailureState.title(e);save();changed();}
    private boolean networkAvailable(){ConnectivityManager cm=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);NetworkCapabilities caps=cm==null?null:cm.getNetworkCapabilities(cm.getActiveNetwork());return caps!=null&&caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);}
}
