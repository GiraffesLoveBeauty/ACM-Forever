package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.Drawable;
import android.media.ExifInterface;
import java.io.*;

/** Device-only appearance. The selected file never enters an API request or backup. */
final class ProfileCover {
    private ProfileCover(){}
    static File file(Context c){String id=AppAppearance.prefs(c).getString("bg_image_id","");return LocalThemes.valid(id)?LocalThemes.image(c,id):new File(c.getFilesDir(),"profile-cover.jpg");}
    static void save(Context c,android.net.Uri uri)throws Exception{
        Bitmap bitmap=load(c,uri);try{save(c,bitmap);}finally{bitmap.recycle();}
    }
    static Bitmap load(Context c,android.net.Uri uri)throws Exception{
        byte[] bytes;
        try(InputStream in=c.getContentResolver().openInputStream(uri);ByteArrayOutputStream out=new ByteArrayOutputStream()){
            if(in==null)throw new IOException("无法读取图片");byte[] buffer=new byte[8192];int n;
            while((n=in.read(buffer))!=-1){if(out.size()+n>20*1024*1024)throw new IOException("请选择 20 MB 以内的图片");out.write(buffer,0,n);}bytes=out.toByteArray();
        }
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
        if(options.outWidth<=0||options.outHeight<=0)throw new IOException("无法识别图片");
        options.inJustDecodeBounds=false;options.inSampleSize=1;while((long)(options.outWidth/options.inSampleSize)*(options.outHeight/options.inSampleSize)>2_000_000)options.inSampleSize*=2;
        Bitmap bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);if(bitmap==null)throw new IOException("图片解码失败");
        try{
            int orientation=ExifInterface.ORIENTATION_NORMAL;try{orientation=new ExifInterface(new ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_NORMAL);}catch(IOException ignored){/* Some supported bitmap formats contain no EXIF. */}
            Matrix matrix=new Matrix();switch(orientation){case 2:matrix.setScale(-1,1);break;case 3:matrix.setRotate(180);break;case 4:matrix.setScale(1,-1);break;case 5:matrix.setRotate(90);matrix.postScale(-1,1);break;case 6:matrix.setRotate(90);break;case 7:matrix.setRotate(270);matrix.postScale(-1,1);break;case 8:matrix.setRotate(270);break;default:break;}
            if(!matrix.isIdentity()){Bitmap rotated=Bitmap.createBitmap(bitmap,0,0,bitmap.getWidth(),bitmap.getHeight(),matrix,true);if(rotated!=bitmap){bitmap.recycle();bitmap=rotated;}}
            return bitmap;
        }catch(Exception error){bitmap.recycle();throw error;}
    }
    static void save(Context c,Bitmap bitmap)throws Exception{
        File destination=file(c),temp=new File(destination.getParentFile(),destination.getName()+".tmp");
        try{
            try(FileOutputStream out=new FileOutputStream(temp)){if(!bitmap.compress(Bitmap.CompressFormat.JPEG,88,out))throw new IOException("图片保存失败");out.getFD().sync();}
            if(!temp.renameTo(destination))throw new IOException("无法替换本地背景");
            retained.clear();stamp=0;
        }finally{if(temp.exists())temp.delete();}
    }
    static void invalidate(){retained.clear();stamp=0;cachedPath="";}
    static boolean exists(Context c){return file(c).isFile();}
    private static java.lang.ref.WeakReference<Bitmap> retained=new java.lang.ref.WeakReference<>(null);
    private static long stamp;
    private static String cachedPath="";
    static void clear(Context c){file(c).delete();retained.clear();stamp=0;}
    static Drawable drawable(Context c){
        String mode=AppAppearance.prefs(c).getString("bg_mode","solid");Bitmap bitmap=null;
        if("image".equals(mode)){
            File file=file(c);long current=file.lastModified()+file.length();bitmap=retained.get();
            if(bitmap==null||current!=stamp||!file.getAbsolutePath().equals(cachedPath)){bitmap=BitmapFactory.decodeFile(file.getAbsolutePath());retained=new java.lang.ref.WeakReference<>(bitmap);stamp=current;cachedPath=file.getAbsolutePath();}
        }
        int step=Math.max(0,Math.min(5,AppAppearance.prefs(c).getInt("bg_transparency",2)));
        android.content.SharedPreferences p=AppAppearance.prefs(c);
        String design="solid".equals(mode)&&"theme".equals(p.getString("bg_source","custom"))&&"web".equals(p.getString("theme_source","acm"))?MobileStyle.DESIGN:"none";
        return new Cover(bitmap,mode,AppAppearance.backgroundColor(c),Math.round(255*(1-step/5f)),design,c.getResources().getDisplayMetrics().density);
    }
    static Drawable drawable(Context c,boolean ignored){return drawable(c);}
    private static final class Cover extends Drawable {
        private final Bitmap bitmap;private final String mode,design;private final int color,opacity,base=MobileStyle.BACKGROUND,ink=MobileStyle.TEXT,accent=MobileStyle.ACCENT;private final float density;
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);private int alpha=255;
        Cover(Bitmap bitmap,String mode,int color,int opacity,String design,float density){this.bitmap=bitmap;this.mode=mode;this.color=color;this.opacity=opacity;this.design=design;this.density=density;}
        @Override public void draw(Canvas canvas){
            Rect bounds=getBounds();float w=bounds.width(),h=bounds.height();if(w<=0||h<=0)return;
            int saved=canvas.save();canvas.translate(bounds.left,bounds.top);
            paint.setColor("image".equals(mode)?base:color);paint.setAlpha(alpha);canvas.drawRect(0,0,w,h,paint);
            ThemeBackdrop.draw(canvas,paint,design,w,h,density,ink,accent,alpha);
            if("gradient".equals(mode)){
                paint.setShader(new LinearGradient(0,0,0,h*.72f,color,Color.WHITE,Shader.TileMode.CLAMP));canvas.drawRect(0,0,w,h,paint);paint.setShader(null);
            }else if(bitmap!=null){
                float scale=Math.max(w/bitmap.getWidth(),h/bitmap.getHeight()),bw=bitmap.getWidth()*scale,bh=bitmap.getHeight()*scale;
                int clip=canvas.save();canvas.clipRect(0,0,w,h);paint.setAlpha(Math.round(opacity*alpha/255f));canvas.drawBitmap(bitmap,null,new RectF((w-bw)/2,(h-bh)/2,(w+bw)/2,(h+bh)/2),paint);paint.setAlpha(alpha);canvas.restoreToCount(clip);
            }
            canvas.restoreToCount(saved);
        }
        @Override public void setAlpha(int value){alpha=value;}
        @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}
        @Override public int getOpacity(){return PixelFormat.OPAQUE;}
    }
}
