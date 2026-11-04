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
import java.util.concurrent.atomic.*;

/** Fixtures and synthetic transport belong only to the separate test APK. */
final class DesignUiSmoke {
    private final Instrumentation test;private Activity activity;
    private static final AtomicInteger detailGets=new AtomicInteger(),writes=new AtomicInteger(),commentIds=new AtomicInteger(70);
    private static final AtomicBoolean failLike=new AtomicBoolean(),failComment=new AtomicBoolean(),authLike=new AtomicBoolean(),authComment=new AtomicBoolean();
    private static volatile boolean liked,bookmarked;private static volatile long detailDelay;
    private DesignUiSmoke(Instrumentation test){this.test=test;}
    static void run(Instrumentation test){new DesignUiSmoke(test).execute();}
    private void execute(){
        Bundle output=new Bundle();int outcome=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)test.getTargetContext().getApplicationContext();ApiClient api=app.api();String original=api.getBaseUrl();SharedPreferences prefs=app.getSharedPreferences("acmforever_settings",0);
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{if(!"design.test.invalid".equals(url.getHost()))throw new IOException("Test forbids external traffic");return new Fake(url);}}:null);
            prefs.edit().putString("api_base_url","https://design.test.invalid").putBoolean("auto_login",false).putBoolean("profile_gradient",false).apply();ProfileCover.clear(app);
            api.setBaseUrl("https://design.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Isolated-Design-Test!");
            activity=test.startActivitySync(new Intent().setClassName(test.getTargetContext(),MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK).putExtra("club_post_id",1));
            await(()->description("话题点赞")!=null,5000,"topic detail");test.waitForIdleSync();
            final View[] input={null},like={null},bookmark={null};final ScrollView[] scroll={null};final int[] y={0};
            test.runOnMainSync(()->{
                input[0]=walk(activity.getWindow().getDecorView(),v->v instanceof EditText&&((EditText)v).getMinLines()==3);check(input[0]!=null,"comment editor");((EditText)input[0]).setText("Preserve this unsent comment");
                like[0]=description("话题点赞");bookmark[0]=description("收藏话题");View parent=like[0];while(parent.getParent() instanceof View){parent=(View)parent.getParent();if(parent instanceof ScrollView){scroll[0]=(ScrollView)parent;break;}}check(scroll[0]!=null,"topic scroll");scroll[0].scrollTo(0,160);y[0]=scroll[0].getScrollY();
                like[0].performClick();like[0].performClick();check(find("已赞 3")!=null&&!like[0].isEnabled(),"optimistic like before network completes");
            });
            await(()->like[0].isEnabled(),5000,"like confirmed");
            test.runOnMainSync(()->{check(description("话题点赞")==like[0],"same reaction view");check(((EditText)input[0]).getText().toString().equals("Preserve this unsent comment"),"input preserved");check(scroll[0].getScrollY()==y[0],"scroll preserved");bookmark[0].performClick();check(find("已收藏")!=null,"optimistic bookmark");});
            await(()->bookmark[0].isEnabled(),5000,"bookmark confirmed");check(detailGets.get()==1&&writes.get()==2,"no GET refresh and duplicate suppressed");
            test.runOnMainSync(()->{View send=find("发布评论");send.performClick();send.performClick();check(find("我 · 正在发送…")!=null,"pending comment immediately visible");check(!send.isEnabled(),"duplicate comment disabled");});
            await(()->find("我 · 评论 #71")!=null,5000,"comment confirmed");
            test.runOnMainSync(()->{check(walk(activity.getWindow().getDecorView(),v->v==input[0])!=null,"same editor after comment");check(((EditText)input[0]).getText().length()==0,"successful draft cleared");check(scroll[0].getScrollY()==y[0],"comment preserves scroll");check(!ModalDialogs.isShowing(activity),"no success dialog");});
            check(detailGets.get()==1&&writes.get()==3,"comment did not reload page");screenshot("reactions-v024.png");
            failLike.set(true);test.runOnMainSync(()->{like[0].performClick();check(find("赞 2")!=null,"optimistic unlike");});
            await(()->description("关闭操作失败提示")!=null&&description("关闭操作失败提示").isShown(),5000,"red write failure banner");
            test.runOnMainSync(()->{check(find("已赞 3")!=null,"failed like rolled back");check(!ModalDialogs.isShowing(activity),"write error is inline");description("关闭操作失败提示").performClick();});
            failComment.set(true);test.runOnMainSync(()->{((EditText)input[0]).setText("Keep this failed comment draft");find("发布评论").performClick();});
            await(()->find("发送失败 · 正文保留在输入框")!=null||find("发送失败 · 正文保留在下方输入框")!=null,5000,"failed comment status");
            test.runOnMainSync(()->{check(((EditText)input[0]).getText().toString().equals("Keep this failed comment draft"),"failed comment draft retained");check(!ModalDialogs.isShowing(activity),"no write failure modal");});
            int after=writes.get();Thread.sleep(800);check(writes.get()==after&&detailGets.get()==1,"writes never auto replayed");screenshot("write-failure-v024.png");
            authLike.set(true);test.runOnMainSync(()->like[0].performClick());
            await(()->!api.isLoggedIn()&&like[0].isEnabled(),5000,"expired reaction finishes");
            test.runOnMainSync(()->{check(find("已赞 3")!=null,"expired reaction rolled back");check(description("关闭操作失败提示").isShown(),"expired reaction inline error");});
            api.login("90000001","Isolated-Design-Test!");authComment.set(true);
            test.runOnMainSync(()->{((EditText)input[0]).setText("Preserve expired session draft");find("发布评论").performClick();});
            await(()->!api.isLoggedIn()&&find("发布评论")!=null,5000,"expired comment finishes");
            test.runOnMainSync(()->{check(((EditText)input[0]).getText().toString().equals("Preserve expired session draft"),"expired comment draft retained");check(description("关闭操作失败提示").isShown(),"expired comment inline error");});
            api.login("90000001","Isolated-Design-Test!");
            // Cache may arrive before a slow GET. Editing must protect the same view from that late read.
            api.getObject("/api/forum/posts/1");detailDelay=700;
            test.runOnMainSync(()->activity.finish());
            activity=test.startActivitySync(new Intent().setClassName(test.getTargetContext(),MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK).putExtra("club_post_id",1));
            await(()->description("话题点赞")!=null,5000,"cached topic");
            final View[] cached={null};test.runOnMainSync(()->{cached[0]=walk(activity.getWindow().getDecorView(),v->v instanceof EditText&&((EditText)v).getMinLines()==3);((EditText)cached[0]).setText("Keep typing during refresh");});
            Thread.sleep(1200);test.runOnMainSync(()->{check(walk(activity.getWindow().getDecorView(),v->v==cached[0])!=null,"late GET keeps editor instance");check(((EditText)cached[0]).getText().toString().equals("Keep typing during refresh"),"late GET keeps draft");});detailDelay=0;
            clickDescription("个人中心");await(()->description("Codeforces通过题数 12")!=null,5000,"profile platform counts");test.waitForIdleSync();Thread.sleep(300);
            final View[] panel={null};test.runOnMainSync(()->{panel[0]=description("平台详情区域");check(panel[0]!=null,"single panel");assertFlat(activity.getWindow().getDecorView());assertButtonGaps(activity.getWindow().getDecorView());});screenshot("profile-white-v024.png");
            clickDescription("切换平台 AtCoder");await(()->description("AtCoder通过题数 5")!=null,3000,"platform tab");
            test.runOnMainSync(()->{check(description("平台详情区域")==panel[0],"same detail panel");check(!ModalDialogs.isShowing(activity),"platform switch never opens a window");check(description("切换平台 AtCoder").isSelected(),"selected platform state");check(description("Codeforces通过题数 12")==null,"only one platform detail");});screenshot("platform-v024.png");
            Bitmap cover=Bitmap.createBitmap(320,200,Bitmap.Config.ARGB_8888);cover.eraseColor(0xff718dd8);File file=new File(app.getCacheDir(),"design-cover.png");try(FileOutputStream stream=new FileOutputStream(file)){cover.compress(Bitmap.CompressFormat.PNG,100,stream);}cover.recycle();
            int before=writes.get();ProfileCover.save(app,android.net.Uri.fromFile(file));file.delete();check(writes.get()==before,"cover never uploaded");
            prefs.edit().putBoolean("profile_gradient",true).apply();clickDescription("主页");await(()->description("筛选社区话题")!=null,5000,"forum");
            clickDescription("筛选社区话题");await(()->ModalDialogs.isShowing(activity),3000,"filter");test.waitForIdleSync();screenshot("filters-v024.png");
            test.runOnMainSync(()->{
                try{java.lang.reflect.Field f=MainActivity.class.getDeclaredField("forumFilterDialog");f.setAccessible(true);AlertDialog originalDialog=(AlertDialog)f.get(activity);description("筛选社区话题").performClick();check(f.get(activity)==originalDialog,"one filter window");View radio=walk(originalDialog.getWindow().getDecorView(),v->v instanceof RadioButton&&"热门话题".equals(((RadioButton)v).getText().toString()));check(radio!=null,"styled choice");radio.performClick();check(((RadioButton)radio).isChecked(),"radio state");assertButtonGaps(originalDialog.getWindow().getDecorView());ModalDialogs.close(activity);}catch(Exception e){throw new AssertionError(e);}
            });
            clickDescription("个人中心");await(()->description("AtCoder通过题数 5")!=null,5000,"selected platform retained");Thread.sleep(300);screenshot("profile-gradient-v024.png");
            test.runOnMainSync(()->{Bitmap bitmap=Bitmap.createBitmap(300,300,Bitmap.Config.ARGB_8888);android.graphics.drawable.Drawable d=ProfileCover.drawable(app,true);d.setBounds(0,0,300,300);d.draw(new Canvas(bitmap));check(bitmap.getPixel(150,210)==Color.WHITE&&bitmap.getPixel(150,285)==Color.WHITE,"gradient bottom remains white");bitmap.recycle();});
            final AlertDialog[] gallery={null};test.runOnMainSync(()->{
                LinearLayout grid=new LinearLayout(activity);grid.setOrientation(1);String[] names={"forum","rank","compose","problems","mine","search","filter","comment","like","bookmark","drafts","checkin","eye","eye-off","settings","history","back","close","next","copy","zoom-in","zoom-out","fit","link","report","download"};
                for(int i=0;i<names.length;i+=4){LinearLayout row=new LinearLayout(activity);grid.addView(row);for(int j=i;j<Math.min(i+4,names.length);j++){LinearLayout cell=new LinearLayout(activity);cell.setOrientation(1);cell.setGravity(Gravity.CENTER);cell.setPadding(4,10,4,10);ImageView image=new ImageView(activity);image.setImageDrawable(AppIcons.get(activity,names[j],MobileStyle.TEXT));cell.addView(image,new LinearLayout.LayoutParams(72,72));TextView caption=new TextView(activity);caption.setText(names[j]);caption.setTextSize(10);cell.addView(caption);row.addView(cell,new LinearLayout.LayoutParams(0,140,1));}}
                grid.addView(new CodingCatView(activity),new LinearLayout.LayoutParams(-1,320));gallery[0]=new ModalDialogs.Builder(activity).setTitle("新版猫娘图标 · v0.2.4").setView(grid).fullPage().show();
            });test.waitForIdleSync();screenshot("icons-v024.png");test.runOnMainSync(()->gallery[0].dismiss());
            test.runOnMainSync(()->{LinearLayout body=new LinearLayout(activity);body.setOrientation(1);body.addView(new CodingCatView(activity),new LinearLayout.LayoutParams(-1,500));new ModalDialogs.Builder(activity).setTitle("正在加载").setView(body).setPositiveButton("完成",null).show();});test.waitForIdleSync();screenshot("loading-dialog-v024.png");test.runOnMainSync(()->ModalDialogs.close(activity));
            output.putString("stream","PASS: immediate likes/comments, duplicate suppression, no GET reload, same views/scroll, rollback and red write errors, retained drafts, late read protection, expired-session write cleanup, single logo tabs/panel, selected tab persistence, flat controls and gaps, local cover, new art screenshots.\n");output.putBoolean("passed",true);outcome=Activity.RESULT_OK;
        }catch(Throwable e){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));output.putBoolean("passed",false);}
        finally{if(activity!=null)test.runOnMainSync(()->{ModalDialogs.close(activity);activity.finish();});try{api.logout();}catch(Exception ignored){}ProfileCover.clear(app);prefs.edit().remove("api_base_url").remove("profile_gradient").apply();api.setBaseUrl(original);}
        test.finish(outcome,output);
    }
    private void screenshot(String name)throws Exception{if("platform-v024.png".equals(name)){test.runOnMainSync(()->{View panel=description("平台详情区域");panel.requestRectangleOnScreen(new Rect(0,0,panel.getWidth(),panel.getHeight()),true);});}Thread.sleep(250);Bitmap screenshot=test.getUiAutomation().takeScreenshot();if(screenshot==null)throw new AssertionError("No screenshot");try(FileOutputStream out=new FileOutputStream(new File(test.getTargetContext().getExternalFilesDir(null),name))){screenshot.compress(Bitmap.CompressFormat.PNG,100,out);}finally{screenshot.recycle();}}
    private void assertFlat(View view){if(view instanceof Button||view instanceof ImageButton)check(view.getElevation()==0&&view.getTranslationZ()==0&&view.getStateListAnimator()==null,"flat control");if(view instanceof ViewGroup){ViewGroup g=(ViewGroup)view;for(int i=0;i<g.getChildCount();i++)assertFlat(g.getChildAt(i));}}
    private void assertButtonGaps(View view){
        if(view instanceof LinearLayout){LinearLayout line=(LinearLayout)view;View previous=null;for(int i=0;i<line.getChildCount();i++){View child=line.getChildAt(i);if(child.getVisibility()!=View.VISIBLE)continue;if(previous instanceof Button&&child instanceof Button){int gap=line.getOrientation()==LinearLayout.HORIZONTAL?child.getLeft()-previous.getRight():child.getTop()-previous.getBottom();check(gap>=MobileStyle.dp(activity,5),"adjacent buttons need gap");}previous=child;}}
        if(view instanceof ViewGroup){ViewGroup g=(ViewGroup)view;for(int i=0;i<g.getChildCount();i++)assertButtonGaps(g.getChildAt(i));}
    }
    private void check(boolean okay,String message){if(!okay)throw new AssertionError(message);}
    private void await(java.util.function.BooleanSupplier condition,long timeout,String message)throws Exception{long end=System.currentTimeMillis()+timeout;while(System.currentTimeMillis()<end){boolean[] okay={false};test.runOnMainSync(()->okay[0]=condition.getAsBoolean());if(okay[0])return;Thread.sleep(60);}throw new AssertionError(message);}
    private View walk(View view,java.util.function.Predicate<View> match){if(match.test(view))return view;if(view instanceof ViewGroup){ViewGroup g=(ViewGroup)view;for(int i=0;i<g.getChildCount();i++){View found=walk(g.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String text){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&text.equals(((TextView)v).getText().toString()));}
    private View description(String text){return walk(activity.getWindow().getDecorView(),v->text.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private void clickDescription(String text){test.runOnMainSync(()->{View view=description(text);check(view!=null,"Missing "+text);view.performClick();});}
    private static final class Fake extends HttpURLConnection {
        private boolean served,failed,unauthorized;private String body="{}";
        Fake(URL url){super(url);}@Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}@Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=isolated-design; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public int getResponseCode(){if(url.getPath().equals("/api/mobile/v1/capabilities"))return 404;serve();return unauthorized?401:failed?500:200;}
        @Override public InputStream getErrorStream(){return new ByteArrayInputStream("{\"error\":\"isolated service failure\"}".getBytes(StandardCharsets.UTF_8));}
        @Override public InputStream getInputStream(){serve();return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));}
        private void serve(){if(served)return;served=true;String path=url.getPath();
            try{
                if(path.endsWith("/auth/me"))body="{\"authenticated\":true,\"csrf_token\":\"test-only\",\"role\":\"member\",\"qq_id\":\"90000001\"}";
                else if(path.endsWith("/like")){writes.incrementAndGet();Thread.sleep(350);failed=failLike.getAndSet(false);unauthorized=authLike.getAndSet(false);if(!failed&&!unauthorized)liked=!liked;body="{\"active\":"+liked+"}";}
                else if(path.endsWith("/bookmark")){writes.incrementAndGet();Thread.sleep(350);bookmarked=!bookmarked;body="{\"active\":"+bookmarked+"}";}
                else if(path.endsWith("/comments")){writes.incrementAndGet();Thread.sleep(350);failed=failComment.getAndSet(false);unauthorized=authComment.getAndSet(false);body="{\"id\":"+commentIds.incrementAndGet()+",\"success\":true}";}
                else if(path.endsWith("/posts/1")){detailGets.incrementAndGet();Thread.sleep(detailDelay);body="{\"id\":1,\"title\":\"Isolated topic for UI verification\",\"author_name\":\"Test member\",\"body\":\"Only the test APK contains this fixture.\\n\\nA topic checks that comments do not refresh the whole page.\",\"likes_count\":"+ (liked?3:2)+",\"viewer_liked\":"+liked+",\"comments\":[]}";}
                else if(path.endsWith("/me/profile"))body="{\"user\":{\"name\":\"UI test member\",\"qq_id\":\"90000001\"},\"platform_counts\":{\"codeforces\":12,\"luogu\":8,\"atcoder\":5,\"nowcoder\":3,\"cjlu\":2},\"total_count\":30,\"recent_ac\":[]}";
                else if(path.endsWith("/forum/posts"))body="{\"rows\":[],\"total\":0}";
                else if(path.endsWith("/categories"))body="[{\"id\":1,\"slug\":\"help\",\"name\":\"求助\"},{\"id\":2,\"slug\":\"solution\",\"name\":\"题解\"},{\"id\":3,\"slug\":\"training\",\"name\":\"训练\"},{\"id\":4,\"slug\":\"event\",\"name\":\"活动\"}]";
                else if(path.contains("/mine/")||path.endsWith("/drafts"))body="[]";
            }catch(InterruptedException e){Thread.currentThread().interrupt();throw new RuntimeException(e);}
        }
    }
}
