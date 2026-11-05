package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.*;
import android.widget.*;

/** Local preview shares the live banner and graph, without business API requests. */
public final class ThemePreviewActivity extends Activity {
    private String themeId;
    @Override public SharedPreferences getSharedPreferences(String name,int mode){return "acmforever_settings".equals(name)&&LocalThemes.valid(themeId)?super.getSharedPreferences("local_theme_"+themeId,mode):super.getSharedPreferences(name,mode);}
    private int dp(int n){return MobileStyle.dp(this,n);}
    private LinearLayout column(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.VERTICAL);return b;}
    private TextView text(String value,int size,int color,boolean bold){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(2),1);if(bold)t.setTypeface(null,Typeface.BOLD);return t;}
    private void gap(LinearLayout parent,int height){parent.addView(new View(this),new LinearLayout.LayoutParams(1,dp(height)));}
    private LinearLayout card(LinearLayout parent){LinearLayout c=column();c.setPadding(dp(18),dp(18),dp(18),dp(18));c.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,12,0));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(10);parent.addView(c,p);return c;}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);themeId=getIntent().getStringExtra(LocalThemes.EXTRA);if(!LocalThemes.valid(themeId)||!LocalThemes.exists(getApplicationContext(),themeId)){finish();return;}AppAppearance.load(this);AppAppearance.window(this);
        LinearLayout root=column();root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));root.setContentDescription("本地主题预览，示例内容");AppAppearance.content(this,root);
        LinearLayout header=new SpacedLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(14),dp(10),dp(14),dp(10));header.setBackgroundColor(MobileStyle.CHROME);
        FrameLayout exit=new FrameLayout(this);android.graphics.drawable.GradientDrawable circle=new android.graphics.drawable.GradientDrawable();circle.setColor(0x80ff0000);circle.setShape(android.graphics.drawable.GradientDrawable.OVAL);exit.setBackground(circle);exit.setContentDescription("退出主题预览");exit.setOnClickListener(v->finish());
        ImageView cat=new ImageView(this);cat.setImageDrawable(AppIcons.get(this,"compose",Color.BLACK));FrameLayout.LayoutParams icon=new FrameLayout.LayoutParams(dp(25),dp(25),Gravity.TOP|Gravity.CENTER_HORIZONTAL);icon.topMargin=dp(2);exit.addView(cat,icon);
        TextView cross=text("×",19,Color.BLACK,true);cross.setGravity(Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);exit.addView(cross,new FrameLayout.LayoutParams(-1,-1));header.addView(exit,new LinearLayout.LayoutParams(dp(44),dp(44)));
        TextView search=text("ACMForever",13,MobileStyle.MUTED,false);search.setGravity(Gravity.CENTER_VERTICAL);search.setPadding(dp(13),0,dp(13),0);search.setBackground(MobileStyle.panel(this,MobileStyle.SEARCH,20,0));android.graphics.drawable.Drawable magnifier=AppIcons.get(this,"search",MobileStyle.MUTED);magnifier.setBounds(0,0,dp(18),dp(18));search.setCompoundDrawables(magnifier,null,null,null);search.setCompoundDrawablePadding(dp(8));
        LinearLayout.LayoutParams searchSize=new LinearLayout.LayoutParams(0,dp(44),1);searchSize.setMargins(dp(9),0,dp(9),0);header.addView(search,searchSize);
        ImageView plus=new ImageView(this);android.graphics.drawable.Drawable plusIcon=getDrawable(R.drawable.skland_add);plusIcon.setTint(MobileStyle.ON_ACCENT);plus.setImageDrawable(plusIcon);plus.setScaleType(ImageView.ScaleType.FIT_CENTER);plus.setPadding(dp(8),dp(8),dp(8),dp(8));plus.setBackground(MobileStyle.panel(this,MobileStyle.controlFill(MobileStyle.ACCENT),12,0));plus.setContentDescription("预览常用工具");header.addView(plus,new LinearLayout.LayoutParams(dp(44),dp(44)));root.addView(header,new LinearLayout.LayoutParams(-1,dp(64)));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));LinearLayout body=column();body.setPadding(dp(12),dp(12),dp(12),dp(24));scroll.addView(body);
        LinearLayout hero=HomeBanner.create(this,"COMMUNITY","一起交流，一起 AC","ACMForever",false,null);LinearLayout.LayoutParams bannerSize=new LinearLayout.LayoutParams(-1,-2);bannerSize.bottomMargin=dp(10);body.addView(hero,bannerSize);
        LinearLayout filter=new SpacedLayout(this);filter.setGravity(Gravity.CENTER_VERTICAL);filter.addView(text("社区话题",20,MobileStyle.TEXT,true),new LinearLayout.LayoutParams(0,-2,1));ImageView funnel=new ImageView(this);funnel.setImageDrawable(AppIcons.get(this,"filter",MobileStyle.TEXT));funnel.setPadding(dp(12),dp(12),dp(12),dp(12));funnel.setBackground(MobileStyle.panel(this,MobileStyle.PANEL,12,MobileStyle.LINE));filter.addView(funnel,new LinearLayout.LayoutParams(dp(44),dp(44)));body.addView(filter);gap(body,12);
        for(int i=0;i<3;i++){
            LinearLayout article=card(body),author=new SpacedLayout(this);author.setGravity(Gravity.CENTER_VERTICAL);ImageView avatar=new ImageView(this);avatar.setImageDrawable(AppIcons.get(this,"avatar",MobileStyle.TEXT));author.addView(avatar,new LinearLayout.LayoutParams(dp(32),dp(32)));LinearLayout copy=column();copy.setPadding(dp(10),0,0,0);copy.addView(text("ACMForever",13,MobileStyle.TEXT,true));copy.addView(text("ACMForever",10,MobileStyle.MUTED,false));author.addView(copy);article.addView(author);gap(article,12);
            article.addView(text("ACMForever",17,MobileStyle.TEXT,true));gap(article,6);article.addView(text("ACMForever",13,MobileStyle.MUTED,false));gap(article,10);TextView tag=text("ACMForever",11,MobileStyle.MUTED,false);tag.setPadding(dp(8),dp(4),dp(8),dp(4));tag.setBackground(MobileStyle.panel(this,MobileStyle.BACKGROUND,10,0));article.addView(tag,new LinearLayout.LayoutParams(-2,-2));gap(article,14);
            LinearLayout metrics=new SpacedLayout(this);metrics.addView(text("ACMForever",10,MobileStyle.MUTED,false),new LinearLayout.LayoutParams(0,-2,1));for(String name:new String[]{"comment","like"}){ImageView mark=new ImageView(this);mark.setImageDrawable(AppIcons.get(this,name,MobileStyle.MUTED));metrics.addView(mark,new LinearLayout.LayoutParams(dp(18),dp(18)));metrics.addView(text("ACMForever",10,MobileStyle.MUTED,false));}article.addView(metrics);
        }
        LinearLayout nav=new SpacedLayout(this);nav.setGravity(Gravity.CENTER_VERTICAL);nav.setBackgroundColor(MobileStyle.CHROME);nav.setPadding(dp(3),dp(5),dp(3),dp(5));String[] ids={"forum","rank","compose","problems","mine"},names={"主页","排名","发帖","题库","个人中心"};
        for(int i=0;i<ids.length;i++){boolean compose=i==2,selected=i==0;LinearLayout tab=column();tab.setGravity(Gravity.CENTER);ImageView image=new ImageView(this);image.setImageDrawable(AppIcons.get(this,ids[i],compose?MobileStyle.ON_ACCENT:selected?MobileStyle.TEXT:MobileStyle.MUTED));if(compose){image.setPadding(dp(5),dp(5),dp(5),dp(5));image.setBackground(MobileStyle.panel(this,MobileStyle.controlFill(MobileStyle.ACCENT),16,0));}tab.addView(image,new LinearLayout.LayoutParams(dp(compose?44:23),dp(compose?44:23)));if(!compose){TextView label=text(names[i],10,selected?MobileStyle.TEXT:MobileStyle.MUTED,selected);label.setGravity(Gravity.CENTER);tab.addView(label);View indicator=new View(this);indicator.setBackground(MobileStyle.panel(this,selected?MobileStyle.ACCENT:Color.TRANSPARENT,2,0));LinearLayout.LayoutParams line=new LinearLayout.LayoutParams(dp(16),dp(3));line.topMargin=dp(3);tab.addView(indicator,line);}nav.addView(tab,new LinearLayout.LayoutParams(0,-1,1));}root.addView(nav,new LinearLayout.LayoutParams(-1,dp(65)));
    }
    @Override protected void onResume(){super.onResume();AppAppearance.load(this);}
    @Override protected void onPause(){AppAppearance.load(getApplicationContext());super.onPause();}
}
