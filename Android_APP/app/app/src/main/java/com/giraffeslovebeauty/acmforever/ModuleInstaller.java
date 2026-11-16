package com.giraffeslovebeauty.acmforever;

import android.app.PendingIntent;
import android.content.*;
import android.content.pm.PackageInstaller;
import android.os.Build;
import java.io.*;
import java.util.*;

/** APK streams must be fsynced AND closed before commit. No silent installs. */
final class ModuleInstaller {
    static void remove(Context context,String module,ModuleNetwork.Cancelled cancelled)throws Exception{
        if(!ModuleSpec.nativeModule(module))throw new IOException("不是原生模块");
        PackageInstaller installer=context.getPackageManager().getPackageInstaller();String receipt="remove:"+module;
        SharedPreferences receipts=context.getSharedPreferences("module_installs",0);
        for(PackageInstaller.SessionInfo old:installer.getMySessions())if(receipt.equals(receipts.getString("session_"+old.getSessionId(),""))){installer.abandonSession(old.getSessionId());receipts.edit().remove("session_"+old.getSessionId()).commit();}
        PackageInstaller.SessionParams params=new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_INHERIT_EXISTING);
        params.setAppPackageName(context.getPackageName());if(Build.VERSION.SDK_INT>=31)params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
        int id=installer.createSession(params);boolean committed=false;
        try(PackageInstaller.Session session=installer.openSession(id)){
            session.removeSplit(module);if(cancelled.get())throw new IOException("登录状态已变化，已取消卸载");
            if(!receipts.edit().putString("session_"+id,receipt).putBoolean("remove_"+module,true).commit())throw new IOException("无法保存卸载回执");
            Intent callback=new Intent(context,ModuleInstallReceiver.class).setAction(context.getPackageName()+".MODULE_REMOVE."+id);
            int flags=PendingIntent.FLAG_UPDATE_CURRENT;if(Build.VERSION.SDK_INT>=31)flags|=PendingIntent.FLAG_MUTABLE;
            session.commit(PendingIntent.getBroadcast(context,id,callback,flags).getIntentSender());committed=true;
        }finally{if(!committed){installer.abandonSession(id);receipts.edit().remove("session_"+id).remove("remove_"+module).apply();}}
    }
    static void commit(Context context,String receipt,File base,Map<String,File> splits,ModuleNetwork.Cancelled cancelled)throws Exception{
        PackageInstaller installer=context.getPackageManager().getPackageInstaller();
        SharedPreferences receipts=context.getSharedPreferences("module_installs",0);
        for(PackageInstaller.SessionInfo old:installer.getMySessions())if(receipt.equals(receipts.getString("session_"+old.getSessionId(),""))){
            receipts.edit().remove("session_"+old.getSessionId()).commit();
            try{installer.abandonSession(old.getSessionId());}catch(SecurityException ignored){}
        }
        PackageInstaller.SessionParams params=new PackageInstaller.SessionParams(base==null?PackageInstaller.SessionParams.MODE_INHERIT_EXISTING:PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());long total=base==null?0:base.length();for(File f:splits.values())total+=f.length();params.setSize(total);
        int id=installer.createSession(params);boolean committed=false;
        try(PackageInstaller.Session session=installer.openSession(id)){
            if(base!=null)copy(session,"base.apk",base,cancelled);
            for(Map.Entry<String,File> entry:splits.entrySet())copy(session,"split_"+entry.getKey()+".apk",entry.getValue(),cancelled);
            if(cancelled.get())throw new IOException("已取消安装");
            if(!context.getSharedPreferences("module_installs",0).edit().putString("session_"+id,receipt).commit())throw new IOException("无法保存安装回执");
            Intent callback=new Intent(context,ModuleInstallReceiver.class).setAction(context.getPackageName()+".MODULE_INSTALL."+id);
            int flags=PendingIntent.FLAG_UPDATE_CURRENT;if(Build.VERSION.SDK_INT>=31)flags|=PendingIntent.FLAG_MUTABLE;
            session.commit(PendingIntent.getBroadcast(context,id,callback,flags).getIntentSender());committed=true;
        }finally{if(!committed){installer.abandonSession(id);context.getSharedPreferences("module_installs",0).edit().remove("session_"+id).apply();}}
    }
    private static void copy(PackageInstaller.Session session,String name,File file,ModuleNetwork.Cancelled cancelled)throws Exception{
        try(InputStream in=new FileInputStream(file);OutputStream out=session.openWrite(name,0,file.length())){byte[] bytes=new byte[16384];int n;while((n=in.read(bytes))!=-1){if(cancelled.get())throw new IOException("已取消安装");out.write(bytes,0,n);}session.fsync(out);}
    }
}
