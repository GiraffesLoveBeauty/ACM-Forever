package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Color;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

/** One visible dialog per Activity. A repeated dialog keeps its current inputs. */
final class ModalDialogs {
    private static final WeakHashMap<Context, WeakReference<AlertDialog>> visible = new WeakHashMap<>();
    private static final WeakHashMap<AlertDialog, String> keys = new WeakHashMap<>();
    static boolean isShowing(Context owner) {
        WeakReference<AlertDialog> entry=visible.get(owner);
        AlertDialog dialog=entry==null?null:entry.get();return dialog!=null&&dialog.isShowing();
    }
    static AlertDialog show(AlertDialog dialog) {
        Context owner=dialog.getOwnerActivity();
        if(owner==null)owner=dialog.getContext();
        if(owner instanceof Activity && (((Activity)owner).isFinishing()||((Activity)owner).isDestroyed()))return dialog;
        WeakReference<AlertDialog> entry=visible.get(owner);
        AlertDialog previous=entry==null?null:entry.get();
        if(previous!=null&&previous.isShowing()){
            if(previous==dialog||keys.getOrDefault(previous,"").equals(keys.getOrDefault(dialog,"")))return previous;
            previous.dismiss();
        }
        visible.put(owner,new WeakReference<>(dialog));dialog.show();
        if(!(dialog instanceof DetailPage))decorate(dialog);AppAppearance.paintFields(dialog.getWindow().getDecorView());
        TextView message=dialog.findViewById(android.R.id.message);if(message!=null)message.setTextColor(MobileStyle.TEXT);
        return dialog;
    }
    private static void decorate(AlertDialog dialog){
        Context context=dialog.getContext();Window window=dialog.getWindow();if(window==null)return;
        window.setBackgroundDrawable(MobileStyle.panel(context,MobileStyle.PANEL,24,0));window.setElevation(0);
        window.setLayout(Math.min(context.getResources().getDisplayMetrics().widthPixels-MobileStyle.dp(context,32),MobileStyle.dp(context,480)),-2);
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        for(int id:new int[]{AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL,AlertDialog.BUTTON_POSITIVE}){
            Button button=dialog.getButton(id);if(button==null)continue;
            MobileStyle.button(button,id==AlertDialog.BUTTON_POSITIVE);button.setMinWidth(MobileStyle.dp(context,72));
            if(button.getLayoutParams() instanceof android.view.ViewGroup.MarginLayoutParams){
                android.view.ViewGroup.MarginLayoutParams gap=(android.view.ViewGroup.MarginLayoutParams)button.getLayoutParams();
                gap.setMarginStart(MobileStyle.dp(context,8));gap.topMargin=MobileStyle.dp(context,8);button.setLayoutParams(gap);
            }
        }
    }
    private static LinearLayout title(Context context,CharSequence value,Runnable dismiss,boolean full){
        LinearLayout header=new LinearLayout(context);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(MobileStyle.dp(context,20),MobileStyle.dp(context,14),MobileStyle.dp(context,8),MobileStyle.dp(context,10));header.setBackgroundColor(MobileStyle.PANEL);
        LinearLayout copy=new LinearLayout(context);copy.setOrientation(LinearLayout.VERTICAL);
        TextView eyebrow=new TextView(context);eyebrow.setText("ACMFOREVER");eyebrow.setTextColor(MobileStyle.MUTED);eyebrow.setTextSize(9);eyebrow.setLetterSpacing(.12f);copy.addView(eyebrow);
        TextView text=new TextView(context);text.setText(value);text.setTextColor(MobileStyle.TEXT);text.setTextSize(20);text.setTypeface(null,android.graphics.Typeface.BOLD);text.setPadding(0,MobileStyle.dp(context,5),0,0);copy.addView(text);header.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        ImageButton close=new ImageButton(context);MobileStyle.flat(close);close.setImageDrawable(AppIcons.get(context,full?"back":"close",MobileStyle.TEXT));int pad=MobileStyle.dp(context,12);close.setPadding(pad,pad,pad,pad);close.setBackgroundColor(Color.TRANSPARENT);close.setContentDescription(full?"返回":"关闭窗口");close.setOnClickListener(v->dismiss.run());header.addView(close,new LinearLayout.LayoutParams(MobileStyle.dp(context,48),MobileStyle.dp(context,48)));return header;
    }
    static void close(Context owner){WeakReference<AlertDialog> entry=visible.remove(owner);AlertDialog dialog=entry==null?null:entry.get();if(dialog!=null)dialog.dismiss();}
    static final class Builder extends AlertDialog.Builder {
        private final Context owner;
        private String key="dialog";
        private CharSequence title="提示";
        private View body;
        private boolean full;
        Builder(Context context){super(context,R.style.AppDialogTheme);owner=context;}
        Builder fullPage(){full=true;return this;}
        @Override public Builder setTitle(CharSequence value){key="title:"+value;title=value;return this;}
        @Override public Builder setView(View view){body=view;return this;}
        @Override public Builder setMessage(CharSequence value){if(!key.startsWith("title:"))key="message:"+value;super.setMessage(value);return this;}
        @Override public AlertDialog create(){
            final AlertDialog dialog;
            if(full)dialog=new DetailPage(owner,title,body);
            else {
                if(body!=null){
                    View inner=body instanceof ScrollView&&((ScrollView)body).getChildCount()>0?((ScrollView)body).getChildAt(0):body;
                    if(inner instanceof ViewGroup)inner.setPadding(0,inner.getPaddingTop(),0,inner.getPaddingBottom());
                    ScrollView scroll;
                    if(body instanceof ScrollView)scroll=(ScrollView)body;else{scroll=new ScrollView(owner);scroll.addView(body);}
                    FrameLayout bound=new FrameLayout(owner){@Override protected void onMeasure(int width,int height){int cap=(int)(getResources().getDisplayMetrics().heightPixels*.58f);super.onMeasure(width,MeasureSpec.makeMeasureSpec(cap,MeasureSpec.AT_MOST));}};
                    bound.addView(scroll);bound.setPadding(MobileStyle.dp(owner,20),MobileStyle.dp(owner,16),MobileStyle.dp(owner,20),MobileStyle.dp(owner,8));super.setView(bound);
                }
                dialog=super.create();dialog.setCustomTitle(title(owner,title,dialog::dismiss,false));
            }
            if(owner instanceof Activity)dialog.setOwnerActivity((Activity)owner);keys.put(dialog,key);return dialog;
        }
        @Override public AlertDialog show(){return ModalDialogs.show(create());}
    }
    /** A full-screen subpage keeps the owner's callbacks and uses ordinary back navigation. */
    private static final class DetailPage extends AlertDialog {
        private final CharSequence heading;private final View body;
        DetailPage(Context context,CharSequence heading,View body){super(context,R.style.AppDetailTheme);this.heading=heading;this.body=body;}
        @Override protected void onCreate(Bundle saved){
            super.onCreate(saved);Context context=getContext();LinearLayout root=new LinearLayout(context);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(context));
            root.addView(title(context,heading,this::dismiss,true));
            ScrollView scroll=body instanceof ScrollView?(ScrollView)body:new ScrollView(context);
            if(body!=null&&body!=scroll)scroll.addView(body);
            scroll.setFillViewport(true);scroll.setPadding(MobileStyle.dp(context,16),MobileStyle.dp(context,16),MobileStyle.dp(context,16),MobileStyle.dp(context,20));scroll.setClipToPadding(false);
            root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));AppAppearance.content(this,root);
            if(getWindow()!=null){getWindow().setBackgroundDrawableResource(android.R.color.transparent);getWindow().setLayout(-1,-1);getWindow().setElevation(0);AppAppearance.window(getWindow());}
        }
    }
}
