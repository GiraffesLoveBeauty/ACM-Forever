package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.pdf.PdfDocument;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Test APK only: synthetic transport exercises the real native reader without a production account. */
public final class ReaderSmoke extends Instrumentation {
    private byte[] pdf;
    private String mode;
    private Activity activity;
    private boolean loginMode;
    private boolean designMode;
    private boolean appearanceMode;
    private boolean webMode;
    private boolean communityMode;
    private boolean settingsMode;
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);mode=arguments==null?"":arguments.getString("mode","");settingsMode=arguments!=null&&"settings".equals(arguments.getString("mode"));communityMode=arguments!=null&&"community".equals(arguments.getString("mode"));loginMode=arguments!=null&&"login".equals(arguments.getString("mode"));designMode=arguments!=null&&"design".equals(arguments.getString("mode"));appearanceMode=arguments!=null&&"appearance".equals(arguments.getString("mode"));webMode=arguments!=null&&"web".equals(arguments.getString("mode"));start();}
    @Override public void onStart(){
        if(mode.startsWith("modules-")){OptionalModulesUiSmoke.run(this,mode);return;}
        if("seed024".equals(mode)||"verify024".equals(mode)){UpgradePersistenceUiSmoke.run(this,"seed024".equals(mode));return;}
        if("recoverysettings".equals(mode)){RecoverySettingsUiSmoke.run(this);return;}
        if("creditslogin".equals(mode)){CreditsLoginUiSmoke.run(this);return;}
        if("wikinavigation".equals(mode)){WikiNavigationUiSmoke.run(this);return;}
        if("problemtags".equals(mode)){ProblemTagsUiSmoke.run(this);return;}
        if("accountclosure".equals(mode)){AccountClosureUiSmoke.run(this);return;}
        if("ojbindings".equals(mode)){OjBindingsUiSmoke.run(this);return;}
        if("themetransfer".equals(mode)){ThemeTransferUiSmoke.run(this);return;}
        if(mode.startsWith("officiallayout-")){ThemeTransferUiSmoke.runLayout(this,mode.substring("officiallayout-".length()));return;}
        if("globalsearchadmin".equals(mode)){GlobalSearchAdminUiSmoke.run(this);return;}
        if("startupupdates".equals(mode)){StartupUpdatesUiSmoke.run(this);return;}
        if("lifecycle".equals(mode)){LifecycleNetworkUiSmoke.run(this);return;}
        if("imports".equals(mode)){MarkdownImportUiSmoke.run(this);return;}
        if("drafts".equals(mode)){DraftSwitchUiSmoke.run(this);return;}
        if("polish".equals(mode)){PolishUiSmoke.run(this);return;}
        if("navigation".equals(mode)){NavigationUiSmoke.run(this);return;}
        if("localthemes".equals(mode)){LocalThemeUiSmoke.run(this);return;}
        if("spacefeatures".equals(mode)){SpaceFeaturesUiSmoke.run(this);return;}
        if(settingsMode){LocalSettingsUiSmoke.run(this);return;}
        if(communityMode){CommunityUiSmoke.run(this);return;}
        if(loginMode){LoginUiSmoke.run(this);return;}
        if(designMode){DesignUiSmoke.run(this);return;}
        if(appearanceMode){AppearanceUiSmoke.run(this);return;}
        if(webMode){WebFeaturesUiSmoke.run(this);return;}
        Bundle result=new Bundle();AcmApplication app=(AcmApplication)getTargetContext().getApplicationContext();
        ApiClient api=app.api();String original=api.getBaseUrl();int outcome=Activity.RESULT_CANCELED;
        android.content.SharedPreferences settings=getTargetContext().getSharedPreferences("acmforever_settings",0);boolean configured=settings.contains("api_base_url");String configuredBase=settings.getString("api_base_url","");
        try {
            PdfDocument document=new PdfDocument();Paint paint=new Paint();paint.setColor(Color.BLACK);paint.setTextSize(24);
            for(int index=1;index<=2;index++){
                PdfDocument.Page page=document.startPage(new PdfDocument.PageInfo.Builder(595,842,index).create());
                page.getCanvas().drawText("ACMforever PDF reader verification - page "+index,36,80,paint);document.finishPage(page);
            }
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();document.writeTo(bytes);document.close();pdf=bytes.toByteArray();
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
                @Override protected URLConnection openConnection(URL url) throws IOException {
                    if(!"reader.test.invalid".equals(url.getHost()))throw new IOException("Test transport forbids external traffic");
                    return new TestConnection(url);
                }
            }:null);
            settings.edit().putString("api_base_url","https://reader.test.invalid").apply();api.setBaseUrl("https://reader.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Password!");
            Intent intent=new Intent().setClassName(getTargetContext(),PdfActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK)
                    .putExtra("platform","luogu").putExtra("problem_id","P1000");
            activity=startActivitySync(intent);await("第1 / 2页 · 100%");
            click("下一页");await("第2 / 2页 · 100%");clickDescription("放大");await("第2 / 2页 · 125%");clickDescription("适应宽度");await("第2 / 2页 · 100%");
            testCachedDocument(api,intent);
            Bitmap screenshot=getUiAutomation().takeScreenshot();
            if(screenshot!=null){try(FileOutputStream out=new FileOutputStream(new File(getTargetContext().getExternalFilesDir(null),"pdf-reader-smoke.png"))){screenshot.compress(Bitmap.CompressFormat.PNG,100,out);}finally{screenshot.recycle();}}
            result.putString("stream","PASS: authenticated PDF load, next page, zoom 125%, fit width, reopen PDF from cache while offline.\n");
            result.putBoolean("passed",true);outcome=Activity.RESULT_OK;
        } catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));result.putBoolean("passed",false);}
        finally {try{api.logout();}catch(Exception ignored){}if(configured)settings.edit().putString("api_base_url",configuredBase).apply();else settings.edit().remove("api_base_url").apply();api.setBaseUrl(original);if(activity!=null)runOnMainSync(()->activity.finish());}
        finish(outcome,result);
    }
    private void testCachedDocument(ApiClient api,Intent intent)throws Exception{runOnMainSync(()->activity.finish());waitForIdleSync();api.setNetworkAvailable(()->false);activity=startActivitySync(intent);await("第1 / 2页 · 100%");click("下一页");await("第2 / 2页 · 100%");}
    private void await(String text) throws Exception {
        long until=System.currentTimeMillis()+15000;
        while(System.currentTimeMillis()<until){final boolean[] found={false};runOnMainSync(()->found[0]=find(activity.getWindow().getDecorView(),text)!=null);if(found[0])return;Thread.sleep(80);}
        throw new AssertionError("Reader did not display: "+text);
    }
    private void click(String title){runOnMainSync(()->{View view=find(activity.getWindow().getDecorView(),title);if(view==null||!view.isEnabled())throw new AssertionError("Unavailable control: "+title);view.performClick();});}
    private View description(View view,String text){if(text.contentEquals(view.getContentDescription()==null?"":view.getContentDescription()))return view;if(view instanceof ViewGroup){ViewGroup g=(ViewGroup)view;for(int i=0;i<g.getChildCount();i++){View found=description(g.getChildAt(i),text);if(found!=null)return found;}}return null;}
    private void clickDescription(String title){runOnMainSync(()->{View view=description(activity.getWindow().getDecorView(),title);if(view==null||!view.isEnabled())throw new AssertionError("Unavailable control: "+title);view.performClick();});}
    private View find(View view,String text){if(view instanceof TextView&&((TextView)view).getText().toString().contains(text))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=find(group.getChildAt(i),text);if(found!=null)return found;}}return null;}
    private final class TestConnection extends HttpURLConnection {
        TestConnection(URL url){super(url);}
        @Override public void connect(){} @Override public void disconnect(){} @Override public boolean usingProxy(){return false;}
        @Override public int getResponseCode(){return 200;}
        @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=reader-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public InputStream getInputStream(){return new ByteArrayInputStream(url.getPath().endsWith("statement.pdf")?pdf:(url.getPath().endsWith("/me")?"{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}":"{}").getBytes(StandardCharsets.UTF_8));}
    }
}
