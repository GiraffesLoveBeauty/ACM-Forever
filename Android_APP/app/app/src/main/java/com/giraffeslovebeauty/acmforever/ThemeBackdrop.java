package com.giraffeslovebeauty.acmforever;

import android.graphics.*;

/** Native rendering of the checked-in web CSS background rules and original dirt.svg. */
final class ThemeBackdrop {
    private static final int[][] DIRT={
        {0x493323,0,2,9,5,13,0,8,4,26,3,6,7,7,13,12,6,0,24,8,8,20,25,12,5},
        {0x5b412b,3,3,4,3,15,1,4,2,25,13,7,4,9,25,6,5,19,18,5,4},
        {0x281d16,8,7,5,5,18,7,8,4,0,16,4,5,12,20,6,4,27,30,5,2},
        {0x6a4c33,4,11,2,2,22,4,2,3,13,15,3,2,26,21,3,3,3,27,2,2}};
    static void draw(Canvas c,Paint p,String design,float w,float h,float density,int ink,int accent,int alpha){
        if("none".equals(design)||"phase".equals(design))return;
        if("minecraft".equals(design)){
            int saved=c.save();c.clipRect(0,0,w,h);c.scale(3*density,3*density);p.setColor(0xff38291f);p.setAlpha(alpha);c.drawRect(0,0,w/(3*density),h/(3*density),p);
            for(int y=0;y<h/(3*density);y+=32)for(int x=0;x<w/(3*density);x+=32)for(int[] layer:DIRT){p.setColor(0xff000000|layer[0]);p.setAlpha(alpha);for(int i=1;i<layer.length;i+=4)c.drawRect(x+layer[i],y+layer[i+1],x+layer[i]+layer[i+2],y+layer[i+1]+layer[i+3],p);}
            p.setColor(0x33000000);p.setAlpha(Math.round(alpha*.2f));c.drawRect(0,0,w/(3*density),h/(3*density),p);c.restoreToCount(saved);
        }else{
            float step=("angel-city".equals(design)?96:64)*density;p.setColor(ink);p.setAlpha(Math.round(alpha*.05f));p.setStrokeWidth(density);
            for(float x=0;x<w;x+=step)c.drawLine(x,0,x,h,p);for(float y=0;y<h;y+=step)c.drawLine(0,y,w,y,p);
            if("angel-city".equals(design)){p.setShader(new RadialGradient(w*.66f,h*.12f,Math.max(w,h)*.48f,(accent&0xffffff)|0x0d000000,accent&0xffffff,Shader.TileMode.CLAMP));p.setAlpha(alpha);c.drawRect(0,0,w,h,p);p.setShader(null);}
        }p.setAlpha(alpha);
    }
}
