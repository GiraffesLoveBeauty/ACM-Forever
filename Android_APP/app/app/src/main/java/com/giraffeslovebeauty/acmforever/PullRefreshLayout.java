package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.view.*;
import android.widget.*;
import java.util.function.BooleanSupplier;

/** Top-edge pull gesture. The callback only repeats registered page reads, never writes. */
@android.annotation.SuppressLint("ViewConstructor") // Built programmatically with a page-scoped read callback.
final class PullRefreshLayout extends FrameLayout {
    private final ScrollView scroll;
    private final LinearLayout indicator;
    private final TextView label;
    private final ProgressBar progress;
    private final BooleanSupplier allowed;
    private final Runnable refresh;
    private final int slop,threshold;
    private float x,y,pull;
    private boolean possible,dragging,loading;
    PullRefreshLayout(Context context,ScrollView scroll,BooleanSupplier allowed,Runnable refresh){
        super(context);this.scroll=scroll;this.allowed=allowed;this.refresh=refresh;slop=ViewConfiguration.get(context).getScaledTouchSlop();threshold=MobileStyle.dp(context,64);
        addView(scroll,new LayoutParams(-1,-1));
        indicator=new LinearLayout(context);indicator.setGravity(Gravity.CENTER);indicator.setPadding(12,8,12,8);indicator.setBackground(MobileStyle.panel(context,MobileStyle.MODULE,100,MobileStyle.LINE));indicator.setVisibility(INVISIBLE);
        progress=new ProgressBar(context);progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(MobileStyle.BRAND));indicator.addView(progress,new LinearLayout.LayoutParams(MobileStyle.dp(context,20),MobileStyle.dp(context,20)));
        label=new TextView(context);label.setTextColor(MobileStyle.TEXT);label.setTextSize(13);label.setPadding(12,0,0,0);label.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);indicator.addView(label);
        LayoutParams p=new LayoutParams(-2,MobileStyle.dp(context,42),Gravity.TOP|Gravity.CENTER_HORIZONTAL);p.topMargin=MobileStyle.dp(context,10);addView(indicator,p);
    }
    @Override public boolean onInterceptTouchEvent(MotionEvent event){
        if(event.getActionMasked()==MotionEvent.ACTION_DOWN){x=event.getX();y=event.getY();possible=!loading&&!scroll.canScrollVertically(-1)&&allowed.getAsBoolean();dragging=false;}
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE&&possible){float dx=event.getX()-x,dy=event.getY()-y;if(Math.abs(dx)>slop&&Math.abs(dx)>Math.abs(dy)){possible=false;return false;}if(dy>slop&&dy>Math.abs(dx)*1.3f&&!scroll.canScrollVertically(-1)){dragging=true;getParent().requestDisallowInterceptTouchEvent(true);return true;}}
        if(event.getActionMasked()==MotionEvent.ACTION_UP||event.getActionMasked()==MotionEvent.ACTION_CANCEL)possible=false;
        return dragging;
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!dragging)return super.onTouchEvent(event);
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE){pull=Math.max(0,Math.min(threshold*1.6f,(event.getY()-y)*.5f));scroll.setTranslationY(pull);indicator.setVisibility(pull>0?VISIBLE:INVISIBLE);indicator.setAlpha(Math.min(1,pull/threshold));progress.setVisibility(GONE);label.setText(pull>=threshold?"松开刷新":"下拉刷新");}
        if(event.getActionMasked()==MotionEvent.ACTION_UP||event.getActionMasked()==MotionEvent.ACTION_CANCEL){boolean go=event.getActionMasked()==MotionEvent.ACTION_UP&&pull>=threshold;dragging=false;possible=false;pull=0;getParent().requestDisallowInterceptTouchEvent(false);scroll.animate().translationY(0).setDuration(180).start();if(go)performClick();else loading(false);}
        return true;
    }
    @Override public boolean performClick(){super.performClick();if(allowed.getAsBoolean())refresh.run();return true;}
    @Override public void onInitializeAccessibilityNodeInfo(android.view.accessibility.AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(info);info.addAction(new android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK,"刷新页面"));}
    void loading(boolean value){loading=value;if(!dragging){indicator.setVisibility(value?VISIBLE:INVISIBLE);indicator.setAlpha(1);progress.setVisibility(value?VISIBLE:GONE);label.setText(value?"正在刷新…":"下拉刷新");}}
    static PullRefreshLayout forPage(Context context,ScrollView scroll,PageRefresh page,BooleanSupplier enabled){
        PullRefreshLayout layout=new PullRefreshLayout(context,scroll,()->enabled.getAsBoolean()&&page.canRefresh(),page::refreshNow);page.observe(layout::loading);return layout;
    }
}
