package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.LayerDrawable;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.function.IntConsumer;

/** The live home and local theme preview share the same banner and interactive graph. */
final class HomeBanner {
    private static int dp(Context c,int value){return MobileStyle.dp(c,value);}
    private static LinearLayout column(Context c){LinearLayout v=new SpacedLayout(c);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private static TextView text(Context c,String value,int size,boolean bold){TextView t=new TextView(c);t.setText(value);t.setTextSize(size);t.setTextColor(MobileStyle.ON_HERO);t.setLineSpacing(dp(c,2),1);if(bold)t.setTypeface(null,Typeface.BOLD);return t;}
    private static void gap(Context c,LinearLayout box,int size){box.addView(new View(c),new LinearLayout.LayoutParams(1,dp(c,size)));}
    static LinearLayout create(Context c,String eyebrow,String title,String subtitle,boolean dark,IntConsumer explore){
        LinearLayout box=column(c);box.setContentDescription("社区主题横幅");box.setPadding(dp(c,18),dp(c,16),dp(c,12),dp(c,16));
        GradientDrawable fill=new GradientDrawable();fill.setColor(ThemePalette.module(MobileStyle.HERO,AppAppearance.prefs(c).getInt("module_transparency",0)));fill.setCornerRadius(dp(c,16));
        boolean official="web".equals(AppAppearance.prefs(c).getString("theme_source","acm"));
        box.setBackground(official?fill:new LayerDrawable(new android.graphics.drawable.Drawable[]{fill,new HeroBackdrop()}));
        LinearLayout brand=new SpacedLayout(c);TextView tag=text(c,eyebrow,9,true);tag.setLetterSpacing(.10f);brand.addView(tag,new LinearLayout.LayoutParams(0,-2,1));
        ImageView signature=new ImageView(c);signature.setImageDrawable(new CommunityArtwork(c,dark));signature.setContentDescription("猫娘代码标志");brand.addView(signature,new LinearLayout.LayoutParams(dp(c,27),dp(c,27)));box.addView(brand);gap(c,box,8);
        LinearLayout line=new SpacedLayout(c),copy=column(c);copy.setContentDescription("社区横幅文字");copy.addView(text(c,title,24,true));gap(c,copy,8);copy.addView(text(c,subtitle,11,false));line.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        View graph;
        if(official){String scene=eyebrow.toLowerCase(java.util.Locale.ROOT).contains("rank")?"podium":eyebrow.toLowerCase(java.util.Locale.ROOT).contains("profile")?"journey":"graph";graph=new OfficialThemeView(c,scene);}
        else{GraphArtView nativeGraph=new GraphArtView(c,false);nativeGraph.setTooltipText("点选节点，长按放大");if(explore!=null)nativeGraph.setOnLongClickListener(v->{explore.accept(nativeGraph.target());return true;});graph=nativeGraph;}
        LinearLayout.LayoutParams graphSize=new LinearLayout.LayoutParams(dp(c,140),dp(c,112));graphSize.leftMargin=dp(c,8);line.addView(graph,graphSize);box.addView(line);return box;
    }
}
