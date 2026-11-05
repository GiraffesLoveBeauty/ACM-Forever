package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.widget.Button;
import android.widget.TextView;

/** Shared original presentation for the native training and reader screens. */
final class MobileStyle {
    static int BACKGROUND=Color.rgb(244,245,247), TEXT=Color.rgb(30,33,28), PANEL=Color.WHITE;
    static int MUTED=Color.rgb(112,119,107), ACCENT=Color.rgb(200,235,33), BRAND=0xff315b36, LINE=0xffe5e8e0, HERO=ACCENT, ON_HERO=TEXT, ON_ACCENT=TEXT, ON_SELECTED=TEXT, SELECTED=0xffedf5ca, CAT=TEXT, MODULE=PANEL;
    static int CONTROL_TRANSPARENCY,CHROME=PANEL,SEARCH=BACKGROUND;
    static int controlFill(int color){return ThemePalette.module(color,CONTROL_TRANSPARENCY);}
    private MobileStyle() { }
    static String DESIGN="original";
    static int dp(Context context,float value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static GradientDrawable panel(Context context,int fill,int radius,int line){
        GradientDrawable shape=new GradientDrawable();shape.setColor(fill);
        int corners="minecraft".equals(DESIGN)?0:"phase".equals(DESIGN)?Math.min(radius,4):"angel-city".equals(DESIGN)?Math.min(radius,3):radius;
        // Circular controls retain their geometry in every template.
        shape.setCornerRadius(dp(context,radius>=100?radius:corners));
        if(line==0&&Color.alpha(fill)>0&&radius<100&&!"original".equals(DESIGN))line=LINE;
        if(line!=0)shape.setStroke(dp(context,1),line);return shape;
    }
    static void button(Button button,boolean primary){
        flat(button);
        Context context=button.getContext();button.setAllCaps(false);button.setTextSize(13);
        button.setTypeface(null,Typeface.BOLD);
        button.setMinHeight(dp(context,48));button.setPadding(dp(context,12),dp(context,8),dp(context,12),dp(context,8));
        control(button,primary,false,10);
        symbol(button);
    }
    /** Buttons and filter chips use the same enabled, disabled and selected palette. */
    static void control(TextView view,boolean primary,boolean selected,int radius){
        boolean web="web".equals(AppAppearance.prefs(view.getContext()).getString("theme_source","acm"));
        int fill=primary?ACCENT:selected?(web?SELECTED:ACCENT):PANEL,ink=selected?(web?ON_SELECTED:ON_ACCENT):primary?ON_ACCENT:BRAND;
        int disabledFill=ThemePalette.mix(PANEL,fill,.22),disabledInk=ThemePalette.readable(new int[]{disabledFill},ThemePalette.mix(ink,disabledFill,.5),3);
        view.setSelected(selected);
        ColorStateList text=new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{disabledInk,ink});
        view.setTextColor(text);view.setCompoundDrawableTintList(text);
        StateListDrawable backgrounds=new StateListDrawable();
        backgrounds.addState(new int[]{-android.R.attr.state_enabled},panel(view.getContext(),controlFill(disabledFill),radius,controlFill(LINE)));
        backgrounds.addState(new int[]{},panel(view.getContext(),controlFill(fill),radius,primary||selected?0:controlFill(LINE)));
        view.setBackground(new RippleDrawable(ColorStateList.valueOf((ink&0x00ffffff)|0x22000000),backgrounds,null));
    }
    static android.widget.ArrayAdapter<String> options(Context context,String[] names){
        android.widget.ArrayAdapter<String> adapter=new android.widget.ArrayAdapter<String>(context,android.R.layout.simple_spinner_item,names){
            private android.view.View colour(android.view.View view){if(view instanceof TextView){((TextView)view).setTextColor(TEXT);view.setBackgroundColor(PANEL);}return view;}
            @Override public android.view.View getView(int position,android.view.View reuse,android.view.ViewGroup parent){return colour(super.getView(position,reuse,parent));}
            @Override public android.view.View getDropDownView(int position,android.view.View reuse,android.view.ViewGroup parent){return colour(super.getDropDownView(position,reuse,parent));}
        };adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);return adapter;
    }
    static void symbol(Button button){
        String text=button.getText().toString(),icon=null;
        if(text.startsWith("←")||text.startsWith("返回")||text.equals("上一页")){icon="back";button.setText(text.replaceFirst("^←\\s*",""));}
        else if(text.equals("下一页"))icon="next";
        else if(text.startsWith("＋ ")){icon="compose";button.setText(text.substring(2));}
        else if(text.equals("＋")||text.equals("−")){icon=text.equals("＋")?"zoom-in":"zoom-out";button.setContentDescription(text.equals("＋")?"放大":"缩小");button.setText("");}
        else if(text.equals("适应宽度")){icon="fit";button.setText("适宽");button.setContentDescription("适应宽度");}
        else if(text.contains("搜索"))icon="search";
        else if(text.contains("历史记录"))icon="history";
        else if(text.contains("设置"))icon="settings";
        else if(text.startsWith("★")||text.startsWith("☆")){icon="bookmark";button.setText(text.replaceFirst("^[★☆]\\s*",""));}
        else if(text.startsWith("复制"))icon="copy";
        else if(text.startsWith("举报"))icon="report";
        else if(text.contains("原题")){icon="link";button.setText(text.replace("↗","").trim());}
        if(icon!=null){AppIcons.on(button,icon,button.getCurrentTextColor(),18);button.setCompoundDrawableTintList(button.getTextColors());}
    }
    static void flat(android.view.View view){view.setStateListAnimator(null);view.setElevation(0);view.setTranslationZ(0);}
}
