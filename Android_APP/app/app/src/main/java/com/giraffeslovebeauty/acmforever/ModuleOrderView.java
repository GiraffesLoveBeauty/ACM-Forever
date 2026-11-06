package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.view.*;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.animation.DecelerateInterpolator;
import android.widget.ScrollView;
import java.util.*;
import java.util.function.Consumer;

/** Local vertical reorder: real rows follow the pointer; no free-floating drag shadow. */
@android.annotation.SuppressLint({"ViewConstructor","ClickableViewAccessibility"}) // Programmatic drag surface; every row supplies accessible move actions.
final class ModuleOrderView extends ViewGroup {
    private final ArrayList<View> order=new ArrayList<>(),before=new ArrayList<>();
    private final ScrollView scroll;
    private final Consumer<List<String>> saved;
    private final int gap,slop;
    private View candidate,selected;
    private float downX,downY,pointerY,grip;
    private boolean dragging;
    private ModuleDragPhysics physics;private long lastFrame;
    private int pointer=-1;
    private final Runnable hold=()->begin();
    private final Runnable edge=new Runnable(){public void run(){
        if(!dragging)return;
        int[] screen=new int[2];scroll.getLocationOnScreen(screen);
        float local=pointerY-screen[1];int zone=MobileStyle.dp(getContext(),64);
        int delta=local<zone?-MobileStyle.dp(getContext(),9):local>scroll.getHeight()-zone?MobileStyle.dp(getContext(),9):0;
        if(delta!=0)scroll.scrollBy(0,delta);position();postOnAnimation(this);
    }};
    ModuleOrderView(Context context,ScrollView scroll,Consumer<List<String>> saved){
        super(context);this.scroll=scroll;this.saved=saved;gap=MobileStyle.dp(context,14);slop=ViewConfiguration.get(context).getScaledTouchSlop();setClipChildren(false);setClipToPadding(false);
    }
    void addModule(View row,String id){row.setTag(id);row.setClickable(true);row.setFocusable(true);order.add(row);addView(row,new LayoutParams(-1,-2));
        row.setAccessibilityDelegate(new View.AccessibilityDelegate(){
            @Override public void onInitializeAccessibilityNodeInfo(View host,AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(host,info);info.addAction(new AccessibilityNodeInfo.AccessibilityAction(0x01020001,"向上移动"));info.addAction(new AccessibilityNodeInfo.AccessibilityAction(0x01020002,"向下移动"));}
            @Override public boolean performAccessibilityAction(View host,int action,android.os.Bundle args){if(action==0x01020001||action==0x01020002){if(dragging)return false;int from=order.indexOf(row),to=from+(action==0x01020001?-1:1);if(to<0||to>=order.size())return false;Collections.swap(order,from,to);persist();requestLayout();host.announceForAccessibility("已移动到第 "+(to+1)+" 项");return true;}return super.performAccessibilityAction(host,action,args);}
        });
    }
    @Override protected void onMeasure(int width,int height){int w=MeasureSpec.getSize(width),h=0;for(View v:order){v.measure(MeasureSpec.makeMeasureSpec(w,MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));h+=v.getMeasuredHeight()+gap;}setMeasuredDimension(w,Math.max(0,h));}
    @Override protected void onLayout(boolean changed,int l,int t,int r,int b){if(dragging)return;int top=0;for(View v:order){v.layout(0,top,r-l,top+v.getMeasuredHeight());v.setTranslationY(0);top+=v.getMeasuredHeight()+gap;}}
    @Override public boolean onInterceptTouchEvent(MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){removeCallbacks(hold);candidate=null;pointer=e.getPointerId(0);downX=e.getRawX();downY=pointerY=e.getRawY();for(View v:order)if(e.getY()>=v.getTop()&&e.getY()<=v.getBottom()){candidate=v;break;}if(candidate!=null)postDelayed(hold,ViewConfiguration.getLongPressTimeout());}
        // The first intercepted event cancels the child's gesture and may not reach
        // onTouchEvent. Consume its position/end here too, including a hold-only UP.
        if(dragging){dragEvent(e);return true;}
        if(e.getActionMasked()==MotionEvent.ACTION_MOVE&&(Math.abs(e.getRawY()-downY)>slop||Math.abs(e.getRawX()-downX)>slop))removeCallbacks(hold);
        if(e.getActionMasked()==MotionEvent.ACTION_CANCEL||e.getActionMasked()==MotionEvent.ACTION_UP)removeCallbacks(hold);
        return false;
    }
    private void begin(){if(candidate==null||!isAttachedToWindow())return;selected=candidate;before.clear();before.addAll(order);dragging=true;
        int[] p=new int[2];selected.getLocationOnScreen(p);grip=downY-(p[1]+selected.getHeight()/2f);pointerY=downY;
        float[] heights=new float[before.size()];for(int i=0;i<before.size();i++)heights[i]=before.get(i).getHeight();physics=new ModuleDragPhysics(heights,before.indexOf(selected),gap,MobileStyle.dp(getContext(),8));lastFrame=System.nanoTime();
        getParent().requestDisallowInterceptTouchEvent(true);selected.bringToFront();performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);
        for(View v:order){v.animate().cancel();v.animate().scaleX(.9f).scaleY(.9f).setDuration(160).start();}position();postOnAnimation(edge);
    }
    @Override public boolean onTouchEvent(MotionEvent e){
        if(!dragging)return super.onTouchEvent(e);
        dragEvent(e);return true;
    }
    private void dragEvent(MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_MOVE){if(e.findPointerIndex(pointer)<0){end(false);return;}pointerY=e.getRawY();}
        else if(e.getActionMasked()==MotionEvent.ACTION_UP){pointerY=e.getRawY();position();end(true);}
        else if(e.getActionMasked()==MotionEvent.ACTION_CANCEL||e.getActionMasked()==MotionEvent.ACTION_POINTER_DOWN)end(false);
    }
    private void position(){if(!dragging||physics==null)return;int[] p=new int[2];getLocationOnScreen(p);float top=pointerY-p[1]-grip-selected.getHeight()/2f;
        long now=System.nanoTime();physics.step(top,(now-lastFrame)/1_000_000_000f);lastFrame=now;
        order.clear();for(int id:physics.order())order.add(before.get(id));
        for(int i=0;i<before.size();i++){View v=before.get(i);v.setTranslationX(0);v.setTranslationY(physics.position(i)-v.getTop());}
    }
    private void end(boolean commit){if(!dragging)return;removeCallbacks(edge);removeCallbacks(hold);if(!commit){order.clear();order.addAll(before);}dragging=false;getParent().requestDisallowInterceptTouchEvent(false);
        int y=0;for(View v:order){v.animate().cancel();float old=v.getY();v.layout(0,y,getWidth(),y+v.getHeight());v.setTranslationY(old-y);v.animate().translationY(0).scaleX(1).scaleY(1).setDuration(180).setInterpolator(new DecelerateInterpolator()).start();y+=v.getHeight()+gap;}physics=null;selected=null;candidate=null;if(commit)persist();
    }
    private void persist(){ArrayList<String> ids=new ArrayList<>();for(View v:order)ids.add((String)v.getTag());saved.accept(ids);}
    @Override protected void onDetachedFromWindow(){removeCallbacks(hold);removeCallbacks(edge);if(dragging)end(false);super.onDetachedFromWindow();}
}
