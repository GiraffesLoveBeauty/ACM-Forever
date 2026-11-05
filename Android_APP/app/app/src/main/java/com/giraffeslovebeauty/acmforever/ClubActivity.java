package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** The five small training features share the process-owned API; no admin bridge. */
public final class ClubActivity extends Activity {
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final ExecutorService previews=Executors.newSingleThreadExecutor();
    private PageRefresh refresh;
    private ApiClient api;
    private SharedPreferences prefs;
    private LinearLayout content;
    private ScrollView scroll;
    private final NavigationStack<Bundle> history=new NavigationStack<>();
    private int restoreY=-1;
    private String page="club", platform="", problem="", keyword="", tag="";
    private int serial;
    private boolean busy;
    private Button pendingSubmit;
    private static final String[] TAGS={"WA","TLE","输入格式","边界","复杂度","思路","其他"};
    private interface Work { Object run() throws Exception; }

    @Override public void onCreate(Bundle state){
        super.onCreate(state);AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();prefs=getSharedPreferences("acmforever_settings",MODE_PRIVATE);
        page=state==null?getIntent().getStringExtra("page"):state.getString("page");if(page==null)page="club";
        platform=state==null?getIntent().getStringExtra("platform"):state.getString("platform");problem=state==null?getIntent().getStringExtra("problem_id"):state.getString("problem");
        if(platform==null)platform="";if(problem==null)problem="";
        if(state!=null){keyword=state.getString("keyword","");tag=state.getString("tag","");restoreY=state.getInt("scroll",0);history.restore(state.getParcelableArrayList("training_history"));}
        LinearLayout root=new SpacedLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        Button back=new Button(this);back.setText("← 返回");MobileStyle.button(back,false);back.setOnClickListener(v->onBackPressed());root.addView(back);
        refresh=new PageRefresh(this,root,1);
        scroll=new ScrollView(this);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));content=new SpacedLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(14),dp(16),dp(14),dp(24));scroll.addView(content);
        render();
    }
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putAll(snapshot());state.putParcelableArrayList("training_history",history.snapshot());}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(busy)return;history.clear();restoreY=0;page=intent.getStringExtra("page");if(page==null)page="club";platform=intent.getStringExtra("platform");problem=intent.getStringExtra("problem_id");if(platform==null)platform="";if(problem==null)problem="";keyword="";tag="";render();}
    @Override protected void onDestroy(){serial++;io.shutdownNow();previews.shutdownNow();refresh.close();ModalDialogs.close(this);super.onDestroy();}
    @Override public void onBackPressed(){if(busy){notice("正在处理，请稍候。");return;}Bundle previous=history.pop();if(previous==null){finish();return;}page=previous.getString("page","club");platform=previous.getString("platform","");problem=previous.getString("problem","");keyword=previous.getString("keyword","");tag=previous.getString("tag","");restoreY=previous.getInt("scroll",0);render();}
    private Bundle snapshot(){Bundle state=new Bundle();state.putString("page",page);state.putString("platform",platform);state.putString("problem",problem);state.putString("keyword",keyword);state.putString("tag",tag);state.putInt("scroll",scroll==null?0:scroll.getScrollY());return state;}
    private void go(String next){go(next,()->{});}
    private void go(String next,Runnable prepare){if(busy||page.equals(next))return;history.push(snapshot());prepare.run();page=next;restoreY=0;render();}
    private int dp(float value){return MobileStyle.dp(this,value);}
    private TextView text(LinearLayout parent,String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(size>=17?MobileStyle.TEXT:MobileStyle.MUTED);if(size>=17)t.setTypeface(null,android.graphics.Typeface.BOLD);t.setLineSpacing(dp(3),1f);t.setPadding(0,dp(6),0,dp(8));parent.addView(t);return t;}
    private LinearLayout card(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.VERTICAL);b.setPadding(dp(18),dp(14),dp(18),dp(18));b.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,12,0));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(10);content.addView(b,lp);return b;}
    private Button button(LinearLayout parent,String title,Runnable action){Button b=new Button(this);b.setText(title);MobileStyle.button(b,false);LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=dp(8);parent.addView(b,params);b.setOnClickListener(v->{if(!busy&&!ModalDialogs.isShowing(this))action.run();});return b;}
    private EditText input(LinearLayout parent,String hint,String value){EditText e=new EditText(this);e.setHint(hint);e.setText(value);parent.addView(e);return e;}
    private Spinner spinner(LinearLayout parent,String[] values){Spinner s=new Spinner(this);s.setAdapter(MobileStyle.options(this,values));s.setBackgroundTintList(android.content.res.ColorStateList.valueOf(MobileStyle.BRAND));parent.addView(s);return s;}
    private void notice(String message){new ModalDialogs.Builder(this).setMessage(message).setPositiveButton("知道了",null).show();}
    private void error(LinearLayout slot,Exception e){slot.setVisibility(android.view.View.VISIBLE);slot.removeAllViews();slot.setMinimumHeight(dp(160));ErrorModule.style(slot);TextView t=text(slot,FailureState.title(e),17);t.setTextColor(ErrorModule.ink());if(!ModalDialogs.isShowing(this))button(slot,"重试",this::render);restorePosition();}
    private void restorePosition(){int y=restoreY>=0?restoreY:scroll.getScrollY();scroll.post(()->{scroll.scrollTo(0,y);restoreY=-1;});}
    private String date(long seconds){java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",java.util.Locale.CHINA);f.setTimeZone(java.util.TimeZone.getTimeZone("Asia/Shanghai"));return f.format(new java.util.Date(seconds*1000))+"（北京时间）";}
    private void task(Work work,java.util.function.Consumer<Object> done,LinearLayout slot){
        if(busy)return;busy=true;int revision=serial;
            io.execute(()->{try{Object result=work.run();runOnUiThread(()->{busy=false;if(pendingSubmit!=null)pendingSubmit.setEnabled(true);if(isDestroyed()||revision!=serial)return;slot.removeAllViews();try{done.accept(result);}catch(Exception e){error(slot,e);}});}catch(Exception e){runOnUiThread(()->{busy=false;if(pendingSubmit!=null)pendingSubmit.setEnabled(true);if(!isDestroyed()&&revision==serial)error(slot,e);});}});
    }
    private void load(String path,java.util.function.Consumer<Object> done){
        LinearLayout slot=card();slot.addView(new CodingCatView(this),new LinearLayout.LayoutParams(dp(160),dp(110)));text(slot,"正在加载…",14);int revision=serial,retained=content.getChildCount();
        java.util.function.Consumer<Object> show=value->{if(isDestroyed()||revision!=serial)return;while(content.getChildCount()>retained)content.removeViewAt(retained);slot.setVisibility(android.view.View.GONE);try{done.accept(value);restorePosition();}catch(Exception e){error(slot,e);}};
        Runnable request=()->{
            if(isDestroyed()||revision!=serial)return;refresh.start(revision);
            try{io.execute(()->{try{Object value=api.get(path);runOnUiThread(()->{if(!isDestroyed()&&revision==serial){show.accept(value);refresh.finish(revision);}});}catch(Exception e){runOnUiThread(()->{if(!isDestroyed()&&revision==serial){if(!refresh.failure(FailureState.title(e)))error(slot,e);refresh.finish(revision);}});}});}catch(RejectedExecutionException ignored){}
        };
        refresh.register(revision,request);
        previews.execute(()->{api.beginReplay();try{Object cached=api.get(path);runOnUiThread(()->{if(!isDestroyed()&&revision==serial){refresh.cached(revision);show.accept(cached);}});}catch(Exception ignored){}finally{api.endReplay();}runOnUiThread(request);});
    }
    private JSONArray rows(Object value){if(!(value instanceof JSONArray))throw new ClassCastException("数据格式异常");return (JSONArray)value;}
    private void render(){serial++;refresh.reset(serial);refresh.userAction();content.removeAllViews();TextView marker=text(content,"ACMforever / TRAINING",11);marker.setLetterSpacing(.10f);text(content,pageTitle(),25);
        if(!page.equals("club")&&!page.equals("templates")&&!api.isLoggedIn()){text(card(),"未登录：请返回顶部头像进入账号设置登录。",16);return;}
        switch(page){case "sheets":sheets();break;case "discussions":discussions();break;case "mistakes":mistakes();break;case "reviews":reviews();break;case "templates":templates();break;case "checkin":checkin();break;default:menu();restorePosition();}
    }
    private String pageTitle(){switch(page){case "sheets":return "社团题单";case "discussions":return "一起解题";case "mistakes":return "我的错题本";case "reviews":return "补题与复习";case "templates":return "Wiki 手册";case "checkin":return "训练打卡";default:return "社团训练";}}
    private void menu(){LinearLayout box=card();text(box,"题单 → 讨论 → 补题 → 复习",17);button(box,"社团题单",()->go("sheets"));button(box,"错题本",()->go("mistakes"));button(box,"待补题与间隔复习",()->go("reviews"));button(box,"Wiki 手册",this::openWiki);button(box,"训练打卡与本地提醒",()->go("checkin"));}
    private void select(JSONObject item){go("discussions",()->{platform=item.optString("platform");problem=item.optString("problem_id");keyword="";tag="";});}
    private String key(){return "platform="+UrlEncoding.form(platform)+"&problem_id="+UrlEncoding.form(problem);}
    private JSONObject keyData() throws JSONException{return new JSONObject().put("platform",platform).put("problem_id",problem);}
    private void sheets(){text(card(),"题单截止时间与完成进度来自服务器，AC 数据同步后更新。",14);load("/api/club/sheets",value->{JSONArray items=rows(value);if(items.length()==0)text(card(),"暂无分配的题单。",15);for(int i=0;i<items.length();i++){JSONObject sheet=items.optJSONObject(i);if(sheet==null)continue;LinearLayout box=card();text(box,sheet.optString("title"),20);text(box,sheet.optString("description"),14);text(box,date(sheet.optLong("deadline"))+" 截止\n已完成 "+sheet.optInt("completed")+" / "+sheet.optInt("total"),14);JSONArray problems=sheet.optJSONArray("items");if(problems==null)continue;for(int j=0;j<problems.length();j++){JSONObject item=problems.optJSONObject(j);if(item==null)continue;text(box,(item.optBoolean("completed")?"已完成 · ":"未完成 · ")+item.optString("platform")+" · "+item.optString("problem_id"),16);button(box,"讨论 / 错题 / 原题",()->select(item));}}});}
    private void discussions(){
        if(platform.isEmpty()||problem.isEmpty()){text(card(),"请从题单、题目或错题本选择一道题。",16);return;}
        LinearLayout controls=card();text(controls,platform+" · "+problem,20);EditText search=input(controls,"搜索本题讨论",keyword);String[] filters={"全部","WA","TLE","输入格式","边界","复杂度","思路","其他"};Spinner choice=spinner(controls,filters);choice.setSelection(Math.max(0,java.util.Arrays.asList(filters).indexOf(tag)));
        button(controls,"按关键词和标签查询",()->{keyword=search.getText().toString().trim();tag=choice.getSelectedItemPosition()==0?"":filters[choice.getSelectedItemPosition()];render();});
        button(controls,"发起本题讨论",this::newDiscussion);button(controls,"加入错题本",()->editMistake(new JSONObject()));button(controls,"加入补题计划",()->reviewAction("add"));button(controls,"系统浏览器打开原题",this::original);
        load("/api/club/problem-discussions?"+key()+"&q="+UrlEncoding.form(keyword)+"&tag="+UrlEncoding.form(tag),value->{JSONArray items=rows(value);if(items.length()==0)text(card(),"暂无已发布讨论。新讨论提交 Web 审核后展示。",15);for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;LinearLayout box=card();text(box,item.optString("title"),18);text(box,item.optString("tags")+" · "+item.optString("author_name"),12);box.addView(new ContentView(this,item.optString("body"),false,this::open));button(box,"评论 / 回复 / 简单举报",()->forum(item.optInt("id")));}});
    }
    private void original(){String url="";switch(platform){case "codeforces":String id=problem.replaceFirst("^cf_","");java.util.regex.Matcher m=java.util.regex.Pattern.compile("^(\\d+)([A-Za-z]\\d*)$").matcher(id);if(m.matches())url="https://codeforces.com/problemset/problem/"+m.group(1)+"/"+m.group(2);break;case "luogu":url="https://www.luogu.com.cn/problem/"+UrlEncoding.form(problem);break;case "atcoder":int index=problem.indexOf('_');if(index>0)url="https://atcoder.jp/contests/"+problem.substring(0,index)+"/tasks/"+UrlEncoding.form(problem);break;default:break;}if(url.isEmpty()){notice("该平台暂未配置原题链接规则，请从题库打开已有原题链接。");return;}open(url);}
    private void open(String url){try{java.net.URI uri=java.net.URI.create(url);if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null)throw new IllegalArgumentException();startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)));}catch(Exception e){notice("无法打开 HTTPS 链接。");}}
    private void forum(int id){startActivity(new Intent(this,MainActivity.class).putExtra("club_post_id",id));}
    private void newDiscussion(){LinearLayout form=new SpacedLayout(this);form.setOrientation(LinearLayout.VERTICAL);EditText title=input(form,"标题 4–120 字",""),body=input(form,"正文 5–20000 字，Markdown"," ");body.setMinLines(4);Spinner choice=spinner(form,TAGS);formDialog("本题讨论（Web 审核后公开）",form,()->keyData().put("title",title.getText().toString()).put("body",body.getText().toString()).put("tags",new JSONArray().put(TAGS[choice.getSelectedItemPosition()])),"POST","/api/club/problem-discussions");}
    private interface Payload{JSONObject get() throws Exception;}
    private void formDialog(String title,LinearLayout form,Payload payload,String method,String path){
        LinearLayout status=new SpacedLayout(this);status.setOrientation(LinearLayout.VERTICAL);form.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.addView(form);AlertDialog dialog=new ModalDialogs.Builder(this).setTitle(title).setView(scroll).setNegativeButton("取消",null).setPositiveButton("提交",null).create();
        dialog.setOnShowListener(d->dialog.getButton(-1).setOnClickListener(v->{if(busy)return;final JSONObject data;try{data=payload.get();}catch(Exception e){notice(e.getMessage());return;}pendingSubmit=dialog.getButton(-1);pendingSubmit.setEnabled(false);task(()->api.writeObject(method,path,data),result->{dialog.dismiss();render();notice(((JSONObject)result).optString("message","操作完成。"));},status);}));ModalDialogs.show(dialog);
    }
    private void editMistake(JSONObject item){LinearLayout form=new SpacedLayout(this);form.setOrientation(LinearLayout.VERTICAL);EditText note=input(form,"个人错因笔记（最多 2000 字）",item.optString("note"));note.setMinLines(4);Spinner choice=spinner(form,TAGS);JSONArray old=item.optJSONArray("tags");if(old!=null&&old.length()>0)choice.setSelection(Math.max(0,java.util.Arrays.asList(TAGS).indexOf(old.optString(0))));formDialog("错题本 · "+problem,form,()->keyData().put("note",note.getText().toString()).put("tags",new JSONArray().put(TAGS[choice.getSelectedItemPosition()])),"PUT","/api/me/club/mistakes");}
    private void mistakes(){load("/api/me/club/mistakes",value->{JSONArray items=rows(value);if(items.length()==0)text(card(),"暂无错题。从题目讨论页加入。",16);for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;LinearLayout box=card();text(box,item.optString("platform")+" · "+item.optString("problem_id"),18);text(box,item.optString("tags")+"\n"+item.optString("note"),14);button(box,"本题讨论",()->select(item));button(box,"编辑错因",()->{platform=item.optString("platform");problem=item.optString("problem_id");editMistake(item);});button(box,"移出错题本",()->new ModalDialogs.Builder(this).setMessage("确认移出该错题？").setNegativeButton("取消",null).setPositiveButton("移出",(d,w)->{LinearLayout status=card();task(()->api.writeObject("DELETE","/api/me/club/mistakes",item),result->render(),status);}).show());}});}
    private void reviewAction(String action){try{JSONObject data=keyData().put("action",action);LinearLayout status=card();task(()->api.writeObject("PUT","/api/me/club/reviews",data),result->{render();notice(((JSONObject)result).optString("message"));},status);}catch(Exception e){notice(e.getMessage());}}
    private void reviews(){text(card(),"赛事复盘待补题自动加入。首次立即到期，完成复习后分别间隔 1、3、7 天；第四次完成后结束。",14);load("/api/me/club/reviews",value->{JSONArray items=rows(value);TrainingReminder.scheduleReviews(this,items);if(items.length()==0)text(card(),"暂无补题计划。",16);for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;LinearLayout box=card();text(box,item.optString("platform")+" · "+item.optString("problem_id"),18);text(box,(item.optBoolean("due")?"已到期":"未到期")+" · 阶段 "+item.optInt("stage")+" · "+date(item.optLong("due_at")),13);button(box,"本题讨论与原题",()->select(item));button(box,"本次复习已完成",()->{platform=item.optString("platform");problem=item.optString("problem_id");reviewAction("reviewed");});button(box,"仍不会，明天再练",()->{platform=item.optString("platform");problem=item.optString("problem_id");reviewAction("retry");});button(box,"忽略此计划",()->{platform=item.optString("platform");problem=item.optString("problem_id");reviewAction("ignore");});}});}
    private boolean openingWiki;
    private void openWiki(){if(openingWiki)return;openingWiki=true;startActivity(new Intent(this,WebFeaturesActivity.class).putExtra("feature","wiki"));}
    private void templates(){openWiki();}
    private CheckBox reminderToggle;
    private TextView reminderState;
    private boolean updatingReminder;
    private void refreshReminder(){
        if(reminderToggle==null)return;updatingReminder=true;boolean enabled=prefs.getBoolean("training_reminder",false)&&TrainingReminder.notificationsAllowed(this);
        reminderToggle.setChecked(enabled);updatingReminder=false;
        reminderState.setText(String.format(java.util.Locale.CHINA,"每日 %02d:%02d · %s",prefs.getInt("reminder_hour",20),prefs.getInt("reminder_minute",0),enabled?"通知提醒已启用":"通知提醒未启用"));
    }
    private void enableReminder(boolean enabled){
        if(!enabled){TrainingReminder.disable(this);refreshReminder();return;}
        if(android.os.Build.VERSION.SDK_INT>=33&&checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED){
            prefs.edit().putBoolean("training_reminder",false).apply();refreshReminder();requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},82);return;
        }
        if(!TrainingReminder.notificationsAllowed(this)){
            prefs.edit().putBoolean("training_reminder",false).apply();refreshReminder();
            new ModalDialogs.Builder(this).setTitle("允许训练通知").setMessage("系统通知或训练通知渠道尚未启用。请开启后返回勾选通知提醒。")
                .setNegativeButton("返回",null).setPositiveButton("通知设置",(d,w)->startActivity(new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName()))).show();return;
        }
        prefs.edit().putBoolean("training_reminder",true).apply();TrainingReminder.scheduleDaily(this);refreshReminder();
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){
        super.onRequestPermissionsResult(request,permissions,grants);if(request!=82)return;
        if(grants.length>0&&grants[0]==android.content.pm.PackageManager.PERMISSION_GRANTED)enableReminder(true);
        else{TrainingReminder.disable(this);refreshReminder();notice("未获得通知权限，提醒未启用；可在系统通知设置中允许后重新勾选。");}
    }
    @Override protected void onResume(){super.onResume();openingWiki=false;if(prefs!=null)refreshReminder();}
    private void pickReminderTime(){
        LinearLayout form=new SpacedLayout(this);form.setOrientation(LinearLayout.VERTICAL);
        text(form,"本机时间 · "+java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT).format(new java.util.Date())+" · "+java.util.TimeZone.getDefault().getDisplayName(),13);
        LinearLayout time=new SpacedLayout(this);time.setGravity(android.view.Gravity.CENTER_VERTICAL);form.addView(time);
        EditText hour=new EditText(this),minute=new EditText(this);
        hour.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);minute.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);hour.setSingleLine(true);minute.setSingleLine(true);
        hour.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2)});minute.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2)});
        hour.setText(String.valueOf(prefs.getInt("reminder_hour",20)));minute.setText(String.format(java.util.Locale.CHINA,"%02d",prefs.getInt("reminder_minute",0)));
        hour.setHint("0–23");minute.setHint("0–59");hour.setContentDescription("提醒小时");minute.setContentDescription("提醒分钟");
        time.addView(hour,new LinearLayout.LayoutParams(0,dp(56),1));text(time,"时",16);time.addView(minute,new LinearLayout.LayoutParams(0,dp(56),1));text(time,"分",16);
        CheckBox notify=new CheckBox(this);notify.setText("通知提醒");notify.setChecked(prefs.getBoolean("training_reminder",false)&&TrainingReminder.notificationsAllowed(this));form.addView(notify);
        android.app.AlertDialog dialog=new ModalDialogs.Builder(this).setTitle("每日提醒时间").setView(form).setNegativeButton("返回",null).setPositiveButton("保存",null).create();
        dialog.setOnShowListener(d->dialog.getButton(-1).setOnClickListener(v->{
            int h,m;try{h=Integer.parseInt(hour.getText().toString());if(h<0||h>23)throw new NumberFormatException();}catch(NumberFormatException e){hour.setError("请输入 0–23");return;}
            try{m=Integer.parseInt(minute.getText().toString());if(m<0||m>59)throw new NumberFormatException();}catch(NumberFormatException e){minute.setError("请输入 0–59");return;}
            prefs.edit().putInt("reminder_hour",h).putInt("reminder_minute",m).apply();dialog.dismiss();enableReminder(notify.isChecked());
        }));ModalDialogs.show(dialog);
    }
    private void checkin(){LinearLayout form=card();text(form,"达标以北京时间当日已同步 AC 为准。",14);EditText target=input(form,"每日目标 1–100 题",String.valueOf(prefs.getInt("daily_target",1)));target.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        button(form,"达到目标后打卡",()->{try{int count=Integer.parseInt(target.getText().toString());if(count<1||count>100)throw new IllegalArgumentException();prefs.edit().putInt("daily_target",count).apply();LinearLayout status=card();task(()->api.writeObject("POST","/api/me/club/checkin",new JSONObject().put("target",count)),result->render(),status);}catch(Exception e){notice("请输入 1–100 的目标。");}});
        text(form,"提醒只在设备本地运行，系统省电策略可能延迟。未允许通知时不能显示。",12);
        reminderToggle=new CheckBox(this);reminderToggle.setText("通知提醒");form.addView(reminderToggle);reminderState=text(form,"",13);refreshReminder();
        reminderToggle.setOnCheckedChangeListener((b,checked)->{if(!updatingReminder)enableReminder(checked);});
        button(form,"设置每日提醒时间",this::pickReminderTime);
        button(form,"关闭所有训练提醒",()->{TrainingReminder.disable(this);refreshReminder();});
        load("/api/me/club/checkin",value->{JSONObject info=(JSONObject)value;LinearLayout box=card();text(box,info.optString("day")+" · 今日已同步 AC "+info.optInt("actual"),18);text(box,(info.optBoolean("checked_in")?"今日已打卡":"今日尚未打卡")+" · 连续 "+info.optInt("streak")+" 天",16);});
    }
}
