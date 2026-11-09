package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.view.*;

/** Free rectangular crop, image panning and pinch zoom; coordinates always remain inside the image. */
final class BackgroundCropView extends View {
    private Bitmap image;
    private final RectF frame=new RectF();
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
    private final ScaleGestureDetector gestures;
    private float scale=1,x,y,lastX,lastY;
    private int edge;
    private float[] restored;
    BackgroundCropView(Context context){
        super(context);setContentDescription("背景裁剪区域，拖动图片、双指缩放或拖动裁剪框边角");setFocusable(true);
        gestures=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScale(ScaleGestureDetector detector){
                if(image==null)return false;float previous=scale;scale=Math.max(minimum(),Math.min(minimum()*8,scale*detector.getScaleFactor()));float factor=scale/previous;
                x=detector.getFocusX()+(x-detector.getFocusX())*factor;y=detector.getFocusY()+(y-detector.getFocusY())*factor;constrain();invalidate();return true;
            }
        });
    }
    private float dp(float n){return MobileStyle.dp(getContext(),n);}
    void image(Bitmap value,float[] selection){image=value;restored=selection;if(getWidth()>0)reset();invalidate();}
    void reset(){
        if(image==null||getWidth()==0||getHeight()==0)return;
        float ratio=(float)getResources().getDisplayMetrics().widthPixels/getResources().getDisplayMetrics().heightPixels;
        float w=getWidth()-dp(48),h=Math.min(getHeight()-dp(48),w/ratio);w=Math.min(w,h*ratio);
        frame.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);
        if(restored!=null&&restored.length==4){
            RectF selected=new RectF(restored[0],restored[1],restored[2],restored[3]);restored=null;
            if(selected.width()>0&&selected.height()>0){float fit=Math.min((getWidth()-dp(48))/selected.width(),(getHeight()-dp(48))/selected.height());scale=fit;frame.set((getWidth()-selected.width()*fit)/2,(getHeight()-selected.height()*fit)/2,(getWidth()+selected.width()*fit)/2,(getHeight()+selected.height()*fit)/2);x=frame.left-selected.left*fit;y=frame.top-selected.top*fit;constrain();invalidate();return;}
        }
        scale=minimum();x=frame.centerX()-image.getWidth()*scale/2;y=frame.centerY()-image.getHeight()*scale/2;constrain();invalidate();
    }
    private float minimum(){return image==null?1:Math.max(frame.width()/image.getWidth(),frame.height()/image.getHeight());}
    private void constrain(){if(image==null)return;if(scale<minimum()){float previous=scale;scale=minimum();x=frame.centerX()+(x-frame.centerX())*scale/previous;y=frame.centerY()+(y-frame.centerY())*scale/previous;}x=Math.max(frame.right-image.getWidth()*scale,Math.min(frame.left,x));y=Math.max(frame.bottom-image.getHeight()*scale,Math.min(frame.top,y));}
    @Override protected void onSizeChanged(int w,int h,int oldW,int oldH){if(image!=null&&oldW>0&&oldH>0)restored=selection();reset();}
    float[] selection(){return new float[]{(frame.left-x)/scale,(frame.top-y)/scale,(frame.right-x)/scale,(frame.bottom-y)/scale};}
    RectF frame(){return new RectF(frame);}
    Bitmap export(){
        if(image==null)throw new IllegalStateException("图片尚未加载。");float[] selected=selection();int left=Math.max(0,Math.min(image.getWidth()-1,Math.round(selected[0]))),top=Math.max(0,Math.min(image.getHeight()-1,Math.round(selected[1]))),right=Math.min(image.getWidth(),Math.max(left+1,Math.round(selected[2]))),bottom=Math.min(image.getHeight(),Math.max(top+1,Math.round(selected[3])));
        Bitmap result=Bitmap.createBitmap(image,left,top,right-left,bottom-top);return result==image?image.copy(Bitmap.Config.ARGB_8888,false):result;
    }
    @Override protected void onDraw(Canvas canvas){
        canvas.drawColor(0xff191c19);if(image==null)return;paint.setStyle(Paint.Style.FILL);paint.setColor(Color.WHITE);canvas.drawBitmap(image,null,new RectF(x,y,x+image.getWidth()*scale,y+image.getHeight()*scale),paint);
        paint.setColor(0x99000000);canvas.drawRect(0,0,getWidth(),frame.top,paint);canvas.drawRect(0,frame.bottom,getWidth(),getHeight(),paint);canvas.drawRect(0,frame.top,frame.left,frame.bottom,paint);canvas.drawRect(frame.right,frame.top,getWidth(),frame.bottom,paint);
        paint.setColor(Color.WHITE);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2));canvas.drawRect(frame,paint);paint.setStrokeWidth(dp(.6f));
        for(int i=1;i<3;i++){canvas.drawLine(frame.left+frame.width()*i/3,frame.top,frame.left+frame.width()*i/3,frame.bottom,paint);canvas.drawLine(frame.left,frame.top+frame.height()*i/3,frame.right,frame.top+frame.height()*i/3,paint);}
        paint.setStyle(Paint.Style.FILL);paint.setColor(MobileStyle.ACCENT);for(float a:new float[]{frame.left,frame.right})for(float b:new float[]{frame.top,frame.bottom})canvas.drawCircle(a,b,dp(6),paint);
        for(float a:new float[]{frame.left,frame.right})canvas.drawCircle(a,frame.centerY(),dp(5),paint);for(float b:new float[]{frame.top,frame.bottom})canvas.drawCircle(frame.centerX(),b,dp(5),paint);
    }
    private int handle(float a,float b){float reach=dp(24);boolean vertical=b>=frame.top-reach&&b<=frame.bottom+reach,horizontal=a>=frame.left-reach&&a<=frame.right+reach;int result=0;if(vertical&&Math.abs(a-frame.left)<reach)result|=1;if(vertical&&Math.abs(a-frame.right)<reach)result|=2;if(horizontal&&Math.abs(b-frame.top)<reach)result|=4;if(horizontal&&Math.abs(b-frame.bottom)<reach)result|=8;return result;}
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!isEnabled())return false;if(image==null)return true;gestures.onTouchEvent(event);float a=event.getX(),b=event.getY();
        switch(event.getActionMasked()){
            case MotionEvent.ACTION_DOWN:lastX=a;lastY=b;edge=handle(a,b);getParent().requestDisallowInterceptTouchEvent(true);return true;
            case MotionEvent.ACTION_POINTER_DOWN:edge=0;return true;
            case MotionEvent.ACTION_POINTER_UP:int remaining=event.getActionIndex()==0?1:0;lastX=event.getX(remaining);lastY=event.getY(remaining);return true;
            case MotionEvent.ACTION_MOVE:
                if(event.getPointerCount()>1||gestures.isInProgress())return true;
                if(edge==0){x+=a-lastX;y+=b-lastY;}else{
                    float gap=dp(72),inset=dp(16);if((edge&1)!=0)frame.left=Math.max(inset,Math.min(frame.right-gap,a));if((edge&2)!=0)frame.right=Math.min(getWidth()-inset,Math.max(frame.left+gap,a));if((edge&4)!=0)frame.top=Math.max(inset,Math.min(frame.bottom-gap,b));if((edge&8)!=0)frame.bottom=Math.min(getHeight()-inset,Math.max(frame.top+gap,b));
                }lastX=a;lastY=b;constrain();invalidate();return true;
            case MotionEvent.ACTION_UP:performClick();getParent().requestDisallowInterceptTouchEvent(false);return true;
            case MotionEvent.ACTION_CANCEL:getParent().requestDisallowInterceptTouchEvent(false);return true;
            default:return true;
        }
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
