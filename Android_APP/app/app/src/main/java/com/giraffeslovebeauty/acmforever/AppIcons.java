package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Redrawn 32-unit symbols with the user's catgirl silhouette as their shared signature. */
final class AppIcons {
    private static Bitmap silhouette;
    private AppIcons(){}
    static void on(android.widget.TextView view,String name,int color,int size){
        Drawable icon=get(view.getContext(),name,color);int px=MobileStyle.dp(view.getContext(),size);icon.setBounds(0,0,px,px);
        view.setCompoundDrawablesRelative(icon,null,null,null);view.setCompoundDrawablePadding(MobileStyle.dp(view.getContext(),7));
    }
    static Drawable get(Context context,String name,int color){return get(context,name,color,false);}
    static Drawable get(Context context,String name,int color,boolean accent){
        if(silhouette==null)silhouette=BitmapFactory.decodeResource(context.getResources(),R.drawable.catgirl_mask);
        if("avatar".equals(name))return new android.graphics.drawable.BitmapDrawable(context.getResources(),CharacterArt.bitmap(context,R.drawable.avatar_catgirl));
        return new Glyph(name,color,accent);
    }
    static void cat(Canvas canvas,Paint paint,float x,float y,float size){
        if(silhouette==null)return;
        ColorFilter old=paint.getColorFilter();boolean filtered=paint.isFilterBitmap();
        paint.setColorFilter(new PorterDuffColorFilter(paint.getColor(),PorterDuff.Mode.SRC_IN));paint.setFilterBitmap(true);
        float scale=size/Math.max(silhouette.getWidth(),silhouette.getHeight()),w=silhouette.getWidth()*scale,h=silhouette.getHeight()*scale;
        canvas.drawBitmap(silhouette,null,new RectF(x+(size-w)/2,y+(size-h)/2,x+(size+w)/2,y+(size+h)/2),paint);
        paint.setColorFilter(old);paint.setFilterBitmap(filtered);
    }
    private static final class Glyph extends Drawable {
        final String name;final boolean accent;final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
        Glyph(String name,int color,boolean accent){this.name=name;this.accent=accent;p.setColor(color);p.setStrokeWidth(2.8f);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);}
        private void line(Canvas c,float...xy){Path path=new Path();path.moveTo(xy[0],xy[1]);for(int i=2;i<xy.length;i+=2)path.lineTo(xy[i],xy[i+1]);c.drawPath(path,p);}
        private void kitty(Canvas canvas,float x,float y,float size){int previous=p.getColor();if(!"compose".equals(name)&&previous!=0xffaf2424&&previous!=0xff285b32)p.setColor(MobileStyle.CAT);AppIcons.cat(canvas,p,x,y,size);p.setColor(previous);}
        private void badge(Canvas c){kitty(c,20,0,11);}
        @Override public void draw(Canvas c){
            int save=c.save();c.translate(getBounds().left,getBounds().top);c.scale(getBounds().width()/32f,getBounds().height()/32f);p.setStyle(Paint.Style.STROKE);
            if(accent){Paint wash=new Paint(Paint.ANTI_ALIAS_FLAG);wash.setColor((MobileStyle.ACCENT&0x00ffffff)|0x24000000);c.drawRoundRect(1,1,31,31,9,9,wash);}
            switch(name){
                case "tools":line(c,16,8,16,30);line(c,5,19,27,19);badge(c);break;
                case "forum":c.drawRoundRect(2,3,30,25,7,7,p);line(c,8,25,6,30,15,25);kitty(c,7,4,19);break;
                case "rank":line(c,8,3,24,3,23,17,19,22,13,22,9,17,8,3);c.drawArc(2,5,12,17,90,180,false,p);c.drawArc(20,5,30,17,270,180,false,p);line(c,16,22,16,28);line(c,10,29,22,29);kitty(c,10,4,12);break;
                case "problems":case "templates":c.drawRoundRect(3,3,26,29,3,3,p);line(c,8,3,8,29);line(c,12,9,21,9);line(c,12,14,19,14);kitty(c,16,17,16);break;
                case "compose":case "mine":kitty(c,0,0,32);break;
                case "comment":c.drawRoundRect(2,6,30,26,8,8,p);line(c,9,26,7,31,16,26);kitty(c,8,3,16);line(c,11,21,22,21);break;
                case "bookmark":line(c,6,3,26,3,26,30,16,24,6,30,6,3);kitty(c,9,6,14);break;
                case "drafts":c.drawRoundRect(5,3,27,29,3,3,p);line(c,10,22,22,22);line(c,10,26,19,26);kitty(c,10,5,13);break;
                case "checkin":c.drawRoundRect(3,7,29,30,4,4,p);line(c,3,13,29,13);line(c,9,3,9,9);line(c,23,3,23,9);kitty(c,9,15,14);break;
                case "search":c.drawCircle(13,13,10,p);line(c,21,21,30,30);kitty(c,7,6,12);break;
                case "filter":line(c,2,8,30,8,20,19,20,28,13,31,13,19,2,8);kitty(c,11,0,10);break;
                case "eye":case "eye-off":c.drawOval(2,8,30,25,p);c.drawCircle(16,16.5f,4.3f,p);if("eye-off".equals(name))line(c,4,3,28,30);break;
                case "like":line(c,3,14,9,14,13,4,17,4,17,12,29,12,26,28,9,28,9,14);line(c,3,14,3,28,8,28);kitty(c,14,15,12);break;
                case "close":line(c,7,10,24,27);line(c,24,10,7,27);badge(c);break;
                case "back":line(c,28,19,4,19,12,11);line(c,4,19,12,27);badge(c);break;
                case "next":line(c,4,19,28,19,20,11);line(c,28,19,20,27);kitty(c,1,0,11);break;
                case "zoom-in":case "zoom-out":c.drawCircle(13,17,9,p);line(c,20,24,28,31);line(c,9,17,17,17);if("zoom-in".equals(name))line(c,13,13,13,21);badge(c);break;
                case "fit":line(c,3,12,3,29);line(c,29,12,29,29);line(c,5,21,27,21);line(c,5,21,10,16);line(c,5,21,10,26);line(c,27,21,22,16);line(c,27,21,22,26);kitty(c,10,0,12);break;
                case "settings":c.drawCircle(16,18,10,p);for(int i=0;i<6;i++){double a=i*Math.PI/3;line(c,16+(float)Math.cos(a)*10,18+(float)Math.sin(a)*10,16+(float)Math.cos(a)*13,18+(float)Math.sin(a)*13);}kitty(c,9,10,14);break;
                case "history":c.drawArc(4,7,30,31,205,315,false,p);line(c,3,7,3,16,11,16);line(c,17,14,17,21,23,24);badge(c);break;
                case "link":c.save();c.rotate(-35,16,19);c.drawRoundRect(2,15,19,23,4,4,p);c.drawRoundRect(13,15,30,23,4,4,p);c.restore();badge(c);break;
                case "copy":c.drawRoundRect(3,10,22,30,3,3,p);c.drawRoundRect(10,4,29,24,3,3,p);kitty(c,13,7,13);break;
                case "report":line(c,5,3,5,31);c.drawRoundRect(5,4,29,23,3,3,p);kitty(c,11,6,14);break;
                case "download":line(c,16,11,16,25,9,19);line(c,16,25,23,19);line(c,3,24,3,30,29,30,29,24);kitty(c,11,0,10);break;
                default:kitty(c,1,1,30);
            }
            c.restoreToCount(save);
        }
        @Override public void setAlpha(int alpha){p.setAlpha(alpha);}
        @Override public void setColorFilter(ColorFilter filter){p.setColorFilter(filter);}
        @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
}
