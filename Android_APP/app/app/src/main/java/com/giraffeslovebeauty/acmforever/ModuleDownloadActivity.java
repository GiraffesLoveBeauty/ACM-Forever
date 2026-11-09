package com.giraffeslovebeauty.acmforever;
import android.content.*;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.*;

public final class ModuleDownloadActivity extends MobilePageActivity {
    private String id;private ModuleDownloads downloads;private LinearLayout panel;private final Runnable observer=this::render;private Intent next;private String previous="";private boolean resumed;private ProgressBar progress;private TextView message;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);id=getIntent().getStringExtra("module_id");if(!ModuleSpec.IDS.contains(id)||!OptionalModules.allowed(this,id)){finish();return;}next=getIntent().getParcelableExtra("next");createPage(ModuleSpec.name(id));panel=card(body);downloads=ModuleDownloads.get(this);downloads.listen(observer);if(saved==null&&("idle".equals(downloads.state(id).phase)||getIntent().getBooleanExtra("refresh_module",false)))downloads.start(id);render();}
    @Override protected void onResume(){super.onResume();resumed=true;if(downloads!=null)render();}
    @Override protected void onPause(){resumed=false;super.onPause();}
    @Override protected void onDestroy(){if(downloads!=null)downloads.unlisten(observer);super.onDestroy();}
    private void render(){
        if(isDestroyed()||panel==null||!OptionalModules.allowed(this,id))return;ModuleDownloads.State state=downloads.state(id);
        if(!state.phase.equals(previous)){previous=state.phase;panel.removeAllViews();if(ArraysBusy(state.phase))panel.addView(new CodingCatView(this),new LinearLayout.LayoutParams(-1,dp(120)));message=text(state.message,16);panel.addView(message);progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);panel.addView(progress,new LinearLayout.LayoutParams(-1,dp(12)));
            if("failed".equals(state.phase)){ErrorModule.style(panel);message.setTextColor(ErrorModule.ink());panel.addView(button("重试",()->downloads.start(id)));}
            else if("idle".equals(state.phase)){message.setText("下载或安装被中断，原文件已保留。");panel.addView(button("继续下载或安装",()->downloads.start(id)));}
            else if("permission".equals(state.phase)){panel.addView(text("仅原生功能包需要Android系统安装确认，账号与本机数据会保留。",13));panel.addView(button("允许安装功能包",()->startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())))));panel.addView(button("继续安装",()->downloads.start(id)));}
            else if("done".equals(state.phase)){panel.addView(button(next==null?"完成":"打开模块",()->{if(next!=null){if(!ModuleStore.available(this,id)){OptionalModules.failure(this,new IllegalStateException("请重新打开App以加载刚安装的功能包"));return;}try{startActivity(next);}catch(Exception error){OptionalModules.failure(this,new IllegalStateException("请重新打开App以加载刚安装的功能包",error));return;}}finish();}));}
            else if("checking".equals(state.phase)||"downloading".equals(state.phase))panel.addView(button("取消下载",()->downloads.cancel(id)));
        }
        message.setText(("idle".equals(state.phase)?"下载或安装被中断，原文件已保留。":state.message)+(state.total>0?"\n"+state.bytes/1024+" / "+((state.total+1023)/1024)+" KB":""));progress.setIndeterminate(state.total==0);if(state.total>0)progress.setProgress((int)(1000*state.bytes/state.total));
        Intent confirmation=resumed?downloads.confirmation(id):null;if(confirmation!=null){try{startActivity(confirmation);}catch(Exception error){downloads.installerResult(id,android.content.pm.PackageInstaller.STATUS_FAILURE,"无法打开系统安装确认",null);}}
    }
    private static boolean ArraysBusy(String phase){return java.util.Arrays.asList("checking","downloading","verifying","installing","approval").contains(phase);}
}
