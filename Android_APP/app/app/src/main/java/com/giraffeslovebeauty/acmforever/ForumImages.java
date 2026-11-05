package com.giraffeslovebeauty.acmforever;

import android.graphics.*;
import java.io.*;

/** Match the Web uploader: 20 MB input, max 2560 pixels, WebP at most 5 MB. */
final class ForumImages {
    private ForumImages(){}
    @SuppressWarnings("deprecation")
    static byte[] compress(byte[] input)throws Exception{
        if(input.length==0||input.length>20*1024*1024)throw new IllegalArgumentException("原图不能超过 20 MB");
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(input,0,input.length,options);
        if(options.outWidth<=0||options.outHeight<=0||!("image/png".equals(options.outMimeType)||"image/jpeg".equals(options.outMimeType)||"image/webp".equals(options.outMimeType)))throw new IllegalArgumentException("请选择可读取的 PNG、JPEG 或 WebP 图片");
        options.inSampleSize=1;while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>4096)options.inSampleSize*=2;options.inJustDecodeBounds=false;
        Bitmap source=BitmapFactory.decodeByteArray(input,0,input.length,options);if(source==null)throw new IllegalArgumentException("图片无法解码");Bitmap oriented=source,scaled=source;
        try{Matrix rotation=new Matrix();int orientation=1;try{orientation=new android.media.ExifInterface(new ByteArrayInputStream(input)).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,1);}catch(IOException ignored){}
            switch(orientation){case 2:rotation.setScale(-1,1);break;case 3:rotation.setRotate(180);break;case 4:rotation.setScale(1,-1);break;case 5:rotation.setRotate(90);rotation.postScale(-1,1);break;case 6:rotation.setRotate(90);break;case 7:rotation.setRotate(-90);rotation.postScale(-1,1);break;case 8:rotation.setRotate(-90);break;default:break;}
            if(!rotation.isIdentity())oriented=Bitmap.createBitmap(source,0,0,source.getWidth(),source.getHeight(),rotation,true);scaled=oriented;
            float ratio=Math.min(1,2560f/Math.max(oriented.getWidth(),oriented.getHeight()));if(ratio<1)scaled=Bitmap.createScaledBitmap(oriented,Math.max(1,Math.round(oriented.getWidth()*ratio)),Math.max(1,Math.round(oriented.getHeight()*ratio)),true);
            ByteArrayOutputStream output=new ByteArrayOutputStream();if(!scaled.compress(Bitmap.CompressFormat.WEBP,90,output)||output.size()>5*1024*1024)throw new IllegalArgumentException("图片压缩失败，请选择较小图片");return output.toByteArray();
        }finally{if(scaled!=source&&scaled!=oriented)scaled.recycle();if(oriented!=source)oriented.recycle();source.recycle();}
    }
    static String markdown(String url){if(url==null||!url.matches("/api/forum/images/[a-f0-9]{32}"))throw new IllegalArgumentException("服务器没有返回有效图片地址");return "\n![图片]("+url+")\n";}
}
