package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import java.io.*;
import java.util.*;

/** Stages only modules already acquired; never downloads other optional modules. */
final class ModuleUpdates {
    static String summary(Context c,int code,String version)throws Exception{
        Set<String> selected=ModuleStore.acquired(c);if(selected.isEmpty())return "尚未下载可选模块";
        Map<String,ModuleSpec> catalog=ModuleNetwork.catalog(c,code,version);
        List<String> names=new ArrayList<>();for(String id:ModuleSpec.IDS)if(selected.contains(id)&&catalog.containsKey(id)&&(code>ModuleStore.code(c)||!ModuleStore.current(c,id)))names.add(ModuleSpec.name(id));
        return !names.isEmpty()?"有配套模块可更新："+String.join("、",names):"已下载模块与当前 App 配套；旧文件和设置继续保留";
    }
    static Map<String,File> prepare(Context c,UpdateManifest release,ModuleNetwork.Cancelled cancelled,java.util.function.Consumer<String> status)throws Exception{
        int code=(int)release.versionCode;String version=release.versionName;Map<String,File> nativeFiles=new LinkedHashMap<>();if(!ModuleStore.updateTogether(c))return nativeFiles;
        Set<String> ids=ModuleStore.acquired(c);if(ids.isEmpty())return nativeFiles;
        if(release.modulesUrl.isEmpty())throw new IOException("新版未提供模块清单；可稍后重试，或关闭随 App 更新模块后仅安装基础包。旧文件与设置会保留。");
        Map<String,ModuleSpec> catalog=ModuleNetwork.catalog(c,code,version);Set<String> trusted=ModuleStore.trusted(c);
        for(String id:ids){
            if(cancelled.get())throw new IOException("已取消模块更新");ModuleSpec spec=catalog.get(id);if(spec==null)throw new IOException("新版缺少"+ModuleSpec.name(id));File file=ModuleStore.archive(c,id,code);
            status.accept("正在更新"+ModuleSpec.name(id)+"…");
            if(file.isFile())try{ModuleFiles.verify(file,spec,trusted);}catch(Exception invalid){java.nio.file.Files.delete(file.toPath());}
            if(!file.isFile())ModuleNetwork.download(spec,file,n->status.accept("正在更新"+ModuleSpec.name(id)+" · "+(n*100/spec.size)+"%"),cancelled);
            ModuleFiles.verify(file,spec,trusted);if(cancelled.get())throw new IOException("已取消模块更新");
            if(ModuleSpec.nativeModule(id))nativeFiles.put(id,file);else ModuleStore.installAssets(c,spec);
        }
        return nativeFiles;
    }
}
