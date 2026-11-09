package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;

/** Actual optional theme pages: return and recreation retain the reading position. */
final class ThemeReturnUiSmoke {
    private final Instrumentation test;
    private final Context app;
    private final List<Activity> opened = new ArrayList<>();
    private final List<String> themes = new ArrayList<>();
    private Activity activity;
    private ThemeReturnUiSmoke(Instrumentation test) { this.test=test; app=test.getTargetContext(); }
    static void run(Instrumentation test) { new ThemeReturnUiSmoke(test).run(); }
    private void run() {
        test.runOnMainSync(()->{});
        AcmApplication application=(AcmApplication)app.getApplicationContext();
        ApiClient api=application.api(); String base=api.getBaseUrl();
        SharedPreferences prefs=AppAppearance.prefs(app), registry=app.getSharedPreferences("local_theme_library",0);
        Map<String,?> settings=new HashMap<>(prefs.getAll()), library=new HashMap<>(registry.getAll());
        Bundle result=new Bundle(); int outcome=Activity.RESULT_CANCELED;
        try {
            OptionalTestClasses.login(test);
            prefs.edit().putString("theme_source","acm").putString("bg_mode","solid").apply();
            registry.edit().clear().apply();
            for(int i=0;i<12;i++) themes.add(LocalThemes.save(app));
            activity=test.startActivitySync(new Intent().setClassName(app,OptionalTestClasses.type("AdvancedAppearanceActivity").getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK)); opened.add(activity); click("我的主题");
            await(()->description("设置主题 未命名5")!=null&&scroll().getHeight()>0,"saved list");
            main(()->scroll().scrollTo(0,MobileStyle.dp(app,480)));
            int listPosition=position(); check(listPosition>300,"list is genuinely scrolled"); Activity list=activity;
            Instrumentation.ActivityMonitor monitor=test.addMonitor(OptionalTestClasses.type("AdvancedAppearanceActivity").getName(),null,false);
            try { clickDescription("设置主题 未命名5"); activity=test.waitForMonitorWithTimeout(monitor,5000); } finally { test.removeMonitor(monitor); }
            check(activity!=null,"theme editor opens"); opened.add(activity);
            click("重命名"); main(()->((EditText)description("主题名称")).setText("返回位置验证")); click("确认");
            main(()->activity.onBackPressed()); activity=list;
            await(()->description("设置主题 返回位置验证")!=null,"returned list refreshes changed name");
            await(()->Math.abs(scroll().getScrollY()-listPosition)<=2,"return from theme settings preserves saved-list position");
            recreate(); await(()->description("设置主题 返回位置验证")!=null,"saved list survives recreation");
            await(()->Math.abs(scroll().getScrollY()-listPosition)<=2,"recreation preserves saved-list position");
            // Internal subpages also restore their own position rather than the list's.
            main(()->activity.onBackPressed()); click("主题选择");
            await(()->description("模块背景透明度")!=null&&scroll().getChildAt(0).getHeight()>scroll().getHeight(),"long theme settings page");
            main(()->scroll().scrollTo(0,MobileStyle.dp(app,240))); int themePosition=position(); check(themePosition>0,"theme page scrolled");
            click("搜索栏与下方菜单背景透明度"); await(()->description("按键搜索栏与下方菜单背景透明度")!=null,"controls subpage");
            main(()->activity.onBackPressed()); await(()->description("模块背景透明度")!=null,"back to theme settings");
            await(()->Math.abs(scroll().getScrollY()-themePosition)<=2,"internal back preserves theme page position");
            result.putString("stream","PASS: saved themes retain scroll after settings return and real Activity recreation, renamed tile refreshes, internal theme/control back restores its independent position.\n"); outcome=Activity.RESULT_OK;
        } catch(Throwable error) { result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)); }
        finally {
            for(Activity page:opened) main(()->{ModalDialogs.close(page);page.finish();});
            for(String id:themes) try { LocalThemes.delete(app,id); } catch(Exception ignored) {}
            try { api.logout(); } catch(Exception ignored) {}
            restore(prefs,settings); restore(registry,library); api.setBaseUrl(base); AppAppearance.load(app);
        }
        test.finish(outcome,result);
    }
    private void recreate() throws Exception {
        Activity previous=activity; AtomicReference<Activity> replacement=new AtomicReference<>();
        Application application=(Application)app.getApplicationContext();
        Application.ActivityLifecycleCallbacks callback=new Application.ActivityLifecycleCallbacks(){
            public void onActivityCreated(Activity page,Bundle saved){if(page.getClass()==previous.getClass()&&page!=previous)replacement.set(page);}
            public void onActivityStarted(Activity page){} public void onActivityResumed(Activity page){} public void onActivityPaused(Activity page){}
            public void onActivityStopped(Activity page){} public void onActivitySaveInstanceState(Activity page,Bundle saved){} public void onActivityDestroyed(Activity page){}
        };
        application.registerActivityLifecycleCallbacks(callback);
        try { main(previous::recreate); await(()->replacement.get()!=null,"Activity recreated"); activity=replacement.get();opened.add(activity); }
        finally { application.unregisterActivityLifecycleCallbacks(callback); }
    }
    private void restore(SharedPreferences prefs,Map<String,?> values) {
        SharedPreferences.Editor edit=prefs.edit().clear();
        for(Map.Entry<String,?> entry:values.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);else if(v instanceof Set)edit.putStringSet(k,new HashSet<>((Set<String>)v));}edit.apply();
    }
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog dialog=ref==null?null:(AlertDialog)ref.get();if(dialog!=null&&dialog.isShowing())return dialog.getWindow().getDecorView();}catch(Exception error){throw new AssertionError(error);}return activity.getWindow().getDecorView();}
    private View walk(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View hit=walk(group.getChildAt(i),match);if(hit!=null)return hit;}}return null;}
    private View description(String text){return walk(decor(),v->text.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private ScrollView scroll(){return (ScrollView)description("个性化滚动区域");}
    private int position(){int[] value={0};main(()->value[0]=scroll().getScrollY());return value[0];}
    private void clickDescription(String text){main(()->{View v=description(text);check(v!=null,"control "+text);v.performClick();});test.waitForIdleSync();}
    private void click(String text){main(()->{View v=walk(decor(),n->n instanceof TextView&&text.contentEquals(((TextView)n).getText()));check(v!=null,"button "+text);v.performClick();});test.waitForIdleSync();}
    private void main(Runnable work){Throwable[] error={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private void await(BooleanSupplier ready,String message)throws Exception{long until=SystemClock.uptimeMillis()+6000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0])return;Thread.sleep(60);}throw new AssertionError(message);}
    private void check(boolean passed,String message){if(!passed)throw new AssertionError(message);}
}
