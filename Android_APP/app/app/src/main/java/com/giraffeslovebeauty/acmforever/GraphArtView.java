package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import java.util.function.IntConsumer;

/** Transparent interactive foreground; decorative scenery belongs behind the whole banner. */
final class GraphArtView extends View {
    private final GraphRoutes graph=new GraphRoutes();private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private int target=5;private IntConsumer listener=i->{};private boolean detailed;
    private final GestureDetector gestures;private boolean longPressed;
    GraphArtView(Context context,boolean detailed){super(context);this.detailed=detailed;setFocusable(true);setClickable(true);setContentDescription("网页同款最短路径图谱");gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener(){@Override public boolean onDown(MotionEvent event){return true;}@Override public void onLongPress(MotionEvent event){longPressed=performLongClick();}});}
    void onTarget(IntConsumer callback){listener=callback;}
    int target(){return target;}
    void select(int next){if(next<0||next>=GraphRoutes.NAMES.length)return;target=next;invalidate();listener.accept(target);announceForAccessibility(graph.description(target));}
    String status(){return graph.description(target);}
    private float scale(){return Math.min(getWidth()/400f,getHeight()/300f);}
    private float left(){return(getWidth()-400*scale())/2;}
    private float top(){return(getHeight()-300*scale())/2;}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);float scale=scale();if(scale<=0)return;int saved=canvas.save();canvas.translate(left(),top());canvas.scale(scale,scale);
        int foreground=MobileStyle.ON_HERO,accent=ThemePalette.readable(new int[]{MobileStyle.HERO},MobileStyle.ACCENT,3);int[] route=graph.route(target);boolean[] active=new boolean[GraphRoutes.NAMES.length];for(int node:route)active[node]=true;
        paint.setStrokeCap(Paint.Cap.ROUND);
        for(int[] edge:GraphRoutes.EDGES){float[] a=GraphRoutes.POINTS[edge[0]],b=GraphRoutes.POINTS[edge[1]];paint.setColor(foreground);paint.setAlpha(68);paint.setStrokeWidth(2.2f);canvas.drawLine(a[0],a[1],b[0],b[1],paint);
            if(detailed){paint.setAlpha(210);paint.setTextSize(13);paint.setTextAlign(Paint.Align.CENTER);canvas.drawText(Integer.toString(edge[2]),(a[0]+b[0])/2+3,(a[1]+b[1])/2-4,paint);}}
        paint.setColor(accent);paint.setAlpha(255);paint.setStrokeWidth(6);for(int i=1;i<route.length;i++){float[] a=GraphRoutes.POINTS[route[i-1]],b=GraphRoutes.POINTS[route[i]];canvas.drawLine(a[0],a[1],b[0],b[1],paint);}
        paint.setTypeface(Typeface.create("monospace",Typeface.BOLD));paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(detailed?19:25);
        for(int i=0;i<GraphRoutes.POINTS.length;i++){float[] p=GraphRoutes.POINTS[i];paint.setStyle(Paint.Style.FILL);paint.setColor(active[i]?accent:foreground);paint.setAlpha(active[i]?255:160);canvas.drawCircle(p[0],p[1],active[i]?10:6,paint);paint.setColor(foreground);paint.setAlpha(255);canvas.drawText(GraphRoutes.NAMES[i],p[0],p[1]-17,paint);if(i==target){paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);paint.setColor(accent);canvas.drawCircle(p[0],p[1],17,paint);paint.setStyle(Paint.Style.FILL);}}
        paint.setTextAlign(Paint.Align.LEFT);paint.setTextSize(detailed?18:22);paint.setColor(foreground);canvas.drawText("dist["+GraphRoutes.NAMES[target]+"] = "+graph.distances[target]+";",55,286,paint);canvas.restoreToCount(saved);
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(event.getAction()==MotionEvent.ACTION_DOWN)longPressed=false;gestures.onTouchEvent(event);if(event.getAction()==MotionEvent.ACTION_UP&&longPressed)return true;
        if(event.getAction()==MotionEvent.ACTION_DOWN)return true;
        if(event.getAction()==MotionEvent.ACTION_UP){float best=Float.MAX_VALUE;int nearest=-1;for(int i=0;i<GraphRoutes.POINTS.length;i++){float[] p=GraphRoutes.POINTS[i];float dx=left()+p[0]*scale()-event.getX(),dy=top()+p[1]*scale()-event.getY(),distance=dx*dx+dy*dy;if(distance<best){best=distance;nearest=i;}}if(nearest>=0&&best<=Math.pow(MobileStyle.dp(getContext(),28),2)){select(nearest);performClick();}return true;}return super.onTouchEvent(event);
    }
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onKeyDown(int key,KeyEvent event){if(key==KeyEvent.KEYCODE_DPAD_LEFT||key==KeyEvent.KEYCODE_DPAD_UP){select((target+GraphRoutes.NAMES.length-1)%GraphRoutes.NAMES.length);return true;}if(key==KeyEvent.KEYCODE_DPAD_RIGHT||key==KeyEvent.KEYCODE_DPAD_DOWN){select((target+1)%GraphRoutes.NAMES.length);return true;}if(key==KeyEvent.KEYCODE_ESCAPE){select(5);return true;}return super.onKeyDown(key,event);}
}
