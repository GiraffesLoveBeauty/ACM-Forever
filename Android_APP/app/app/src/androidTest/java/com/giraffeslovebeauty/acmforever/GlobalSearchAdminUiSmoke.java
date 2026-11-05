package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.*;

/** Synthetic fixtures stay in the test APK; no production writes or student data. */
final class GlobalSearchAdminUiSmoke {
    private final Instrumentation test;private final Context context;private Activity activity;
    private ApiClient api;private volatile String role="member";private volatile boolean wikiDown;
    private final List<Activity> pages=new ArrayList<>();private final List<String> requests=Collections.synchronizedList(new ArrayList<>());
    private final AtomicInteger approvals=new AtomicInteger(),challenges=new AtomicInteger();private volatile boolean approved;private volatile JSONObject lastChallenge;
    private GlobalSearchAdminUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new GlobalSearchAdminUiSmoke(test).run();}
    private void run(){Bundle result=new Bundle();int code=Activity.RESULT_CANCELED;main(()->{});
        AcmApplication app=(AcmApplication)context.getApplicationContext();api=app.api();String original=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL u)throws IOException{if(!Arrays.asList("global.test.invalid","github.com").contains(u.getHost()))throw new IOException("External traffic forbidden");return new Fixture(u);}}:null);
            prefs.edit().remove(SearchModules.KEY).remove("search_history").putBoolean("record_search",true).putBoolean("app_update_automatic",false).putBoolean("auto_login",false).apply();api.setBaseUrl("https://global.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=open(SearchActivity.class,new Intent().putExtra("query","needle"));await(()->has("Zero AC member")&&has("Forum needle")&&has("Wiki needle")&&has("Problem needle"),"all four result sections");
            check("[\"needle\"]".equals(prefs.getString("search_history","[]")),"home Intent query is recorded before any in-page submit");searchEntryHistory(prefs);
            check(requests.stream().anyMatch(s->s.contains("positive_only=0")),"zero AC users remain searchable");
            main(()->{View a=find("用户"),b=find("论坛"),c=find("Wiki");int[] x=new int[2],y=new int[2],z=new int[2];a.getLocationOnScreen(x);b.getLocationOnScreen(y);c.getLocationOnScreen(z);check(y[0]>x[0]&&z[1]>x[1],"two-column row-major layout");});
            click("搜索设置");clickDescription("移除 Wiki");check(!SearchModules.decode(prefs.getString(SearchModules.KEY,null)).contains("wiki"),"remove module saved");click("添加模块");clickDescription("添加 Wiki");check(SearchModules.decode(prefs.getString(SearchModules.KEY,null)).get(3).equals("wiki"),"added module appended");back();click("历史记录");back();back();await(()->has("Forum needle"),"search restored on return");
            wikiDown=true;activity=open(SearchActivity.class,new Intent().putExtra("query","needle"));await(()->has("API连接失败")&&has("Forum needle"),"one failed module retains other results");wikiDown=false;closeCurrent();
            activity=open(SearchActivity.class,new Intent());main(()->{EditText field=(EditText)walk(decor(),v->v instanceof EditText);field.setText("needle");});click("搜索");await(()->has("Forum needle"),"submit search");check(new JSONArray(prefs.getString("search_history","[]")).getString(0).equals("needle"),"history stored on device");
            click("搜索设置");click("添加模块");clickDescription("添加 社团题单");back();back();await(()->has("无API接口"),"missing module has honest error");
            click("搜索设置");click("添加模块");clickDescription("添加 比赛进度");back();back();await(()->has("AtCoder fixture"),"cross-platform contest result");
            Activity searchPage=activity;Instrumentation.ActivityMonitor trackerMonitor=test.addMonitor(WebFeaturesActivity.class.getName(),null,false);
            try{click("AtCoder fixture");activity=test.waitForMonitorWithTimeout(trackerMonitor,8000);check(activity!=null,"tracker page opened");pages.add(activity);await(()->has("比赛进度"),"tracker visible");await(()->requests.stream().anyMatch(s->s.contains("tracker?platform=atcoder")),"AtCoder platform retained");back();test.waitForIdleSync();activity=searchPage;}finally{test.removeMonitor(trackerMonitor);}
            prefs.edit().putString("search_history",new JSONArray().put("newer search").put("needle").toString()).commit();
            Activity old=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(SearchActivity.class.getName(),null,false);try{main(old::recreate);activity=test.waitForMonitorWithTimeout(monitor,8000);check(activity!=null&&activity!=old,"search recreated");pages.add(activity);await(()->has("Forum needle"),"query and results restored");check("newer search".equals(new JSONArray(prefs.getString("search_history","[]")).getString(0)),"recreation does not reinsert or reorder the restored query");}finally{test.removeMonitor(monitor);}
            activity=open(AdminQuickActivity.class,new Intent());await(()->has("无访问权限"),"member denied management");closeCurrent();
            role="admin";api.refreshSession();activity=open(AdminQuickActivity.class,new Intent());await(()->has("待审核话题"),"admin entrance");click("待审核话题");await(()->has("Pending fixture"),"moderation list");click("通过并发布");click("确认");await(()->has("没有待处理内容"),"approval refreshes pending list");check(approvals.get()==1,"one CSRF and revision-bound approval");back();click("成员查询");await(()->has("查看资料"),"members pagination");click("查看资料");await(()->has("为该成员生成训练"),"member details");click("为该成员生成训练");training();back();back();back();click("比赛播报");await(()->has("保存播报时间"),"HH:MM settings");back();
            role="member";old=activity;monitor=test.addMonitor(AdminQuickActivity.class.getName(),null,false);try{Activity current=old;main(current::recreate);activity=test.waitForMonitorWithTimeout(monitor,8000);check(activity!=null,"admin recreated");pages.add(activity);await(()->has("无访问权限"),"role revocation rechecked");check(!has("待审核话题"),"management hidden after revocation");}finally{test.removeMonitor(monitor);}
            // This independent App PR keeps the existing GitHub-only update source.
            AppUpdates updates=app.updates();main(()->{updates.source("");updates.check(false);});await(()->!updates.busy(),"GitHub check finishes");check(updates.error().isEmpty()&&requests.stream().anyMatch(s->s.contains("github.com")),"default GitHub source succeeds");
            int before=requests.size();main(()->{updates.source("https://global.test.invalid/custom-update");updates.check(false);});await(()->!updates.busy(),"custom check finishes");check(!updates.error().isEmpty(),"custom failure remains visible");check(requests.subList(before,requests.size()).stream().noneMatch(s->s.contains("github.com")),"custom failure does not switch official source");
            result.putString("stream","PASS: four global modules; zero AC users; two columns; add/remove persistence; home Intent history, disabled recording, trim/deduplication, ten-term cap, settings exclusion and restore without reorder; missing API; partial failure; AtCoder tracker platform; recreation; member denial; CSRF/revision moderation; member detail; training defaults for four platforms, zero rating, platform rebinding and invalid-selection rejection; report settings; role revocation; existing GitHub updates and custom-source isolation.\n");code=Activity.RESULT_OK;
        }catch(Throwable failure){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure));}
        finally{for(int i=pages.size()-1;i>=0;i--){Activity a=pages.get(i);main(()->{ModalDialogs.close(a);a.finish();});}try{api.logout();}catch(Exception ignored){}api.setBaseUrl(original);SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){Object v=entry.getValue();if(v instanceof String)edit.putString(entry.getKey(),(String)v);else if(v instanceof Boolean)edit.putBoolean(entry.getKey(),(Boolean)v);else if(v instanceof Integer)edit.putInt(entry.getKey(),(Integer)v);else if(v instanceof Long)edit.putLong(entry.getKey(),(Long)v);else if(v instanceof Float)edit.putFloat(entry.getKey(),(Float)v);}edit.apply();}
        test.finish(code,result);
    }
    private void searchEntryHistory(SharedPreferences prefs)throws Exception{
        Activity first=activity;String recorded=prefs.getString("search_history","[]");
        prefs.edit().putBoolean("record_search",false).commit();activity=open(SearchActivity.class,new Intent().putExtra("query","not-recorded"));await(()->has("搜索结果 · not-recorded"),"disabled recording still searches");check(recorded.equals(prefs.getString("search_history","[]")),"Intent entry respects disabled recording");closeCurrent();activity=first;
        prefs.edit().putBoolean("record_search",true).commit();activity=open(SearchActivity.class,new Intent().putExtra("mode","settings").putExtra("query","settings-only"));await(()->has("添加模块"),"settings entry opens");check(recorded.equals(prefs.getString("search_history","[]")),"settings entry does not record its query");closeCurrent();activity=first;
        JSONArray history=new JSONArray();for(int i=0;i<10;i++)history.put("previous-"+i);prefs.edit().putString("search_history",history.toString()).commit();
        activity=open(SearchActivity.class,new Intent().putExtra("query","  needle  "));await(()->has("搜索结果 · needle"),"Intent term is normalized through submit");JSONArray terms=new JSONArray(prefs.getString("search_history","[]"));check(terms.length()==10&&"needle".equals(terms.getString(0))&&"previous-8".equals(terms.getString(9)),"Intent history is newest-first and capped at ten");closeCurrent();activity=first;
        activity=open(SearchActivity.class,new Intent().putExtra("query","needle"));await(()->has("搜索结果 · needle"),"repeat Intent search opens");check(terms.toString().equals(prefs.getString("search_history","[]")),"repeat Intent search is deduplicated");closeCurrent();activity=first;
    }
    private void main(Runnable r){Throwable[] issue={null};test.runOnMainSync(()->{try{r.run();}catch(Throwable e){issue[0]=e;}});if(issue[0]!=null)throw new AssertionError(issue[0]);}
    private Spinner trainingSpinner(String description){return (Spinner)walk(decor(),v->v instanceof Spinner&&description.contentEquals(v.getContentDescription()));}
    private void training()throws Exception{
        await(()->has("生成训练题"),"training form");
        String[] platforms={"codeforces","atcoder","luogu","nowcoder"},defaults={"1000","800","普及-","2星"};
        for(int i=0;i<platforms.length;i++){
            final int position=i;
            main(()->trainingSpinner("训练平台").setSelection(position));test.waitForIdleSync();
            main(()->check(defaults[position].equals(trainingSpinner("训练难度").getSelectedItem()),"valid platform default"));
            generateTraining(platforms[i],defaults[i]);
        }
        main(()->{trainingSpinner("训练平台").setSelection(1);find("生成训练题").performClick();});
        // Click in the same main-thread task, before the platform listener is dispatched.
        await(()->lastChallenge!=null&&"atcoder".equals(lastChallenge.optString("platform"))&&challenges.get()==5&&!((AdminQuickActivity)activity).writing,"pending callback submits matching default");
        check("800".equals(lastChallenge.getString("difficulty")),"no stale Nowcoder value");
        main(()->trainingSpinner("训练难度").setSelection(0));test.waitForIdleSync();generateTraining("atcoder","0");
        // Spinner restores a valid row after setSelection(-1); use an empty adapter to exercise no selection.
        main(()->trainingSpinner("训练难度").setAdapter(MobileStyle.options(activity,new String[0])));test.waitForIdleSync();
        main(()->check(trainingSpinner("训练难度").getSelectedItem()==null,"unselected difficulty fixture"));
        click("生成训练题");main(()->check(!((AdminQuickActivity)activity).writing,"invalid selection blocked before network"));
        check(challenges.get()==6,"invalid selection cannot post");
        main(()->trainingSpinner("训练平台").setSelection(0));test.waitForIdleSync();generateTraining("codeforces","1000");
    }
    private void generateTraining(String platform,String difficulty)throws Exception{
        int before=challenges.get();click("生成训练题");
        await(()->challenges.get()==before+1&&!((AdminQuickActivity)activity).writing&&has("Training fixture"),"training created and history loaded");
        check(platform.equals(lastChallenge.getString("platform"))&&difficulty.equals(lastChallenge.getString("difficulty")),"platform-bound difficulty payload");
    }
    private Activity open(Class<?> page,Intent extras){Activity a=test.startActivitySync(new Intent(extras).setClassName(context,page.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_MULTIPLE_TASK));pages.add(a);return a;}
    private void closeCurrent(){Activity a=activity;main(a::finish);test.waitForIdleSync();}
    private void back(){main(activity::onBackPressed);test.waitForIdleSync();}
    private View walk(View view,Predicate<View> p){if(p.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),p);if(found!=null)return found;}}return null;}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog d=ref==null?null:(AlertDialog)ref.get();if(d!=null&&d.isShowing())return d.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View find(String s){return walk(decor(),v->v instanceof TextView&&s.contentEquals(((TextView)v).getText()));}
    private boolean has(String s){boolean[] yes={false};main(()->yes[0]=find(s)!=null);return yes[0];}
    private void click(String s){main(()->{View v=find(s);check(v!=null&&v.isEnabled(),"button "+s);v.performClick();});test.waitForIdleSync();}
    private void clickDescription(String s){main(()->{View v=walk(decor(),x->x.getContentDescription()!=null&&s.contentEquals(x.getContentDescription()));check(v!=null,"description "+s);v.performClick();});test.waitForIdleSync();}
    private void await(BooleanSupplier ready,String label)throws Exception{long end=SystemClock.uptimeMillis()+12000;while(SystemClock.uptimeMillis()<end){if(ready.getAsBoolean())return;Thread.sleep(60);}throw new AssertionError("Timeout: "+label);}
    private static void check(boolean yes,String label){if(!yes)throw new AssertionError(label);}
    private final class Fixture extends HttpURLConnection{
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public OutputStream getOutputStream(){return sent;}
        public int getResponseCode(){return url.getPath().equals("/custom-update")||wikiDown&&url.getPath().equals("/api/wiki/search")?503:200;}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));}
        public InputStream getInputStream(){requests.add(url.toString());String p=url.getPath(),value="{}";
            if(url.getHost().equals("github.com"))value="{\"packageName\":\"com.giraffeslovebeauty.acmforever\",\"versionCode\":30,\"versionName\":\"0.2.16\",\"channel\":\"debug\",\"apkUrl\":\"https://global.test.invalid/a.apk\",\"sha256\":\""+String.join("",Collections.nCopies(64,"a"))+"\"}";
            else if(p.endsWith("/login"))value="{\"success\":true}";
            else if(p.equals("/api/auth/me"))value="{\"authenticated\":true,\"csrf_token\":\"synthetic-csrf\",\"qq_id\":\"90000001\",\"role\":\""+role+"\"}";
            else if(p.endsWith("/capabilities"))value="{\"api_version\":1,\"features\":{\"public_member_ids\":true}}";
            else if(p.endsWith("/leaderboard"))value="{\"rows\":[{\"name\":\"Zero AC member\",\"public_member_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"total_count\":0}],\"total\":1}";
            else if(p.equals("/api/mobile/v1/forum/posts"))value="{\"items\":[{\"id\":101,\"title\":\"Forum needle\"}],\"total\":1}";
            else if(p.equals("/api/wiki/search"))value="{\"items\":[{\"title\":\"Wiki needle\",\"slug\":\"basics\"}],\"total\":1}";
            else if(p.equals("/api/me/problems"))value="{\"items\":[{\"platform\":\"codeforces\",\"problem_id\":\"1A\",\"problem_name\":\"Problem needle\"}],\"total\":1}";
            else if(p.equals("/api/me/problems/tracker"))value="{\"items\":[{\"platform\":\"atcoder\",\"contest_id\":\"abc100\",\"contest_name\":\"AtCoder fixture\",\"total_count\":0,\"solved_count\":0,\"problems\":[]}],\"total\":1}";
            else if(p.equals("/api/forum/moderation/posts"))value=approved?"[]":"[{\"id\":10,\"title\":\"Pending fixture\",\"body\":\"fixture\",\"content_version\":2}]";
            else if(p.equals("/api/forum/moderation/posts/10")){try{JSONObject body=new JSONObject(sent.toString("UTF-8"));check("POST".equals(getRequestMethod())&&"synthetic-csrf".equals(getRequestProperty("X-CSRF-Token"))&&body.getInt("content_version")==2,"CSRF and current revision sent");approvals.incrementAndGet();approved=true;value="{\"success\":true}";}catch(Exception e){throw new AssertionError(e);}}
            else if(p.equals("/api/admin/members"))value="{\"items\":[{\"qq_id\":\"90000002\",\"name\":\"Member fixture\"}],\"total\":1}";
            else if(p.equals("/api/member/90000002"))value="{\"user\":{\"name\":\"Member fixture\"},\"platform_counts\":{\"codeforces\":1}}";
            else if(p.equals("/api/challenge/list"))value="[{\"platform\":\"codeforces\",\"problem_id\":\"1A\",\"problem_name\":\"Training fixture\",\"status\":\"active\"}]";
            else if(p.equals("/api/challenge/start")){try{
                JSONObject body=new JSONObject(sent.toString("UTF-8"));String platform=body.getString("platform"),difficulty=body.getString("difficulty");
                check("POST".equals(getRequestMethod())&&"synthetic-csrf".equals(getRequestProperty("X-CSRF-Token")),"training POST with CSRF");
                check("90000002".equals(body.getString("owner_qq_id"))&&!body.getBoolean("weak_tag"),"target training member");
                if("codeforces".equals(platform)||"atcoder".equals(platform)){int rating=Integer.parseInt(difficulty);check(rating>=("codeforces".equals(platform)?800:0)&&rating<=("codeforces".equals(platform)?3500:4000),"numeric difficulty accepted by backend");}
                else if("luogu".equals(platform))check(Arrays.asList("未评定","入门","普及-","普及/提高-","普及+/提高","提高+/省选-","省选/NOI-","NOI/NOI+/CTSC").contains(difficulty),"valid Luogu label");
                else check("nowcoder".equals(platform)&&Arrays.asList("1星","2星","3星","4星","5星").contains(difficulty),"valid Nowcoder stars");
                lastChallenge=body;challenges.incrementAndGet();value="{\"success\":true}";
            }catch(Exception e){throw new AssertionError(e);}}
            else if(p.equals("/api/settings/contest-report"))value="{\"time\":\"08:30\",\"group_id\":\"synthetic\"}";
            return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));}
    }
}
