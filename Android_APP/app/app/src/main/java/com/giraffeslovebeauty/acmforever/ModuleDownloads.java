package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.content.pm.PackageInstaller;
import android.os.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Application-owned jobs survive page rotation. Writes/installer sessions never auto-retry. */
final class ModuleDownloads {
    static final class State {final String phase,message;final long bytes,total;State(String p,String m,long b,long t){phase=p;message=m;bytes=b;total=t;}}
    private static ModuleDownloads instance;
    static synchronized ModuleDownloads get(Context context){if(instance==null)instance=new ModuleDownloads(context.getApplicationContext());return instance;}
    private final Context context;private final ExecutorService io=Executors.newSingleThreadExecutor();private final Handler main=new Handler(Looper.getMainLooper());
    private final Map<String,State> states=new HashMap<>();private final Map<String,Boolean> cancelled=new HashMap<>();private final Set<Runnable> listeners=new HashSet<>();
    private Intent confirmation;private String confirmationModule;
    private ModuleDownloads(Context c){context=c;}
    synchronized State state(String id){State state=states.get(id);if(state!=null)return state;return new State(ModuleStore.available(context,id)?"done":"idle","",0,0);}
    synchronized void listen(Runnable observer){listeners.add(observer);}
    synchronized void unlisten(Runnable observer){listeners.remove(observer);}
    private synchronized void publish(String id,String phase,String message,long bytes,long total){states.put(id,new State(phase,message,bytes,total));for(Runnable listener:new ArrayList<>(listeners))main.post(listener);}
    synchronized boolean active(){for(State state:states.values())if(Arrays.asList("checking","downloading","verifying","installing","approval").contains(state.phase))return true;return false;}
    synchronized void cancel(String id){cancelled.put(id,true);}
    private synchronized boolean cancelled(String id){return Boolean.TRUE.equals(cancelled.get(id));}
    synchronized Intent confirmation(String id){if(!id.equals(confirmationModule))return null;Intent result=confirmation;confirmation=null;return result;}
    synchronized void start(String id){
        if(Arrays.asList("checking","downloading","verifying","installing","approval").contains(state(id).phase))return;
        if(active()){publish(id,"failed","请先完成或取消另一个模块的下载/安装。",0,0);return;}
        if(((AcmApplication)context).updates().operationActive()){publish(id,"failed","App正在更新，请完成或取消更新后再下载模块。",0,0);return;}
        cancelled.put(id,false);publish(id,"checking","正在读取模块信息…",0,0);
        io.execute(()->{try{
            ModuleSpec spec=ModuleNetwork.catalog(context).get(id);if(spec==null)throw new IOException("缺少模块信息");File file=ModuleStore.archive(context,id);
            if(!file.isFile()){publish(id,"downloading","正在下载…",0,spec.size);ModuleNetwork.download(spec,file,n->publish(id,"downloading","正在下载…",n,spec.size),()->cancelled(id));}
            if(cancelled(id))throw new IOException("已取消下载");publish(id,"verifying","正在校验签名与版本…",spec.size,spec.size);
            try{ModuleFiles.verify(file,spec,ModuleStore.trusted(context));}catch(Exception e){java.nio.file.Files.deleteIfExists(file.toPath());throw e;}
            if(cancelled(id))throw new IOException("已取消下载");if(!OptionalModules.allowed(context,id))throw new IOException("登录状态或权限已变化");
            ModuleStore.acquired(context,id);
            if(ModuleSpec.nativeModule(id))installNative(id,file,spec);else{ModuleStore.installAssets(context,spec);CharacterArt.clear();publish(id,"done","模块已下载",spec.size,spec.size);}
        }catch(Exception e){publish(id,"failed",e.getMessage()==null?"模块操作失败":e.getMessage(),0,0);}});
    }
    private void installNative(String id,File file,ModuleSpec spec)throws Exception{
        if(!OptionalModules.allowed(context,id))throw new IOException("请重新登录有权使用该模块的账号");
        if(ModuleStore.code(context)!=spec.versionCode)throw new IOException("App版本已变化，请重新下载");
        if(Build.VERSION.SDK_INT>=26&&!context.getPackageManager().canRequestPackageInstalls()){publish(id,"permission","请允许此应用安装功能包，再点击继续安装。",spec.size,spec.size);return;}
        if(((AcmApplication)context).updates().operationActive())throw new IOException("App正在更新，请完成后再安装模块");
        publish(id,"installing","等待系统安装确认…",spec.size,spec.size);
        ModuleInstaller.commit(context,id,null,Collections.singletonMap(id,file),()->cancelled(id)||!OptionalModules.allowed(context,id));
    }
    synchronized void installerResult(String id,int status,String message,Intent intent){
        if(status==PackageInstaller.STATUS_PENDING_USER_ACTION){if(intent==null){publish(id,"failed","系统未提供安装确认窗口",0,0);return;}confirmation=intent;confirmationModule=id;publish(id,"approval","请在系统窗口确认安装。",0,0);}
        else if(status==PackageInstaller.STATUS_SUCCESS)publish(id,"done","模块已安装；若页面尚不可用，请重新打开App。",0,0);
        else publish(id,"failed",status==PackageInstaller.STATUS_FAILURE_ABORTED?"已取消系统安装，可稍后继续。":"系统安装失败："+message,0,0);
    }
}
