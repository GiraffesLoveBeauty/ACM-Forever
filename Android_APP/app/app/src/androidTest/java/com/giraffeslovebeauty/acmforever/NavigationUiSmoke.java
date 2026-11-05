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
import java.util.function.BooleanSupplier;

/** Exercises the real navigation with test-only transport, never production records. */
final class NavigationUiSmoke {
    private static volatile boolean notificationCommentSeen;
    private final Instrumentation test;private final Context context;private Activity activity;
    private final ArrayList<Activity> opened=new ArrayList<>();
    private NavigationUiSmoke(Instrumentation test){this.test=test;context=test.getTargetContext();}
    static void run(Instrumentation test){new NavigationUiSmoke(test).run();}
    private void run(){
        Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;ApiClient api=((AcmApplication)context.getApplicationContext()).api();String base=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> before=new HashMap<>(prefs.getAll());
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"navigation.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://navigation.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).apply();api.setBaseUrl("https://navigation.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            activity=test.startActivitySync(new Intent().setClassName(context,MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));opened.add(activity);
            await(()->find("社区话题")!=null&&((ImageView)description("常用工具")).getDrawable().getBounds().width()>=MobileStyle.dp(context,28),"home and enlarged plus drawn");main(()->{ImageView plus=(ImageView)description("常用工具");check(plus.getScaleType()==ImageView.ScaleType.FIT_CENTER,"plus fits its button without stretching");plus.performClick();});
            main(()->{Button settings=(Button)find("个性化设置");check(settings!=null&&settings.getGravity()==Gravity.CENTER&&settings.getCompoundDrawables()[0]==null,"personalization text is centered");ModalDialogs.close(activity);});
            testForumMembers();
            testManualSessionRecreation(api,prefs);
            testHomeSearch(prefs);
            click("排名");await(()->find("榜单导航成员")!=null,"mobile leaderboard with public identity");
            main(()->description("查看榜单导航成员的公开主页").performClick());
            await(()->find("榜单成员的公开话题")!=null,"leaderboard opens fetched member profile and posts");
            check("member".equals(field("screen"))&&find("无API接口")==null,"available member APIs do not show a missing endpoint");
            back();await(()->"rank".equals(field("screen"))&&find("榜单导航成员")!=null,"member returns to originating leaderboard");
            click("个人中心");await(()->find("导航最近AC")!=null,"recent AC");main(()->scroll().scrollTo(0,320));test.waitForIdleSync();click("导航最近AC");await(()->find("导航题面")!=null,"problem opened from profile");back();await(()->find("导航最近AC")!=null,"return to profile");check("mine".equals(field("screen")),"returns to actual recent AC source");
            click("题库");await(()->find("查看题面与样例")!=null,"problem list");click("洛谷");await(()->find("查看题面与样例")!=null,"platform filter");
            click("下一页");await(()->Integer.valueOf(2).equals(field("page"))&&find("导航列表20")!=null,"second page");
            main(()->scroll().scrollTo(0,600));test.waitForIdleSync();int sourceY=scroll().getScrollY();check(sourceY>0,"source is scrolled");click("查看题面与样例");await(()->find("导航题面")!=null,"problem detail");
            Bundle saved=new Bundle();main(()->test.callActivityOnSaveInstanceState(activity,saved));ArrayList<Bundle> history=saved.getParcelableArrayList("navigation_history");check(history!=null&&!history.isEmpty(),"history saved for recreation");Bundle source=history.get(0);check(source.getInt("page")==2&&source.getInt("scroll_y")==sourceY,"saved source includes query, page and scroll");check(!source.containsKey("session_generation")&&!source.containsKey("csrf_token")&&!source.containsKey("password"),"history excludes authentication secrets");
            main(()->{NavigationStack<Bundle> stack=(NavigationStack<Bundle>)field("navigation");stack.clear();stack.restore(history);});back();await(()->find("导航列表20")!=null&&scroll().getScrollY()==sourceY,"restore page and scroll");check("luogu".equals(field("platform"))&&Integer.valueOf(2).equals(field("page")),"filters and page preserved");
            click("个人中心");await(()->find("导航最近AC")!=null,"profile again");Activity profile=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(SpaceActivity.class.getName(),null,false);click("我的话题");activity=test.waitForMonitorWithTimeout(monitor,5000);test.removeMonitor(monitor);check(activity!=null,"space opened");opened.add(activity);await(()->find("查看话题")!=null,"space list");Activity space=activity;
            monitor=test.addMonitor(MainActivity.class.getName(),null,false);click("查看话题");activity=test.waitForMonitorWithTimeout(monitor,5000);test.removeMonitor(monitor);check(activity!=null,"external post opened");opened.add(activity);await(()->find("导航话题")!=null&&find("返回")!=null,"external detail");Activity child=activity;back();test.waitForIdleSync();check(child.isFinishing()&&!space.isFinishing()&&!profile.isFinishing(),"external back keeps the original activities");activity=space;await(()->find("查看话题")!=null,"original space visible");
            result.putString("stream","PASS: forum list/detail authors open fetched profiles/posts and return, notification comment_id retained; real Activity recreation with auto-login off preserves login; mobile leaderboard identity opens fetched member profile/posts and returns to rank; global search returns to an empty home field while history and detail results survive, enlarged plus, centered tool text, recent AC source, filtered page and scroll restoration, saved-state history without credentials, external topic returns to original space.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));}
        finally{for(Activity item:opened)main(()->{ModalDialogs.close(item);item.finish();});try{api.logout();}catch(Exception ignored){}SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> item:before.entrySet()){Object value=item.getValue();if(value instanceof String)edit.putString(item.getKey(),(String)value);else if(value instanceof Integer)edit.putInt(item.getKey(),(Integer)value);else if(value instanceof Boolean)edit.putBoolean(item.getKey(),(Boolean)value);else if(value instanceof Long)edit.putLong(item.getKey(),(Long)value);else if(value instanceof Float)edit.putFloat(item.getKey(),(Float)value);}edit.apply();api.setBaseUrl(base);AppAppearance.load(context);}
        test.finish(outcome,result);
    }
    private void testForumMembers()throws Exception{
        await(()->find("导航话题")!=null,"forum list loaded");
        main(()->description("查看论坛导航作者的公开主页").performClick());
        await(()->find("论坛作者的公开话题")!=null,"list author opens fetched public profile and posts");
        check("member".equals(field("screen"))&&find("无API接口")==null,"forum list retains public author identity");
        back();await(()->"forum".equals(field("screen"))&&find("导航话题")!=null,"author returns to forum list");
        click("导航话题");await(()->"detail".equals(field("screen"))&&find("发布新的评论")!=null,"forum detail loaded");
        main(()->{View author=walk(decor(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith("论坛导航作者 · ")&&v.isClickable());check(author!=null,"detail author control");author.performClick();});
        await(()->find("论坛作者的公开话题")!=null,"detail author opens fetched public profile and posts");
        check("member".equals(field("screen"))&&find("无API接口")==null,"forum detail retains public author identity");
        back();await(()->"detail".equals(field("screen"))&&find("发布新的评论")!=null,"author returns to detail");back();
        await(()->"forum".equals(field("screen")),"detail returns to list");notificationCommentSeen=false;
        main(()->test.callActivityOnNewIntent(activity,new Intent().putExtra("club_post_id",8).putExtra("notification_comment_id",17)));
        await(()->notificationCommentSeen&&"detail".equals(field("screen"))&&find("发布新的评论")!=null,"mobile detail preserves notification comment_id query");
        back();await(()->"forum".equals(field("screen"))&&find("导航话题")!=null,"notification detail returns to list");
    }
    private void testManualSessionRecreation(ApiClient api,SharedPreferences prefs)throws Exception{
        Activity previous=activity;long generation=api.sessionGeneration();Application app=previous.getApplication();
        java.util.concurrent.atomic.AtomicReference<Activity> next=new java.util.concurrent.atomic.AtomicReference<>();
        Application.ActivityLifecycleCallbacks callbacks=new Application.ActivityLifecycleCallbacks(){
            public void onActivityCreated(Activity a,Bundle b){if(a instanceof MainActivity&&a!=previous)next.set(a);}
            public void onActivityStarted(Activity a){}public void onActivityResumed(Activity a){}public void onActivityPaused(Activity a){}
            public void onActivityStopped(Activity a){}public void onActivitySaveInstanceState(Activity a,Bundle b){}public void onActivityDestroyed(Activity a){}
        };
        app.registerActivityLifecycleCallbacks(callbacks);
        try{main(previous::recreate);await(()->next.get()!=null,"real Activity recreated");activity=next.get();opened.add(activity);
            await(()->find("导航话题")!=null,"forum survives recreation");
            check(previous.isDestroyed()&&field("api")==api&&api.isLoggedIn()&&api.sessionGeneration()==generation&&!prefs.getBoolean("auto_login",true),"manual login survives recreation without automatic login");
        }finally{app.unregisterActivityLifecycleCallbacks(callbacks);}
    }
    private void testHomeSearch(SharedPreferences prefs)throws Exception{
        Activity home=activity;Instrumentation.ActivityMonitor monitor=test.addMonitor(SearchActivity.class.getName(),null,false);
        try{main(()->((EditText)field("search")).performClick());activity=test.waitForMonitorWithTimeout(monitor,7000);check(activity!=null,"global search opens once");opened.add(activity);}finally{test.removeMonitor(monitor);}
        await(()->find("最近 10 条搜索")!=null,"global search page");
        main(()->{((EditText)walk(decor(),v->v instanceof EditText)).setText("清空验证");description("搜索").performClick();});await(()->find("导航话题")!=null,"cross-module forum results");
        Activity searchPage=activity;monitor=test.addMonitor(MainActivity.class.getName(),null,false);
        try{click("导航话题");activity=test.waitForMonitorWithTimeout(monitor,7000);check(activity!=null,"search result opens native detail");opened.add(activity);}finally{test.removeMonitor(monitor);}
        await(()->"detail".equals(field("screen"))&&find("发布新的评论")!=null,"forum result detail");Activity detail=activity;back();test.waitForIdleSync();check(detail.isFinishing(),"detail returns to search activity");
        activity=searchPage;await(()->find("导航话题")!=null,"search results remain");check(prefs.getString("search_history","").contains("清空验证"),"history retained");
        back();test.waitForIdleSync();activity=home;await(()->"forum".equals(field("screen")),"search returns to home");check(((EditText)field("search")).getText().length()==0,"home search field clears");
    }
    private Object field(String name){try{java.lang.reflect.Field f=MainActivity.class.getDeclaredField(name);f.setAccessible(true);return f.get(activity);}catch(Exception e){throw new AssertionError(e);}}
    private ScrollView scroll(){return (ScrollView)field("pageScroll");}
    private View walk(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View hit=walk(group.getChildAt(i),match);if(hit!=null)return hit;}}return null;}
    private View decor(){try{java.lang.reflect.Field f=ModalDialogs.class.getDeclaredField("visible");f.setAccessible(true);java.lang.ref.WeakReference<?> ref=(java.lang.ref.WeakReference<?>)((Map<?,?>)f.get(null)).get(activity);AlertDialog dialog=ref==null?null:(AlertDialog)ref.get();if(dialog!=null&&dialog.isShowing())return dialog.getWindow().getDecorView();}catch(Exception e){throw new AssertionError(e);}return activity.getWindow().getDecorView();}
    private View find(String label){return walk(decor(),v->v instanceof TextView&&label.contentEquals(((TextView)v).getText()));}
    private View description(String label){return walk(decor(),v->label.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void click(String label){main(()->{View v=find(label);check(v!=null,"control exists "+label);while(!v.isClickable()&&v.getParent() instanceof View)v=(View)v.getParent();v.performClick();});}
    private void back(){main(()->activity.onBackPressed());}
    private void main(Runnable action){final Throwable[] failure={null};test.runOnMainSync(()->{try{action.run();}catch(Throwable error){failure[0]=error;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private void await(BooleanSupplier ready,String label)throws Exception{long until=SystemClock.uptimeMillis()+7000;while(SystemClock.uptimeMillis()<until){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0]){test.waitForIdleSync();return;}Thread.sleep(70);}throw new AssertionError(label);}
    private void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private static final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public int getResponseCode(){return 200;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=navigation-test; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        public InputStream getInputStream()throws IOException{
            try{return new ByteArrayInputStream(body().getBytes(StandardCharsets.UTF_8));}catch(JSONException e){throw new IOException(e);}
        }
        private String body()throws JSONException{
            String path=url.getPath();if(path.equals("/api/auth/me"))return "{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            if(path.equals("/api/mobile/v1/capabilities"))return "{\"api_version\":1,\"features\":{\"public_member_ids\":true,\"member_profiles\":true,\"member_posts\":true}}";
            if(path.equals("/api/mobile/v1/leaderboard"))return "{\"positive_only\":true,\"rows\":[{\"name\":\"榜单导航成员\",\"public_member_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"total_count\":3}],\"total\":1,\"page\":1}";
            if(path.equals("/api/mobile/v1/members/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))return "{\"name\":\"榜单导航成员\",\"public_member_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"platform_counts\":{\"codeforces\":3},\"total_count\":3}";
            if(path.equals("/api/mobile/v1/members/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/posts"))return "{\"rows\":[{\"id\":8,\"title\":\"榜单成员的公开话题\",\"body\":\"Public member fixture\"}],\"total\":1}";
            if(path.equals("/api/mobile/v1/members/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))return "{\"name\":\"论坛导航作者\",\"public_member_id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"platform_counts\":{\"atcoder\":2},\"total_count\":2}";
            if(path.equals("/api/mobile/v1/members/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/posts"))return "{\"rows\":[{\"id\":8,\"title\":\"论坛作者的公开话题\",\"body\":\"Public forum author fixture\"}],\"total\":1}";
            if(path.equals("/api/me/profile"))return "{\"user\":{\"name\":\"导航成员\",\"status\":\"active\"},\"platform_counts\":{\"luogu\":1},\"total_count\":1,\"recent_ac\":[{\"platform\":\"luogu\",\"problem_id\":\"P1000\",\"problem_name\":\"导航最近AC\"}]}";
            if(path.equals("/api/forum/posts")||path.equals("/api/mobile/v1/forum/posts")){JSONObject author=new JSONObject().put("id",8).put("title","导航话题").put("excerpt","Test fixture").put("author_name","论坛导航作者");if(path.startsWith("/api/mobile/"))author.put("author_public_member_id","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");return new JSONObject().put("rows",new JSONArray().put(author)).put("total",1).toString();}
            if(path.equals("/api/me/problems")){int page=android.net.Uri.parse(url.toString()).getQueryParameter("page")==null?1:Integer.parseInt(android.net.Uri.parse(url.toString()).getQueryParameter("page"));JSONArray items=new JSONArray();for(int i=(page-1)*20;i<page*20;i++)items.put(new JSONObject().put("platform","luogu").put("problem_id","P"+(1000+i)).put("problem_name","导航列表"+i));return new JSONObject().put("items",items).put("total",60).toString();}
            if(path.startsWith("/api/me/problems/"))return "{\"platform\":\"luogu\",\"problem_id\":\"P1000\",\"problem_name\":\"导航题面\",\"content_available\":true,\"statement_text\":\"Navigation fixture\",\"samples\":[]}";
            if(path.equals("/api/forum/mine/posts"))return "[{\"id\":8,\"status\":\"published\",\"title\":\"导航话题\",\"body\":\"Navigation fixture\"}]";
            if(path.equals("/api/forum/posts/8")||path.equals("/api/mobile/v1/forum/posts/8")){JSONObject post=new JSONObject().put("id",8).put("title","导航话题").put("author_name","论坛导航作者").put("body","Navigation fixture").put("comments",new JSONArray().put(new JSONObject().put("id",17).put("author_name","论坛导航作者").put("body","导航评论")));if(path.startsWith("/api/mobile/")){post.put("author_public_member_id","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");if("comment_id=17".equals(url.getQuery()))notificationCommentSeen=true;}return post.toString();}
            if(path.equals("/api/forum/categories")||path.equals("/api/forum/mine/bookmarks")||path.equals("/api/forum/drafts"))return "[]";
            return "{}";
        }
    }
}
