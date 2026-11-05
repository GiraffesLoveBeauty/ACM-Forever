package com.giraffeslovebeauty.acmforever;
import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Aspect-preserving code mark and theme-coloured character signature. */
final class CommunityArtwork extends Drawable {
    private final Drawable character;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    CommunityArtwork(Context context,boolean ignored){character=AppIcons.get(context,"compose",MobileStyle.ON_HERO);paint.setStrokeWidth(5);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);}
    @Override public void draw(Canvas canvas){
        Rect b=getBounds();int save=canvas.save();float side=Math.min(b.width(),b.height());canvas.translate(b.left+(b.width()-side)/2,b.top+(b.height()-side)/2);canvas.scale(side/120f,side/120f);
        paint.setStyle(Paint.Style.STROKE);paint.setColor(MobileStyle.ON_HERO);
        Path code=new Path();code.moveTo(25,43);code.lineTo(9,60);code.lineTo(25,77);code.moveTo(95,43);code.lineTo(111,60);code.lineTo(95,77);canvas.drawPath(code,paint);
        character.setBounds(33,33,87,87);character.draw(canvas);canvas.restoreToCount(save);
    }
    @Override public void setAlpha(int alpha){character.setAlpha(alpha);paint.setAlpha(alpha);}
    @Override public void setColorFilter(ColorFilter filter){character.setColorFilter(filter);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
}
