package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Isolated emulator checks; this transport and these member fixtures exist only in the test APK. */
final class AppearanceUiSmoke {
    private final Instrumentation test;private Activity activity;private final Context app;private final SharedPreferences prefs;
    private AppearanceUiSmoke(Instrumentation test){this.test=test;app=test.getTargetContext();prefs=AppAppearance.prefs(app);}
    static void run(Instrumentation test){new AppearanceUiSmoke(test).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;ApiClient api=((AcmApplication)app.getApplicationContext()).api();String original=api.getBaseUrl();
        Map<String,?> settings=new HashMap<>(prefs.getAll());
        File cover=new File(app.getFilesDir(),"profile-cover.jpg");byte[] originalCover;
        try{originalCover=cover.isFile()?java.nio.file.Files.readAllBytes(cover.toPath()):null;}catch(IOException error){throw new AssertionError(error);}
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"appearance.test.invalid".equals(url.getHost()))throw new IOException("External traffic blocked in this test");return new Fixture(url);}}:null);
            // A previous theme test may leave a valid original image. Specify the
            // intended fixture rather than invoking legacy background migration.
            prefs.edit().clear().putString("bg_mode","solid").putString("bg_source","custom").putString("api_base_url","https://appearance.test.invalid").putBoolean("remember_account",false).apply();
            api.setBaseUrl("https://appearance.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent().setClassName(app,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            await(()->description("筛选社区话题")!=null,8000,"forum ready");clickDescription("发帖");
            await(()->description("发帖格式工具")!=null,8000,"compose ready");test.waitForIdleSync();
            main(()->{
                check(walk(decor(),v->v instanceof HorizontalScrollView)==null,"compose has no horizontal scroller");
                WrapLayout format=(WrapLayout)description("发帖格式工具");check(format.getChildCount()==11,"all formatting tools remain available");
                checkRows(format);checkRows((WrapLayout)description("发帖草稿工具"));
                int rows=1,previous=-1;for(int i=0;i<format.getChildCount();i++){int top=format.getChildAt(i).getTop();if(previous>=0&&previous!=top)rows++;previous=top;}check(rows>=2,"format tools use multiple rows at this viewport");
                description("发帖格式工具").requestRectangleOnScreen(new Rect(0,0,format.getWidth(),format.getHeight()),true);
            });screenshot("compose-v025.png");
            clickDescription("进入账号设置");await(()->find("修改昵称")!=null,8000,"account ready");
            main(()->{View row=(View)find("修改昵称").getParent().getParent();check(((ViewGroup)row).getChildCount()==1,"account rows have no arrow icons");ViewGroup tiles=(ViewGroup)description("我的话题").getParent();int height=tiles.getChildAt(0).getHeight();for(int i=1;i<4;i++)check(height==tiles.getChildAt(i).getHeight(),"community entries align");});screenshot("account-v026.png");
            clickDescription("个人中心");await(()->description("切换平台 ALL")!=null,8000,"ALL tab");clickDescription("切换平台 ALL");
            main(()->{check(description("ALL通过题数 30")!=null,"ALL total");check(description("过题数框")!=description("最近AC框"),"counts and recent AC are separate");});screenshot("profile-v025.png");
            main(()->activity.finish());activity=test.startActivitySync(new Intent().setClassName(app,AppearanceActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            click("背景选择");main(()->{check(find("使用纯色背景").isSelected(),"solid selected by default");check(!find("使用渐变背景").isSelected(),"one selected mode");});
            click("使用渐变背景");click("与主题同色");main(()->{check(find("与主题同色").isSelected(),"follow theme selected");check(description("打开调色盘")==null,"custom colours hidden while following theme");});
            click("自定义");clickDescription("天蓝");screenshot("background-gradient-v025.png");
            checkBackground();clickDescription("打开调色盘");await(()->description("调色盘，滑动选择色相和饱和度")!=null,2000,"picker page");screenshot("palette-v025.png");click("应用颜色");
            main(()->activity.onBackPressed());click("主题选择");clickDescription("樱粉");checkArt();screenshot("theme-character-v025.png");
            click("主题库");await(()->find("森空岛（工业）")!=null||find("工业黄绿")!=null||walk(decor(),v->v.getContentDescription()!=null&&v.getContentDescription().toString().endsWith("深色"))!=null,2000,"web presets");
            main(()->{try{check(AppAppearance.presets(app).length()==9,"four latest Web templates and five palettes");for(int i=0;i<9;i++){org.json.JSONObject preset=AppAppearance.presets(app).getJSONObject(i);for(boolean dark:new boolean[]{false,true}){org.json.JSONObject profile=WebThemes.profile(preset,dark),colors=profile.getJSONObject("colors");ThemePalette p=new ThemePalette(Color.parseColor(colors.getString("primary")),Color.parseColor(colors.getString("background")),Color.parseColor(colors.getString("surface")),Color.parseColor(colors.getString("accent")),dark,"industrial".equals(preset.getString("id")),WebThemes.overrides(profile));check(ThemePalette.contrast(p.surface,p.text)>=4.49,"preset text readable");}}}catch(Exception e){throw new AssertionError(e);}});testInPlace();screenshot("theme-library-v026.png");testControls();
            testReconnect();result.putString("stream","PASS: wrapping compose controls/no horizontal scroll, no account arrows, ALL/separate AC cards, full-screen gradient, six-step local image transparency, colour picker, 5 Web themes, protected character pixels and 3 colour groups, 10s persistent failure/retry and 3s recovery.\n");result.putBoolean("passed",true);outcome=Activity.RESULT_OK;
        }catch(Throwable e){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));result.putBoolean("passed",false);}
        finally{
            if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});try{api.logout();}catch(Exception ignored){}ProfileCover.clear(app);SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> e:settings.entrySet()){Object v=e.getValue();if(v instanceof String)edit.putString(e.getKey(),(String)v);else if(v instanceof Boolean)edit.putBoolean(e.getKey(),(Boolean)v);else if(v instanceof Integer)edit.putInt(e.getKey(),(Integer)v);else if(v instanceof Long)edit.putLong(e.getKey(),(Long)v);else if(v instanceof Float)edit.putFloat(e.getKey(),(Float)v);}edit.apply();AppAppearance.load(app);api.setBaseUrl(original);
        }
        try{if(originalCover!=null)try(FileOutputStream out=new FileOutputStream(cover)){out.write(originalCover);}ProfileCover.invalidate();}catch(IOException error){throw new AssertionError(error);}
        test.finish(outcome,result);
    }
    private void checkRows(WrapLayout layout){for(int i=0;i<layout.getChildCount();i++){View a=layout.getChildAt(i);check(a.getLeft()>=0&&a.getRight()<=layout.getWidth(),"button within page");for(int j=i+1;j<layout.getChildCount();j++){View b=layout.getChildAt(j);if(a.getTop()==b.getTop())check(b.getLeft()-a.getRight()>=MobileStyle.dp(app,8),"horizontal gap");else if(b.getTop()>a.getTop())check(b.getTop()-a.getBottom()>=MobileStyle.dp(app,8),"vertical gap");}}}
    private void testInPlace()throws Exception{
        final View[] before={null,null};final int[] position={0};
        main(()->{before[0]=description("个性化页面");before[1]=description("个性化滚动区域");((ScrollView)before[1]).scrollTo(0,220);position[0]=((ScrollView)before[1]).getScrollY();});
        for(String name:new String[]{"天使之城浅色","相变信号深色","方块工坊浅色"}){clickDescription(name);main(()->{check(before[0]==description("个性化页面"),"colour keeps root instance");check(before[1]==description("个性化滚动区域"),"colour keeps scroll instance");check(((ScrollView)before[1]).getScrollY()==position[0],"colour keeps scroll position");check("solid".equals(prefs.getString("bg_mode",""))&&"theme".equals(prefs.getString("bg_source","")),"preset selects matching full-screen background");check(AppAppearance.backgroundColor(app)==MobileStyle.BACKGROUND,"preset background follows light/dark palette");});}
        main(()->check("minecraft".equals(MobileStyle.DESIGN),"latest Web template applied"));String chosen=prefs.getString("theme_preset","");click("原神");main(()->{check(find("此分类暂无模板")!=null,"empty category is honest");check(chosen.equals(prefs.getString("theme_preset","")),"category does not change theme");});click("全部");
        main(()->activity.onBackPressed());await(()->description("模块背景透明度")!=null,2000,"theme opacity");
        int image=prefs.getInt("bg_transparency",2);main(()->{SeekBar bar=(SeekBar)description("模块背景透明度");check(bar.getMax()==5,"six module opacity stops");Bundle args=new Bundle();args.putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,3);check(bar.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),args),"user changes module opacity");check(prefs.getInt("module_transparency",0)==3,"module opacity persisted");check(Color.alpha(MobileStyle.MODULE)==102,"module alpha independent");check(prefs.getInt("bg_transparency",2)==image,"image opacity untouched");args.putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,0);bar.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),args);});
    }
    private void testControls()throws Exception{
        prefs.edit().putString("theme_source","acm").putInt("theme_primary",0xff83b8e5).apply();main(()->activity.finish());activity=test.startActivitySync(new Intent().setClassName(app,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));await(()->description("筛选社区话题")!=null,5000,"forum rebuilt with new palette");
        main(()->{View icon=description("猫娘代码标志"),graph=description("网页同款最短路径图谱"),copy=description("社区横幅文字");check(icon!=null&&graph!=null,"both heading artworks present");int[] a=new int[2],b=new int[2],c=new int[2];icon.getLocationOnScreen(a);graph.getLocationOnScreen(b);copy.getLocationOnScreen(c);check(a[0]+icon.getWidth()>=b[0]+graph.getWidth()-MobileStyle.dp(app,2)&&a[1]<b[1],"code mark at upper right of graph");check(c[0]+copy.getWidth()<=b[0],"text and interactive graph never overlap");});
        clickDescription("排名");await(()->find("近7日")!=null,4000,"rank filters");main(()->{View date=find("近7日");check(date.isSelected(),"date selected state");check(fill(date)==MobileStyle.ACCENT,"date follows chosen accent");});screenshot("rank-v026.png");
        clickDescription("题库");await(()->find("全部题目")!=null&&find("Codeforces")!=null&&find("Codeforces").getWidth()>0,5000,"problem filters laid out");main(()->{check(walk(decor(),v->v instanceof HorizontalScrollView)==null,"problem filters never scroll horizontally");View platform=find("Codeforces");check(platform.isSelected(),"default platform is CF");WrapLayout wrap=(WrapLayout)platform.getParent();checkRows(wrap);int required=MobileStyle.dp(app,8)*(wrap.getChildCount()-1);for(int i=0;i<wrap.getChildCount();i++)required+=wrap.getChildAt(i).getWidth();if(required>wrap.getWidth())check(wrap.getChildAt(wrap.getChildCount()-1).getTop()>wrap.getChildAt(0).getTop(),"platform buttons wrap when they do not fit");check(fill(platform)==MobileStyle.ACCENT,"problem filter follows accent");ViewGroup tool=(ViewGroup)description("社团题单");check(fill(tool.getChildAt(0))==MobileStyle.SELECTED,"training icon background follows theme");});screenshot("problems-v026.png");
    }
    private int fill(View view){Bitmap b=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);android.graphics.drawable.Drawable background=view.getBackground();background.setBounds(0,0,b.getWidth(),b.getHeight());background.draw(new Canvas(b));int color=b.getPixel(b.getWidth()/2,b.getHeight()/2);b.recycle();return color;}
    private void checkBackground()throws Exception{
        main(()->{Bitmap b=Bitmap.createBitmap(200,300,Bitmap.Config.ARGB_8888);android.graphics.drawable.Drawable d=ProfileCover.drawable(app);d.setBounds(0,0,200,300);d.draw(new Canvas(b));check(b.getPixel(100,5)!=b.getPixel(100,285),"background spans screen");check(b.getPixel(100,285)==Color.WHITE,"gradient bottom white");b.recycle();});
        Bitmap image=Bitmap.createBitmap(200,300,Bitmap.Config.ARGB_8888);image.eraseColor(0xff8844cc);File file=new File(app.getCacheDir(),"appearance-test.png");try(FileOutputStream out=new FileOutputStream(file)){image.compress(Bitmap.CompressFormat.PNG,100,out);}ProfileCover.save(app,android.net.Uri.fromFile(file));file.delete();image.recycle();
        prefs.edit().putString("bg_mode","image").putInt("bg_transparency",2).apply();main(()->activity.finish());activity=test.startActivitySync(new Intent().setClassName(app,AppearanceActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));click("背景选择");await(()->description("背景透明度") instanceof SeekBar,3000,"image options restored");
        main(()->{SeekBar seek=(SeekBar)description("背景透明度");check(seek.getMax()==5&&seek.getProgress()==2,"six transparency stops default 40 percent");});screenshot("background-image-v025.png");
        click("使用渐变背景");await(()->find("与主题同色")!=null,3000,"background options restored");
    }
    private void checkArt(){
        prefs.edit().putString("theme_source","acm").putInt("theme_primary",0xff83b8e5).apply();AppAppearance.load(app);
        for(int resource:new int[]{R.drawable.avatar_catgirl,R.drawable.catgirl_loading}){
            Bitmap source=BitmapFactory.decodeResource(app.getResources(),resource),mask=BitmapFactory.decodeResource(app.getResources(),resource==R.drawable.avatar_catgirl?R.drawable.avatar_color_mask:R.drawable.loading_color_mask),colored=CharacterArt.bitmap(app,resource);int[] changes=new int[3];
            // The supplied PNGs contain mostly alpha 253/254, not fully opaque pixels.
            // Allow one premultiply/unpremultiply rounding step when checking fixed regions.
            for(int y=0;y<source.getHeight();y++)for(int x=0;x<source.getWidth();x++){int original=source.getPixel(x,y),group=mask.getPixel(x,y)&0xffffff,current=colored.getPixel(x,y);if(Color.alpha(original)<200)continue;if(group==0){for(int shift:new int[]{0,8,16,24})check(Math.abs(((original>>>shift)&255)-((current>>>shift)&255))<=2,"protected skin/ears/collar/cuffs stay unchanged");}else if(original!=current)changes[group==0xff0000?0:group==0x00ff00?1:2]++;}
            check(changes[0]>100&&changes[2]>30,"hair/eyes and bows respond to theme: resource="+resource+", counts="+Arrays.toString(changes));if(resource==R.drawable.catgirl_loading)check(changes[1]>100,"clothing responds independently");source.recycle();mask.recycle();
        }
        prefs.edit().putInt("theme_primary",0xffebafc5).apply();AppAppearance.load(app);
    }
    private void testReconnect()throws Exception{
        final PageRefresh[] refresh={null};final TextView[] text={null};AtomicInteger reads=new AtomicInteger();
        main(()->{LinearLayout root=new LinearLayout(activity);root.setOrientation(1);activity.setContentView(root);refresh[0]=new PageRefresh(activity,root,0);refresh[0].reset(1);refresh[0].register(1,()->{reads.incrementAndGet();refresh[0].start(1);});refresh[0].start(1);refresh[0].failure("无网络");refresh[0].finish(1);text[0]=(TextView)((LinearLayout)root.getChildAt(0)).getChildAt(0);});
        Thread.sleep(8500);main(()->check(((View)text[0].getParent()).getVisibility()!=View.VISIBLE,"no warning before 10 seconds"));
        await(()->"API连接失败".contentEquals(text[0].getText())&&((View)text[0].getParent()).getVisibility()==View.VISIBLE,3000,"10 second failure banner");check(reads.get()>0,"background retry continues");Thread.sleep(1100);main(()->check(((View)text[0].getParent()).getVisibility()==View.VISIBLE,"warning remains open"));
        main(()->refresh[0].finish(1));await(()->"重连成功".contentEquals(text[0].getText()),1000,"green recovery");Thread.sleep(3300);main(()->{check(((View)text[0].getParent()).getVisibility()==View.GONE,"recovery hides after 3 seconds");refresh[0].close();});
    }
    private void main(Runnable work){Throwable[] error={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){error[0]=e;}});if(error[0]!=null)throw new AssertionError(error[0]);}
    private View decor(){return activity.getWindow().getDecorView();}
    private View walk(View root,java.util.function.Predicate<View> match){if(root.getVisibility()==View.GONE)return null;if(match.test(root))return root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String value){return walk(decor(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private View description(String value){return walk(decor(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void click(String value){main(()->{View v=find(value);check(v!=null,"missing "+value);v.performClick();});test.waitForIdleSync();}
    private void clickDescription(String value){main(()->{View v=description(value);check(v!=null,"missing "+value);v.performClick();});test.waitForIdleSync();}
    private void await(java.util.function.BooleanSupplier check,long millis,String message)throws Exception{long end=System.currentTimeMillis()+millis;while(System.currentTimeMillis()<end){boolean[] passed={false};main(()->passed[0]=check.getAsBoolean());if(passed[0])return;Thread.sleep(70);}throw new AssertionError(message);}
    private void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private void screenshot(String name)throws Exception{Thread.sleep(180);Bitmap b=test.getUiAutomation().takeScreenshot();check(b!=null,"screenshot available");try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}finally{b.recycle();}}
    private static final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}@Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}@Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=appearance-fixture; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public int getResponseCode(){return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}
        @Override public InputStream getInputStream(){String p=url.getPath(),body="{}";
            if(p.endsWith("/auth/me"))body="{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            else if(p.endsWith("/categories"))body="[{\"id\":1,\"name\":\"求助\",\"slug\":\"help\"}]";
            else if(p.endsWith("/me/profile"))body="{\"user\":{\"name\":\"Isolated UI member\",\"qq_id\":\"90000001\"},\"platform_counts\":{\"codeforces\":12,\"luogu\":8,\"atcoder\":5,\"nowcoder\":3,\"cjlu\":2},\"total_count\":30,\"recent_ac\":[]}";
            else if(p.contains("/mine/")||p.endsWith("/drafts"))body="[]";
            else if(p.endsWith("/forum/posts"))body="{\"rows\":[],\"total\":0}";
            else if(p.endsWith("/community/leaderboard"))body="{\"rows\":[],\"total\":0,\"page\":1}";
            else if(p.endsWith("/me/problems"))body="{\"items\":[],\"total\":0,\"page\":1}";
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));}
    }
}
