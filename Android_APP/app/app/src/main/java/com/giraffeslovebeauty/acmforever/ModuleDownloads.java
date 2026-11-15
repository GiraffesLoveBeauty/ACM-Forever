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
    private final Set<String> removalPermissions=new HashSet<>(),cleaningRemovals=new HashSet<>();
    private ModuleDownloads(Context c){context=c;}
    synchronized State state(String id){State state=states.get(id);if(state!=null)return state;return new State(ModuleStore.available(context,id)?"done":"idle","",0,0);}
    synchronized void listen(Runnable observer){listeners.add(observer);}
    synchronized void unlisten(Runnable observer){listeners.remove(observer);}
    private synchronized void publish(String id,String phase,String message,long bytes,long total){states.put(id,new State(phase,message,bytes,total));for(Runnable listener:new ArrayList<>(listeners))main.post(listener);}
    synchronized boolean active(){for(State state:states.values())if(Arrays.asList("checking","downloading","verifying","installing","approval").contains(state.phase))return true;return false;}
    synchronized void cancel(String id){cancelled.put(id,true);}
    private synchronized boolean cancelled(String id){return Boolean.TRUE.equals(cancelled.get(id));}
    synchronized Intent confirmation(String id){if(!id.equals(confirmationModule))return null;Intent result=confirmation;confirmation=null;return result;}
    synchronized boolean removalPermission(String id){return removalPermissions.contains(id);}
    synchronized void confirmationFailed(String id,String message){if(context.getSharedPreferences("module_installs",0).getBoolean("remove_"+id,false))removalResult(id,PackageInstaller.STATUS_FAILURE,message,null);else installerResult(id,PackageInstaller.STATUS_FAILURE,message,null);}
    synchronized void remove(String id,long owner){
        if(!ModuleSpec.IDS.contains(id))return;
        if(active()||((AcmApplication)context).updates().operationActive()){publish(id,"failed","请先完成或取消当前 App / 模块操作。",0,0);return;}
        ApiClient api=((AcmApplication)context).api();if(!api.isLoggedIn()||owner!=api.sessionGeneration())return;
        removalPermissions.remove(id);publish(id,"checking","正在准备删除模块…",0,0);
        io.execute(()->{try{
            if(!api.isLoggedIn()||owner!=api.sessionGeneration())throw new IOException("登录账号已切换");
            if(ModuleStore.installedNative(context).contains(id)){
                if(!context.getPackageManager().canRequestPackageInstalls()){synchronized(this){removalPermissions.add(id);}publish(id,"permission","请先允许系统功能包安装/卸载，再点击删除模块。",0,0);return;}
                publish(id,"installing","等待系统卸载确认，可能重启 App…",0,0);
                ModuleInstaller.remove(context,id,()->!api.isLoggedIn()||owner!=api.sessionGeneration());
            }else{ModuleHealth.removeLocal(context,id);publish(id,"removed","模块已删除，个人数据和设置已保留",0,0);}
        }catch(Exception failure){publish(id,"failed",failure.getMessage(),0,0);}});
    }
    synchronized void removalResult(String id,int status,String message,Intent intent){
        if(status==PackageInstaller.STATUS_PENDING_USER_ACTION){if(intent==null){publish(id,"failed","系统未提供卸载确认窗口，未删除本机模块",0,0);return;}confirmation=intent;confirmationModule=id;publish(id,"approval","请在系统窗口确认卸载模块。",0,0);return;}
        if(status==PackageInstaller.STATUS_SUCCESS){cleanupRemoval(id);return;}
        context.getSharedPreferences("module_installs",0).edit().remove("remove_"+id).apply();
        publish(id,"failed",status==PackageInstaller.STATUS_FAILURE_ABORTED?"已取消卸载，原模块和文件保留":"系统卸载失败，原文件保留："+message,0,0);
    }
    synchronized void reconcileRemovals(){for(String id:ModuleSpec.IDS)if(ModuleSpec.nativeModule(id)&&context.getSharedPreferences("module_installs",0).getBoolean("remove_"+id,false)&&!ModuleStore.installedNative(context).contains(id))cleanupRemoval(id);}
    private synchronized void cleanupRemoval(String id){
        if(!cleaningRemovals.add(id))return;publish(id,"checking","正在清理已卸载模块文件…",0,0);
        io.execute(()->{try{ModuleHealth.removeLocal(context,id);if(!context.getSharedPreferences("module_installs",0).edit().remove("remove_"+id).commit())throw new IOException("无法保存删除回执");publish(id,"removed","模块已卸载，下载副本已清理，个人设置已保留",0,0);}catch(Exception failure){publish(id,"failed","模块文件清理未完成，可重试："+failure.getMessage(),0,0);}finally{synchronized(this){cleaningRemovals.remove(id);}}});
    }
    synchronized void start(String id){
        if(Arrays.asList("checking","downloading","verifying","installing","approval").contains(state(id).phase))return;
        if(active()){publish(id,"failed","请先完成或取消另一个模块的下载/安装。",0,0);return;}
        if(((AcmApplication)context).updates().operationActive()){publish(id,"failed","App正在更新，请完成或取消更新后再下载模块。",0,0);return;}
        cancelled.put(id,false);publish(id,"checking","正在读取模块信息…",0,0);
        io.execute(()->{try{
            if(!ModuleSpec.nativeModule(id)){ModuleHealth.Status local=ModuleHealth.verify(context,id);if(local.intact&&ModuleStore.current(context,id)){publish(id,"done","本机模块已检查并恢复，无需下载",0,0);return;}}
            ModuleSpec spec=ModuleNetwork.catalog(context).get(id);if(spec==null)throw new IOException("缺少模块信息");File file=ModuleStore.archive(context,id);
            if(!ModuleSpec.nativeModule(id)&&ModuleStore.reuse(context,spec)){if(cancelled(id)||!OptionalModules.allowed(context,id))throw new IOException("操作取消或权限已变化");ModuleStore.acquired(context,id);if(!ModuleHealth.verify(context,id).intact)throw new IOException("模块恢复验证失败");publish(id,"done","已复用并恢复本机完整模块",0,0);return;}
            if(file.isFile())try{ModuleFiles.verify(file,spec,ModuleStore.trusted(context));}catch(Exception invalid){java.nio.file.Files.deleteIfExists(file.toPath());}
            if(!file.isFile()){publish(id,"downloading","正在下载…",0,spec.size);ModuleNetwork.download(spec,file,n->publish(id,"downloading","正在下载…",n,spec.size),()->cancelled(id));}
            if(cancelled(id))throw new IOException("已取消下载");publish(id,"verifying","正在校验签名与版本…",spec.size,spec.size);
            try{ModuleFiles.verify(file,spec,ModuleStore.trusted(context));}catch(Exception e){java.nio.file.Files.deleteIfExists(file.toPath());throw e;}
            if(cancelled(id))throw new IOException("已取消下载");if(!OptionalModules.allowed(context,id))throw new IOException("登录状态或权限已变化");
            ModuleStore.acquired(context,id);
            if(ModuleSpec.nativeModule(id))installNative(id,file,spec);else{ModuleStore.installAssets(context,spec);if(!ModuleHealth.verify(context,id).intact)throw new IOException("模块恢复验证失败");CharacterArt.clear();publish(id,"done","模块完整，已完成下载/修复",spec.size,spec.size);}
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
