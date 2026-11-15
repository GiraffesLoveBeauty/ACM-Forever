package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import java.io.*;
import java.util.*;

/** Stages only modules already acquired; never downloads other optional modules. */
final class ModuleUpdates {
    static String summary(Context c,int code,String version)throws Exception{
        Set<String> selected=ModuleStore.acquired(c);if(selected.isEmpty())return "尚未下载可选模块";
        Map<String,ModuleSpec> catalog=ModuleNetwork.catalog(c,code,version);
        List<String> names=new ArrayList<>();long bytes=0;StringBuilder details=new StringBuilder();
        for(String id:ModuleSpec.IDS)if(selected.contains(id)&&catalog.containsKey(id)){
            ModuleSpec target=catalog.get(id);ModuleHealth.Status local=ModuleHealth.verify(c,id);boolean same=local.intact&&(ModuleSpec.nativeModule(id)?code==ModuleStore.code(c):!target.revision.isEmpty()&&target.revision.equals(local.revision));
            details.append('\n').append(ModuleSpec.name(id)).append("：").append(local.intact?(local.number.isEmpty()?shortRevision(local.revision):local.number):local.message).append(" → ").append(target.number.isEmpty()?shortRevision(target.revision):target.number).append(same?" · 无需下载":" · 可更新/修复");
            if(!same){names.add(ModuleSpec.name(id));File saved=ModuleStore.archive(c,id,code);boolean valid=false;if(saved.isFile())try{ModuleFiles.verify(saved,target,ModuleStore.trusted(c));valid=true;}catch(Exception ignored){}if(!valid)bytes+=target.size;}
        }
        return (names.isEmpty()?"已下载模块完整；无需重复下载":"需配套文件约 "+((bytes+1023)/1024)+" KB："+String.join("、",names))+details;
    }
    private static String shortRevision(String r){return r.isEmpty()?"旧版编号":r.length()>15?r.substring(0,15):r;}
    static Map<String,File> prepare(Context c,UpdateManifest release,ModuleNetwork.Cancelled cancelled,java.util.function.Consumer<String> status)throws Exception{
        int code=(int)release.versionCode;String version=release.versionName;Map<String,File> nativeFiles=new LinkedHashMap<>();if(!ModuleStore.updateTogether(c))return nativeFiles;
        Set<String> ids=ModuleStore.acquired(c);if(ids.isEmpty())return nativeFiles;
        if(release.modulesUrl.isEmpty())throw new IOException("新版未提供模块清单；可稍后重试，或关闭随 App 更新模块后仅安装基础包。旧文件与设置会保留。");
        Map<String,ModuleSpec> catalog=ModuleNetwork.catalog(c,code,version);Set<String> trusted=ModuleStore.trusted(c);
        for(String id:ids){
            if(cancelled.get())throw new IOException("已取消模块更新");ModuleSpec spec=catalog.get(id);if(spec==null)throw new IOException("新版缺少"+ModuleSpec.name(id));File file=ModuleStore.archive(c,id,code);
            if(!ModuleSpec.nativeModule(id)&&ModuleStore.reuse(c,spec)){status.accept(ModuleSpec.name(id)+"内容未变，已复用本机完整包");continue;}
            status.accept("正在更新"+ModuleSpec.name(id)+"…");
            if(file.isFile())try{ModuleFiles.verify(file,spec,trusted);}catch(Exception invalid){java.nio.file.Files.delete(file.toPath());}
            if(!file.isFile())ModuleNetwork.download(spec,file,n->status.accept("正在更新"+ModuleSpec.name(id)+" · "+(n*100/spec.size)+"%"),cancelled);
            ModuleFiles.verify(file,spec,trusted);if(cancelled.get())throw new IOException("已取消模块更新");
            if(ModuleSpec.nativeModule(id))nativeFiles.put(id,file);else ModuleStore.installAssets(c,spec);
        }
        return nativeFiles;
    }
}
