package com.giraffeslovebeauty.acmforever;

import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Native rendering of the repository's GraphArt.vue twelve-node graph and s-v-d-t route. */
final class WebGraphArtwork extends Drawable {
    private static final float[][] POINTS={{50,151},{114,83},{177,47},{248,63},{323,96},{348,174},{198,130},{256,167},{285,232},{155,215},{84,227},{312,32}};
    private static final int[][] EDGES={{0,1},{0,6},{0,10},{1,2},{1,6},{2,3},{2,11},{3,4},{3,6},{4,5},{4,11},{6,7},{6,9},{7,5},{7,8},{9,8},{9,10},{10,8},{8,5},{3,7},{11,5}};
    private static final String[] NAMES={"s","u","a","b","c","t","v","d","e","f","g","h"};
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private int alpha=255;
    @Override public void draw(Canvas canvas){
        Rect bounds=getBounds();int saved=canvas.save();float scale=Math.min(bounds.width()/400f,bounds.height()/300f);canvas.translate(bounds.left+(bounds.width()-400*scale)/2,bounds.top+(bounds.height()-300*scale)/2);canvas.scale(scale,scale);
        int backdrop=ThemePalette.mix(AppAppearance.palette().primary,0xff101820,.75);paint.setStyle(Paint.Style.FILL);paint.setColor(backdrop);paint.setAlpha(alpha);canvas.drawRoundRect(7,5,393,295,40,40,paint);
        paint.setColor(ThemePalette.mix(backdrop,MobileStyle.ACCENT,.18));canvas.drawCircle(95,80,70,paint);canvas.drawRoundRect(270,182,378,278,18,18,paint);
        paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeWidth(2);paint.setColor(ThemePalette.mix(backdrop,MobileStyle.ACCENT,.42));
        for(int[] edge:EDGES){float[] a=POINTS[edge[0]],b=POINTS[edge[1]];canvas.drawLine(a[0],a[1],b[0],b[1],paint);}
        paint.setColor(MobileStyle.ACCENT);paint.setStrokeWidth(7);int[] route={0,6,7,5};for(int i=1;i<route.length;i++){float[] a=POINTS[route[i-1]],b=POINTS[route[i]];canvas.drawLine(a[0],a[1],b[0],b[1],paint);}
        int label=ThemePalette.readable(new int[]{backdrop},0xffeef3df,4.5);paint.setTypeface(Typeface.create("monospace",Typeface.BOLD));paint.setTextSize(20);paint.setTextAlign(Paint.Align.CENTER);
        for(int i=0;i<POINTS.length;i++){float[] p=POINTS[i];boolean active=i==0||i==6||i==7||i==5;paint.setColor(active?MobileStyle.ACCENT:label);canvas.drawCircle(p[0],p[1],active?11:6,paint);paint.setColor(label);canvas.drawText(NAMES[i],p[0],p[1]-16,paint);}
        paint.setTextSize(18);paint.setTextAlign(Paint.Align.LEFT);canvas.drawText("dist[t] = 9;",145,280,paint);canvas.restoreToCount(saved);
    }
    @Override public void setAlpha(int value){alpha=value;invalidateSelf();}
    @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
}
