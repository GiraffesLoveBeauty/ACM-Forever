package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Bitmap;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Real signed local artifacts, intercepted HTTPS, no production traffic or account. */
final class OptionalModulesUiSmoke {
    private final Instrumentation test;private final AcmApplication app;private Activity activity;
    private final List<Activity> opened=new ArrayList<>();private String role="member";private int downloads;
    private final String mode;
    private OptionalModulesUiSmoke(Instrumentation t,String m){test=t;mode=m;app=(AcmApplication)t.getTargetContext().getApplicationContext();}
    static void run(Instrumentation test,String mode){new OptionalModulesUiSmoke(test,mode).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;
        try{
            Thread watchdog=new Thread(()->{try{Thread.sleep(18000);StringBuilder stacks=new StringBuilder();for(Map.Entry<Thread,StackTraceElement[]> item:Thread.getAllStackTraces().entrySet())if(item.getKey().getName().equals("main")||item.getKey().getName().contains("Instrumentation")){stacks.append(item.getKey().getName()).append("\n");for(StackTraceElement element:item.getValue())stacks.append(element).append("\n");}trace(stacks.toString());}catch(Exception ignored){}});watchdog.setDaemon(true);watchdog.start();
            test.runOnMainSync(()->{});
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL u)throws IOException{return new Fixture(u);}}:null);
            AppAppearance.prefs(app).edit().putString("api_base_url","https://modules.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).putString("app_update_url","https://modules.test.invalid/update.json").commit();
            app.api().setBaseUrl("https://modules.test.invalid");app.api().setNetworkAvailable(()->true);app.api().login("90000001","Synthetic-Only!");
            trace("logged in");
            if(mode.equals("modules-upgrade")||mode.equals("modules-upgrade-optout")){
                upgrade(mode.endsWith("optout"));throw new AssertionError("Upgrade installer did not restart the test app");
            }else if(mode.equals("modules-retention")){
                check(ModuleStore.code(app)==40,"local new base version installed");
                check(ModuleStore.available(app,"advanced")&&ModuleStore.available(app,"admin"),"compatible splits installed atomically with base");
                check(ModuleStore.assets(app,"cat-art").getAbsolutePath().contains("/40/"),"staged resources activated after upgrade");
                check(ModuleStore.archive(app,"advanced",39).isFile(),"older native download retained");
                check(AppAppearance.prefs(app).getInt("theme_primary",0)==0xff83b8e5,"appearance unchanged by update");
                check(ModuleStore.updateTogether(app),"update preference survives upgrade");
            }else if(mode.equals("modules-retention-optout")){
                check(ModuleStore.code(app)==41,"local base-only upgrade installed");
                check(!ModuleStore.available(app,"advanced")&&!ModuleStore.available(app,"admin"),"incompatible old native splits not executed");
                check(ModuleStore.available(app,"cat-art")&&ModuleStore.assets(app,"cat-art").getAbsolutePath().contains("/40/"),"compatible older resources remain usable");
                check(ModuleStore.archive(app,"advanced",39).isFile()&&ModuleStore.archive(app,"advanced",40).isFile(),"all older downloaded modules retained");
                check(!ModuleStore.updateTogether(app)&&ModuleStore.acquired(app).size()==4,"opt-out and inventory survive upgrade");
            }else if(mode.startsWith("modules-install-")){
                role="admin";app.api().refreshSession();String id=mode.substring("modules-install-".length());
                activity=open(ModuleDownloadActivity.class,new Intent().putExtra("module_id",id).putExtra("next",OptionalModules.target(app,id)));
                await(()->"approval".equals(ModuleDownloads.get(app).state(id).phase),"system installation confirmation");
                Bundle status=new Bundle();status.putString("stream","INSTALLER_READY "+id+"\n");test.sendStatus(0,status);
                // The shell harness accepts the genuine system prompt. Installing a split
                // normally restarts the app and deliberately ends this instrumentation.
                long end=SystemClock.uptimeMillis()+25000;while(SystemClock.uptimeMillis()<end)Thread.sleep(200);
                throw new AssertionError("The system installer was not accepted by the local harness");
            }else if("modules-resource-update".equals(mode)){
                File current=ModuleStore.assets(app,"cat-art"),older=new File(ModuleStore.root(app,ModuleStore.code(app)-1),"installed/cat-art");older.getParentFile().mkdirs();
                check(current.renameTo(older),"simulate a compatible retained resource package");
                check(ModuleStore.available(app,"cat-art")&&!ModuleStore.current(app,"cat-art"),"retained resource works but is visibly behind");
                check(ModuleUpdates.summary(app,ModuleStore.code(app),ModuleStore.version(app)).contains("分层猫娘素材"),"version check reports retained resource upgrade");
                activity=open(UpdateActivity.class,new Intent().putExtra("manage_downloads",true));Instrumentation.ActivityMonitor monitor=test.addMonitor(ModuleDownloadActivity.class.getName(),null,false);
                try{click("更新分层猫娘素材");Activity page=test.waitForMonitorWithTimeout(monitor,8000);check(page!=null,"manual compatible resource update entry");activity=page;opened.add(page);await(()->ModuleStore.current(app,"cat-art")&&has("打开模块"),"manual update completes without app upgrade");}finally{test.removeMonitor(monitor);}
                check(older.isDirectory(),"manual resource update retains the older module files");
            }else if("modules-admin-entry".equals(mode)){
                adminEntry();
            }else if("modules-admin-consent".equals(mode)){
                adminConsent();
            }else if("modules-native".equals(mode)){
                role="admin";app.api().refreshSession();
                check(ModuleStore.available(app,"advanced")&&ModuleStore.available(app,"admin"),"both real native splits installed");
                activity=open(OptionalTestClasses.type("AdvancedAppearanceActivity"),new Intent());await(()->has("一键保存"),"advanced activity and base helpers load together");
                close();activity=open(OptionalTestClasses.type("AdminQuickActivity"),new Intent());await(()->has("待审核话题"),"admin split opens after server role refresh");
                check(ModuleStore.acquired(app).containsAll(Arrays.asList("advanced","admin","official-themes","cat-art")),"acquired modules retained");
                role="member";app.api().refreshSession();close();activity=open(OptionalTestClasses.type("AdminQuickActivity"),new Intent());await(()->has("无访问权限"),"member cannot use installed admin module");
            }else{
                check(!ModuleStore.available(app,"advanced")&&!ModuleStore.available(app,"admin"),"base installs alone without native features");
                try{Class.forName(app.getPackageName()+".AdvancedAppearanceActivity");throw new AssertionError("advanced class leaked into base");}catch(ClassNotFoundException expected){}
                try(InputStream ignored=app.getAssets().open("character/catalog.json")){throw new AssertionError("art leaked into base");}catch(FileNotFoundException expected){}
                Bitmap fallback=CharacterArt.bitmap(app,CharacterArt.AVATAR);check(fallback.getWidth()==96,"bundled small silhouette fallback");
                activity=open(AppearanceActivity.class,new Intent());click("高级个性化");await(()->has("下载喵"),"advanced download consent");
                trace("advanced consent shown");
                String question=ModuleNetwork.catalog(app).get("advanced").confirmation();check(has(question),"consent uses actual native package KB");
                main(()->{View yes=find("下载喵"),no=find("点错了喵");check(yes.getWidth()==no.getWidth()&&yes.getHeight()==no.getHeight(),"equal consent buttons");});
                click("点错了喵");check(downloads==0,"cancel never downloads a payload");
                main(()->{OptionalModules.open(activity,"admin",OptionalModules.target(app,"admin"));check(!ModalDialogs.isShowing(activity),"member has no admin download entry");});
                click("主题选择");downloadFrom("主题库","official-themes");click("打开模块");
                trace("official theme installed");
                // Opening target activity is async; monitor by locating the latest foreground.
                trace("closing resource page");close();trace("opening library directly");activity=open(AppearanceActivity.class,new Intent().putExtra("page","library"));trace("library activity opened");await(()->has("网页主题"),"official library unlocked");
                check(ModuleStore.open(app,"official-themes","themes/renderer/index.html").read()>0,"official source installed privately");
                trace("library checked");close();trace("opening menu");activity=open(AppearanceActivity.class,new Intent());trace("menu opened");downloadFrom("下载分层猫娘素材","cat-art");
                trace("cat art installed");
                check(CharacterArt.bitmap(app,CharacterArt.LOADING).getWidth()>96,"real layered illustration enabled");
                check(ModuleStore.acquired(app).containsAll(Arrays.asList("official-themes","cat-art")),"downloaded resource inventory saved");
                close();activity=open(UpdateActivity.class,new Intent().putExtra("manage_downloads",true));
                main(()->{CheckBox toggle=(CheckBox)find("随 App 更新已下载模块");check(toggle!=null&&toggle.isChecked(),"module updates default on");toggle.performClick();check(!ModuleStore.updateTogether(app),"setting can be disabled");toggle.performClick();});
                File old=ModuleStore.assets(app,"cat-art");String oldPath=old.getAbsolutePath();
                ModuleStore.root(app,ModuleStore.code(app)+1).mkdirs();check(ModuleStore.assets(app,"cat-art").getAbsolutePath().equals(oldPath),"future staging never replaces currently active resources");
                check(ModuleStore.available(app,"cat-art"),"module remains after update setting changes");
            }
            result.putString("stream","PASS: "+mode+" real optional-module checks\n");outcome=Activity.RESULT_OK;
        }catch(Throwable failure){StringBuilder tree=new StringBuilder();try{main(()->{dump(activity.getWindow().getDecorView(),tree);try{java.lang.reflect.Field field=ModalDialogs.class.getDeclaredField("visible");field.setAccessible(true);for(Object value:((Map<?,?>)field.get(null)).values()){AlertDialog dialog=(AlertDialog)((java.lang.ref.WeakReference<?>)value).get();if(dialog!=null&&dialog.isShowing())dump(dialog.getWindow().getDecorView(),tree);}}catch(Exception e){tree.append(e);}});}catch(Exception ignored){}result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure)+"\nVisible: "+tree+"\nLogged: "+app.api().isLoggedIn()+", downloads="+downloads);}
        finally{for(Activity page:opened)main(()->{ModalDialogs.close(page);page.finish();});}
        test.finish(outcome,result);
    }
    private void downloadFrom(String label,String id)throws Exception{
        click(label);await(()->has("下载喵"),"consent "+id);Instrumentation.ActivityMonitor monitor=test.addMonitor(ModuleDownloadActivity.class.getName(),null,false);
        try{click("下载喵");Activity page=test.waitForMonitorWithTimeout(monitor,8000);check(page!=null,"download page "+id);activity=page;opened.add(page);await(()->ModuleStore.available(app,id)&&has("打开模块"),"signed installed "+id);}finally{test.removeMonitor(monitor);}
    }
    private void administrator(){role="admin";try{app.api().refreshSession();}catch(Exception e){throw new AssertionError(e);}check(app.api().isAdministrator(),"synthetic administrator session");}
    private void adminClick(){OptionalTestClasses.call(activity,"showAdministratorMenu",new Class<?>[0]);}
    private boolean adminOpening(){try{java.lang.reflect.Field field=MainActivity.class.getDeclaredField("returnFromAdmin");field.setAccessible(true);return field.getBoolean(activity);}catch(Exception e){throw new AssertionError(e);}}
    private void adminConsent()throws Exception{
        administrator();check(!ModuleStore.available(app,"admin")&&!ModuleStore.archive(app,"admin").isFile(),"first-use admin module fixture");
        activity=open(MainActivity.class,new Intent());
        for(int i=0;i<2;i++){
            main(()->{adminClick();adminClick();});await(()->has("下载喵"),"repeatable first-use consent");
            main(()->check(!adminOpening(),"consent alone does not lock the entry"));click("点错了喵");
            main(()->check(!adminOpening()&&!ModalDialogs.isShowing(activity),"cancel leaves the entry available"));
        }
        check(downloads==0,"cancelled admin consent never downloads payloads");
        trace("admin consent can be cancelled and reopened without a stuck launch guard");
    }
    private void adminEntry()throws Exception{
        administrator();check(ModuleStore.available(app,"admin"),"real installed admin split");
        activity=open(MainActivity.class,new Intent());String admin=app.getPackageName()+".AdminQuickActivity";
        java.util.concurrent.atomic.AtomicInteger launches=new java.util.concurrent.atomic.AtomicInteger();
        Instrumentation.ActivityMonitor counter=new Instrumentation.ActivityMonitor(){
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(intent.getComponent()!=null&&admin.equals(intent.getComponent().getClassName()))launches.incrementAndGet();return null;}
        };
        test.addMonitor(counter);Instrumentation.ActivityMonitor monitor=test.addMonitor(admin,null,false);
        try{
            main(()->{adminClick();adminClick();});
            Activity page=test.waitForMonitorWithTimeout(monitor,8000);check(page!=null,"admin page actually opened");opened.add(page);test.waitForIdleSync();
            check(launches.get()==1,"two same-task entry callbacks start exactly one admin Activity");
            main(()->check(adminOpening(),"actual launch arms the entry guard"));
            main(page::finish);await(()->!adminOpening()&&activity.hasWindowFocus(),"return releases the launch guard");
            // waitForMonitorWithTimeout consumes/removes its monitor after a hit.
            monitor=test.addMonitor(admin,null,false);
            main(this::adminClick);Activity again=test.waitForMonitorWithTimeout(monitor,8000);check(again!=null,"entry opens again after return");opened.add(again);
            check(launches.get()==2,"one new admin launch after return");main(again::finish);await(()->!adminOpening()&&activity.hasWindowFocus(),"second return releases guard");
        }finally{test.removeMonitor(monitor);test.removeMonitor(counter);}
        Instrumentation.ActivityMonitor failure=new Instrumentation.ActivityMonitor(){
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(intent.getComponent()!=null&&admin.equals(intent.getComponent().getClassName()))throw new ActivityNotFoundException("Synthetic admin launch failure");return null;}
        };
        test.addMonitor(failure);
        try{main(()->{adminClick();check(!adminOpening(),"failed launch never arms the guard");check(ModalDialogs.isShowing(activity),"failed launch is visible");ModalDialogs.close(activity);});}
        finally{test.removeMonitor(failure);}
        monitor=test.addMonitor(admin,null,false);
        try{main(this::adminClick);Activity retry=test.waitForMonitorWithTimeout(monitor,8000);check(retry!=null,"retry works after launch failure");opened.add(retry);main(retry::finish);await(()->!adminOpening()&&activity.hasWindowFocus(),"retry return releases guard");}
        finally{test.removeMonitor(monitor);}
        trace("same-task double entry, return/reopen and failed-launch retry passed");
    }
    private void upgrade(boolean optout)throws Exception{
        role="admin";app.api().refreshSession();ModuleStore.updateTogether(app,!optout);
        JSONObject raw;try(InputStream in=new FileInputStream(new File(app.getFilesDir(),"module-fixtures/update-next.json"))){raw=new JSONObject(new String(ModuleNetwork.read(in,32768),StandardCharsets.UTF_8));}
        UpdateManifest next=new UpdateManifest(raw,app.getPackageName());
        File folder=new File(app.getCacheDir(),"updates");folder.mkdirs();File base=new File(folder,"verified-upgrade.apk");java.nio.file.Files.copy(new File(app.getFilesDir(),"module-fixtures/next-base.apk").toPath(),base.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        AppUpdates updates=app.updates();java.lang.reflect.Field release=AppUpdates.class.getDeclaredField("release"),verified=AppUpdates.class.getDeclaredField("verifiedName");release.setAccessible(true);verified.setAccessible(true);release.set(updates,next);verified.set(updates,base.getName());
        AppAppearance.prefs(app).edit().putInt("theme_primary",0xff83b8e5).commit();
        activity=open(UpdateActivity.class,new Intent().putExtra("manage_downloads",true));main(()->updates.install(activity));
        await(()->updates.awaitingModuleInstall()||!updates.error().isEmpty(),"upgrade system confirmation");check(updates.error().isEmpty(),updates.error());
        check(ModuleStore.code(app)==next.versionCode-1,"base not changed before confirmation");
        if(!optout)check(ModuleStore.assets(app,"cat-art").getAbsolutePath().contains("/39/"),"future staged assets do not affect old app");
        trace("INSTALLER_READY upgrade");long end=SystemClock.uptimeMillis()+25000;while(SystemClock.uptimeMillis()<end)Thread.sleep(100);
    }
    private Activity open(Class<?> type,Intent intent){Activity a=test.startActivitySync(intent.setClassName(app,type.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));opened.add(a);return a;}
    private void close(){if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});test.waitForIdleSync();}
    private void main(Runnable task){Throwable[] failure={null};test.runOnMainSync(()->{try{task.run();}catch(Throwable t){failure[0]=t;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private View walk(View view,String label){if(view instanceof TextView&&label.contentEquals(((TextView)view).getText()))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),label);if(found!=null)return found;}}return null;}
    private void dump(View view,StringBuilder text){if(view instanceof TextView)text.append(((TextView)view).getText()).append(" | ");if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)dump(((ViewGroup)view).getChildAt(i),text);}
    private View find(String label){try{java.lang.reflect.Field field=ModalDialogs.class.getDeclaredField("visible");field.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)field.get(null)).get(activity);AlertDialog dialog=ref==null?null:(AlertDialog)ref.get();if(dialog!=null&&dialog.isShowing()){View found=walk(dialog.getWindow().getDecorView(),label);if(found!=null)return found;}}catch(Exception e){throw new AssertionError(e);}return activity==null?null:walk(activity.getWindow().getDecorView(),label);}
    private boolean has(String text){boolean[] found={false};main(()->found[0]=find(text)!=null);return found[0];}
    private void click(String text){main(()->{View v=find(text);check(v!=null,"button "+text);v.performClick();});test.waitForIdleSync();}
    private void await(BooleanSupplier condition,String title)throws Exception{long end=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(70);}throw new AssertionError("Timeout: "+title);}
    private static void check(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    private void trace(String text){Bundle value=new Bundle();value.putString("stream","STEP: "+text+"\n");test.sendStatus(0,value);}
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        @Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}
        @Override public int getResponseCode(){return 200;}
        @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=modules-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        @Override public InputStream getInputStream()throws IOException{
            if(url.getHost().equals("github.com")){String name=url.getPath().substring(url.getPath().lastIndexOf('/')+1);String version=url.getPath().replaceFirst(".*/download/v([^/]+)/.*","$1");File versioned=new File(app.getFilesDir(),"module-fixtures/"+version+"/"+name);if(!name.equals("modules.json"))downloads++;return new FileInputStream(versioned.isFile()?versioned:new File(app.getFilesDir(),"module-fixtures/"+name));}
            if(!url.getHost().equals("modules.test.invalid"))throw new IOException("External test traffic blocked");
            String response=url.getPath().endsWith("/me")?"{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\""+role+"\",\"qq_id\":\"90000001\"}":"{}";
            return new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8));
        }
    }
}
