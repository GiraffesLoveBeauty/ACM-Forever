package com.giraffeslovebeauty.acmforever;
import android.app.Activity;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.webkit.*;
import android.widget.*;

/** Authenticated image bytes rendered locally, with pinch zoom and no JavaScript/network bridge. */
public final class ImagePreviewActivity extends Activity {
    private final java.util.concurrent.ExecutorService io=java.util.concurrent.Executors.newSingleThreadExecutor();private WebView viewer;private TextView status;private boolean dead;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);AppAppearance.load(this);AppAppearance.window(this);LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setPadding(12,12,12,12);root.setBackgroundColor(MobileStyle.PANEL);AppAppearance.content(this,root);
        Button back=new Button(this);back.setText("返回");MobileStyle.button(back,false);back.setOnClickListener(v->finish());root.addView(back);status=new TextView(this);status.setTextColor(MobileStyle.TEXT);status.setText("正在读取图片…");root.addView(status);
        viewer=new WebView(this);viewer.setBackgroundColor(MobileStyle.PANEL);viewer.setContentDescription("图片，支持双指缩放和拖动");viewer.getSettings().setJavaScriptEnabled(false);viewer.getSettings().setAllowFileAccess(false);viewer.getSettings().setAllowContentAccess(false);viewer.getSettings().setBuiltInZoomControls(true);viewer.getSettings().setDisplayZoomControls(false);viewer.getSettings().setUseWideViewPort(true);viewer.getSettings().setLoadWithOverviewMode(true);
        viewer.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return true;}@Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){return new WebResourceResponse("text/plain","UTF-8",new java.io.ByteArrayInputStream(new byte[0]));}});root.addView(viewer,new LinearLayout.LayoutParams(-1,0,1));
        String address=getIntent().getStringExtra("url");io.execute(()->{String html=null;Exception error=null;try{ApiClient.Media data=((AcmApplication)getApplication()).api().communityMedia(address);BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(data.bytes,0,data.bytes.length,bounds);if(bounds.outWidth<=0||bounds.outHeight<=0||(long)bounds.outWidth*bounds.outHeight>16000000L)throw new java.io.IOException("图片尺寸不支持");html="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\"><style>body{margin:0}img{width:100%;height:auto}</style></head><body><img alt='社区图片' src='data:"+data.mime+";base64,"+android.util.Base64.encodeToString(data.bytes,android.util.Base64.NO_WRAP)+"'></body></html>";}catch(Exception e){error=e;}String image=html;Exception failure=error;runOnUiThread(()->{if(dead)return;if(failure!=null){status.setText(FailureState.title(failure));status.setTextColor(ErrorModule.ink());ErrorModule.style(status);}else{status.setText("双指缩放 · 拖动查看");viewer.loadDataWithBaseURL(null,image,"text/html","UTF-8",null);}});});
    }
    @Override protected void onDestroy(){dead=true;io.shutdownNow();if(viewer!=null){viewer.stopLoading();if(viewer.getParent() instanceof android.view.ViewGroup)((android.view.ViewGroup)viewer.getParent()).removeView(viewer);viewer.destroy();}super.onDestroy();}
}
