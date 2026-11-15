package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import java.util.*;
import java.util.concurrent.*;

/** No file hashing on the UI thread. Only local repair runs without download consent. */
final class ModuleHealth {
    static final class Status {final boolean intact;final String message,revision;Status(boolean ok,String text,String r){intact=ok;message=text;revision=r;}}
    private static final Map<String,Status> states=new ConcurrentHashMap<>();
    private static final Set<String> broken=ConcurrentHashMap.newKeySet();
    private static final ExecutorService io=Executors.newSingleThreadExecutor();
    private static final Handler main=new Handler(Looper.getMainLooper());
    private static final Set<Runnable> observers=Collections.newSetFromMap(new ConcurrentHashMap<>());
    static boolean damaged(String id){return broken.contains(id);}
    static Status state(String id){return states.getOrDefault(id,new Status(false,"待检查",""));}
    static void listen(Runnable observer){observers.add(observer);}
    static void unlisten(Runnable observer){observers.remove(observer);}
    private static void publish(String id,Status status){if(status.intact)broken.remove(id);else if(!"检查中".equals(status.message))broken.add(id);states.put(id,status);for(Runnable observer:observers)main.post(observer);}
    static void recovering(String id){publish(id,new Status(false,"修复中",""));}
    static void bad(Context c,String id,String reason){publish(id,new Status(false,reason,""));check(c,id,null);}
    static synchronized Status verify(Context c,String id){
        publish(id,new Status(false,"检查中",""));
        try{
            String revision;
            if(ModuleSpec.nativeModule(id)){if(!ModuleStore.installedNative(c).contains(id))throw new IllegalStateException("原生模块未安装或版本不匹配");revision="App "+ModuleStore.code(c);try{String recorded=ModuleStore.localSpec(c,id,ModuleStore.code(c)).revision;if(!recorded.isEmpty())revision=recorded;}catch(Exception notRecorded){}}
            else revision=ModuleStore.inspect(c,id,true).revision;
            Status result=new Status(true,"完整",revision);publish(id,result);CharacterArt.clear();return result;
        }catch(Exception failure){Status result=new Status(false,("修复中".equals(state(id).message)?"修复失败 / 待修复：":"损坏 / 待修复：")+failure.getMessage(),"");publish(id,result);CharacterArt.clear();return result;}
    }
    static void check(Context context,String id,java.util.function.Consumer<Status> done){Context c=context.getApplicationContext();io.execute(()->{Status result=verify(c,id);if(done!=null)main.post(()->done.accept(result));});}
    static void checkAll(Context context){Context c=context.getApplicationContext();io.execute(()->{Set<String> ids;try{ids=ModuleStore.acquired(c);}catch(Exception unavailable){return;}for(String id:ids)verify(c,id);});}
}
