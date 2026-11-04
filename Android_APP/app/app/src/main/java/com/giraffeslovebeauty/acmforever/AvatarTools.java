package com.giraffeslovebeauty.acmforever;

final class AvatarTools {
    static byte[] compress(byte[] input) throws Exception {
        android.graphics.BitmapFactory.Options opts=new android.graphics.BitmapFactory.Options();opts.inJustDecodeBounds=true;
        android.graphics.BitmapFactory.decodeByteArray(input,0,input.length,opts);
        if(opts.outWidth<=0||opts.outHeight<=0)throw new IllegalArgumentException("无法读取头像图片");
        opts.inSampleSize=1;while(Math.max(opts.outWidth,opts.outHeight)/opts.inSampleSize>1024)opts.inSampleSize*=2;
        opts.inJustDecodeBounds=false;
        android.graphics.Bitmap bitmap=android.graphics.BitmapFactory.decodeByteArray(input,0,input.length,opts);
        if(bitmap==null)throw new IllegalArgumentException("无法解码头像");
        try(java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream()){
            if(!bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG,85,output))throw new IllegalStateException("头像压缩失败");
            if(output.size()>2*1024*1024)throw new IllegalArgumentException("压缩后头像仍超过2 MB");return output.toByteArray();
        } finally {bitmap.recycle();}
    }
}
