package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Verifies real local storage isolation and the theme editing/preview navigation. */
final class LocalThemeUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;private String id;
    private LocalThemeUiSmoke(Instrumentation t){test=t;app=t.getTargetContext();}
    static void run(Instrumentation t){new LocalThemeUiSmoke(t).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;SharedPreferences prefs=AppAppearance.prefs(app),registry=app.getSharedPreferences("local_theme_library",0);
        Map<String,?> before=new HashMap<>(prefs.getAll()),library=new HashMap<>(registry.getAll());File cover=new File(app.getFilesDir(),"profile-cover.jpg");byte[] previous=read(cover);
        try{
            registry.edit().clear().apply();prefs.edit().clear().putString("theme_source","acm").putInt("theme_primary",0xff83b8e5).putString("bg_mode","image").putString("bg_source","custom").putInt("bg_color",0xffffffff).putString("saved_password","test-secret-must-not-copy").putString("api_base_url","https://themes.test.invalid").apply();
            Bitmap image=Bitmap.createBitmap(80,80,Bitmap.Config.ARGB_8888);image.eraseColor(Color.RED);ProfileCover.save(app,image);image.recycle();id=LocalThemes.save(app);
            check("未命名1".equals(LocalThemes.name(app,id)),"incrementing default theme name");SharedPreferences stored=LocalThemes.prefs(app,id);
            check(!stored.contains("saved_password")&&!stored.contains("api_base_url"),"snapshot excludes credentials and endpoint");check(LocalThemes.image(app,id).isFile(),"snapshot owns its image");
            byte[] snapshot=read(LocalThemes.image(app,id));image=Bitmap.createBitmap(80,80,Bitmap.Config.ARGB_8888);image.eraseColor(Color.BLUE);ProfileCover.save(app,image);image.recycle();check(Arrays.equals(snapshot,read(LocalThemes.image(app,id))),"changing global image preserves saved theme");
            open(OptionalTestClasses.type("AdvancedAppearanceActivity"),null);await(()->find("一键保存")!=null,"four-button menu");test.waitForIdleSync();
            main(()->{View save=find("一键保存"),mine=find("我的主题"),background=find("背景选择"),theme=find("主题选择");check(save.getHeight()==mine.getHeight()&&Math.abs(save.getWidth()-mine.getWidth())<=1,"bottom actions same size");check(save.getTop()==mine.getTop(),"bottom actions share a row");check(background.getWidth()==theme.getWidth()&&theme.getTop()>=background.getBottom(),"background and theme use full separate rows");});shot("theme-menu-v0210.png");
            click("我的主题");await(()->description("设置主题 未命名1")!=null,"saved theme tile");main(()->{View thumb=description("主题缩略图 未命名1");check(thumb!=null&&thumb.getClipToOutline(),"saved thumbnail clips rounded corners");android.graphics.Outline outline=new android.graphics.Outline();thumb.getOutlineProvider().getOutline(thumb,outline);check(outline.getRadius()>0,"thumbnail has rounded geometry");});
            Instrumentation.ActivityMonitor monitor=test.addMonitor(OptionalTestClasses.type("AdvancedAppearanceActivity").getName(),null,false);clickDescription("设置主题 未命名1");Activity editor=test.waitForMonitorWithTimeout(monitor,5000);test.removeMonitor(monitor);check(editor!=null,"settings opens independent editor");activity=editor;
            test.waitForIdleSync();main(()->{String[] labels={"背景选择","主题选择","预览","重命名"};View previousAction=null;for(String label:labels){View v=find(label);check(v!=null,"saved theme action exists");if(previousAction!=null)check(v.getWidth()==previousAction.getWidth()&&v.getHeight()==previousAction.getHeight()&&v.getTop()>=previousAction.getBottom(),"editor actions are four equal rows");previousAction=v;}});
            click("主题选择");clickDescription("薄荷");check(stored.getInt("theme_primary",0)==0xff82c7aa,"editor auto-saves its theme");check(prefs.getInt("theme_primary",0)==0xff83b8e5,"editor does not apply to app");main(()->activity.onBackPressed());
            click("主题选择");clickDescription("ACMForever辅色：暖杏");check(stored.getInt("theme_secondary",0)==0xffe9c786,"editor auto-saves secondary");check(prefs.getInt("theme_secondary",0xffffffff)==0xffffffff,"saved editor leaves global secondary unchanged");main(()->activity.onBackPressed());
            click("重命名");await(()->find("确认")!=null,"rename dialog");main(()->{EditText name=(EditText)description("主题名称");check("未命名1".contentEquals(name.getText()),"rename prefilled");name.setText("薄荷主题");});click("确认");check("薄荷主题".equals(LocalThemes.name(app,id)),"rename persisted");
            monitor=test.addMonitor(OptionalTestClasses.type("ThemePreviewActivity").getName(),null,false);click("预览");Activity preview=test.waitForMonitorWithTimeout(monitor,5000);test.removeMonitor(monitor);check(preview!=null,"preview opens");activity=preview;await(()->description("退出主题预览")!=null,"preview close control");shot("theme-preview-v029.png");
            main(()->{check(find("社区话题")!=null&&find("一起交流，一起 AC")!=null,"preview retains page headings");check(description("网页同款最短路径图谱") instanceof GraphArtView,"preview shares real interactive graph");check(walk(decor(),v->v instanceof TextView&&"ACMForever".contentEquals(((TextView)v).getText()))!=null,"preview uses explicit placeholders");android.graphics.drawable.GradientDrawable red=(android.graphics.drawable.GradientDrawable)description("退出主题预览").getBackground();check(red.getColor().getDefaultColor()==0x80ff0000,"half-transparent red return avatar");});clickDescription("退出主题预览");activity=editor;main(()->activity.finish());
            LocalThemes.apply(app,id);check(prefs.getInt("theme_primary",0)==0xff82c7aa,"app changes only when theme applied");check(Arrays.equals(snapshot,read(cover)),"app receives saved background");check(!prefs.contains("bg_image_id"),"global background detached from saved theme");
            check(prefs.getInt("theme_secondary",0)==0xffe9c786&&MobileStyle.PANEL==0xffe9c786,"secondary applies with saved theme");
            Context scoped=LocalThemes.scope(app,id);Bitmap green=Bitmap.createBitmap(40,40,Bitmap.Config.ARGB_8888);green.eraseColor(Color.GREEN);ProfileCover.save(scoped,green);green.recycle();check(Arrays.equals(snapshot,read(cover)),"editing saved image does not mutate applied background");
            main(()->{try{prefs.edit().putString("theme_source","web").putString("theme_preset","minecraft").putBoolean("theme_dark",false).putString("bg_mode","solid").putString("bg_source","theme").apply();AppAppearance.load(app);Bitmap canvas=Bitmap.createBitmap(288,288,Bitmap.Config.ARGB_8888);android.graphics.drawable.Drawable bg=ProfileCover.drawable(app);bg.setBounds(0,0,288,288);bg.draw(new Canvas(canvas));check(canvas.getPixel(1,1)!=MobileStyle.BACKGROUND,"minecraft uses web dirt texture");canvas.recycle();}catch(Exception e){throw new AssertionError(e);}});
            result.putString("stream","PASS: four menu actions, independent saved images, no credential snapshots, isolated autosave, default names/rename, preview/return, explicit application and web dirt background.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable e){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));try{shot("theme-failure-v029.png");}catch(Exception ignored){}}
        finally{
            if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});if(id!=null){LocalThemes.image(app,id).delete();LocalThemes.prefs(app,id).edit().clear().apply();}
            restore(prefs,before);restore(registry,library);try{if(previous==null)cover.delete();else try(FileOutputStream out=new FileOutputStream(cover)){out.write(previous);}}catch(IOException ignored){}AppAppearance.load(app);
        }test.finish(outcome,result);
    }
    private byte[] read(File f){if(!f.isFile())return null;try{return java.nio.file.Files.readAllBytes(f.toPath());}catch(IOException e){throw new AssertionError(e);}}
    private void restore(SharedPreferences p,Map<String,?> data){SharedPreferences.Editor e=p.edit().clear();for(Map.Entry<String,?> entry:data.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)e.putString(k,(String)v);else if(v instanceof Integer)e.putInt(k,(Integer)v);else if(v instanceof Long)e.putLong(k,(Long)v);else if(v instanceof Boolean)e.putBoolean(k,(Boolean)v);else if(v instanceof Float)e.putFloat(k,(Float)v);}e.apply();}
    private void open(Class<?> cls,String kind){if(activity!=null)main(()->activity.finish());Intent intent=new Intent().setClassName(app,cls.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);if(kind!=null)intent.putExtra("kind",kind);activity=test.startActivitySync(intent);}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog d=ref==null?null:(AlertDialog)ref.get();if(d!=null&&d.isShowing())return d.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View walk(View v,java.util.function.Predicate<View> match){if(match.test(v))return v;if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){View found=walk(g.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String s){return walk(decor(),v->v instanceof TextView&&s.contentEquals(((TextView)v).getText()));}
    private View description(String s){return walk(decor(),v->s.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void main(Runnable r){final Throwable[] error={null};test.runOnMainSync(()->{try{r.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void click(String s){main(()->{View v=find(s);check(v!=null,"button exists "+s);v.performClick();});}
    private void clickDescription(String s){main(()->{View v=description(s);check(v!=null,"control exists "+s);v.performClick();});}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+6000;while(SystemClock.uptimeMillis()<until){final boolean[] ok={false};main(()->ok[0]=ready.getAsBoolean());if(ok[0])return;Thread.sleep(70);}throw new AssertionError(label);}
    private void shot(String name)throws IOException{test.waitForIdleSync();try{Thread.sleep(450);}catch(InterruptedException e){Thread.currentThread().interrupt();}Bitmap b=test.getUiAutomation().takeScreenshot();if(b!=null){try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}}
    private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);}
}
