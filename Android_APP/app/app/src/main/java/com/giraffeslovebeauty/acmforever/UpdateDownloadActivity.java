package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.os.Bundle;
import android.view.*;
import android.widget.*;

/** A foreground view of the process-owned, persistent system download. */
public final class UpdateDownloadActivity extends Activity {
    private AppUpdates updates;
    private CodingCatView cat;
    private TextView heading,status,error;
    private ProgressBar progress;
    private Button install,retry,cancel;
    private int dp(int n){return MobileStyle.dp(this,n);}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);AppAppearance.load(this);AppAppearance.window(this);updates=((AcmApplication)getApplication()).updates();
        LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(12),dp(8),dp(12),dp(8));header.setBackgroundColor(MobileStyle.CHROME);
        ImageButton back=new ImageButton(this);MobileStyle.flat(back);back.setImageDrawable(AppIcons.get(this,"back",MobileStyle.TEXT));back.setBackgroundColor(android.graphics.Color.TRANSPARENT);back.setContentDescription("返回，下载在后台继续");back.setOnClickListener(v->finish());header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));header.addView(text("安装包下载",22));root.addView(header);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout body=new SpacedLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setGravity(Gravity.CENTER);body.setPadding(dp(24),dp(24),dp(24),dp(24));scroll.addView(body);
        cat=new CodingCatView(this);cat.setContentDescription("猫娘敲代码加载动画");body.addView(cat,new LinearLayout.LayoutParams(dp(240),dp(160)));
        heading=text("正在下载…",24);body.addView(heading);status=text("",15);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);body.addView(status);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(MobileStyle.ACCENT));LinearLayout.LayoutParams bar=new LinearLayout.LayoutParams(-1,dp(12));bar.setMargins(0,dp(16),0,dp(16));body.addView(progress,bar);
        error=text("",15);error.setPadding(dp(16),dp(16),dp(16),dp(16));ErrorModule.style(error);error.setTextColor(ErrorModule.ink());LinearLayout.LayoutParams failure=new LinearLayout.LayoutParams(-1,-2);failure.setMargins(0,dp(20),0,dp(12));body.addView(error,failure);
        install=button(body,"安装新版",()->updates.install(this));retry=button(body,"重试下载",()->updates.download());cancel=button(body,"取消下载",updates::cancelDownload);
        body.addView(text("返回后下载仍在后台继续。完成校验后，由 Android 系统确认安装。",13));refresh();
    }
    private TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextColor(MobileStyle.TEXT);t.setTextSize(size);t.setGravity(Gravity.CENTER);t.setPadding(0,dp(8),0,dp(8));return t;}
    private Button button(LinearLayout parent,String label,Runnable action){Button b=new Button(this);b.setText(label);MobileStyle.button(b,false);b.setOnClickListener(v->{if(!ModalDialogs.isShowing(this))action.run();});LinearLayout.LayoutParams bounds=new LinearLayout.LayoutParams(-1,dp(52));bounds.topMargin=dp(12);parent.addView(b,bounds);return b;}
    private void refresh(){
        if(isFinishing()||isDestroyed())return;
        boolean active=updates.downloading()||updates.verifying();
        heading.setText(updates.verifying()?"正在校验…":active?"正在下载…":updates.ready()?"下载完成":!updates.error().isEmpty()?"下载失败":"下载已取消");
        status.setText(updates.status());cat.setVisibility(active?View.VISIBLE:View.GONE);progress.setVisibility(active?View.VISIBLE:View.GONE);progress.setIndeterminate(updates.progress()<0||updates.verifying());progress.setProgress(Math.max(0,updates.progress()));
        error.setText(updates.error());error.setVisibility(updates.error().isEmpty()?View.GONE:View.VISIBLE);
        install.setVisibility(updates.ready()?View.VISIBLE:View.GONE);retry.setVisibility(!active&&!updates.ready()&&updates.available()?View.VISIBLE:View.GONE);cancel.setVisibility(active?View.VISIBLE:View.GONE);
    }
    @Override protected void onResume(){super.onResume();updates.attach(this,this::refresh);updates.resumeInstall(this);}
    @Override protected void onPause(){updates.detach(this);super.onPause();}
    @Override protected void onDestroy(){ModalDialogs.close(this);super.onDestroy();}
}
