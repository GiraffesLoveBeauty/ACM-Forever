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
import java.util.concurrent.atomic.AtomicInteger;

/** Contract/UI fixtures are restricted to this test APK and cannot reach a real host. */
final class WebFeaturesUiSmoke {
    private final Instrumentation test;private final Context app;private Activity activity;private ApiClient api;
    private final List<Activity> activities=new ArrayList<>();private static final String HASH="0123456789abcdef0123456789abcdef";
    private static final AtomicInteger detailReads=new AtomicInteger(),savedVersion=new AtomicInteger(),submitVersion=new AtomicInteger(),readThrough=new AtomicInteger(),imageReads=new AtomicInteger();
    private static volatile boolean imageCookie,failLike;private static byte[] png;
    private WebFeaturesUiSmoke(Instrumentation test){this.test=test;app=test.getTargetContext();}
    static void run(Instrumentation test){new WebFeaturesUiSmoke(test).run();}
    private void run(){Bundle result=new Bundle();int outcome=Activity.RESULT_CANCELED;api=((AcmApplication)app.getApplicationContext()).api();String base=api.getBaseUrl();SharedPreferences prefs=AppAppearance.prefs(app);Map<String,?> settings=new HashMap<>(prefs.getAll());
        try{
            Bitmap bitmap=Bitmap.createBitmap(32,24,Bitmap.Config.ARGB_8888);bitmap.eraseColor(0xff4488cc);ByteArrayOutputStream output=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,output);bitmap.recycle();png=output.toByteArray();
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"features.test.invalid".equals(url.getHost()))throw new IOException("All external traffic is blocked by this test");return new Fixture(url);}}:null);
            prefs.edit().putString("api_base_url","https://features.test.invalid").putBoolean("auto_login",false).apply();api.setBaseUrl("https://features.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Test!");
            wiki();notifications();tracker();revision();comments();members();images();
            result.putBoolean("passed",true);result.putString("stream","PASS: Wiki navigation/list/article/public history, notification read-all snapshot, tracker statuses, edit/resubmit versions, Markdown comments and reactions without page refresh, failed writes banner, authenticated thumbnails/image viewer and external-media rejection.\n");outcome=Activity.RESULT_OK;
        }catch(Throwable e){result.putBoolean("passed",false);result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));}
        finally{for(Activity item:activities)main(()->{ModalDialogs.close(item);item.finish();});try{api.logout();}catch(Exception ignored){}SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> entry:settings.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);}edit.apply();AppAppearance.load(app);api.setBaseUrl(base);}
        test.finish(outcome,result);
    }
    private void wiki()throws Exception{
        feature("wiki",0);await(()->find("测试算法分类")!=null,5000,"Wiki navigation");click("查看文章");await(()->find("测试算法条目")!=null,5000,"Wiki list");click("阅读文章");await(()->find("关联练习")!=null,5000,"Wiki body and practice");check(find("许可：CC BY 4.0")!=null,"real licence metadata");click("公开历史");await(()->findPrefix("测试算法旧版")!=null,5000,"public revision history");clickPrefix("测试算法旧版");await(()->find("测试算法旧版")!=null,5000,"public historical article");screenshot("wiki-v026.png");
    }
    private void notifications()throws Exception{
        feature("notifications",0);await(()->find("未读 2 条")!=null,5000,"notifications");click("全部标为已读");await(()->readThrough.get()==42,3000,"snapshot sent");await(()->find("未读 0 条")!=null,4000,"read state refreshed");check(readThrough.get()==42,"mark-read stops at observed latest id");screenshot("notifications-v026.png");
    }
    private void tracker()throws Exception{feature("tracker",0);await(()->find("测试比赛")!=null,5000,"tracker list");check(find("A · 已 AC")!=null&&find("B · 尝试未通过")!=null,"tracker statuses remain distinct");screenshot("tracker-v026.png");}
    private void revision()throws Exception{
        feature("progress",8);await(()->find("退回原因：请补充解释")!=null,5000,"review reason");Instrumentation.ActivityMonitor edit=test.addMonitor(MainActivity.class.getName(),null,false);click("修改后重新投稿");Activity opened=test.waitForMonitorWithTimeout(edit,6000);test.removeMonitor(edit);check(opened!=null,"editor launched");activity=opened;activities.add(opened);
        await(()->hint("描述问题、已经尝试的方法，或分享解题思路…")!=null,5000,"edit draft loaded");main(()->((EditText)hint("描述问题、已经尝试的方法，或分享解题思路…")).setText("Changed Markdown **explanation**"));
        await(()->savedVersion.get()==4,6000,"autosave edit version 4");Instrumentation.ActivityMonitor progress=test.addMonitor(WebFeaturesActivity.class.getName(),null,false);click("提交审核");Activity submitted=test.waitForMonitorWithTimeout(progress,6000);test.removeMonitor(progress);check(submitted!=null,"submit opens progress");activity=submitted;activities.add(submitted);await(()->find("等待审核")!=null,5000,"new progress after submission");check(submitVersion.get()==5,"submission uses latest saved version");screenshot("submission-v026.png");
    }
    private void comments()throws Exception{
        launch(new Intent().setClassName(app,MainActivity.class.getName()).putExtra("club_post_id",8));await(()->desc("评论Markdown工具")!=null,6000,"Markdown comment editor");View before=desc("评论Markdown工具");int reads=detailReads.get();
        clickDescription("话题点赞");await(()->find("已赞 1")!=null&&desc("话题点赞").isEnabled(),3000,"like response");check(before==desc("评论Markdown工具")&&reads==detailReads.get(),"like keeps page");
        main(()->((EditText)hint("支持 Markdown、代码和公式（2–5000 字）")).setText("A **Markdown** comment"));click("发布评论");await(()->find("我 · 评论 #77")!=null,4000,"comment shown immediately");check(before==desc("评论Markdown工具")&&reads==detailReads.get(),"comment keeps page");
        failLike=true;clickDescription("话题点赞");await(()->findPrefix("点赞失败")!=null,4000,"write failure red banner");check(before==desc("评论Markdown工具"),"failure keeps editor");failLike=false;screenshot("comments-v026.png");
    }
    private void members()throws Exception{
        launch(new Intent().setClassName(app,MainActivity.class.getName()));await(()->desc("查看公开成员的公开主页")!=null,5000,"member entry in forum");clickDescription("查看公开成员的公开主页");await(()->find("ACMFOREVER / MEMBER")!=null&&desc("ALL通过题数 60")!=null,5000,"full member page");check(find("公开座右铭")==null&&find("发布的论坛话题")!=null,"public profile and topics without motto");check(desc("最近AC框")==null,"other member private recent AC not shown");screenshot("member-v026.png");click("返回");await(()->desc("查看无公开ID成员的公开主页")!=null,5000,"return forum");clickDescription("查看无公开ID成员的公开主页");await(()->find("ACMFOREVER / MEMBER")!=null&&find("无API接口")!=null,5000,"missing member API stays on full page with explicit error");check(desc("ALL通过题数 999")==null,"rank snapshot is never treated as lifetime total");
    }
    private void images()throws Exception{
        String address=api.getBaseUrl()+"/api/forum/images/"+HASH;check(api.isCommunityMedia(address),"existing image route accepted");check(!api.isCommunityMedia("https://outside.invalid/api/forum/images/"+HASH),"external image rejected");check(!api.isCommunityMedia(api.getBaseUrl()+"/api/forum/images/%2e%2e/secret"),"encoded traversal rejected");
        api.communityMedia(address+"?variant=thumb");check(imageCookie&&imageReads.get()>0,"image sends same-origin session cookie");launch(new Intent().setClassName(app,ImagePreviewActivity.class.getName()).putExtra("url",address));await(()->find("双指缩放 · 拖动查看")!=null,5000,"local zoom viewer");main(()->{WebView viewer=(WebView)desc("图片，支持双指缩放和拖动");check(!viewer.getSettings().getJavaScriptEnabled(),"viewer has no JS bridge");check(!viewer.getSettings().getAllowFileAccess()&&viewer.getSettings().getBuiltInZoomControls(),"local zoom without file access");});screenshot("image-v026.png");
    }
    private void feature(String name,int id){launch(new Intent().setClassName(app,WebFeaturesActivity.class.getName()).putExtra("feature",name).putExtra("post_id",id));}
    private void launch(Intent intent){if(activity!=null)main(()->activity.finish());activity=test.startActivitySync(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));activities.add(activity);}
    private void main(Runnable work){test.runOnMainSync(work);}
    private View walk(View view,java.util.function.Predicate<View> match){if(view.getVisibility()!=View.VISIBLE)return null;if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=walk(group.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&value.contentEquals(((TextView)v).getText()));}
    private View findPrefix(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&((TextView)v).getText().toString().startsWith(value));}
    private View desc(String value){return walk(activity.getWindow().getDecorView(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private View hint(String value){return walk(activity.getWindow().getDecorView(),v->v instanceof EditText&&value.contentEquals(((EditText)v).getHint()));}
    private void click(String value){main(()->{View view=find(value);check(view!=null&&view.isEnabled(),"button "+value);view.performClick();});test.waitForIdleSync();}
    private void clickPrefix(String value){main(()->{View view=findPrefix(value);check(view!=null,"button "+value);view.performClick();});test.waitForIdleSync();}
    private void clickDescription(String value){main(()->{View view=desc(value);check(view!=null,"control "+value);view.performClick();});test.waitForIdleSync();}
    private void await(java.util.function.BooleanSupplier ready,long millis,String message)throws Exception{long end=System.currentTimeMillis()+millis;while(System.currentTimeMillis()<end){boolean[] done={false};main(()->done[0]=ready.getAsBoolean());if(done[0])return;Thread.sleep(60);}throw new AssertionError(message);}
    private void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    private void screenshot(String name)throws Exception{Thread.sleep(200);Bitmap bitmap=test.getUiAutomation().takeScreenshot();check(bitmap!=null,"screenshot");try(FileOutputStream out=new FileOutputStream(new File(app.getExternalFilesDir(null),name))){bitmap.compress(Bitmap.CompressFormat.PNG,100,out);}finally{bitmap.recycle();}}
    private static final class Fixture extends HttpURLConnection {
        private final ByteArrayOutputStream sent=new ByteArrayOutputStream();Fixture(URL url){super(url);}
        @Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}@Override public OutputStream getOutputStream(){return sent;}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=features-fixture; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public String getContentType(){return url.getPath().contains("/images/")?"image/png":"application/json";}
        @Override public int getResponseCode(){return failLike&&url.getPath().endsWith("/like")?500:200;}
        @Override public InputStream getErrorStream(){return bytes("{\"message\":\"synthetic server failure\"}");}
        @Override public InputStream getInputStream()throws IOException{try{return bytes(response());}catch(JSONException e){throw new IOException(e);}}
        private String response()throws JSONException,IOException{String p=url.getPath();JSONObject body=sent.size()==0?new JSONObject():new JSONObject(sent.toString("UTF-8"));
            if(p.contains("/images/")){imageCookie=String.valueOf(getRequestProperty("Cookie")).contains("features-fixture");imageReads.incrementAndGet();return "";}
            if(p.endsWith("/auth/me"))return "{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
            if(p.endsWith("/auth/login")||p.endsWith("/auth/logout"))return "{}";
            if(p.equals("/api/mobile/v1/capabilities"))return "{\"api_version\":1,\"features\":{\"public_member_ids\":true,\"member_profiles\":true,\"member_posts\":true}}";
            if(p.equals("/api/mobile/v1/members/"+HASH))return "{\"public_member_id\":\""+HASH+"\",\"name\":\"公开成员\",\"platform_counts\":{\"codeforces\":60},\"total_count\":60}";
            if(p.equals("/api/mobile/v1/members/"+HASH+"/posts"))return "{\"rows\":[],\"total\":0}";
            if(p.endsWith("/wiki/navigation"))return "{\"categories\":[{\"id\":1,\"name\":\"测试算法分类\",\"parent_id\":null}]}";
            if(p.equals("/api/wiki/pages")||p.equals("/api/wiki/search"))return "{\"items\":[{\"slug\":\"test-algorithm\",\"title\":\"测试算法条目\",\"summary\":\"测试摘要\"}],\"total\":1}";
            if(p.endsWith("/revisions"))return "[{\"id\":2,\"title\":\"测试算法旧版\",\"published_at\":1700000000}]";
            if(p.startsWith("/api/wiki/pages/"))return new JSONObject().put("title",p.endsWith("/2")?"测试算法旧版":"测试算法条目").put("body","# Test\n**Actual Markdown**").put("source","测试来源").put("license","CC BY 4.0").put("exercises",new JSONArray("[{\"label\":\"练习题\",\"url\":\"https://example.test/\"}]")).toString();
            if(p.endsWith("/notifications/read-all")){readThrough.set(body.getInt("through_id"));return "{}";}
            if(p.endsWith("/notifications"))return "{\"rows\":[],\"total\":0,\"unread_count\":"+(readThrough.get()>0?0:2)+",\"latest_id\":42}";
            if(p.endsWith("/problems/tracker"))return "{\"items\":[{\"contest_name\":\"测试比赛\",\"solved_count\":1,\"total_count\":2,\"attempted_count\":1,\"problems\":[{\"platform\":\"codeforces\",\"problem_id\":\"1A\",\"problem_index\":\"A\",\"status\":\"solved\"},{\"platform\":\"codeforces\",\"problem_id\":\"1B\",\"problem_index\":\"B\",\"status\":\"attempted\"}]}],\"total\":1}";
            if(p.equals("/api/forum/mine/posts/8/edit"))return "{\"id\":51}";
            if(p.equals("/api/forum/mine/posts/8"))return new JSONObject().put("id",8).put("title","测试投稿").put("status",submitVersion.get()>0?"pending":"rejected").put("review_reason","请补充解释").put("body","Original body").put("history",new JSONArray()).toString();
            if(p.equals("/api/forum/drafts/51/submit")){submitVersion.set(body.getInt("edit_version"));return "{\"id\":8}";}
            if(p.equals("/api/forum/drafts/51")){if("PUT".equals(getRequestMethod()))savedVersion.set(body.getInt("edit_version"));return new JSONObject().put("id",51).put("category_id",1).put("title","测试投稿标题").put("body","Original body").put("edit_version",savedVersion.get()>0?5:4).put("source_post_id",8).toString();}
            if(p.equals("/api/forum/categories"))return "[{\"id\":1,\"name\":\"求助\",\"slug\":\"help\"}]";
            if(p.equals("/api/mobile/v1/forum/posts"))return "{\"rows\":[{\"id\":8,\"title\":\"公开成员话题\",\"author_name\":\"公开成员\",\"author_public_member_id\":\""+HASH+"\"},{\"id\":9,\"title\":\"无ID话题\",\"author_name\":\"无公开ID成员\",\"total_count\":999}],\"total\":2}";
            if(p.equals("/api/mobile/v1/forum/posts/8")){detailReads.incrementAndGet();return "{\"id\":8,\"title\":\"测试话题\",\"body\":\"# Test\",\"likes_count\":0,\"viewer_liked\":false,\"viewer_bookmarked\":false,\"comments\":[]}";}
            if(p.endsWith("/comments"))return "{\"id\":77}";
            if(p.endsWith("/like"))return "{\"active\":true,\"likes_count\":1}";
            throw new IOException("Fixture has no API for "+getRequestMethod()+" "+p);
        }
        private InputStream bytes(String value){return new ByteArrayInputStream(url.getPath().contains("/images/")?png:value.getBytes(StandardCharsets.UTF_8));}
    }
}
