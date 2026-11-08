package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.*;

/** Test APK only. Real Activities against a synthetic exact-label/keyword/paging contract. */
final class ProblemTagsUiSmoke {
    private final Instrumentation test; private final Context context; private ApiClient api; private Activity activity;
    private final List<Activity> pages=new ArrayList<>(); private final List<String> requests=Collections.synchronizedList(new ArrayList<>());
    private final List<JSONObject> catalog=new ArrayList<>(); private volatile int tagStatus=200; private volatile String badPlatform="";
    private ProblemTagsUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new ProblemTagsUiSmoke(test).run();}
    private void run(){
        Bundle output=new Bundle();int status=Activity.RESULT_CANCELED;main(()->{});
        AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String base=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> before=new HashMap<>(prefs.getAll());
        try{
            for(int i=1;i<=24;i++)catalog.add(problem("codeforces","DP"+i,"Needle DP "+i,new JSONArray().put("dp").put("math"),i<=10,i<=2));
            catalog.add(problem("codeforces","DIGIT","Needle digit-only",new JSONArray().put("digit dp"),false,false));
            catalog.add(problem("codeforces","MATH","Needle mathematics-only",new JSONArray().put("mathematics"),false,false));
            catalog.add(problem("codeforces","SPECIAL","A&B 中文",new JSONArray().put("%_& 中文"),false,false));
            catalog.add(problem("atcoder","abc100_a","Needle AtCoder",new JSONArray().put("math"),true,false));
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{if(!"tags.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putBoolean("auto_login",false).putBoolean("app_update_automatic",false).putString(SearchModules.KEY,"[\"users\",\"forum\",\"wiki\",\"problems\",\"tracker\"]").apply();
            api.setBaseUrl("https://tags.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=open(MainActivity.class,new Intent());show("problems");await(()->has("共 27 道题目"),"native catalog");
            await(()->description("难度 800")!=null&&description("算法标签：dp")!=null&&description("算法标签：math")!=null,"catalog directly exposes real difficulty and whole tags");
            editDescription("题库搜索关键词","Needle");clickDescription("搜索题库");await(()->has("共 26 道题目"),"keyword search");
            clickDescription("筛选题库标签");await(()->candidateCount()>0,"real catalog tags");editDescription("搜索题目标签","DP");await(()->candidateCount()==2,"search candidates includes both dp and digit dp");screenshot("problem-tags-picker.png");pick("dp");
            await(()->has("共 24 道题目")&&has("题目标签：dp"),"exact dp excludes digit-only and title-only");check(!has("digit-only"),"not fuzzy label match");
            click("下一页");await(()->nativePage()==2&&has("共 24 道题目"),"native pagination retains tag");checkParam(last("/api/me/problems"),"problem_tag","dp");checkParam(last("/api/me/problems"),"tag","Needle");
            click("查看题面与样例");await(()->has("按题讨论 / 加入错题本"),"native detail");
            verifyStatementTypography();screenshot("problem-typography-v0224.png");
            main(activity::onBackPressed);await(()->nativePage()==2&&has("题目标签：dp"),"back stack retains keyword tag page");
            recreate();await(()->nativePage()==2&&has("共 24 道题目"),"native rotation");check("Needle".contentEquals(inputDescription("题库搜索关键词").getText()),"keyword restored");
            click("我已 AC");await(()->has("共 10 道题目"),"AC and exact label combine");click("已收藏");await(()->has("共 2 道题目"),"favorite and solved combine");
            checkParam(last("/api/me/problems"),"scope","solved");checkParam(last("/api/me/problems"),"state","favorite");checkParam(last("/api/me/problems"),"problem_tag","dp");
            click("清除搜索与标签");await(()->has("题目标签：全部标签")&&has("共 2 道题目"),"clear only keyword and tag");
            click("全部题目");click("全部收藏状态");await(()->has("共 27 道题目"),"reset ranges");
            editDescription("题库搜索关键词","A&B");clickDescription("搜索题库");await(()->has("共 1 道题目"),"encoded keyword");
            clickDescription("筛选题库标签");await(()->candidateCount()>0,"special candidates");editDescription("搜索题目标签","%_&");await(()->candidateCount()==1,"literal special label");pick("%_& 中文");await(()->has("题目标签：%_& 中文")&&has("共 1 道题目"),"encoded exact label");
            checkParam(last("/api/me/problems"),"tag","A&B");checkParam(last("/api/me/problems"),"problem_tag","%_& 中文");
            click("AtCoder");await(()->has("题目标签：全部标签")&&has("没有符合条件的题目。"),"platform clears exact label but keeps keyword");checkParam(last("/api/me/problems"),"tag","A&B");
            editDescription("题库搜索关键词","Needle");clickDescription("搜索题库");await(()->has("共 1 道题目"),"AtCoder keyword");clickDescription("筛选题库标签");await(()->candidateCount()==1,"platform-specific candidates");pick("math");await(()->has("题目标签：math"),"platform selection");checkParam(last("/api/me/problems/tags"),"platform","atcoder");
            badPlatform="luogu";tagStatus=404;click("洛谷");await(()->has("没有符合条件的题目。"),"empty platform");clickDescription("筛选题库标签");await(()->has("无API接口"),"missing label API honest");editDescription("搜索题目标签","dp");check(has("无API接口")&&candidateCount()==0,"typing cannot turn missing endpoint into empty success or sample tags");click("全部标签");
            // A 404 deliberately invalidates every cached response for that endpoint. Prime a
            // genuine success again before testing a later transient 500 retaining that cache.
            tagStatus=200;click("Codeforces");await(()->has("共 26 道题目"),"cached platform list");clickDescription("筛选题库标签");await(()->candidateCount()>0,"fresh labels after endpoint recovery");click("全部标签");
            badPlatform="codeforces";tagStatus=500;clickDescription("筛选题库标签");await(()->has("保留已缓存标签")&&candidateCount()>0,"cached labels survive failed refresh");editDescription("搜索题目标签","dp");tagStatus=200;click("重新读取标签");await(()->!has("服务器异常")&&has("重连成功")&&candidateCount()==2,"manual retry recovers without waiting for another retry");pick("dp");await(()->has("共 24 道题目"),"cached real choice still filters");
            main(()->{View v=description("筛选题库标签");v.requestRectangleOnScreen(new android.graphics.Rect(0,0,v.getWidth(),v.getHeight()),true);});screenshot("problem-tags-native.png");

            activity=open(SearchActivity.class,new Intent().putExtra("query","needle"));await(()->has("Needle User")&&has("Needle forum")&&has("Needle wiki"),"other global modules unchanged");
            clickDescription("筛选题目搜索标签");await(()->candidateCount()>0,"global candidates");editDescription("搜索题目标签","dp");pick("dp");await(()->has("题目标签：dp")&&has("共 24 条"),"global keyword and exact tag");
            checkParam(last("/api/me/problems"),"problem_tag","dp");checkParam(last("/api/me/problems"),"tag","needle");checkParam(last("/api/me/problems"),"platform",null);
            click("下一页");await(()->"2".equals(param(last("/api/me/problems"),"page")),"global next page retains tag");checkParam(last("/api/me/problems"),"problem_tag","dp");
            clickDescription("筛选比赛进度搜索标签");await(()->candidateCount()>0,"tracker search candidates");editDescription("搜索题目标签","dp");pick("dp");await(()->has("比赛进度标签：dp")&&has("Needle contest"),"tracker independent exact tag");
            recreate();await(()->has("题目标签：dp")&&has("比赛进度标签：dp"),"global selections survive rotation");
            for(String request:requests)if(request.startsWith("/api/forum/")||request.startsWith("/api/wiki/")||request.startsWith("/api/community/leaderboard"))check(param(request,"problem_tag")==null,"exact labels never affect other content modules");
            activity=follow(WebFeaturesActivity.class,()->click("Needle contest"));await(()->has("题目标签：dp"),"tracker inherits exact tag");checkParam(last("/api/me/problems/tracker"),"problem_tag","dp");
            await(()->description("算法标签：dp")!=null&&description("难度 800")!=null,"tracker exposes difficulty and labels without opening details");
            int detailReads=detailReads();Thread.sleep(250);check(detailReads()==detailReads,"tracker metadata does not fan out to per-problem requests");
            screenshot("problem-tracker-v0224.png");Activity tracker=activity;
            activity=follow(MainActivity.class,()->clickDescription("DP1. Needle DP 1 · 已 AC · 难度 800 · 算法标签：dp、math"));
            await(()->description("题目标题")!=null,"tracker tile opens native statement");verifyStatementTypography();main(activity::onBackPressed);activity=tracker;
            await(()->has("题目标签：dp")&&description("算法标签：dp")!=null,"statement returns to the same tracker and filters");
            click("AtCoder");await(()->has("题目标签：全部标签"),"tracker platform reset");clickDescription("筛选比赛进度标签");await(()->candidateCount()==1,"tracker scoped candidates");pick("math");await(()->has("题目标签：math"),"native tracker filter");recreate();await(()->has("题目标签：math"),"tracker rotation retains selection");
            checkParam(last("/api/me/problems/tracker"),"problem_tag","math");checkParam(last("/api/me/problems/tracker"),"platform","atcoder");
            clickDescription("筛选比赛进度标签");await(()->candidateCount()>0,"old picker open");ListView old=candidates();api.logout();main(()->{test.callActivityOnPause(activity);test.callActivityOnResume(activity);});await(()->!ModalDialogs.isShowing(activity),"session change closes picker");
            main(()->old.performItemClick(old.getAdapter().getView(0,null,old),0,0));check(!has("题目标签：math"),"old picker callback cannot apply to new session");
            output.putString("stream","PASS: catalog and tracker expose real difficulty/whole algorithm labels without per-problem reads; real statement WebView heading/body/time/memory/code typography, sanitized script and math, no page overflow; tracker tile native statement and return; original label candidates and exact search, pagination, favorites, platform reset, rotation and stale-session protection; no production calls or business writes.\n");status=Activity.RESULT_OK;
        }catch(Throwable failure){StringBuilder visible=new StringBuilder();if(activity!=null)main(()->walk(decor(),v->{if(v instanceof TextView)visible.append(((TextView)v).getText()).append(" | ");return false;}));output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure)+"\nUI: "+visible+"\nRequests: "+requests);}
        finally{
            for(int i=pages.size()-1;i>=0;i--){Activity page=pages.get(i);main(()->{ModalDialogs.close(page);page.finish();});}
            try{api.logout();}catch(Exception ignored){}api.setBaseUrl(base);SharedPreferences.Editor restore=prefs.edit().clear();
            for(Map.Entry<String,?> entry:before.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)restore.putString(k,(String)v);else if(v instanceof Boolean)restore.putBoolean(k,(Boolean)v);else if(v instanceof Integer)restore.putInt(k,(Integer)v);else if(v instanceof Long)restore.putLong(k,(Long)v);else if(v instanceof Float)restore.putFloat(k,(Float)v);}restore.apply();AppAppearance.load(context);
        }test.finish(status,output);
    }
    private static final String STATEMENT="<div class='header'><div class='title'>Duplicate source title</div><div class='time-limit'><span class='property-title'>time limit per test</span>2 seconds</div><div class='memory-limit'><span class='property-title'>memory limit per test</span>256 megabytes</div></div><p>这是排版与安全测试题面。Find $n + 1$.</p><div class='section-title'>Input</div><h2>Constraints</h2><h3>Notes</h3><p>保留完整算法名称和说明。</p><pre>"+String.join(" ",Collections.nCopies(50,"sample"))+"</pre><script>window.problemInjected=true</script>";
    private JSONObject problem(String platform,String id,String name,JSONArray tags,boolean solved,boolean favorite)throws Exception{return new JSONObject().put("platform",platform).put("problem_id",id).put("problem_name",name).put("tags",tags).put("is_favorite",favorite).put("solved",solved).put("problem_rating",800).put("content_available",true).put("statement_html",STATEMENT).put("samples",new JSONArray());}
    private int detailReads(){int count=0;synchronized(requests){for(String path:requests)if(path.matches("/api/me/problems/(codeforces|atcoder)/.*"))count++;}return count;}
    private void verifyStatementTypography()throws Exception{
        await(()->walk(decor(),v->v instanceof ContentView)!=null,"native statement reader");
        java.util.concurrent.atomic.AtomicBoolean passed=new java.util.concurrent.atomic.AtomicBoolean();
        await(()->{ContentView reader=(ContentView)walk(decor(),v->v instanceof ContentView);reader.evaluateJavascript("(()=>{const a=document.getElementById('article'),style=s=>getComputedStyle(a.querySelector(s)),size=s=>style(s).fontSize;if(!a||!a.classList.contains('problem-reader')||!a.querySelector('pre'))return false;return getComputedStyle(a).fontSize==='16px'&&size('.section-title')==='20px'&&size('h3')==='18px'&&size('.time-limit')==='13px'&&size('.memory-limit')==='13px'&&size('pre')==='14px'&&style('.header .title').display==='none'&&a.querySelector('.time-limit').textContent.includes('2 seconds')&&a.querySelector('.memory-limit').textContent.includes('256 megabytes')&&typeof window.problemInjected==='undefined'&&a.querySelector('math')!==null&&document.documentElement.scrollWidth<=document.documentElement.clientWidth+1;})()",value->passed.set("true".equals(value)));return passed.get();},"statement heading/body/limits/code hierarchy; sanitized script and math; no page horizontal overflow");
        main(()->{TextView title=(TextView)description("题目标题");check(title!=null&&Math.abs(title.getTextSize()/context.getResources().getDisplayMetrics().scaledDensity-24)<.1,"native title is 24sp");});
    }
    private Activity open(Class<?> type,Intent intent){Activity page=test.startActivitySync(intent.setClass(context,type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));pages.add(page);return page;}
    private Activity follow(Class<?> type,Runnable work){Instrumentation.ActivityMonitor monitor=test.addMonitor(type.getName(),null,false);try{work.run();Activity page=test.waitForMonitorWithTimeout(monitor,10000);check(page!=null,"Activity opened "+type.getSimpleName());pages.add(page);return page;}finally{test.removeMonitor(monitor);}}
    private void recreate(){Activity old=activity;activity=follow(old.getClass(),()->main(old::recreate));}
    private void show(String screen){main(()->{try{java.lang.reflect.Method method=MainActivity.class.getDeclaredMethod("show",String.class);method.setAccessible(true);method.invoke(activity,screen);}catch(Exception e){throw new AssertionError(e);}});}
    private int nativePage(){try{java.lang.reflect.Field field=MainActivity.class.getDeclaredField("page");field.setAccessible(true);return field.getInt(activity);}catch(Exception e){return -1;}}
    private View decor(){try{java.lang.reflect.Field field=ModalDialogs.class.getDeclaredField("visible");field.setAccessible(true);Object ref=((Map<?,?>)field.get(null)).get(activity);AlertDialog modal=ref instanceof java.lang.ref.WeakReference?(AlertDialog)((java.lang.ref.WeakReference<?>)ref).get():null;return modal!=null&&modal.isShowing()?modal.getWindow().getDecorView():activity.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}}
    private View walk(View view,Predicate<View> match){if(view.getVisibility()!=View.VISIBLE)return null;if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private boolean has(String value){return walk(decor(),v->v instanceof TextView&&((TextView)v).getText().toString().contains(value))!=null;}
    private View description(String value){return walk(decor(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private EditText inputDescription(String value){return (EditText)description(value);}
    private void editDescription(String value,String text){main(()->{EditText input=inputDescription(value);check(input!=null,"input "+value);input.setText(text);});}
    private void clickDescription(String value){main(()->{View v=description(value);check(v!=null&&v.isEnabled(),"description "+value);v.performClick();});test.waitForIdleSync();}
    private void click(String value){main(()->{View v=walk(decor(),item->item instanceof TextView&&value.contentEquals(((TextView)item).getText()));while(v!=null&&!v.isClickable()&&v.getParent() instanceof View)v=(View)v.getParent();check(v!=null&&v.isEnabled(),"button "+value);v.performClick();});test.waitForIdleSync();}
    private ListView candidates(){return (ListView)description("题目标签候选列表");}
    private int candidateCount(){ListView list=candidates();return list==null?-1:list.getAdapter().getCount();}
    private void pick(String value){main(()->{ListView list=candidates();check(list!=null,"candidate list");for(int i=0;i<list.getAdapter().getCount();i++)if(value.equals(list.getAdapter().getItem(i))){list.performItemClick(list.getAdapter().getView(i,null,list),i,i);return;}throw new AssertionError("Missing actual tag "+value);});test.waitForIdleSync();}
    private void main(Runnable work){if(Looper.myLooper()==Looper.getMainLooper()){work.run();return;}Throwable[] failure={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){failure[0]=e;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){test.waitForIdleSync();boolean[] value={false};main(()->value[0]=ready.getAsBoolean());if(value[0])return;Thread.sleep(70);}throw new AssertionError("Timeout: "+label);}
    private String last(String path){synchronized(requests){for(int i=requests.size()-1;i>=0;i--)if(Uri.parse("https://tags.test.invalid"+requests.get(i)).getPath().equals(path))return requests.get(i);}return "";}
    private static String param(String path,String key){return Uri.parse("https://tags.test.invalid"+path).getQueryParameter(key);}
    private static void checkParam(String path,String key,String expected){check(Objects.equals(expected,param(path,key)),"parameter "+key+" expected="+expected+" got="+param(path,key));}
    private static void check(boolean yes,String message){if(!yes)throw new AssertionError(message);}
    private void screenshot(String name)throws Exception{
        check(name.matches("[a-z0-9-]+\\.png"),"fixed test screenshot name");test.waitForIdleSync();Thread.sleep(200);
        // Shell-owned output survives the old/new package UID changes in covering tests.
        try(ParcelFileDescriptor capture=test.getUiAutomation().executeShellCommand("screencap -p /data/local/tmp/"+name);InputStream done=new FileInputStream(capture.getFileDescriptor())){while(done.read()!=-1){}}
    }
    private final class Fixture extends HttpURLConnection{
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public int getResponseCode(){return url.getPath().equals("/api/me/problems/tags")&&badPlatform.equals(param(url.getFile(),"platform"))?tagStatus:200;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().equals("/api/auth/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic-tags; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return stream("{\"message\":\"Synthetic unavailable endpoint\"}");}
        public InputStream getInputStream()throws IOException{
            String path=url.getPath();requests.add(url.getFile());
            try{
                if(path.equals("/api/auth/login")||path.equals("/api/auth/logout"))return stream("{\"success\":true}");
                check("GET".equals(getRequestMethod()),"no business writes during filter test");
                if(path.equals("/api/auth/me"))return stream("{\"authenticated\":true,\"csrf_token\":\"tags-csrf\",\"qq_id\":\"90000001\",\"role\":\"member\",\"account_epoch\":1}");
                if(path.equals("/api/me/problems/tags")){
                    Set<String> tags=new LinkedHashSet<>();String platform=param(url.getFile(),"platform");
                    for(JSONObject item:catalog)if(platform==null||platform.isEmpty()||platform.equals(item.getString("platform")))for(int i=0;i<item.getJSONArray("tags").length();i++)tags.add(item.getJSONArray("tags").getString(i));
                    return stream(new JSONObject().put("tags",new JSONArray(tags)).toString());
                }
                if(path.equals("/api/me/problems")){
                    List<JSONObject> selected=filtered();int page=Integer.parseInt(param(url.getFile(),"page")),size=Integer.parseInt(param(url.getFile(),"page_size"));JSONArray rows=new JSONArray();for(int i=(page-1)*size;i<Math.min(selected.size(),page*size);i++)rows.put(selected.get(i));
                    return stream(new JSONObject().put("items",rows).put("total",selected.size()).put("page",page).put("page_size",size).toString());
                }
                if(path.equals("/api/me/problems/tracker")){
                    JSONArray rows=new JSONArray();String platform=param(url.getFile(),"platform");if(platform==null||platform.isEmpty())platform="codeforces";
                    List<JSONObject> problems=filtered();JSONArray all=new JSONArray();for(JSONObject p:problems)if(platform.equals(p.getString("platform")))all.put(new JSONObject(p.toString()).put("problem_index",p.getString("problem_id")).put("status","solved"));
                    if(all.length()>0)rows.put(new JSONObject().put("platform",platform).put("contest_id","123").put("contest_name","Needle contest").put("total_count",all.length()).put("solved_count",all.length()).put("problems",all));
                    return stream(new JSONObject().put("items",rows).put("total",rows.length()).toString());
                }
                if(path.startsWith("/api/me/problems/")){String id=path.substring(path.lastIndexOf('/')+1);for(JSONObject item:catalog)if(id.equals(item.getString("problem_id")))return stream(item.toString());}
                if(path.equals("/api/mobile/v1/capabilities"))return stream("{\"api_version\":1,\"features\":{}}");
                if(path.equals("/api/community/leaderboard"))return stream("{\"rows\":[{\"name\":\"Needle User\",\"total_count\":0}],\"total\":1}");
                if(path.equals("/api/forum/posts"))return stream("{\"rows\":[{\"id\":1,\"title\":\"Needle forum\"}],\"total\":1}");
                if(path.equals("/api/wiki/search"))return stream("{\"items\":[{\"title\":\"Needle wiki\",\"slug\":\"needle\"}],\"total\":1}");
                return stream("[]");
            }catch(Exception e){throw new IOException(e);}
        }
        private List<JSONObject> filtered()throws Exception{
            String platform=param(url.getFile(),"platform"),term=param(url.getFile(),"tag"),exact=param(url.getFile(),"problem_tag"),scope=param(url.getFile(),"scope"),state=param(url.getFile(),"state");List<JSONObject> matches=new ArrayList<>();
            for(JSONObject item:catalog){if(platform!=null&&!platform.isEmpty()&&!platform.equals(item.getString("platform")))continue;
                if("solved".equals(scope)&&!item.getBoolean("solved")||"favorite".equals(state)&&!item.getBoolean("is_favorite"))continue;
                String search=item.getString("problem_name")+" "+item.getString("problem_id")+" "+item.getJSONArray("tags")+(url.getPath().equals("/api/me/problems/tracker")?" 123 Needle contest":"");
                if(term!=null&&!term.isEmpty()&&!search.toLowerCase(Locale.ROOT).contains(term.toLowerCase(Locale.ROOT)))continue;
                if(exact!=null&&!exact.isEmpty()){boolean found=false;JSONArray tags=item.getJSONArray("tags");for(int i=0;i<tags.length();i++)found|=exact.equalsIgnoreCase(tags.getString(i));if(!found)continue;}matches.add(item);
            }return matches;
        }
        private InputStream stream(String value){return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));}
    }
}
