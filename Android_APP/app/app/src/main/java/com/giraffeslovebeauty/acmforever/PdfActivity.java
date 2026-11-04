package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.pdf.PdfRenderer;
import android.os.ParcelFileDescriptor;
import android.widget.*;
import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Authenticated PDF stays in app cache. PdfRenderer is available on all supported Android versions. */
public final class PdfActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final ExecutorService downloads=Executors.newSingleThreadExecutor();
    private PageRefresh refresh;
    private volatile boolean hasDocument;
    private PdfRenderer renderer;
    private ParcelFileDescriptor descriptor;
    private File file;
    private ImageView image;
    private TextView status;
    private LinearLayout controls;
    private Button previous,next,zoomOut,zoomIn,fit,retry;
    private HorizontalScrollView horizontal;
    private volatile boolean dead;
    private boolean busy;
    private boolean downloading;
    private Runnable request;
    private CodingCatView loadingCat;
    private int page;
    private float zoom=1;
    private long generation;
    private ApiClient api;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();generation=api.sessionGeneration();
        if(state!=null){page=state.getInt("page");zoom=state.getFloat("zoom",1);}
        LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setFitsSystemWindows(true);root.setPadding(dp(12),dp(12),dp(12),dp(8));root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        Button back=new Button(this);back.setText("← 返回题目");MobileStyle.button(back,false);back.setOnClickListener(v->finish());root.addView(back);
        refresh=new PageRefresh(this,root,1);refresh.reset(1);
        status=new TextView(this);status.setTextColor(MobileStyle.TEXT);status.setPadding(dp(12),dp(12),dp(12),dp(12));status.setText("正在读取已采集 PDF…");root.addView(status);
        loadingCat=new CodingCatView(this);LinearLayout.LayoutParams loadingSize=new LinearLayout.LayoutParams(dp(180),dp(120));loadingSize.gravity=android.view.Gravity.CENTER_HORIZONTAL;root.addView(loadingCat,loadingSize);
        controls=new SpacedLayout(this);controls.setOrientation(LinearLayout.HORIZONTAL);root.addView(controls);
        previous=button("上一页",()->{page--;render();});next=button("下一页",()->{page++;render();});
        zoomOut=button("−",()->{zoom=Math.max(.5f,zoom-.25f);render();});zoomIn=button("＋",()->{zoom=Math.min(3,zoom+.25f);render();});
        fit=button("适应宽度",()->{zoom=1;render();});
        retry=new Button(this);retry.setText("重新读取 PDF");MobileStyle.button(retry,true);retry.setVisibility(android.view.View.GONE);retry.setOnClickListener(v->{if(request!=null)request.run();});root.addView(retry);
        ScrollView vertical=new ScrollView(this);root.addView(vertical,new LinearLayout.LayoutParams(-1,0,1));
        horizontal=new HorizontalScrollView(this);vertical.addView(horizontal);image=new ImageView(this);image.setContentDescription("PDF 当前页题面");horizontal.addView(image);setBusy(true);
        String platform=getIntent().getStringExtra("platform"),id=getIntent().getStringExtra("problem_id");
        if(platform==null||id==null||!api.isLoggedIn()){fail(new IllegalStateException("未登录或缺少题目信息，请返回题库重新打开。"));return;}
        PdfFiles cache=((AcmApplication)getApplication()).pdfFiles();String cacheKey=api.getBaseUrl()+"/"+api.accountKey()+"/"+generation+"/"+platform+"/"+id;
        request=()->{if(dead||downloading||generation!=api.sessionGeneration())return;downloading=true;retry.setEnabled(false);refresh.start(1);try{downloads.execute(()->download(platform,id,cacheKey,cache));}catch(java.util.concurrent.RejectedExecutionException ignored){downloading=false;}};
        refresh.register(1,request);
        worker.execute(()->{
            try{file=File.createTempFile("acm-statement-",".pdf",getCacheDir());if(cache.copyTo(cacheKey,file)){openDocument();runOnUiThread(()->{if(!dead){refresh.cached(1);render();}});}}
            catch(Exception ignored){/* A corrupt or evicted cache falls back to the authenticated request. */}
            runOnUiThread(()->{if(!dead)request.run();});
        });
    }
    private void download(String platform,String id,String cacheKey,PdfFiles cache){
        File updated=null;boolean transferred=false;
        try{
            updated=File.createTempFile("acm-statement-",".pdf",getCacheDir());api.downloadPdf(platform,id,updated);
            if(dead||generation!=api.sessionGeneration())return;
            cache.save(cacheKey,updated);File fresh=updated;
            worker.execute(()->{
                try{
                    if(dead||generation!=api.sessionGeneration()){fresh.delete();return;}
                    closeDocument();if(file!=null)file.delete();file=fresh;openDocument();
                    runOnUiThread(()->{if(!dead){downloading=false;retry.setEnabled(true);refresh.finish(1);status.setTextColor(MobileStyle.TEXT);status.setBackgroundColor(android.graphics.Color.TRANSPARENT);status.setMinHeight(0);retry.setVisibility(android.view.View.GONE);render();}});
                }catch(Exception e){runOnUiThread(()->{downloading=false;retry.setEnabled(true);fail(e);refresh.finish(1);});}
            });transferred=true;
        }catch(Exception e){runOnUiThread(()->{if(dead)return;downloading=false;retry.setEnabled(true);boolean retain=refresh.failure(FailureState.title(e));if(!hasDocument||!retain){image.setImageDrawable(null);fail(e);}refresh.finish(1);});}
        finally{if(!transferred&&updated!=null)updated.delete();}
    }
    private void openDocument() throws Exception {
        descriptor=ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY);
        try{renderer=new PdfRenderer(descriptor);}catch(Exception e){descriptor.close();descriptor=null;throw e;}
        hasDocument=true;page=Math.max(0,Math.min(page,renderer.getPageCount()-1));
    }
    private void closeDocument(){hasDocument=false;if(renderer!=null){renderer.close();renderer=null;}if(descriptor!=null){try{descriptor.close();}catch(Exception ignored){}descriptor=null;}}
    private int dp(float value){return MobileStyle.dp(this,value);}
    private Button button(String title,Runnable action){Button b=new Button(this);b.setText(title);MobileStyle.button(b,false);b.setTextSize(11);b.setMinWidth(0);b.setPadding(2,2,2,2);controls.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));b.setOnClickListener(v->{if(!busy&&!dead)action.run();});return b;}
    private void setBusy(boolean value){busy=value;previous.setEnabled(!value&&page>0);next.setEnabled(!value&&renderer!=null&&page+1<renderer.getPageCount());zoomOut.setEnabled(!value&&zoom>.5f);zoomIn.setEnabled(!value&&zoom<3);fit.setEnabled(!value);}
    private void render(){
        if(dead||renderer==null)return;
        if(generation!=api.sessionGeneration()){image.setImageDrawable(null);status.setText("登录账号已变化，请返回题库重新打开。");setBusy(true);return;}
        setBusy(true);int current=page;float scale=zoom;int width=Math.max(240,horizontal.getWidth()>0?horizontal.getWidth():getResources().getDisplayMetrics().widthPixels-32);
        status.setText("正在绘制第"+(page+1)+"页…");
        worker.execute(()->{try(PdfRenderer.Page pdf=renderer.openPage(current)){
            float factor=width*scale/pdf.getWidth();
            double pixels=pdf.getWidth()*factor*(double)pdf.getHeight()*factor;
            if(pixels>12_000_000)factor*=(float)Math.sqrt(12_000_000/pixels);
            Bitmap bitmap=Bitmap.createBitmap(Math.max(1,Math.round(pdf.getWidth()*factor)),Math.max(1,Math.round(pdf.getHeight()*factor)),Bitmap.Config.ARGB_8888);
            bitmap.eraseColor(Color.WHITE);Matrix matrix=new Matrix();matrix.setScale(factor,factor);pdf.render(bitmap,null,matrix,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
            runOnUiThread(()->{if(dead||generation!=api.sessionGeneration()){bitmap.recycle();return;}loadingCat.setVisibility(android.view.View.GONE);image.setImageBitmap(bitmap);image.setLayoutParams(new android.widget.FrameLayout.LayoutParams(bitmap.getWidth(),bitmap.getHeight()));status.setText("第"+(current+1)+" / "+renderer.getPageCount()+"页 · "+Math.round(scale*100)+"%");setBusy(false);});
        }catch(Exception|OutOfMemoryError e){runOnUiThread(()->fail(e));}});
    }
    private void fail(Throwable e){if(dead)return;loadingCat.setVisibility(android.view.View.GONE);status.setText(e instanceof Exception?FailureState.title(e)+"\n"+String.valueOf(e.getMessage()):"PDF 页面过大，无法分配内存");status.setTextColor(ErrorModule.ink());ErrorModule.style(status);status.setMinHeight(Math.round(120*getResources().getDisplayMetrics().density));retry.setVisibility(android.view.View.VISIBLE);setBusy(renderer==null);}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putInt("page",page);state.putFloat("zoom",zoom);}
    @Override protected void onDestroy(){dead=true;refresh.close();downloads.shutdownNow();image.setImageDrawable(null);worker.execute(()->{try{if(renderer!=null)renderer.close();if(descriptor!=null)descriptor.close();}catch(Exception ignored){}finally{if(file!=null)file.delete();}});worker.shutdown();super.onDestroy();}
}
