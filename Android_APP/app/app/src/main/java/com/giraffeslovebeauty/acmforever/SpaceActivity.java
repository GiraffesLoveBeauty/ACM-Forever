package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.concurrent.*;

/** Account-scoped community pages. Cached reads never fabricate content or replay writes. */
public final class SpaceActivity extends Activity {
    private ApiClient api;private PageRefresh refresh;private ActionNotice notice;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private LinearLayout root,list;private TextView count;private ScrollView scroll;
    private String kind,query="",scope="all";private JSONArray rows;
    private boolean writing,opening;private int serial;private long account;
    private int dp(int n){return MobileStyle.dp(this,n);}
    private LinearLayout column(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.VERTICAL);return b;}
    private TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(size<15?MobileStyle.MUTED:MobileStyle.TEXT);t.setPadding(0,dp(5),0,dp(5));if(size>=17)t.setTypeface(null,android.graphics.Typeface.BOLD);return t;}
    private Button button(String title,Runnable action){Button b=new Button(this);b.setText(title);MobileStyle.button(b,false);b.setOnClickListener(v->{if(!writing&&!opening&&!ModalDialogs.isShowing(this))action.run();});return b;}
    private LinearLayout card(LinearLayout parent){LinearLayout box=column();box.setPadding(dp(18),dp(16),dp(18),dp(16));box.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(14);parent.addView(box,p);return box;}
    private boolean drafts(){return "drafts".equals(kind);}
    private boolean bookmarks(){return "bookmarks".equals(kind);}
    private String title(){return drafts()?"云端草稿":bookmarks()?"话题收藏":"我的话题";}
    private String path(){return drafts()?"/api/forum/drafts":bookmarks()?"/api/forum/mine/bookmarks":"/api/forum/mine/posts";}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();account=api.sessionGeneration();kind=getIntent().getStringExtra("kind");if(saved!=null){query=saved.getString("query","");scope=saved.getString("scope","all");}
        root=column();root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        LinearLayout header=new SpacedLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(12),dp(8),dp(12),dp(8));header.setBackgroundColor(MobileStyle.CHROME);header.addView(button("返回",this::finish));header.addView(text(title(),21),new LinearLayout.LayoutParams(0,-2,1));header.addView(button("刷新",this::load));root.addView(header);
        refresh=new PageRefresh(this,root,1);notice=new ActionNotice(this,root,2);
        scroll=new ScrollView(this);root.addView(PullRefreshLayout.forPage(this,scroll,refresh,()->!ModalDialogs.isShowing(this)),new LinearLayout.LayoutParams(-1,0,1));LinearLayout body=column();body.setPadding(dp(14),dp(16),dp(14),dp(24));scroll.addView(body);
        LinearLayout intro=card(body);TextView heading=text(title(),24);AppIcons.on(heading,drafts()?"drafts":bookmarks()?"bookmark":"forum",MobileStyle.BRAND,28);intro.addView(heading);
        intro.addView(text(drafts()?"多份草稿 · 编辑中自动保存到云端":bookmarks()?"收藏的话题与讨论，随时继续阅读":"查看审核状态，管理自己的投稿",13));
        count=text("正在加载…",12);intro.addView(count);
        EditText search=new EditText(this);search.setHint("搜索已载入的话题标题");search.setSingleLine(true);search.setText(query);search.setContentDescription("搜索我的空间");intro.addView(search);
        search.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){query=s.toString();display();}public void afterTextChanged(android.text.Editable e){}});
        if(!drafts()&&!bookmarks()){
            WrapLayout filter=new WrapLayout(this);String[] keys={"all","pending","published","rejected"},labels={"全部","待审核","已发布","未通过"};
            for(int i=0;i<keys.length;i++){String value=keys[i];Button choice=button(labels[i],()->{scope=value;for(int j=0;j<filter.getChildCount();j++){Button child=(Button)filter.getChildAt(j);MobileStyle.control(child,false,value.equals(child.getTag()),12);}display();});choice.setTag(value);MobileStyle.control(choice,false,value.equals(scope),12);filter.addView(choice);}intro.addView(filter);
        }
        if(drafts())intro.addView(button("新建话题",()->openDraft(0)));
        list=column();body.addView(list);AppAppearance.paintFields(root);
    }
    @Override protected void onResume(){super.onResume();opening=false;if(api.sessionGeneration()!=account){finish();return;}load();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("query",query);out.putString("scope",scope);}
    @Override protected void onDestroy(){serial++;io.shutdownNow();refresh.close();ModalDialogs.close(this);super.onDestroy();}
    private void load(){
        if(writing)return;int token=++serial;refresh.reset(token);refresh.userAction();if(rows!=null)refresh.cached(token);
        if(!api.isLoggedIn()){error(new ApiClient.ApiException(401,"请先登录",false));return;}
        Runnable read=()->{if(isDestroyed()||token!=serial)return;refresh.start(token);io.execute(()->{try{JSONArray result=api.getArray(path());runOnUiThread(()->{if(token!=serial||isDestroyed()||account!=api.sessionGeneration())return;boolean changed=rows==null||!rows.toString().equals(result.toString());rows=result;if(changed)display();refresh.finish(token);});}catch(Exception e){runOnUiThread(()->{if(token!=serial||isDestroyed()||account!=api.sessionGeneration())return;if(!refresh.failure(FailureState.title(e)))error(e);refresh.finish(token);});}});};
        refresh.register(token,read);
        io.execute(()->{api.beginReplay();try{JSONArray cached=api.getArray(path());runOnUiThread(()->{if(token==serial&&!isDestroyed()&&account==api.sessionGeneration()){rows=cached;refresh.cached(token);display();}});}catch(Exception ignored){}finally{api.endReplay();}runOnUiThread(read);});
    }
    private void error(Exception e){list.removeAllViews();LinearLayout box=card(list);ErrorModule.style(box);TextView message=text(FailureState.title(e),17);message.setTextColor(ErrorModule.ink());box.addView(message);box.addView(button("重试",this::load));count.setText("未取得内容");}
    private String state(String value){switch(value){case "pending":return "待审核";case "published":return "已发布";case "rejected":return "未通过";case "removed":return "已删除";default:return value;}}
    private String date(JSONObject row){long value=row.optLong("updated_at",row.optLong("created_at"));return value>0?new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",java.util.Locale.CHINA).format(new java.util.Date(value*1000)):"";}
    private void display(){
        if(list==null||rows==null)return;int y=scroll.getScrollY();list.removeAllViews();count.setText("已载入 "+rows.length()+" 条 · 仅自己可见");int shown=0;
        for(int i=0;i<rows.length();i++){
            JSONObject item=rows.optJSONObject(i);if(item==null||!item.optString("title").toLowerCase(java.util.Locale.ROOT).contains(query.toLowerCase(java.util.Locale.ROOT))||!"all".equals(scope)&&!scope.equals(item.optString("status")))continue;shown++;
            LinearLayout box=card(list);box.setContentDescription(title()+"条目 "+item.optInt("id"));
            String category=item.optString("category_name"),status=drafts()?"草稿":state(item.optString("status"));
            TextView meta=text(category+(category.isEmpty()||status.isEmpty()?"":" · ")+status,12);meta.setTextColor(MobileStyle.BRAND);box.addView(meta);
            String name=item.optString("title");box.addView(text(name.isEmpty()?"未命名草稿":name,19));
            String excerpt=item.optString("excerpt");if(!excerpt.isEmpty()){TextView copy=text(excerpt,14);copy.setMaxLines(3);copy.setEllipsize(android.text.TextUtils.TruncateAt.END);box.addView(copy);}
            String by=item.optString("author_name");box.addView(text((by.isEmpty()?"":by+" · ")+date(item),12));
            if(item.has("review_reason")&&!item.optString("review_reason").isEmpty())box.addView(text("退回原因："+item.optString("review_reason"),13));
            WrapLayout actions=new WrapLayout(this);box.addView(actions,new LinearLayout.LayoutParams(-1,-2));
            actions.addView(button(drafts()?"继续编辑":bookmarks()?"查看话题":"投稿进度",()->{if(drafts())openDraft(item.optInt("id"));else if(bookmarks())openPost(item.optInt("id"));else openProgress(item.optInt("id"));}));
            if(!drafts()&&!bookmarks()&&"published".equals(item.optString("status")))actions.addView(button("查看话题",()->openPost(item.optInt("id"))));
            actions.addView(button(bookmarks()?"取消收藏":"删除"+(drafts()?"草稿":"话题"),()->confirmRemove(item)));
        }
        if(shown==0){LinearLayout empty=card(list);TextView icon=text(drafts()?"尚未保存草稿":bookmarks()?"暂无收藏话题":"暂无话题",20);AppIcons.on(icon,drafts()?"drafts":bookmarks()?"bookmark":"forum",MobileStyle.BRAND,32);empty.addView(icon);empty.addView(text(rows.length()>0?"没有匹配当前筛选的内容。":drafts()?"新建一篇话题，编辑中会自动保存。":bookmarks()?"在话题详情点击收藏后，可在这里继续阅读。":"发布的话题及审核进度会显示在这里。",14));}
        scroll.post(()->scroll.scrollTo(0,y));
    }
    private void openDraft(int id){opening=true;startActivity(new Intent(this,MainActivity.class).putExtra("cloud_draft_id",id));}
    private void openPost(int id){opening=true;startActivity(new Intent(this,MainActivity.class).putExtra("club_post_id",id));}
    private void openProgress(int id){opening=true;startActivity(new Intent(this,WebFeaturesActivity.class).putExtra("feature","progress").putExtra("post_id",id));}
    private void confirmRemove(JSONObject item){new ModalDialogs.Builder(this).setTitle(bookmarks()?"取消收藏？":drafts()?"删除草稿？":"删除话题？").setMessage(bookmarks()?"可以再次从话题详情收藏。":"此操作无法撤销。").setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->remove(item)).show();}
    private void remove(JSONObject item){
        if(writing)return;writing=true;int id=item.optInt("id");io.execute(()->{try{api.writeObject(bookmarks()?"POST":"DELETE",drafts()?"/api/forum/drafts/"+id:"/api/forum/posts/"+id+(bookmarks()?"/bookmark":""),new JSONObject());runOnUiThread(()->{writing=false;if(isDestroyed()||account!=api.sessionGeneration())return;JSONArray kept=new JSONArray();for(int i=0;i<rows.length();i++)if(rows.optJSONObject(i).optInt("id")!=id)kept.put(rows.optJSONObject(i));rows=kept;display();load();});}catch(Exception e){runOnUiThread(()->{writing=false;if(!isDestroyed())notice.show(bookmarks()?"取消收藏":"删除",e);});}});
    }
}
