package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.os.Bundle;
import android.view.*;
import android.widget.*;

/** Update preferences and download status. All version claims come from release metadata. */
public final class UpdateActivity extends Activity {
    private AppUpdates updates;
    private LinearLayout body,banner;
    private TextView status,notes,error,source,last;
    private Button check,download,install,cancel,clearPackages;
    private CheckBox automatic,moduleUpdates;
    private TextView modulesSummary;
    private LinearLayout moduleActions;
    private boolean painting;
    private boolean initialCheck;
    private PullRefreshLayout pull;
    private GithubCredits credits;
    private CreditsViews creditsViews;
    private int dp(int n){return MobileStyle.dp(this,n);}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);initialCheck=state==null&&!getIntent().getBooleanExtra("manage_downloads",false);AppAppearance.load(this);AppAppearance.window(this);updates=((AcmApplication)getApplication()).updates();
        LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        LinearLayout header=new SpacedLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(12),dp(8),dp(16),dp(8));header.setBackgroundColor(MobileStyle.CHROME);
        ImageButton back=new ImageButton(this);MobileStyle.flat(back);back.setImageDrawable(AppIcons.get(this,"back",MobileStyle.TEXT));back.setBackgroundColor(Color.TRANSPARENT);back.setContentDescription("返回");back.setOnClickListener(v->finish());header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));header.addView(text("应用更新",22));root.addView(header);
        banner=new LinearLayout(this);banner.setGravity(Gravity.CENTER_VERTICAL);banner.setPadding(dp(16),dp(8),dp(8),dp(8));ErrorModule.style(banner);
        error=text("",14);error.setTextColor(ErrorModule.ink());error.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);banner.addView(error,new LinearLayout.LayoutParams(0,-2,1));
        ImageButton close=new ImageButton(this);MobileStyle.flat(close);close.setBackgroundColor(Color.TRANSPARENT);close.setImageDrawable(AppIcons.get(this,"close",0xffaf2424));close.setContentDescription("关闭更新错误提示");close.setOnClickListener(v->updates.dismissError());banner.addView(close,new LinearLayout.LayoutParams(dp(48),dp(48)));LinearLayout.LayoutParams bannerBounds=new LinearLayout.LayoutParams(-1,-2);bannerBounds.setMargins(dp(12),dp(16),dp(12),dp(8));root.addView(banner,bannerBounds);
        ScrollView scroll=new ScrollView(this);pull=new PullRefreshLayout(this,scroll,()->!updates.busy()&&!ModalDialogs.isShowing(this),()->updates.check(true));root.addView(pull,new LinearLayout.LayoutParams(-1,0,1));body=new SpacedLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(dp(16),dp(16),dp(16),dp(24));scroll.addView(body);
        try{credits=GithubCredits.load(this);creditsViews=new CreditsViews(this,credits);}catch(Exception ignored){}
        LinearLayout current=card();current.addView(text("ACMforever "+updates.currentName(),20));status=text("",16);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);current.addView(status);notes=text("",14);current.addView(notes);
        if(creditsViews!=null)creditsViews.version(current,updates.currentName());else current.addView(text("本地人员记录读取失败",12));
        last=text("",12);current.addView(last);check=button(current,"检查更新",()->updates.check(true));download=button(current,"下载新版安装包",()->updates.openDownload(this));install=button(current,"安装新版",()->updates.install(this));cancel=button(current,"取消下载",updates::cancelDownload);
        clearPackages=button(current,"清理已下载安装包",()->new ModalDialogs.Builder(this).setTitle("清理已下载安装包？").setMessage("仅删除本 App 下载的安装包，不会卸载当前 App，也不影响账号密码、主题或草稿。需要更新时可重新下载。").setNegativeButton("取消",null).setPositiveButton("确认清理",(d,w)->updates.clearDownloadedPackages()).show());
        LinearLayout options=card();options.addView(text("自动更新选项",18));automatic=new CheckBox(this);automatic.setText("启动时自动检查更新");automatic.setMinHeight(dp(48));options.addView(automatic);
        options.addView(text("自动检查默认开启，启动时在会话处理后发起，检查成功后间隔 6 小时；失败可在下一次启动重试。进入本页与手动检查始终立即检查。发现新版先询问，点击下载后进入猫娘下载页；安装仍需系统确认。",12));
        automatic.setOnCheckedChangeListener((b,value)->{if(!painting){updates.automatic(value);if(value)updates.check(false);}});
        moduleUpdates=new CheckBox(this);moduleUpdates.setText("随 App 更新已下载模块");moduleUpdates.setMinHeight(dp(48));moduleUpdates.setChecked(ModuleStore.updateTogether(this));options.addView(moduleUpdates);
        moduleUpdates.setOnCheckedChangeListener((b,value)->{if(!painting)ModuleStore.updateTogether(this,value);});
        options.addView(text("默认勾选，仅更新已下载的模块。关闭后保留原文件和设置；旧资源包兼容时继续使用，原生模块须匹配新版 App，可能暂不可用。安装仍需系统确认。",12));
        modulesSummary=text("模块：等待版本检查",12);options.addView(modulesSummary);
        moduleActions=new SpacedLayout(this);moduleActions.setOrientation(LinearLayout.VERTICAL);options.addView(moduleActions);
        for(String id:ModuleSpec.IDS)if(ModuleStore.acquired(this).contains(id)&&!ModuleStore.current(this,id)&&OptionalModules.allowed(this,id))button(moduleActions,"更新"+ModuleSpec.name(id),()->startActivity(new Intent(this,ModuleDownloadActivity.class).putExtra("module_id",id).putExtra("refresh_module",true).putExtra("next",OptionalModules.target(this,id))));
        LinearLayout publishing=card();publishing.addView(text("版本发布地址",16));source=text("",12);source.setTextIsSelectable(true);publishing.addView(source);button(publishing,"设置发布地址",this::editSource);
        releaseHistory();
        refresh();AppAppearance.paintFields(root);
    }
    private TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(MobileStyle.TEXT);t.setPadding(0,dp(4),0,dp(6));return t;}
    private LinearLayout card(){LinearLayout box=new SpacedLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(16),dp(16),dp(16),dp(16));box.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);body.addView(box,p);return box;}
    private Button button(LinearLayout box,String label,Runnable action){Button b=new Button(this);b.setText(label);MobileStyle.button(b,false);b.setOnClickListener(v->{if(!ModalDialogs.isShowing(this))action.run();});box.addView(b,new LinearLayout.LayoutParams(-1,-2));return b;}
    private void releaseHistory(){
        LinearLayout intro=card();TextView heading=text("更新日志与说明",20);heading.setContentDescription("更新日志与说明");intro.addView(heading);intro.addView(text("随安装包保存，可离线查看。按版本从新到旧排列；历史记录不代表服务器已上线对应功能。",13));
        if(credits!=null)intro.addView(text("人员记录快照 · "+credits.capturedOn+"；发起 Review 与执行评审分别记录，机器人评审不等于人工批准。",12));
        try(java.io.InputStream in=getAssets().open(ReleaseHistory.ASSET);java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream()){
            byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1){if(bytes.size()+n>131072)throw new java.io.IOException("更新日志过大");bytes.write(buffer,0,n);}
            ReleaseHistory history=ReleaseHistory.parse(new String(bytes.toByteArray(),java.nio.charset.StandardCharsets.UTF_8),updates.currentName());
            for(ReleaseHistory.Entry entry:history.entries){
                LinearLayout version=card();version.setContentDescription("更新记录 "+entry.versionName);version.addView(text("v"+entry.versionName+(entry.versionName.equals(updates.currentName())?" · 当前版本":""),18));
                if(!entry.date.isEmpty())version.addView(text("记录日期 · "+entry.date,12));version.addView(text(entry.summary,14));
                if(creditsViews!=null)creditsViews.version(version,entry.versionName);
                Button open=button(version,"查看更新日志与说明",()->showReleaseNotes(entry));open.setContentDescription("查看 v"+entry.versionName+" 更新说明");
            }
        }catch(Exception failure){TextView unavailable=text("本地更新日志读取失败，请重新安装完整安装包。",14);unavailable.setTextColor(ErrorModule.ink());intro.addView(unavailable);}
    }
    private void showReleaseNotes(ReleaseHistory.Entry entry){
        TextView details=text(entry.details(),15);details.setTextIsSelectable(true);details.setLineSpacing(dp(4),1.1f);details.setPadding(dp(16),dp(16),dp(16),dp(16));details.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));details.setContentDescription("版本更新详情 "+entry.versionName);
        LinearLayout page=new SpacedLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.addView(details);
        if(creditsViews!=null)creditsViews.version(page,entry.versionName);
        new ModalDialogs.Builder(this).fullPage().setTitle("v"+entry.versionName+" 更新说明").setView(page).show();
    }
    private void refresh(){
        if(isFinishing()||isDestroyed())return;painting=true;pull.loading(updates.checking());
        try{status.setText(updates.status());last.setText(updates.lastCheck());error.setText(updates.error());banner.setVisibility(updates.error().isEmpty()?View.GONE:View.VISIBLE);notes.setText(updates.notes());notes.setVisibility(updates.notes().isEmpty()?View.GONE:View.VISIBLE);
            check.setEnabled(!updates.busy());download.setText(updates.downloadLabel());download.setVisibility(updates.available()&&!updates.ready()?View.VISIBLE:View.GONE);download.setEnabled(!updates.busy());install.setVisibility(updates.ready()?View.VISIBLE:View.GONE);install.setEnabled(!updates.busy());cancel.setVisibility(updates.downloading()?View.VISIBLE:View.GONE);clearPackages.setEnabled(!updates.busy());
            automatic.setChecked(updates.automatic());moduleUpdates.setChecked(ModuleStore.updateTogether(this));moduleUpdates.setEnabled(!updates.operationActive());modulesSummary.setText("模块："+updates.modulesStatus());for(int i=0;i<moduleActions.getChildCount();i++)moduleActions.getChildAt(i).setEnabled(!updates.operationActive());source.setText(updates.endpoint());
        }finally{painting=false;}
    }
    private void editSource(){
        EditText field=new EditText(this);field.setSingleLine(true);field.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);field.setHint("HTTPS 清单地址；留空恢复当前渠道默认地址");field.setText(updates.customSource());
        AlertDialog dialog=new ModalDialogs.Builder(this).setTitle("版本发布地址").setView(field).setNegativeButton("取消",null).setPositiveButton("保存",null).create();ModalDialogs.show(dialog);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try{updates.source(field.getText().toString());dialog.dismiss();}catch(IllegalArgumentException e){field.setError(e.getMessage());}});
    }
    @Override protected void onResume(){super.onResume();updates.attach(this,this::refresh);updates.resumeInstall(this);if(initialCheck){initialCheck=false;if(!updates.busy()&&!updates.ready())updates.check(true);}}
    @Override protected void onPause(){updates.detach(this);super.onPause();}
    @Override protected void onDestroy(){ModalDialogs.close(this);super.onDestroy();}
}
