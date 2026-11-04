package com.giraffeslovebeauty.acmforever;

import android.content.*;
import android.graphics.*;
import android.widget.*;
import java.util.concurrent.*;

/** Real Web cover/thumbnail endpoint; no stand-in image on failure. */
final class CommunityCover extends LinearLayout {
    private static final ExecutorService IO=Executors.newFixedThreadPool(2);
    private final ApiClient api;private final String address;private final boolean thumbnail;
    private final ImageView image;private final TextView state;private Bitmap bitmap;private Future<?> pending;private long lastOpen;
    CommunityCover(Context context,String source,boolean thumbnail){
        super(context);this.thumbnail=thumbnail;api=((AcmApplication)context.getApplicationContext()).api();address=api.communityImageUrl(source);setOrientation(VERTICAL);
        image=new ImageView(context);image.setScaleType(thumbnail?ImageView.ScaleType.CENTER_CROP:ImageView.ScaleType.FIT_CENTER);image.setContentDescription("放大查看话题封面");addView(image,new LayoutParams(-1,MobileStyle.dp(context,thumbnail?150:210)));
        state=new TextView(context);state.setText("正在加载封面…");state.setTextColor(MobileStyle.MUTED);addView(state);setPadding(0,MobileStyle.dp(context,8),0,MobileStyle.dp(context,8));
        image.setOnClickListener(v->{long now=android.os.SystemClock.elapsedRealtime();if(bitmap==null||now-lastOpen<700)return;lastOpen=now;context.startActivity(new Intent(context,ImagePreviewActivity.class).putExtra("url",address));});
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();if(address.isEmpty()){setVisibility(GONE);return;}long owner=api.sessionGeneration();
        pending=IO.submit(()->{Bitmap decoded=null;Exception failure=null;try{ApiClient.Media media=api.communityMedia(address+(thumbnail?"?variant=thumb":""));BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(media.bytes,0,media.bytes.length,options);if(options.outWidth<=0||options.outHeight<=0||(long)options.outWidth*options.outHeight>16000000L)throw new java.io.IOException("图片尺寸不支持");options.inJustDecodeBounds=false;options.inSampleSize=1;while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>1024)options.inSampleSize*=2;decoded=BitmapFactory.decodeByteArray(media.bytes,0,media.bytes.length,options);if(decoded==null)throw new java.io.IOException("图片无法解码");}catch(Exception e){failure=e;}Bitmap result=decoded;Exception error=failure;
            post(()->{if(!isAttachedToWindow()||owner!=api.sessionGeneration()){if(result!=null)result.recycle();return;}if(error!=null){image.setVisibility(GONE);state.setText("封面暂时无法显示 · "+FailureState.title(error));state.setTextColor(0xffaf2424);}else{bitmap=result;image.setImageBitmap(result);state.setVisibility(GONE);}});
        });
    }
    @Override protected void onDetachedFromWindow(){if(pending!=null)pending.cancel(true);image.setImageDrawable(null);if(bitmap!=null){bitmap.recycle();bitmap=null;}super.onDetachedFromWindow();}
}
