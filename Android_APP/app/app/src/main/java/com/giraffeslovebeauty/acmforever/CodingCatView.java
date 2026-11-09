package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.view.View;

/** User-provided colour art. A gentle bob and progress dots animate only while visible. */
final class CodingCatView extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
    CodingCatView(Context context){
        super(context);
        setContentDescription("猫娘正在敲代码");setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);Bitmap illustration=CharacterArt.bitmap(getContext(),CharacterArt.LOADING);float phase=SystemClock.uptimeMillis()/480f;
        float size=Math.min(getWidth(),getHeight()-MobileStyle.dp(getContext(),12));
        float x=(getWidth()-size)/2,y=(getHeight()-size)/2-4+(float)Math.sin(phase)*2;
        float scale=size/Math.max(illustration.getWidth(),illustration.getHeight()),w=illustration.getWidth()*scale,h=illustration.getHeight()*scale;
        paint.setAlpha(255);canvas.drawBitmap(illustration,null,new RectF(x+(size-w)/2,y+(size-h)/2,x+(size+w)/2,y+(size+h)/2),paint);
        float dot=MobileStyle.dp(getContext(),2),base=getHeight()-dot*2;paint.setColor(MobileStyle.BRAND);
        for(int i=0;i<3;i++){paint.setAlpha(100+(int)((Math.sin(phase-i)+1)*75));canvas.drawCircle(getWidth()/2f+(i-1)*dot*5,base,dot,paint);}
        if(isShown()&&getWindowVisibility()==VISIBLE)postInvalidateDelayed(60);
    }
}
