package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BooleanSupplier;
import org.json.*;

/** Exercises real Android storage, exact original bytes, round-trip appearance and visible controls. */
final class ThemeTransferUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;private final List<String> created=new ArrayList<>();
    private ThemeTransferUiSmoke(Instrumentation test){this.test=test;app=test.getTargetContext();}
    static void run(Instrumentation test){new ThemeTransferUiSmoke(test).run();}
    private void run(){
        SharedPreferences prefs=AppAppearance.prefs(app),registry=app.getSharedPreferences("local_theme_library",0);Map<String,?> before=new HashMap<>(prefs.getAll()),oldRegistry=new HashMap<>(registry.getAll());File background=new File(app.getFilesDir(),"profile-cover.jpg"),original=new File(app.getCacheDir(),"transfer-source.png");byte[] oldImage=read(background);Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;
        try{
            registry.edit().clear().commit();prefs.edit().clear().putString("theme_source","acm").putInt("theme_primary",0xff83b8e5).putInt("theme_secondary",0xffe9c786).putString("bg_mode","image").putString("bg_source","custom").putInt("bg_transparency",1).putInt("module_transparency",2).putInt("control_transparency",3).putString("saved_password","must-never-export").commit();
            Bitmap input=Bitmap.createBitmap(1600,1300,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(input);canvas.drawColor(Color.RED);Paint paint=new Paint();paint.setColor(Color.BLUE);canvas.drawRect(400,200,1000,1100,paint);try(FileOutputStream out=new FileOutputStream(original)){input.compress(Bitmap.CompressFormat.PNG,100,out);}input.recycle();
            prefs.edit().putBoolean("theme_custom_color",true).putBoolean("secondary_custom_color",false).putBoolean("background_custom_color",true).commit();
            ProfileCover.saveOriginal(app,Uri.fromFile(original),new float[]{.125f,.25f,.875f,.9f});check(Arrays.equals(read(original),read(background)),"selected original is not resized or re-encoded");
            String saved=LocalThemes.save(app);created.add(saved);ThemePackage pack=LocalThemes.pack(app,saved);check(!pack.settings.has("saved_password"),"export excludes credentials");ByteArrayOutputStream output=new ByteArrayOutputStream();pack.write(output);ThemePackage restored=ThemePackage.read(new ByteArrayInputStream(output.toByteArray()));String imported=LocalThemes.install(app,restored);created.add(imported);
            check(Arrays.equals(read(original),read(LocalThemes.image(app,imported))),"exported and imported image bytes match original");check(!imported.equals(saved),"import adds a separate theme");
            Map<String,?> sourceSettings=LocalThemes.prefs(app,saved).getAll(),targetSettings=LocalThemes.prefs(app,imported).getAll();for(Iterator<String> keys=pack.settings.keys();keys.hasNext();){String key=keys.next();check(sourceSettings.get(key).equals(targetSettings.get(key)),"setting round trip: "+key);}
            LocalThemes.apply(app,saved);int[] expected=pixels(app);LocalThemes.apply(app,imported);check(Arrays.equals(expected,pixels(app)),"image crop, colors and transparency render identically after import");
            prefs.edit().putString("theme_source","acm").putInt("theme_primary",Color.RED).commit();open(AppearanceActivity.class,null);click("主题选择");main(()->{View library=find("主题库"),local=find("本地导入");check(local!=null&&local.getTop()>=library.getBottom(),"local import is below theme library");});main(()->activity.onBackPressed());click("我的主题");clickDescription("主题缩略图 未命名1");await(()->prefs.getInt("theme_primary",0)==0xff83b8e5,"thumbnail applies saved theme");
            Instrumentation.ActivityMonitor monitor=test.addMonitor(AppearanceActivity.class.getName(),null,false);clickDescription("设置主题 未命名1");Activity editor=test.waitForMonitorWithTimeout(monitor,5000);test.removeMonitor(monitor);check(editor!=null,"saved editor opens");activity=editor;test.waitForIdleSync();main(()->{View rename=find("重命名"),share=find("分享"),delete=find("删除");check(share!=null&&share.getTop()>=rename.getBottom()&&delete.getTop()>=share.getBottom()&&find("导出")==null,"share replaces export between rename and delete");});
            Intent attachment=share();Uri exported=attachment.getParcelableExtra(Intent.EXTRA_STREAM);check(exported!=null&&"content".equals(exported.getScheme()),"share uses a content attachment");
            check("application/zip".equals(attachment.getType())&&(attachment.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0&&(attachment.getFlags()&Intent.FLAG_GRANT_WRITE_URI_PERMISSION)==0,"read-only ZIP share grant");
            check(attachment.getClipData()!=null&&exported.equals(attachment.getClipData().getItemAt(0).getUri()),"share grants the exact ClipData attachment");
            try(InputStream in=app.getContentResolver().openInputStream(exported)){ThemePackage shared=ThemePackage.read(in);check(Arrays.equals(pack.image,shared.image)&&pack.settings.toString().equals(shared.settings.toString()),"shared file contains exact original image and complete settings");}
            try(android.database.Cursor meta=app.getContentResolver().query(exported,null,null,null,null)){check(meta!=null&&meta.moveToFirst()&&meta.getString(meta.getColumnIndexOrThrow(android.provider.OpenableColumns.DISPLAY_NAME)).endsWith(".acmtheme")&&meta.getLong(meta.getColumnIndexOrThrow(android.provider.OpenableColumns.SIZE))>0,"receiving app can query the theme name and size");}
            try{app.getContentResolver().openFileDescriptor(exported,"rw");throw new AssertionError("writable attachment");}catch(FileNotFoundException expectedError){}
            Uri traversal=exported.buildUpon().path("/../acmforever_settings.xml").build();try{app.getContentResolver().openInputStream(traversal);throw new AssertionError("provider escaped share directory");}catch(FileNotFoundException expectedError){}
            Intent secondShare=share();check(!exported.equals(secondShare.getParcelableExtra(Intent.EXTRA_STREAM)),"each share uses an independent file");
            int beforeImport=LocalThemes.list(app).length();main(()->((AppearanceActivity)activity).onActivityResult(74,Activity.RESULT_OK,new Intent().setData(exported)));
            await(()->LocalThemes.list(app).length()==beforeImport+1,"shared file imports as a new theme");String fromDocument=LocalThemes.list(app).getJSONObject(beforeImport).getString("id");created.add(fromDocument);
            check(Arrays.equals(pack.image,read(LocalThemes.image(app,fromDocument))),"document import retains exact bytes");check(!LocalThemes.prefs(app,saved).contains("saved_password")&&LocalThemes.prefs(app,saved).getInt("theme_primary",0)==0xff83b8e5,"import from saved-theme editor never overwrites its owner");
            main(()->check(find("分享")!=null,"import keeps saved-theme editor scope"));
            for(String preset:new String[]{"industrial","mint","gray","sunshine","rose","original","phase","angel-city","minecraft"})for(boolean dark:new boolean[]{false,true}){
                prefs.edit().putString("theme_source","web").putString("theme_preset",preset).putBoolean("theme_dark",dark).putString("bg_mode","solid").putString("bg_source","theme").commit();AppAppearance.load(app);String design=AppAppearance.findPreset(app,preset).optString("design_template","original");String id=LocalThemes.save(app);created.add(id);ByteArrayOutputStream bytes=new ByteArrayOutputStream();LocalThemes.pack(app,id).write(bytes);String duplicate=LocalThemes.install(app,ThemePackage.read(new ByteArrayInputStream(bytes.toByteArray())));created.add(duplicate);ThemePalette p=AppAppearance.palette();LocalThemes.apply(app,duplicate);ThemePalette q=AppAppearance.palette();check(Arrays.equals(paletteValues(p),paletteValues(q))&&p.dark==q.dark&&design.equals(MobileStyle.DESIGN),"all palette colours and design round trip: "+preset+" dark="+dark);if("industrial".equals(preset))check(q.hero==(dark?0xff151814:0xff20231f),"industrial banner keeps its original colour");
            }
            open(ThemePreviewActivity.class,created.get(created.size()-1));await(()->walk(activity.getWindow().getDecorView(),v->v instanceof OfficialThemeView)!=null,"official source layer mounted");
            final String[] response={null};long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){main(()->{OfficialThemeView web=(OfficialThemeView)walk(activity.getWindow().getDecorView(),v->v instanceof OfficialThemeView&&((OfficialThemeView)v).getContentDescription().toString().contains("graph"));if(web!=null)web.evaluateJavascript("JSON.stringify({design:document.documentElement.dataset.designTemplate,svg:document.querySelectorAll('svg').length,mc:!!document.querySelector('.minecraft-art')})",value->response[0]=value);});Thread.sleep(200);if(response[0]!=null&&response[0].contains("minecraft")&&response[0].contains("true"))break;}check(response[0]!=null&&response[0].contains("minecraft")&&response[0].contains("true"),"real compiled Minecraft Vue SVG and CSS loaded offline: "+response[0]);shot("official-minecraft-v0217.png");
            OfficialThemeView[] layer={null};main(()->layer[0]=(OfficialThemeView)description("官方主题原始素材 background"));check(layer[0]!=null,"official background layer mounted");
            SharedPreferences preview=LocalThemes.prefs(app,created.get(created.size()-1));JSONObject darkStyle=backgroundStyle(layer[0],"dark");check("#181818".equals(darkStyle.getString("shadow")),"Minecraft dark CSS selector matches body");
            preview.edit().putBoolean("theme_dark",false).commit();main(()->layer[0].refresh());JSONObject lightStyle=backgroundStyle(layer[0],"light");check(!darkStyle.getString("image").equals(lightStyle.getString("image")),"Minecraft background changes to the light overlay without rebuilding the view");
            preview.edit().putBoolean("theme_dark",true).commit();main(()->layer[0].refresh());JSONObject darkAgain=backgroundStyle(layer[0],"dark");check(darkStyle.getString("image").equals(darkAgain.getString("image"))&&"#181818".equals(darkAgain.getString("shadow")),"Minecraft dark overlay is restored on the same view");
            officialLayouts(prefs);
            prefs.edit().putString("theme_source","acm").putString("search_history",new JSONArray().put("图论").put("DP").put("一个很长很长的搜索历史词条用于测试自动换行并且不产生横向滑动").put("CF").toString()).commit();open(SearchActivity.class,null);await(()->description("搜索历史词条")!=null,"history words");test.waitForIdleSync();main(()->{ViewGroup words=(ViewGroup)description("搜索历史词条");View first=words.getChildAt(0),second=words.getChildAt(1),longTerm=words.getChildAt(2);check(first.getWidth()<words.getWidth()/2,"short border fits text");check(first.getTop()==second.getTop(),"short terms share row");check(longTerm.getTop()>first.getTop()&&longTerm.getWidth()<=words.getWidth(),"long term wraps inside page");});shot("search-history-v0217.png");
            result.putString("stream","PASS: exact original bytes, crop and all settings round trip; isolated import; nine preset palettes in both modes; Minecraft dark/light/dark CSS; four templates in both modes with all graph nodes inside the host, separate centred text/art and original node interaction; thumbnail application; real share button and system chooser, repeated tap guard, readable ZIP content/metadata, exact image/settings, read-only/path boundaries and independent attachments; history content widths and wrapping.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable e){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));try{shot("theme-transfer-failure-v0217.png");}catch(Exception ignored){}}
        finally{if(activity!=null)main(()->activity.finish());for(String id:created){try{LocalThemes.delete(app,id);}catch(Exception ignored){}}restore(prefs,before);restore(registry,oldRegistry);try{if(oldImage==null)background.delete();else try(FileOutputStream out=new FileOutputStream(background)){out.write(oldImage);}}catch(Exception ignored){}original.delete();ProfileCover.invalidate();AppAppearance.load(app);}test.finish(outcome,result);
    }
    private int[] paletteValues(ThemePalette p){return new int[]{p.primary,p.background,p.surface,p.accent,p.text,p.muted,p.line,p.brand,p.hero,p.onHero,p.onAccent,p.onSelected,p.selected,p.cat};}
    private Intent share()throws Exception{
        java.util.concurrent.atomic.AtomicReference<Intent> received=new java.util.concurrent.atomic.AtomicReference<>();java.util.concurrent.atomic.AtomicInteger count=new java.util.concurrent.atomic.AtomicInteger();
        Instrumentation.ActivityMonitor capture=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_CHOOSER.equals(intent.getAction())){count.incrementAndGet();received.set(intent.getParcelableExtra(Intent.EXTRA_INTENT));return new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);}return null;}};
        test.addMonitor(capture);try{main(()->{find("分享").performClick();find("分享").performClick();});await(()->received.get()!=null,"sharing opens system chooser");test.waitForIdleSync();check(count.get()==1,"repeated taps create one chooser");return received.get();}finally{test.removeMonitor(capture);}
    }
    private JSONObject evaluate(OfficialThemeView web,String expression)throws Exception{
        java.util.concurrent.atomic.AtomicReference<String> result=new java.util.concurrent.atomic.AtomicReference<>();main(()->web.evaluateJavascript("JSON.stringify(("+expression+"))",result::set));
        long until=SystemClock.uptimeMillis()+3000;while(result.get()==null&&SystemClock.uptimeMillis()<until)Thread.sleep(20);if(result.get()==null)throw new AssertionError("theme JavaScript callback");Object decoded=new JSONTokener(result.get()).nextValue();return decoded instanceof String?new JSONObject((String)decoded):new JSONObject();
    }
    private void officialLayouts(SharedPreferences prefs)throws Exception{
        for(String preset:new String[]{"original","phase","angel-city","minecraft"})for(boolean dark:new boolean[]{false,true}){
            prefs.edit().putString("theme_source","web").putString("theme_preset",preset).putBoolean("theme_dark",dark).putString("bg_mode","solid").putString("bg_source","theme").commit();String id=LocalThemes.save(app);created.add(id);open(ThemePreviewActivity.class,id);
            OfficialThemeView[] art={null};await(()->{art[0]=(OfficialThemeView)description("官方主题原始素材 graph");return art[0]!=null;},"graph host");
            String script="(()=>{const g=document.querySelector('.algorithm-graph'),r=g?.getBoundingClientRect(),nodes=[...document.querySelectorAll('.graph-node-hit')];return {design:document.documentElement.dataset.designTemplate,mode:document.body.dataset.theme,ready:!!g&&nodes.length===12,fit:!!r&&r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,nodesFit:nodes.length===12&&nodes.every(n=>{let b=n.getBoundingClientRect();return b.left>=-1&&b.top>=-1&&b.right<=innerWidth+1&&b.bottom<=innerHeight+1;}),background:getComputedStyle(document.body).backgroundColor};})()";
            JSONObject geometry=null;long until=SystemClock.uptimeMillis()+12000;while(SystemClock.uptimeMillis()<until){geometry=evaluate(art[0],script);if(geometry.optBoolean("ready")&&preset.equals(geometry.optString("design"))&&(dark?"dark":"light").equals(geometry.optString("mode")))break;Thread.sleep(100);}
            check(geometry!=null&&geometry.optBoolean("ready")&&geometry.optBoolean("fit")&&geometry.optBoolean("nodesFit"),"all original graph nodes fit inside host for "+preset+" dark="+dark+": "+geometry);
            main(()->{View copy=description("社区横幅文字");int[] a=new int[2],b=new int[2];copy.getLocationOnScreen(a);art[0].getLocationOnScreen(b);check(a[0]+copy.getWidth()<=b[0]&&Math.abs(a[1]+copy.getHeight()/2-b[1]-art[0].getHeight()/2)<=MobileStyle.dp(app,2),"banner text and graph are separate centred columns");});
            JSONObject click=evaluate(art[0],"(()=>{document.querySelector('.graph-node').dispatchEvent(new MouseEvent('click',{bubbles:true}));return {ok:true};})()");check(click.optBoolean("ok"),"graph receives a click");Thread.sleep(80);JSONObject selected=evaluate(art[0],"({status:document.querySelector('.graph-status')?.textContent})");check(selected.optString("status").contains("权重 0"),"original graph interaction selects source node");
            shot("official-"+preset+"-"+(dark?"dark":"light")+"-v0218.png");
        }
    }
    private JSONObject backgroundStyle(OfficialThemeView web,String mode)throws Exception{
        long until=SystemClock.uptimeMillis()+15000;JSONObject last=null;
        while(SystemClock.uptimeMillis()<until){
            java.util.concurrent.atomic.AtomicReference<String> response=new java.util.concurrent.atomic.AtomicReference<>();main(()->web.evaluateJavascript("JSON.stringify({html:document.documentElement.dataset.theme,body:document.body.dataset.theme,image:getComputedStyle(document.body).backgroundImage,shadow:getComputedStyle(document.body).getPropertyValue('--mc-shadow').trim()})",response::set));
            long callbackUntil=SystemClock.uptimeMillis()+2000;while(response.get()==null&&SystemClock.uptimeMillis()<callbackUntil)Thread.sleep(20);
            if(response.get()!=null){Object value=new JSONTokener(response.get()).nextValue();if(value instanceof String){last=new JSONObject((String)value);if(mode.equals(last.optString("html"))&&mode.equals(last.optString("body"))&&last.optString("image").contains("linear-gradient"))return last;}}
            Thread.sleep(100);
        }
        throw new AssertionError("Minecraft "+mode+" document and background: "+last);
    }
    private int[] pixels(Context c){AppAppearance.load(c);Bitmap b=Bitmap.createBitmap(320,600,Bitmap.Config.ARGB_8888);android.graphics.drawable.Drawable cover=ProfileCover.drawable(c);cover.setBounds(0,0,320,600);cover.draw(new Canvas(b));int[] result=new int[320*600];b.getPixels(result,0,320,0,0,320,600);b.recycle();return result;}
    private byte[] read(File f){try{return f.isFile()?java.nio.file.Files.readAllBytes(f.toPath()):null;}catch(Exception e){throw new AssertionError(e);}}
    private void restore(SharedPreferences prefs,Map<String,?> old){SharedPreferences.Editor e=prefs.edit().clear();for(Map.Entry<String,?> entry:old.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)e.putString(k,(String)v);else if(v instanceof Integer)e.putInt(k,(Integer)v);else if(v instanceof Long)e.putLong(k,(Long)v);else if(v instanceof Boolean)e.putBoolean(k,(Boolean)v);else if(v instanceof Float)e.putFloat(k,(Float)v);}e.commit();}
    private void open(Class<?> type,String unused){if(activity!=null)main(()->activity.finish());Intent intent=new Intent(app,type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);if(unused!=null)intent.putExtra(LocalThemes.EXTRA,unused);activity=test.startActivitySync(intent);test.waitForIdleSync();}
    private View walk(View view,java.util.function.Predicate<View> predicate){if(predicate.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),predicate);if(found!=null)return found;}}return null;}
    private View find(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private View description(String value){return walk(activity.getWindow().getDecorView(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void click(String value){main(()->{View v=find(value);check(v!=null,"button "+value);v.performClick();});test.waitForIdleSync();}
    private void clickDescription(String value){main(()->{View v=description(value);check(v!=null,"control "+value);v.performClick();});test.waitForIdleSync();}
    private void main(Runnable task){Throwable[] error={null};test.runOnMainSync(()->{try{task.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void await(BooleanSupplier condition,String label)throws Exception{long until=SystemClock.uptimeMillis()+6000;while(SystemClock.uptimeMillis()<until){boolean[] ready={false};main(()->ready[0]=condition.getAsBoolean());if(ready[0])return;Thread.sleep(60);}throw new AssertionError(label);}
    private void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private void shot(String name)throws Exception{test.waitForIdleSync();Bitmap image=test.getUiAutomation().takeScreenshot();if(image!=null){try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();}}
}
