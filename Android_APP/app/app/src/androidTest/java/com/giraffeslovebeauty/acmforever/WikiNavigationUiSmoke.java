package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.*;
import android.view.*;
import android.webkit.WebView;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.*;

/** Public Wiki contract plus real sanitized WebView/native ScrollView navigation. */
final class WikiNavigationUiSmoke {
    private final Instrumentation test;private final Context context;private ApiClient api;private Activity activity;
    private final List<Activity> pages=new ArrayList<>();private final List<String> requests=Collections.synchronizedList(new ArrayList<>());
    private volatile boolean directoryDown,categoryDown;private String markdown;
    private WikiNavigationUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new WikiNavigationUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int status=Activity.RESULT_CANCELED;main(()->{});AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> before=new HashMap<>(prefs.getAll());
        try{
            markdown="# 图论入门\n\n[跳到复杂度](#复杂度)\n\n[外部Wiki](https://outside.test.invalid/wiki.html?slug=outside)\n\n## Dijkstra\n\n"+paragraphs(24)+"\n```cpp\n# 这不是章节\nint main() {}\n```\n\n## Dijkstra\n\n"+paragraphs(24)+"\n### 复杂度\n\n"+paragraphs(32)+"\n<script>window.untrustedExecuted = true</script>";
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"wiki.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://wiki.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();api.setBaseUrl("https://wiki.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=open("wiki",null);await(()->has("算法")&&has("图论 · 2 篇文章")&&has("1 个小类 · 2 篇文章"),"complete public directory and counts");
            clickDescription("浏览Wiki分类 图论");await(()->has("下级分类")==false&&has("最短路讲解")&&description("返回Wiki分类 算法")!=null,"category path and articles");check(requests.stream().anyMatch(s->s.equals("/api/wiki/categories/2")),"existing category detail API");
            click("阅读文章");ready();WikiOutline initial=new WikiOutline(new JSONObject(js("AcmReader.layout()")));check(initial.headings.size()==4,"fenced code is not a heading");check(initial.find("dijkstra")!=null&&initial.find("dijkstra-2")!=null,"duplicate heading ids remain unique");check("undefined".equals(js("typeof window.untrustedExecuted")),"untrusted script never runs");
            check(description("Wiki分类路径")!=null&&description("Wiki文章标签")!=null&&has("最短路"),"article breadcrumb and real tags");
            click("文章目录");ListView first=chapters();check(first!=null&&first.getAdapter().getCount()==4,"all rendered headings in native picker");click("关闭窗口");
            choose("dijkstra-2");await(()->scroll().getScrollY()>1500,"second duplicate section jumps independently");
            choose("复杂度");await(()->current().contains("复杂度"),"current chapter highlight");check(Math.abs(relativeTop("复杂度")-dp(12))<dp(5),"jump aligns the outer native viewport");
            main(()->scroll().scrollBy(0,dp(100)));float position=relativeTop("复杂度");recreate();ready();await(()->current().contains("复杂度")&&scroll().getScrollY()>1500,"rotation restores chapter");check(Math.abs(relativeTop("复杂度")-position)<dp(16),"rotation preserves offset within chapter");
            click("知识目录");await(()->has("知识目录")&&has("图论 · 2 篇文章"),"directory from article");back();ready();await(()->current().contains("复杂度"),"directory return restores reading position");
            clickDescription("返回Wiki分类 图论");await(()->has("公开文章 · 共 2 篇"),"breadcrumb category navigation");back();ready();await(()->current().contains("复杂度"),"breadcrumb return restores chapter");
            click("公开历史");await(()->has("历史版"),"public history list");clickPrefix("历史版");ready();WikiOutline historical=new WikiOutline(new JSONObject(js("AcmReader.layout()")));check(historical.find("旧版章节")!=null&&historical.find("dijkstra")==null,"history uses its own headings");check(has("正在阅读历史版本")&&has("阅读当前版本"),"historical version labelled");back();back();ready();await(()->current().contains("复杂度"),"history return restores current version chapter");
            main(()->scroll().scrollTo(0,0));await(()->current().contains("图论入门"),"upward scrolling updates highlight");check("#复杂度".equals(js("decodeURIComponent(document.querySelector('a[href^=\"#\"]').getAttribute('href'))")),"rendered fragment targets the real heading");tapLink("a[href^=\"#\"]");await(()->current().contains("复杂度"),"in-body fragment uses native chapter navigation");
            AtomicInteger external=new AtomicInteger();Instrumentation.ActivityMonitor browser=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_VIEW.equals(intent.getAction())){check("https://outside.test.invalid/wiki.html?slug=outside".equals(String.valueOf(intent.getData())),"external Wiki URL is not captured as internal");external.incrementAndGet();return new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);}return null;}};
            test.addMonitor(browser);try{tapLink("a[href*=\"outside.test.invalid\"]");await(()->external.get()==1,"external HTTPS stays external");}finally{test.removeMonitor(browser);}
            js("const spacer=document.createElement('div');spacer.style.height='240px';document.getElementById('复杂度').before(spacer);true");Thread.sleep(1300);choose("复杂度");check(Math.abs(relativeTop("复杂度")-dp(12))<dp(7),"late content resizing updates chapter coordinates");await(()->current().contains("复杂度"),"fractional heading coordinates retain the correct highlight");
            screenshot("wiki-reader-navigation.png");click("文章目录");screenshot("wiki-chapters.png");click("关闭窗口");
            Activity original=activity;Instrumentation.ActivityMonitor problem=test.addMonitor(MainActivity.class.getName(),null,false);try{click("站内练习");Activity opened=test.waitForMonitorWithTimeout(problem,10000);check(opened!=null,"native problem opens");activity=opened;pages.add(opened);await(()->has("Wiki关联题面")&&has("样例 1"),"native statement and samples");back();activity=original;ready();await(()->current().contains("复杂度"),"practice returns to the same reader");}finally{test.removeMonitor(problem);}
            directoryDown=true;int directoryReads=count("/api/wiki/navigation");activity=open("wiki-article","dijkstra");ready();check(count("/api/wiki/navigation")==directoryReads,"directory availability never blocks a direct article");directoryDown=false;
            activity=open("wiki",null);await(()->has("工具"),"directory recovered");categoryDown=true;clickDescription("浏览Wiki分类 工具");await(()->has("服务器异常")&&has("暂无公开文章")&&has("API连接失败"),"category failure independent of empty article list and banner");categoryDown=false;
            activity=open("wiki-article","plain");await(()->current().contains("本文暂无章节目录"),"no headings stays honest");click("文章目录");check(has("本文暂无章节目录")&&chapters()==null,"no invented chapters");click("关闭窗口");
            api.logout();activity=open("wiki-article","dijkstra");ready();check(!api.isLoggedIn()&&has("最短路讲解"),"public reading needs no login");
            for(String request:requests)check(!request.startsWith("WRITE:"),"navigation does not perform business writes");
            output.putString("stream","PASS: public hierarchy/counts/category paths and tags; all rendered headings and unique duplicates; code fence and script exclusion; native chapter picker, scrolling highlight and fragment jumps; chapter/offset restoration after rotation, directory/breadcrumb/history/practice return; distinct historical outline; late layout changes; external Wiki links stay external; category failure independent of article list; direct articles independent of directory; empty outline; anonymous reading. No production requests or business writes.\n");status=Activity.RESULT_OK;
        }catch(Throwable error){StringBuilder visible=new StringBuilder();if(activity!=null)main(()->walk(decor(),v->{if(v instanceof TextView)visible.append(((TextView)v).getText()).append(" | ");return false;}));output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\nUI: "+visible+"\nRequests: "+requests);}
        finally{for(int i=pages.size()-1;i>=0;i--){Activity page=pages.get(i);main(()->{ModalDialogs.close(page);page.finish();});}try{api.logout();}catch(Exception ignored){}api.setBaseUrl(base);SharedPreferences.Editor restore=prefs.edit().clear();for(Map.Entry<String,?> e:before.entrySet()){Object value=e.getValue();String key=e.getKey();if(value instanceof String)restore.putString(key,(String)value);else if(value instanceof Boolean)restore.putBoolean(key,(Boolean)value);else if(value instanceof Integer)restore.putInt(key,(Integer)value);else if(value instanceof Long)restore.putLong(key,(Long)value);else if(value instanceof Float)restore.putFloat(key,(Float)value);}restore.apply();AppAppearance.load(context);}test.finish(status,output);
    }
    private String paragraphs(int count){StringBuilder source=new StringBuilder();for(int i=0;i<count;i++)source.append("这是算法讲解的真实排版测试段落，用于验证长文章滚动、标题定位和恢复阅读位置。第 ").append(i+1).append(" 段。\n\n");return source.toString();}
    private Activity open(String feature,String slug){Intent intent=new Intent(context,WebFeaturesActivity.class).putExtra("feature",feature).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_MULTIPLE_TASK);if(slug!=null)intent.putExtra("wiki_slug",slug);Activity page=test.startActivitySync(intent);pages.add(page);return page;}
    private void recreate(){Activity old=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(old.getClass().getName(),null,false);try{main(old::recreate);activity=test.waitForMonitorWithTimeout(monitor,10000);check(activity!=null,"reader recreated");pages.add(activity);}finally{test.removeMonitor(monitor);}}
    private int dp(float value){return MobileStyle.dp(context,value);}
    private ScrollView scroll(){return (ScrollView)walk(activity.getWindow().getDecorView(),v->v instanceof ScrollView);}
    private ContentView reader(){return (ContentView)description("Wiki文章正文");}
    private String current(){View view=description("Wiki当前章节");return view instanceof TextView?((TextView)view).getText().toString():"";}
    private void ready()throws Exception{await(()->reader()!=null&&current().startsWith("当前：")&&reader().getHeight()>dp(100),"rendered Wiki headings");test.waitForIdleSync();}
    private String js(String code)throws Exception{AtomicReference<String> value=new AtomicReference<>();CountDownLatch latch=new CountDownLatch(1);main(()->{check(reader()!=null,"reader exists");reader().evaluateJavascript(code,result->{value.set(result);latch.countDown();});});check(latch.await(15,TimeUnit.SECONDS),"local reader JavaScript replied");String result=value.get();if(result!=null&&result.startsWith("\""))return new JSONArray("["+result+"]").getString(0);return result;}
    private float relativeTop(String id)throws Exception{WikiOutline metrics=new WikiOutline(new JSONObject(js("AcmReader.layout()")));WikiOutline.Heading heading=metrics.find(id);check(heading!=null,"requested actual heading");float[] top={0};main(()->{int[] r=new int[2],s=new int[2];reader().getLocationInWindow(r);scroll().getLocationInWindow(s);top[0]=r[1]-s[1]+dp(heading.top);});return top[0];}
    private void tapLink(String selector)throws Exception{
        String result=js("(()=>{const link=document.querySelector("+JSONObject.quote(selector)+");if(!link)return {missing:[...document.querySelectorAll('a')].map(a=>a.getAttribute('href'))};const r=link.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()");JSONObject rect=new JSONObject(result);check(!rect.has("missing"),"rendered link exists: "+result);int x=dp((float)rect.getDouble("x")),y=dp((float)rect.getDouble("y"));int[] point=new int[2];
        main(()->{int[] r=new int[2],s=new int[2];reader().getLocationOnScreen(r);scroll().getLocationOnScreen(s);scroll().scrollTo(0,Math.max(0,scroll().getScrollY()+r[1]-s[1]+y-dp(80)));});test.waitForIdleSync();Thread.sleep(150);
        main(()->{reader().getLocationOnScreen(point);point[0]+=x;point[1]+=y;});long down=SystemClock.uptimeMillis();MotionEvent press=MotionEvent.obtain(down,down,MotionEvent.ACTION_DOWN,point[0],point[1],0),release=MotionEvent.obtain(down,down+100,MotionEvent.ACTION_UP,point[0],point[1],0);try{test.sendPointerSync(press);test.sendPointerSync(release);}finally{press.recycle();release.recycle();}test.waitForIdleSync();
    }
    private View decor(){try{java.lang.reflect.Field field=ModalDialogs.class.getDeclaredField("visible");field.setAccessible(true);Object ref=((Map<?,?>)field.get(null)).get(activity);AlertDialog modal=ref instanceof java.lang.ref.WeakReference?(AlertDialog)((java.lang.ref.WeakReference<?>)ref).get():null;return modal!=null&&modal.isShowing()?modal.getWindow().getDecorView():activity.getWindow().getDecorView();}catch(Exception error){throw new AssertionError(error);}}
    private View walk(View view,Predicate<View> match){if(view.getVisibility()!=View.VISIBLE)return null;if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private boolean has(String value){return walk(decor(),v->v instanceof TextView&&((TextView)v).getText().toString().contains(value))!=null;}
    private View description(String value){return walk(decor(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void clickDescription(String value){main(()->{View v=description(value);check(v!=null&&v.isEnabled(),"control "+value);v.performClick();});test.waitForIdleSync();}
    private void click(String value){main(()->{View v=walk(decor(),item->item instanceof TextView&&value.contentEquals(((TextView)item).getText()));if(v==null)v=description(value);while(v!=null&&!v.isClickable()&&v.getParent() instanceof View)v=(View)v.getParent();check(v!=null&&v.isEnabled(),"button "+value);v.performClick();});test.waitForIdleSync();}
    private void clickPrefix(String value){main(()->{View v=walk(decor(),item->item instanceof TextView&&((TextView)item).getText().toString().startsWith(value)&&item.isClickable());check(v!=null,"prefix "+value);v.performClick();});test.waitForIdleSync();}
    private ListView chapters(){return (ListView)description("Wiki章节目录列表");}
    private void choose(String id){click("文章目录");main(()->{ListView list=chapters();check(list!=null,"chapter picker");for(int i=0;i<list.getAdapter().getCount();i++){WikiOutline.Heading heading=(WikiOutline.Heading)list.getAdapter().getItem(i);if(id.equals(heading.id)){list.performItemClick(list.getAdapter().getView(i,null,list),i,i);return;}}throw new AssertionError("No chapter "+id);});test.waitForIdleSync();}
    private void back(){main(activity::onBackPressed);test.waitForIdleSync();}
    private void main(Runnable work){if(Looper.myLooper()==Looper.getMainLooper()){work.run();return;}Throwable[] problem={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable error){problem[0]=error;}});if(problem[0]!=null)throw new AssertionError(problem[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+18000;while(SystemClock.uptimeMillis()<until){test.waitForIdleSync();boolean[] result={false};main(()->result[0]=ready.getAsBoolean());if(result[0])return;Thread.sleep(60);}throw new AssertionError("Timeout: "+label);}
    private int count(String prefix){synchronized(requests){int n=0;for(String path:requests)if(path.startsWith(prefix))n++;return n;}}
    private static void check(boolean okay,String message){if(!okay)throw new AssertionError(message);}
    private void screenshot(String name)throws Exception{test.waitForIdleSync();Thread.sleep(350);Bitmap picture=test.getUiAutomation().takeScreenshot();check(picture!=null,"screenshot available");try(FileOutputStream out=new FileOutputStream(new File(context.getExternalFilesDir(null),name))){picture.compress(Bitmap.CompressFormat.PNG,100,out);}finally{picture.recycle();}}
    private JSONObject category(int id,Integer parent,String name,int total)throws Exception{return new JSONObject().put("id",id).put("parent_id",parent==null?JSONObject.NULL:parent).put("name",name).put("published_count",total);}
    private JSONArray categories()throws Exception{return new JSONArray().put(category(1,null,"算法",2)).put(category(2,1,"图论",2)).put(category(3,null,"工具",0));}
    private final class Fixture extends HttpURLConnection{
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public int getResponseCode(){if(directoryDown&&url.getPath().equals("/api/wiki/navigation")||categoryDown&&url.getPath().equals("/api/wiki/categories/3"))return 503;return 200;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().equals("/api/auth/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic-wiki; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return stream("{\"message\":\"Synthetic temporary failure\"}");}
        public InputStream getInputStream()throws IOException{
            String path=url.getPath();requests.add(("GET".equals(getRequestMethod())||path.startsWith("/api/auth/")?"":"WRITE:")+url.getFile());
            try{
                if(path.equals("/api/auth/login")||path.equals("/api/auth/logout"))return stream("{}");
                if(path.equals("/api/auth/me"))return stream("{\"authenticated\":true,\"csrf_token\":\"wiki-csrf\",\"qq_id\":\"90000001\",\"role\":\"member\"}");
                if(path.equals("/api/wiki/navigation"))return stream(new JSONObject().put("categories",categories()).put("default_category_id",1).toString());
                if(path.startsWith("/api/wiki/categories/")){int id=Integer.parseInt(path.substring(path.lastIndexOf('/')+1));JSONArray all=categories(),trail=new JSONArray(),children=new JSONArray();JSONObject selected=null;for(int i=0;i<all.length();i++){JSONObject row=all.getJSONObject(i);if(row.getInt("id")==id)selected=row;if(!row.isNull("parent_id")&&row.getInt("parent_id")==id)children.put(row);}check(selected!=null,"known category");if(id==2)trail.put(all.getJSONObject(0));trail.put(selected);return stream(new JSONObject().put("category",selected).put("path",trail).put("children",children).toString());}
                if(path.equals("/api/wiki/pages")||path.equals("/api/wiki/search")){String id=android.net.Uri.parse(url.toString()).getQueryParameter("category_id");JSONArray rows=new JSONArray();if(!"3".equals(id))rows.put(new JSONObject().put("slug","dijkstra").put("title","最短路讲解").put("summary","示例讲解").put("tags",new JSONArray().put("最短路"))).put(new JSONObject().put("slug","plain").put("title","无章节文章").put("summary","普通段落"));return stream(new JSONObject().put("items",rows).put("total",rows.length()).toString());}
                if(path.endsWith("/revisions"))return stream("[{\"id\":2,\"title\":\"历史版\",\"published_at\":1700000000}]");
                if(path.startsWith("/api/wiki/pages/")){boolean plain=path.endsWith("/plain"),old=path.endsWith("/revisions/2");return stream(new JSONObject().put("title",plain?"无章节文章":old?"历史版":"最短路讲解").put("body",plain?"这是没有标题的普通正文。":old?"# 旧版章节\n\n"+paragraphs(8):markdown).put("summary","公开讲解").put("path",new JSONArray().put(new JSONObject().put("id",1).put("name","算法")).put(new JSONObject().put("id",2).put("name","图论"))).put("tags",new JSONArray().put("最短路").put("图论")).put("source","合成测试来源").put("license","CC BY 4.0").put("exercises",new JSONArray().put(new JSONObject().put("label","站内练习").put("url","/problem.html?platform=codeforces&problem_id=123A"))).toString());}
                if(path.equals("/api/me/problems/codeforces/123A"))return stream("{\"platform\":\"codeforces\",\"problem_id\":\"123A\",\"problem_name\":\"Wiki关联题面\",\"content_available\":true,\"statement_text\":\"Native practice statement\",\"samples\":[{\"input\":\"1 2\",\"output\":\"3\"}]}");
                if(path.equals("/api/mobile/v1/capabilities"))return stream("{\"api_version\":1,\"features\":{}}");return stream("[]");
            }catch(Exception error){throw new IOException(error);}
        }
        private InputStream stream(String value){return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));}
    }
}
