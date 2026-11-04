package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.view.*;

/** Native HSV wheel; no remote image, WebView or third-party picker. */
final class ColorWheel extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private final float[] hsv=new float[3];
    private java.util.function.IntConsumer listener;private boolean rainbowOnly;
    ColorWheel(Context c,int color){super(c);Color.colorToHSV(color,hsv);setContentDescription("调色盘，滑动选择色相和饱和度");setFocusable(true);}
    void onColor(java.util.function.IntConsumer listener){this.listener=listener;}
    int color(){return Color.HSVToColor(hsv);}
    void brightness(float value){hsv[2]=Math.max(.08f,Math.min(1,value));invalidate();if(listener!=null)listener.accept(color());}
    @Override protected void onDraw(Canvas c){
        float x=getWidth()/2f,y=getHeight()/2f,r=Math.min(x,y)-MobileStyle.dp(getContext(),12);if(r<=0)return;
        int[] colors={Color.RED,Color.YELLOW,Color.GREEN,Color.CYAN,Color.BLUE,Color.MAGENTA,Color.RED};
        paint.setShader(new SweepGradient(x,y,colors,null));c.drawCircle(x,y,r,paint);
        paint.setShader(new RadialGradient(x,y,r,Color.WHITE,0x00ffffff,Shader.TileMode.CLAMP));c.drawCircle(x,y,r,paint);paint.setShader(null);
        paint.setColor(Color.BLACK);paint.setAlpha(Math.round((1-hsv[2])*255));c.drawCircle(x,y,r,paint);paint.setAlpha(255);
        float angle=(float)Math.toRadians(hsv[0]),px=x+(float)Math.cos(angle)*r*hsv[1],py=y+(float)Math.sin(angle)*r*hsv[1];
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(MobileStyle.dp(getContext(),3));paint.setColor(Color.WHITE);c.drawCircle(px,py,MobileStyle.dp(getContext(),8),paint);
        paint.setStrokeWidth(MobileStyle.dp(getContext(),1));paint.setColor(0xff292c29);c.drawCircle(px,py,MobileStyle.dp(getContext(),10),paint);paint.setStyle(Paint.Style.FILL);
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(event.getAction()==MotionEvent.ACTION_DOWN||event.getAction()==MotionEvent.ACTION_MOVE){
            getParent().requestDisallowInterceptTouchEvent(true);float dx=event.getX()-getWidth()/2f,dy=event.getY()-getHeight()/2f,r=Math.min(getWidth(),getHeight())/2f-MobileStyle.dp(getContext(),12);
            hsv[0]=(float)((Math.toDegrees(Math.atan2(dy,dx))+360)%360);hsv[1]=Math.min(1,(float)Math.hypot(dx,dy)/r);invalidate();if(listener!=null)listener.accept(color());return true;
        }
        if(event.getAction()==MotionEvent.ACTION_UP){performClick();return true;}return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
