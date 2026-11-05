package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.ArrayDeque;
import java.util.concurrent.*;

/** Mobile readers for the existing Web APIs. No administration or invented content. */
public final class WebFeaturesActivity extends Activity {
    private interface Display { void show(Object data)throws Exception; }
    private interface Write { Object run()throws Exception; }
    private ApiClient api;private LinearLayout root,body;private TextView heading;private ScrollView scroll;
    private PageRefresh refresh;private ActionNotice notice;private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final Handler ui=new Handler(Looper.getMainLooper());private final ArrayDeque<String> history=new ArrayDeque<>();
    private JSONObject route;private int serial;private boolean reading,writing,active;private Runnable currentRead;
    private final Runnable poll=new Runnable(){public void run(){if(active&&"notifications".equals(view())&&currentRead!=null)currentRead.run();if(active)ui.postDelayed(this,30000);}};
    private int dp(float value){return MobileStyle.dp(this,value);}
    private JSONObject state(String view){return put(new JSONObject(),"view",view);}
    private JSONObject put(JSONObject json,String key,Object value){try{return json.put(key,value);}catch(JSONException e){throw new IllegalArgumentException(e);}}
    private String view(){return route.optString("view","wiki");}
    private int page(){return Math.max(1,route.optInt("page",1));}
    static String encode(String value){try{return java.net.URLEncoder.encode(value,"UTF-8");}catch(java.io.UnsupportedEncodingException e){throw new AssertionError(e);}}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();
        try{route=saved==null?put(state(getIntent().getStringExtra("feature")==null?"wiki":getIntent().getStringExtra("feature")),"id",getIntent().getIntExtra("post_id",0)):new JSONObject(saved.getString("route"));}catch(Exception e){route=state("wiki");}
        if(saved==null){String slug=getIntent().getStringExtra("wiki_slug"),query=getIntent().getStringExtra("initial_query");if(slug!=null)put(route,"slug",slug);if(query!=null)put(route,"q",query);}
        if(saved!=null){java.util.ArrayList<String> back=saved.getStringArrayList("history");if(back!=null)history.addAll(back);}
        root=column();root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        LinearLayout top=row();top.setPadding(dp(12),dp(8),dp(12),dp(8));top.setBackgroundColor(MobileStyle.CHROME);
        Button back=button("返回",this::onBackPressed);top.addView(back);heading=text("",21);top.addView(heading,new LinearLayout.LayoutParams(0,-2,1));root.addView(top);
        refresh=new PageRefresh(this,root,1);notice=new ActionNotice(this,root,2);scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=column();body.setPadding(dp(14),dp(16),dp(14),dp(24));scroll.addView(body);render();
    }
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("route",route.toString());out.putStringArrayList("history",new java.util.ArrayList<>(history));}
    @Override protected void onResume(){super.onResume();active=true;ui.removeCallbacks(poll);ui.postDelayed(poll,30000);}
    @Override protected void onPause(){active=false;ui.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){serial++;ui.removeCallbacksAndMessages(null);io.shutdownNow();refresh.close();ModalDialogs.close(this);super.onDestroy();}
    @Override public void onBackPressed(){if(writing)return;if(history.isEmpty()){finish();return;}try{route=new JSONObject(history.pop());render();}catch(Exception e){finish();}}
    private void nav(JSONObject next){if(writing)return;history.push(route.toString());route=next;scroll.scrollTo(0,0);render();}
    private void filter(String key,Object value){if(writing)return;put(route,key,value);put(route,"page",1);render();}
    private LinearLayout column(){LinearLayout box=new SpacedLayout(this);box.setOrientation(LinearLayout.VERTICAL);return box;}
    private LinearLayout row(){LinearLayout box=new SpacedLayout(this);box.setOrientation(LinearLayout.HORIZONTAL);box.setGravity(Gravity.CENTER_VERTICAL);return box;}
    private TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextColor(MobileStyle.TEXT);t.setTextSize(size);t.setPadding(0,dp(5),0,dp(7));if(size>=17)t.setTypeface(null,android.graphics.Typeface.BOLD);return t;}
    private Button button(String title,Runnable run){Button b=new Button(this);b.setText(title);MobileStyle.button(b,false);b.setOnClickListener(v->{if(!writing&&!ModalDialogs.isShowing(this))run.run();});return b;}
    private LinearLayout card(LinearLayout parent){LinearLayout box=column();box.setPadding(dp(16),dp(14),dp(16),dp(14));box.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,12,0));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);parent.addView(box,p);return box;}
    private void error(LinearLayout slot,Exception e){slot.removeAllViews();slot.setMinimumHeight(dp(160));ErrorModule.style(slot);TextView title=text(FailureState.title(e),17);title.setTextColor(ErrorModule.ink());slot.addView(title);slot.addView(button("重试",this::render));}
    private String date(long seconds){if(seconds<=0)return "未记录时间";java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",java.util.Locale.CHINA);f.setTimeZone(java.util.TimeZone.getTimeZone("Asia/Shanghai"));return f.format(new java.util.Date(seconds*1000));}
    private String status(String value){switch(value){case "pending":return "等待审核";case "published":return "审核通过，已发布";case "rejected":return "审核未通过";case "removed":return "已删除";default:return "服务器状态："+value;}}
    private void pager(LinearLayout slot,int total,int size){int last=Math.max(1,(total+size-1)/size);LinearLayout row=row();Button previous=button("上一页",()->{put(route,"page",page()-1);render();}),next=button("下一页",()->{put(route,"page",page()+1);render();});previous.setEnabled(page()>1);next.setEnabled(page()<last);row.addView(previous);TextView at=text("第 "+page()+" 页 / 共 "+last+" 页",12);at.setGravity(Gravity.CENTER);row.addView(at,new LinearLayout.LayoutParams(0,-2,1));row.addView(next);slot.addView(row);}
    private void chips(LinearLayout parent,String[] labels,String[] values,String selected,java.util.function.Consumer<String> choose){WrapLayout wrap=new WrapLayout(this);parent.addView(wrap,new LinearLayout.LayoutParams(-1,-2));for(int i=0;i<labels.length;i++){String value=values[i];Button b=button(labels[i],()->choose.accept(value));MobileStyle.control(b,false,selected.equals(value),12);wrap.addView(b);}}
    private void search(LinearLayout parent,String hint,Runnable searchAction){EditText input=new EditText(this);input.setHint(hint);input.setSingleLine(true);input.setText(route.optString("q"));input.setContentDescription(hint);parent.addView(input);parent.addView(button("搜索",()->{put(route,"q",input.getText().toString().trim());put(route,"page",1);searchAction.run();}));}
    private void load(String path,Display display){
        LinearLayout slot=column();body.addView(slot,new LinearLayout.LayoutParams(-1,-2));slot.addView(text("正在加载…",14));int token=serial;long account=api.sessionGeneration();final String[] rendered={null};
        java.util.function.Consumer<Object> show=data->{if(token!=serial||account!=api.sessionGeneration()||isDestroyed())return;if(data.toString().equals(rendered[0]))return;int y=scroll.getScrollY();slot.removeAllViews();slot.setMinimumHeight(0);slot.setBackgroundColor(Color.TRANSPARENT);try{displayInto=slot;display.show(data);rendered[0]=data.toString();AppAppearance.paintFields(slot);scroll.post(()->scroll.scrollTo(0,y));}catch(Exception e){rendered[0]=null;error(slot,e);}};
        currentRead=()->{if(reading||token!=serial||isDestroyed())return;reading=true;refresh.start(token);io.execute(()->{Object data=null;Exception failure=null;try{data=api.get(path);}catch(Exception e){failure=e;}Object result=data;Exception err=failure;runOnUiThread(()->{if(token!=serial||isDestroyed())return;reading=false;if(account!=api.sessionGeneration()){rendered[0]=null;slot.removeAllViews();error(slot,new ApiClient.ApiException(401,"登录账号已切换",false));refresh.finish(token);return;}if(err==null)show.accept(result);else if(!refresh.failure(FailureState.title(err))){rendered[0]=null;error(slot,err);}refresh.finish(token);});});};
        Runnable read=currentRead;refresh.register(token,read);io.execute(()->{api.beginReplay();try{Object cached=api.get(path);runOnUiThread(()->{if(token==serial){refresh.cached(token);show.accept(cached);}});}catch(Exception ignored){}finally{api.endReplay();}runOnUiThread(()->{if(token==serial)read.run();});});
    }
    private LinearLayout displayInto;
    private void write(Button source,Write work,java.util.function.Consumer<Object> done){
        if(writing)return;writing=true;source.setEnabled(false);notice.hide();int token=serial;long owner=api.sessionGeneration();
        io.execute(()->{Object data=null;Exception failure=null;try{synchronized(api){if(owner!=api.sessionGeneration())throw new IllegalStateException("登录账号已切换");data=work.run();}}catch(Exception e){failure=e;}Object result=data;Exception err=failure;runOnUiThread(()->{writing=false;if(isDestroyed()||token!=serial||owner!=api.sessionGeneration())return;source.setEnabled(true);if(err!=null)notice.show("操作",err);else done.accept(result);});});
    }
    private void render(){
        serial++;reading=false;currentRead=null;refresh.reset(serial);refresh.userAction();notice.hide();body.removeAllViews();heading.setText(title());
        if(!view().startsWith("wiki")&&!api.isLoggedIn()){error(card(body),new ApiClient.ApiException(401,"请先在账号设置登录",false));return;}
        switch(view()){case "notifications":notifications();break;case "submissions":submissions();break;case "progress":progress();break;case "tracker":tracker();break;case "wiki-list":wikiList();break;case "wiki-article":wikiArticle();break;case "wiki-history":wikiHistory();break;default:wiki();}AppAppearance.paintFields(body);
    }
    private String title(){switch(view()){case "notifications":return "通知中心";case "submissions":return "我的投稿";case "progress":return "投稿进度";case "tracker":return "比赛进度";default:return "Wiki 手册";}}
    private void notifications(){
        LinearLayout tools=card(body);chips(tools,new String[]{"全部通知","未读通知"},new String[]{"all","unread"},route.optString("scope","all"),v->filter("scope",v));tools.addView(button("刷新",this::render));
        load("/api/me/notifications?page="+page()+"&page_size=20"+("unread".equals(route.optString("scope"))?"&unread=1":""),data->{JSONObject result=(JSONObject)data;JSONArray rows=result.getJSONArray("rows");LinearLayout slot=displayInto;slot.addView(text("未读 "+result.getInt("unread_count")+" 条",14));
            Button all=button("全部标为已读",()->{});all.setEnabled(result.getInt("unread_count")>0);all.setOnClickListener(v->write(all,()->api.writeObject("POST","/api/me/notifications/read-all",put(new JSONObject(),"through_id",result.getInt("latest_id"))),r->render()));slot.addView(all);
            if(rows.length()==0)slot.addView(text("暂无通知",15));
            for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.optLong("read_at")==0?"未读":"已读",12));box.addView(text(item.getString("post_title"),17));box.addView(text(item.optString("actor_name")+" · "+date(item.optLong("created_at")),12));
                String kind=item.getString("kind");box.addView(text("rejected".equals(kind)?"退回原因："+item.optString("review_reason","此前未记录原因"):"published".equals(kind)?"审核通过":"reply".equals(kind)?"收到回复":"收到评论",14));
                String target=item.optString("target_url");Button open=button(target.isEmpty()?"原话题已不可访问":"查看详情",()->{});open.setEnabled(!target.isEmpty());open.setOnClickListener(v->write(open,()->api.writeObject("POST","/api/me/notifications/"+item.getInt("id")+"/read",new JSONObject()),r->openNotification(target)));box.addView(open);
                if(item.optLong("read_at")==0){Button mark=button("标为已读",()->{});mark.setOnClickListener(v->write(mark,()->api.writeObject("POST","/api/me/notifications/"+item.getInt("id")+"/read",new JSONObject()),r->render()));box.addView(mark);}
            }pager(slot,result.getInt("total"),20);
        });
    }
    private void openNotification(String value){try{Uri target=Uri.parse(value);if(target.getScheme()!=null||target.getHost()!=null)throw new IllegalArgumentException("通知地址格式异常");int id=Integer.parseInt(target.getQueryParameter("id"));if(id<=0)throw new IllegalArgumentException("通知缺少话题编号");if("/my-post.html".equals(target.getPath()))nav(put(state("progress"),"id",id));else if("/post.html".equals(target.getPath())){int comment=0;try{comment=Integer.parseInt(target.getQueryParameter("comment_id"));}catch(Exception ignored){}startActivity(new Intent(this,MainActivity.class).putExtra("club_post_id",id).putExtra("notification_comment_id",comment));}else throw new IllegalArgumentException("通知目标不可识别");}catch(Exception e){notice.show("打开通知",e);}}
    private void submissions(){load("/api/forum/mine/posts",data->{JSONArray items=(JSONArray)data;LinearLayout slot=displayInto;if(items.length()==0)slot.addView(text("暂无投稿",15));for(int i=0;i<items.length();i++){JSONObject item=items.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.getString("title"),17));box.addView(text(status(item.getString("status")),13));box.addView(button("查看投稿进度",()->nav(put(state("progress"),"id",item.optInt("id")))));}});}
    private void progress(){
        load("/api/forum/mine/posts/"+route.optInt("id"),data->{JSONObject post=(JSONObject)data;LinearLayout slot=displayInto,box=card(slot);box.addView(text(post.getString("title"),20));box.addView(text(status(post.getString("status")),16));box.addView(text("提交时间："+date(post.optLong("created_at"))+"\n审核时间："+date(post.optLong("reviewed_at")),13));
            if("rejected".equals(post.getString("status")))box.addView(text("退回原因："+post.optString("review_reason","此前未记录原因"),14));
            box.addView(button("刷新状态",this::render));
            if(!"removed".equals(post.getString("status"))){Button edit=button("rejected".equals(post.getString("status"))?"修改后重新投稿":"修改帖子",()->{});edit.setOnClickListener(v->write(edit,()->api.writeObject("POST","/api/forum/mine/posts/"+post.getInt("id")+"/edit",new JSONObject()),r->{int id=((JSONObject)r).optInt("id");if(id>0)startActivity(new Intent(this,MainActivity.class).putExtra("cloud_draft_id",id));else notice.show("加载修改草稿",new IllegalArgumentException("缺少草稿编号"));}));box.addView(edit);}
            if("published".equals(post.getString("status")))box.addView(button("查看公开话题",()->startActivity(new Intent(this,MainActivity.class).putExtra("club_post_id",post.optInt("id")))));
            LinearLayout article=card(slot);article.addView(text("投稿原文 · 仅本人可见",12));article.addView(new ContentView(this,post.getString("body"),false,this::openLink));
            JSONArray history=post.optJSONArray("history");if(history!=null)for(int i=0;i<history.length();i++){JSONObject old=history.getJSONObject(i);LinearLayout snapshot=card(slot);snapshot.addView(text("第 "+old.getInt("content_version")+" 版 · "+old.optString("title"),15));snapshot.addView(text(status(old.optString("status")),12));if(!old.optString("review_reason").isEmpty())snapshot.addView(text(old.optString("review_reason"),13));snapshot.addView(button("查看该版原文",()->{LinearLayout content=column();content.addView(new ContentView(this,old.optString("body"),false,this::openLink));new ModalDialogs.Builder(this).setTitle("历史原文 · 仅本人可见").setView(content).fullPage().show();}));}
        });
    }
    private void tracker(){
        LinearLayout tools=card(body);chips(tools,new String[]{"Codeforces","AtCoder"},new String[]{"codeforces","atcoder"},route.optString("platform","codeforces"),v->filter("platform",v));chips(tools,new String[]{"全部题目","我已 AC","已收藏"},new String[]{"all","solved","favorite"},route.optString("scope","all"),v->filter("scope",v));search(tools,"搜索比赛、题号或标签",this::render);
        String scope=route.optString("scope","all");load("/api/me/problems/tracker?platform="+route.optString("platform","codeforces")+"&scope="+("solved".equals(scope)?"solved":"all")+"&state="+("favorite".equals(scope)?"favorite":"")+"&tag="+encode(route.optString("q"))+"&page="+page()+"&page_size=20",data->{JSONObject result=(JSONObject)data;JSONArray contests=result.getJSONArray("items");LinearLayout slot=displayInto;slot.addView(text("进度依据本人已同步记录；未记录不代表从未提交。",12));if(contests.length()==0)slot.addView(text("暂无比赛记录",15));
            for(int i=0;i<contests.length();i++){JSONObject contest=contests.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(contest.optString("contest_name",contest.optString("contest_id")),18));box.addView(text(contest.optLong("start_time")>0?date(contest.optLong("start_time")):"比赛时间未收录",12));box.addView(text("已 AC "+contest.getInt("solved_count")+" / "+contest.getInt("total_count")+" · 尝试未通过 "+contest.optInt("attempted_count"),14));JSONArray problems=contest.getJSONArray("problems");WrapLayout wrap=new WrapLayout(this);box.addView(wrap,new LinearLayout.LayoutParams(-1,-2));for(int n=0;n<problems.length();n++){JSONObject problem=problems.getJSONObject(n);String state=problem.getString("status"),label="solved".equals(state)?"已 AC":"attempted".equals(state)?"尝试未通过":"未记录";Button item=button(problem.optString("problem_index",problem.getString("problem_id"))+" · "+label,()->openProblem(problem));item.setContentDescription(problem.optString("problem_name")+" · "+label);if("solved".equals(state)){item.setTextColor(0xff285b32);item.setBackground(MobileStyle.panel(this,0xffe5f2df,10,0xff7fa882));}else if("attempted".equals(state)){item.setTextColor(0xffaf2424);item.setBackground(MobileStyle.panel(this,0xffffe8e6,10,0xffc98b87));}wrap.addView(item);}}
            pager(slot,result.getInt("total"),20);
        });
    }
    private void openProblem(JSONObject problem){startActivity(new Intent(this,MainActivity.class).putExtra("web_problem_platform",problem.optString("platform")).putExtra("web_problem_id",problem.optString("problem_id")));}
    private void wiki(){LinearLayout tools=card(body);search(tools,"搜索 Wiki",()->nav(put(state("wiki-list"),"q",route.optString("q"))));load("/api/wiki/navigation",data->{JSONArray categories=((JSONObject)data).getJSONArray("categories");LinearLayout slot=displayInto;if(categories.length()==0)slot.addView(text("暂无公开分类",15));for(int i=0;i<categories.length();i++){JSONObject category=categories.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(category.getString("name"),category.isNull("parent_id")?18:15));if(!category.optString("description").isEmpty())box.addView(text(category.optString("description"),13));box.addView(button("查看文章",()->nav(put(state("wiki-list"),"category",category.optInt("id")))));}});}
    private void wikiList(){String q=route.optString("q");LinearLayout tools=card(body);search(tools,"搜索 Wiki",this::render);String path=q.isEmpty()?"/api/wiki/pages?category_id="+route.optInt("category"):"/api/wiki/search?q="+encode(q);load(path+"&page="+page()+"&page_size=20",data->{JSONObject result=(JSONObject)data;JSONArray items=result.getJSONArray("items");LinearLayout slot=displayInto;if(items.length()==0)slot.addView(text("暂无公开文章",15));for(int i=0;i<items.length();i++){JSONObject item=items.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.getString("title"),18));box.addView(text(item.optString("summary"),13));box.addView(button("阅读文章",()->nav(put(state("wiki-article"),"slug",item.optString("slug")))));}pager(slot,result.getInt("total"),20);});}
    private void wikiArticle(){String slug=route.optString("slug"),suffix=route.optInt("revision")>0?"/revisions/"+route.optInt("revision"):"";load("/api/wiki/pages/"+encode(slug)+suffix,data->{JSONObject article=(JSONObject)data;LinearLayout slot=displayInto,box=card(slot);box.addView(text(article.getString("title"),22));box.addView(text(article.optString("summary"),14));box.addView(button("公开历史",()->nav(put(state("wiki-history"),"slug",slug))));box.addView(new ContentView(this,article.getString("body"),false,this::openLink));if(!article.optString("source").isEmpty())box.addView(text("来源："+article.optString("source"),12));if(!article.optString("license").isEmpty())box.addView(text("许可："+article.optString("license"),12));JSONArray exercises=article.optJSONArray("exercises");if(exercises!=null&&exercises.length()>0){LinearLayout practice=card(slot);practice.addView(text("关联练习",17));for(int i=0;i<exercises.length();i++){JSONObject exercise=exercises.getJSONObject(i);practice.addView(button(exercise.optString("label","练习"),()->openLink(exercise.optString("url"))));}}});}
    private void wikiHistory(){String slug=route.optString("slug");load("/api/wiki/pages/"+encode(slug)+"/revisions",data->{JSONArray rows=(JSONArray)data;LinearLayout slot=displayInto;if(rows.length()==0)slot.addView(text("暂无公开历史",15));for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);slot.addView(button(item.getString("title")+" · "+date(item.optLong("published_at")),()->nav(put(put(state("wiki-article"),"slug",slug),"revision",item.optInt("id")))));}});}
    private void openLink(String value){
        try{
            Uri url=Uri.parse(value);
            if(url.getScheme()==null&&url.getAuthority()==null&&"/problem.html".equals(url.getPath())){
                String platform=url.getQueryParameter("platform"),id=url.getQueryParameter("problem_id");
                if(platform==null||platform.trim().isEmpty()||id==null||id.trim().isEmpty())throw new IllegalArgumentException("站内题面链接缺少平台或题号");
                openProblem(new JSONObject().put("platform",platform).put("problem_id",id));return;
            }
            if(url.getPath()!=null&&url.getPath().endsWith("wiki.html")&&url.getQueryParameter("slug")!=null){nav(put(state("wiki-article"),"slug",url.getQueryParameter("slug")));return;}
            if(!"https".equalsIgnoreCase(url.getScheme()))throw new IllegalArgumentException("仅支持 HTTPS 外链");
            startActivity(new Intent(Intent.ACTION_VIEW,url));
        }catch(Exception e){notice.show("打开链接",e);}
    }
}
