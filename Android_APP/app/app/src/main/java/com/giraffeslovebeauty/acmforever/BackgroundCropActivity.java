package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.util.concurrent.*;

/** The picker URI and cropped pixels stay on this device. Cancel never replaces the old background. */
public final class BackgroundCropActivity extends Activity {
    private String themeId;
    @Override public android.content.SharedPreferences getSharedPreferences(String name,int mode){return "acmforever_settings".equals(name)&&LocalThemes.valid(themeId)?super.getSharedPreferences("local_theme_"+themeId,mode):super.getSharedPreferences(name,mode);}
    private final ExecutorService files=Executors.newSingleThreadExecutor();
    private BackgroundCropView crop;
    private Bitmap image;
    private Button apply,reset;
    private TextView status;
    private boolean saving;
    private int dp(int n){return MobileStyle.dp(this,n);}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);themeId=getIntent().getStringExtra(LocalThemes.EXTRA);if(themeId!=null&&(!LocalThemes.valid(themeId)||!LocalThemes.exists(getApplicationContext(),themeId))){finish();return;}AppAppearance.load(this);AppAppearance.window(this);
        LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setBackgroundColor(MobileStyle.PANEL);AppAppearance.content(this,root);
        LinearLayout header=new SpacedLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(12),dp(8),dp(12),dp(8));
        ImageButton back=new ImageButton(this);MobileStyle.flat(back);back.setBackgroundColor(android.graphics.Color.TRANSPARENT);back.setImageDrawable(AppIcons.get(this,"back",MobileStyle.TEXT));back.setContentDescription("取消裁剪");back.setOnClickListener(v->onBackPressed());header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));
        TextView title=new TextView(this);title.setText("裁剪背景");title.setTextSize(21);title.setTextColor(MobileStyle.TEXT);header.addView(title);root.addView(header);
        crop=new BackgroundCropView(this);root.addView(crop,new LinearLayout.LayoutParams(-1,0,1));
        status=new TextView(this);status.setText("正在读取图片…");status.setTextColor(MobileStyle.TEXT);status.setTextSize(13);status.setPadding(dp(16),dp(12),dp(16),dp(12));root.addView(status);
        LinearLayout actions=new SpacedLayout(this);actions.setPadding(dp(16),0,dp(16),dp(16));actions.setGravity(Gravity.CENTER_VERTICAL);
        reset=new Button(this);reset.setText("重置");MobileStyle.button(reset,false);reset.setOnClickListener(v->crop.reset());actions.addView(reset,new LinearLayout.LayoutParams(0,-2,1));
        apply=new Button(this);apply.setText("使用此背景");MobileStyle.button(apply,true);apply.setEnabled(false);apply.setOnClickListener(v->save());actions.addView(apply,new LinearLayout.LayoutParams(0,-2,1));root.addView(actions);
        Uri uri=getIntent().getData();float[] selection=saved==null?null:saved.getFloatArray("selection");
        if(uri==null){status.setText("未收到相册图片，请返回重新选择。");return;}
        files.execute(()->{
            try{Bitmap loaded=ProfileCover.load(this,uri);runOnUiThread(()->{if(isDestroyed()||isFinishing()){loaded.recycle();return;}image=loaded;crop.image(image,selection);apply.setEnabled(true);status.setText("拖动图片 · 双指缩放 · 拖动裁剪框边角");});}
            catch(Exception e){runOnUiThread(()->{if(!isDestroyed())status.setText("图片读取失败："+e.getMessage());});}
        });
    }
    private void save(){
        if(saving||image==null)return;float[] selected=crop.selection();for(int i=0;i<4;i++)selected[i]=Math.max(0,Math.min(1,selected[i]/(i%2==0?image.getWidth():image.getHeight())));
        saving=true;apply.setEnabled(false);reset.setEnabled(false);crop.setEnabled(false);status.setText("正在保存到本机…");
        files.execute(()->{
            try{ProfileCover.saveOriginal(this,getIntent().getData(),selected);runOnUiThread(()->{saving=false;if(isDestroyed())return;setResult(RESULT_OK);finish();});}
            catch(Exception e){runOnUiThread(()->{saving=false;if(isDestroyed())return;apply.setEnabled(true);reset.setEnabled(true);crop.setEnabled(true);status.setText("背景保存失败："+e.getMessage());});}
        });
    }
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);if(image!=null)state.putFloatArray("selection",crop.selection());}
    @Override public void onBackPressed(){if(!saving)super.onBackPressed();}
    @Override protected void onDestroy(){if(image!=null)image.recycle();files.shutdown();super.onDestroy();}
}
