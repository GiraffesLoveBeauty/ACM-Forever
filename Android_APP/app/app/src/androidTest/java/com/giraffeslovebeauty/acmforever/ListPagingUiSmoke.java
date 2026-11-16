package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.BooleanSupplier;
import org.json.*;

/** Real gestures, cache/live replacement, navigation, and first-page refresh against synthetic HTTPS. */
final class ListPagingUiSmoke {
    private final Instrumentation test;private final AcmApplication app;private MainActivity activity;
    private final List<String> reads=Collections.synchronizedList(new ArrayList<>());
    private volatile boolean failForum;
    private ListPagingUiSmoke(Instrumentation t){test=t;app=(AcmApplication)t.getTargetContext().getApplicationContext();}
    static void run(Instrumentation t){new ListPagingUiSmoke(t).run();}
    private void run(){Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){protected URLConnection openConnection(URL u)throws IOException{if(!u.getHost().equals("list-pages.test.invalid"))throw new IOException("External test traffic forbidden");return new Fixture(u);}}:null);
            AppAppearance.prefs(app).edit().putString("api_base_url","https://list-pages.test.invalid").putBoolean("auto_login",false).putBoolean("app_update_automatic",false).commit();
            app.api().setBaseUrl("https://list-pages.test.invalid");app.api().setNetworkAvailable(()->true);app.api().login("90000001","Synthetic!Only43");
            activity=(MainActivity)test.startActivitySync(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            await(()->ready()&&has("Post 2"),"first two forum posts");Thread.sleep(500);
            check(!has("Post 3")&&reads.stream().filter(s->s.contains("/forum/posts?")).count()==1,"first screen must make only a two-item request");
            main(()->{ScrollView scroll=(ScrollView)field("pageScroll");scroll.scrollTo(0,scroll.getChildAt(0).getHeight());});
            test.waitForIdleSync();
            main(()->{ScrollView scroll=(ScrollView)field("pageScroll");long time=SystemClock.uptimeMillis();float x=scroll.getWidth()*.5f,y=scroll.getHeight()*.75f;for(int n=0;n<=6;n++){int action=n==0?MotionEvent.ACTION_DOWN:n==6?MotionEvent.ACTION_UP:MotionEvent.ACTION_MOVE;MotionEvent e=MotionEvent.obtain(time,time+n*30,action,x,y-n*35,0);scroll.dispatchTouchEvent(e);e.recycle();}});
            await(()->ready()&&has("Post 4"),"next two posts after upward finger gesture");check(!has("Post 5"),"one gesture loads one further batch");
            main(()->{ForumFeed feed=(ForumFeed)field("forumFeed");check(feed.visibleRows((int)field("forumVisibleCount")).length()==4,"cache/live callbacks cannot duplicate visible cards");});
            check(reads.stream().filter(s->s.contains("/forum/posts?")).count()==1,"buffered server rows do not require a second download");
            click("继续加载社区话题");await(()->has("Post 5"),"last buffered post");click("继续加载社区话题");await(()->ready()&&has("Post 7"),"next server page uses actual server page size without skipping posts");check(has("Post 6")&&!has("Post 8"),"second server page is revealed incrementally");
            int[] y={0};main(()->{ScrollView scroll=(ScrollView)field("pageScroll");scroll.scrollTo(0,400);y[0]=scroll.getScrollY();invoke("openPost",int.class,1);});
            await(()->ready()&&has("预览评论"),"post detail");main(activity::onBackPressed);
            await(()->ready()&&has("Post 7"),"return restores loaded forum range");test.waitForIdleSync();main(()->check(Math.abs(((ScrollView)field("pageScroll")).getScrollY()-y[0])<=2,"return retains forum reading position: expected "+y[0]+", actual "+((ScrollView)field("pageScroll")).getScrollY()));
            app.api().clearReadCaches();
            main(()->invoke("refreshCurrentPage"));await(()->ready()&&has("Post 2")&&!has("Post 3"),"forum pull refresh resets to first two posts");
            // No cached first load: pagination gets a separate error card, then retry must remove it.
            failForum=true;main(()->invoke("loadForumPages",new Class<?>[]{int.class,int.class,int.class},field("requestSerial"),2,2));
            await(()->has("请求超时")&&has("Post 2"),"pagination failure keeps existing posts");
            failForum=false;click("继续加载社区话题");await(()->ready()&&has("Post 2")&&!has("请求超时"),"successful pagination removes standalone error card");
            main(()->invoke("show",String.class,"rank"));await(()->ready()&&has("Rank 20"),"rank has full 20 item first page");click("下一页");await(()->ready()&&has("Rank 40"),"rank second page");
            main(()->invoke("refreshCurrentPage"));await(()->ready()&&has("Rank 20")&&!has("Rank 40"),"rank refresh resets to a full first page");
            main(()->invoke("show",String.class,"problems"));click("进入题库");await(()->ready()&&has("Problem 20"),"bank has full 20 item first page");click("下一页");await(()->ready()&&has("Problem 40"),"bank second page");
            main(()->invoke("refreshCurrentPage"));await(()->ready()&&has("Problem 20")&&!has("Problem 40"),"bank refresh resets to a full first page");
            check(reads.stream().filter(s->s.contains("/forum/posts?")).allMatch(s->s.contains("page_size=2")),"all forum pages use the promised batch size");
            result.putString("stream","PASS: initial two posts, touch-driven incremental loading, cache/live dedup, back restores loaded range and position, pagination timeout/retry clears error card, full first-page rank and bank refresh.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error)+"\nReads: "+reads+"\n");}
        finally{if(activity!=null)main(()->{ModalDialogs.close(activity);activity.finish();});}test.finish(outcome,result);
    }
    private Object field(String name){try{java.lang.reflect.Field f=MainActivity.class.getDeclaredField(name);f.setAccessible(true);return f.get(activity);}catch(Exception e){throw new AssertionError(e);}}
    private void invoke(String name){try{java.lang.reflect.Method m=MainActivity.class.getDeclaredMethod(name);m.setAccessible(true);m.invoke(activity);}catch(Exception e){throw new AssertionError(e);}}
    private void invoke(String name,Class<?> type,Object argument){try{java.lang.reflect.Method m=MainActivity.class.getDeclaredMethod(name,type);m.setAccessible(true);m.invoke(activity,argument);}catch(Exception e){throw new AssertionError(e);}}
    private void invoke(String name,Class<?>[] types,Object... arguments){try{java.lang.reflect.Method m=MainActivity.class.getDeclaredMethod(name,types);m.setAccessible(true);m.invoke(activity,arguments);}catch(Exception e){throw new AssertionError(e);}}
    private boolean ready(){boolean[] value={false};main(()->value[0]=((PageRefresh)field("pageRefresh")).canRefresh());return value[0];}
    private View find(View v,String text){if(v instanceof TextView&&(text.contentEquals(((TextView)v).getText())||text.equals(v.getContentDescription())))return v;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++){View found=find(((ViewGroup)v).getChildAt(i),text);if(found!=null)return found;}return null;}
    private boolean has(String text){boolean[] value={false};main(()->value[0]=find(activity.getWindow().getDecorView(),text)!=null);return value[0];}
    private void click(String text){main(()->{View v=find(activity.getWindow().getDecorView(),text);check(v!=null,"missing "+text);v.performClick();});test.waitForIdleSync();}
    private void main(Runnable work){Throwable[] failure={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){failure[0]=e;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private void await(BooleanSupplier condition,String message)throws Exception{long end=SystemClock.uptimeMillis()+16000;while(SystemClock.uptimeMillis()<end){if(condition.getAsBoolean())return;Thread.sleep(80);}throw new AssertionError("Timeout: "+message);}
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private int parameter(URL url,String key,int fallback){String q=url.getQuery();if(q!=null)for(String item:q.split("&")){String[] pair=item.split("=",2);if(pair[0].equals(key)&&pair.length==2)try{return Integer.parseInt(pair[1]);}catch(Exception ignored){}}return fallback;}
    private JSONObject post(int id)throws Exception{return new JSONObject().put("id",id).put("title","Post "+id).put("author_name","Member fixture").put("excerpt","Plain forum summary").put("body","Forum body").put("comments",new JSONArray());}
    private Object response(URL url)throws Exception{
        String path=url.getPath();int page=parameter(url,"page",1),size=parameter(url,"page_size",20);
        if(path.equals("/api/auth/login"))return new JSONObject();
        if(path.equals("/api/auth/me"))return new JSONObject().put("authenticated",true).put("qq_id","90000001").put("role","member").put("csrf_token","fixture-csrf");
        if(path.endsWith("/capabilities"))return new JSONObject().put("api_version",1).put("features",new JSONObject().put("public_member_ids",true));
        if(path.endsWith("/forum/posts")){size=Math.max(5,size);JSONArray rows=new JSONArray();for(int i=(page-1)*size+1;i<=Math.min(8,page*size);i++)rows.put(post(i));return new JSONObject().put("rows",rows).put("total",8).put("page_size",size);}
        if(path.matches(".*/forum/posts/[0-9]+"))return post(Integer.parseInt(path.substring(path.lastIndexOf('/')+1)));
        if(path.endsWith("/leaderboard")){JSONArray rows=new JSONArray();for(int i=(page-1)*size+1;i<=Math.min(40,page*size);i++)rows.put(new JSONObject().put("name","Rank "+i).put("total_count",41-i));return new JSONObject().put("rows",rows).put("total",40).put("page",page).put("positive_only",true);}
        if(path.equals("/api/me/problems")){JSONArray rows=new JSONArray();for(int i=(page-1)*size+1;i<=Math.min(40,page*size);i++)rows.put(new JSONObject().put("platform","codeforces").put("problem_id","cf_"+i+"A").put("problem_name","Problem "+i));return new JSONObject().put("items",rows).put("total",40);}
        if(path.equals("/api/me/profile"))return new JSONObject().put("user",new JSONObject().put("name","Member fixture"));
        throw new IOException("Unexpected test endpoint: "+path);
    }
    private final class Fixture extends HttpURLConnection {
        Fixture(URL url){super(url);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public int getResponseCode()throws IOException{if(failForum&&url.getPath().endsWith("/forum/posts"))throw new SocketTimeoutException("Pagination fixture timeout");return 200;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=list-fixture; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
        public InputStream getInputStream()throws IOException{reads.add(url.getPath()+(url.getQuery()==null?"":"?"+url.getQuery()));try{return new ByteArrayInputStream(response(url).toString().getBytes(StandardCharsets.UTF_8));}catch(Exception e){throw new IOException(e);}}
    }
}
