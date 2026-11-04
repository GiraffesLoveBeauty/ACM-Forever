package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.View;

/** Error surfaces keep rounded geometry in every template and follow module opacity. */
final class ErrorModule {
    static GradientDrawable background(Context c,boolean success){
        int ink=success?0xff287543:0xffc3313c;
        int fill=ThemePalette.mix(MobileStyle.PANEL,ink,.10);
        GradientDrawable bg=new GradientDrawable();bg.setColor((fill&0xffffff)|(Color.alpha(MobileStyle.MODULE)<<24));bg.setCornerRadius(MobileStyle.dp(c,18));return bg;
    }
    static void style(View view){view.setBackground(background(view.getContext(),false));view.setClipToOutline(true);separate(view);}
    static void separate(View view){if(view.getLayoutParams() instanceof android.view.ViewGroup.MarginLayoutParams){android.view.ViewGroup.MarginLayoutParams bounds=(android.view.ViewGroup.MarginLayoutParams)view.getLayoutParams();bounds.topMargin=Math.max(bounds.topMargin,MobileStyle.dp(view.getContext(),16));bounds.bottomMargin=Math.max(bounds.bottomMargin,MobileStyle.dp(view.getContext(),8));view.setLayoutParams(bounds);}}
    static int ink(){return ThemePalette.readable(new int[]{MobileStyle.PANEL,MobileStyle.BACKGROUND},0xffc3313c,4.5);}
}
