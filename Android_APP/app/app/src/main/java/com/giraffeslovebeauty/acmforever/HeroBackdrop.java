package com.giraffeslovebeauty.acmforever;

import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Low contrast theme scenery below both text and interactive graph. */
final class HeroBackdrop extends Drawable {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private int alpha=255;
    @Override public void draw(Canvas canvas){Rect b=getBounds();int save=canvas.save();Path clip=new Path();float radius="minecraft".equals(MobileStyle.DESIGN)?0:"phase".equals(MobileStyle.DESIGN)?b.width()*.013f:"angel-city".equals(MobileStyle.DESIGN)?b.width()*.01f:b.width()*.05f;clip.addRoundRect(new RectF(b),radius,radius,Path.Direction.CW);canvas.clipPath(clip);canvas.translate(b.left,b.top);canvas.scale(b.width()/400f,b.height()/220f);paint.setColor(MobileStyle.ON_HERO);paint.setAlpha(Math.round(alpha*.06f));paint.setStyle(Paint.Style.FILL);
        switch(MobileStyle.DESIGN){
            case "minecraft":for(int x=0;x<400;x+=26){int height=20+(x*13%6)*8;canvas.drawRect(x,220-height,x+25,220,paint);}canvas.drawRect(285,27,330,72,paint);canvas.drawRect(323,43,357,72,paint);break;
            case "angel-city":for(int x=0;x<400;x+=32){int height=40+(x*17%7)*13;canvas.drawRect(x,220-height,x+23,220,paint);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1);canvas.drawLine(x+11,220-height-17,x+11,220-height,paint);paint.setStyle(Paint.Style.FILL);}break;
            case "phase":paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);for(int i=0;i<5;i++){Path p=new Path();p.moveTo(-20,i*45);p.lineTo(180,i*45+75);p.lineTo(440,i*45+15);canvas.drawPath(p,paint);}break;
            default:canvas.drawCircle(60,35,72,paint);canvas.drawRoundRect(290,100,410,230,22,22,paint);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.3f);for(int x=0;x<400;x+=25)canvas.drawLine(x,0,x,220,paint);for(int y=0;y<220;y+=25)canvas.drawLine(0,y,400,y,paint);
        }paint.setStyle(Paint.Style.FILL);canvas.restoreToCount(save);
    }
    @Override public void setAlpha(int value){alpha=value;invalidateSelf();}
    @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
}
