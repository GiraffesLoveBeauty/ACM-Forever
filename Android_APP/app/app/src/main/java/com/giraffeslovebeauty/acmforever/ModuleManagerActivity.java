package com.giraffeslovebeauty.acmforever;

import android.content.*;
import android.os.Bundle;
import android.widget.*;

/** Storage owns explicit module removal; cache cleanup and ordinary upgrades never remove modules. */
public final class ModuleManagerActivity extends MobilePageActivity {
    private ModuleDownloads jobs;
    private final Runnable observer=this::render;
    private boolean resumed;
    private long owner;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);createPage("模块管理");owner=api.sessionGeneration();jobs=ModuleDownloads.get(this);jobs.listen(observer);ModuleHealth.listen(observer);render();}
    @Override protected void onResume(){super.onResume();resumed=true;if(jobs!=null){jobs.reconcileRemovals();render();}}
    @Override protected void onPause(){resumed=false;super.onPause();}
    @Override protected void onDestroy(){if(jobs!=null)jobs.unlisten(observer);ModuleHealth.unlisten(observer);super.onDestroy();}
    private void render(){
        if(isDestroyed()||!api.isLoggedIn())return;
        if(owner!=api.sessionGeneration()){finish();return;}
        int position=scroll.getScrollY();body.removeAllViews();
        LinearLayout info=card(body);info.addView(text("按需保留功能包",19));info.addView(text("删除模块只清理该模块的安装文件，保留账号、主题原图和私人主题设置。原生模块由 Android 确认卸载，可能重启 App；官方主题库和猫娘素材可直接移除。删除后不会随 App 自动下载，需再次主动选择下载。",13));
        for(String id:new String[]{"official-themes","advanced","admin","cat-art"}){
            // A previously installed admin module may be removed after demotion, but never downloaded/opened.
            if("admin".equals(id)&&!api.isAdministrator()&&!ModuleStore.acquired(this).contains(id))continue;
            LinearLayout box=card(body);box.addView(text(ModuleSpec.name(id),18));ModuleDownloads.State state=jobs.state(id);
            boolean acquired=ModuleStore.acquired(this).contains(id),available=ModuleStore.available(this,id);
            ModuleHealth.Status health=ModuleHealth.state(id);
            String status=available?"已安装":acquired?"已下载 / 待安装或修复":"未下载";
            if(!health.number.isEmpty()&&available)status+="\n"+health.number;
            if(!state.message.isEmpty())status+="\n"+state.message;
            box.addView(text(status,13));
            if(OptionalModules.allowed(this,id)){
                Button download=button(available?"检查 / 修复模块":"下载 / 安装模块",()->{if(available)ModuleHealth.check(this,id,null);else OptionalModules.open(this,id,null);});
                download.setContentDescription("管理下载"+ModuleSpec.name(id));
                download.setEnabled(!jobs.active()&&!((AcmApplication)getApplication()).updates().operationActive());box.addView(download);
            }
            if(acquired){Button remove=button("删除模块",()->confirmDelete(id));remove.setContentDescription("删除"+ModuleSpec.name(id));remove.setEnabled(!jobs.active());box.addView(remove);}
            if(jobs.removalPermission(id))box.addView(button("允许系统卸载功能包",()->startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,android.net.Uri.parse("package:"+getPackageName())))));
            if(resumed){Intent confirmation=jobs.confirmation(id);if(confirmation!=null)try{startActivity(confirmation);}catch(Exception error){jobs.confirmationFailed(id,"无法打开系统确认");}}
        }
        AppAppearance.paintFields(root);scroll.post(()->scroll.scrollTo(0,position));
    }
    private void confirmDelete(String id){
        new ModalDialogs.Builder(this).setTitle("删除"+ModuleSpec.name(id)+"？").setMessage("将移除此模块及各版本下载副本；个人数据和外观设置会保留。之后可重新下载。"+(ModuleSpec.nativeModule(id)?"需要 Android 系统确认，取消不会卸载。":""))
            .setNegativeButton("点错了喵",null).setPositiveButton("确认删除",(d,w)->jobs.remove(id,owner)).show();
    }
}
