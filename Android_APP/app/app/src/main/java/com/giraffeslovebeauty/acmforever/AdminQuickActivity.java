package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.*;
import org.json.*;
import java.util.*;

/** Small native management tasks. Bulk credentials, roles and long editors stay on Web. */
public final class AdminQuickActivity extends MobilePageActivity {
    private String mode="home",member="",contest="",query="";private int page=1;
    private final ArrayDeque<String> back=new ArrayDeque<>();private boolean verified,firstResume=true;private long account;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);if(saved!=null){mode=saved.getString("mode","home");member=saved.getString("member","");contest=saved.getString("contest","");query=saved.getString("query","");page=saved.getInt("page",1);ArrayList<String> stack=saved.getStringArrayList("back");if(stack!=null)back.addAll(stack);}createPage("便捷管理");account=api.sessionGeneration();verify();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("mode",mode);out.putString("member",member);out.putString("contest",contest);out.putString("query",query);out.putInt("page",page);out.putStringArrayList("back",new ArrayList<>(back));}
    @Override public void onBackPressed(){if(writing)return;if(back.isEmpty()){super.onBackPressed();return;}mode=back.pop();render();}
    private void verify(){
        verified=false;resetPage("正在确认管理权限…");LinearLayout slot=card(body);slot.addView(text("正在验证会话…",14));
        body.addView(button("重新确认权限",this::verify));
        read(()->{api.refreshSession();if(!api.isAdministrator())throw new ApiClient.ApiException(403,"仅限管理员",false);return Boolean.TRUE;},slot,false,value->{account=api.sessionGeneration();verified=true;render();});
    }
    @Override protected void onResume(){super.onResume();if(firstResume){firstResume=false;}else if(api!=null){verified=false;verify();}}
    private void nav(String next){if(!verified)return;back.push(mode);mode=next;page=1;render();}
    private void render(){resetPage(title());if(!verified||account!=api.sessionGeneration()||!api.isAdministrator()){verified=false;error(card(body),new ApiClient.ApiException(403,"管理权限已失效，请返回重新登录",false));return;}
        switch(mode){case "posts":case "reports":moderation();break;case "tasks":tasks();break;case "members":members();break;case "member":member();break;case "training":training();break;case "contests":contests();break;case "settings":settings();break;default:home();}AppAppearance.paintFields(root);}
    private String title(){switch(mode){case "posts":return "话题审核";case "reports":return "举报处理";case "tasks":return "同步任务";case "members":case "member":return "成员查询";case "training":return "训练管理";case "contests":return "复盘管理";case "settings":return "比赛播报";default:return "便捷管理";}}
    private void home(){LinearLayout intro=card(body);intro.addView(text("手机便捷管理",23));intro.addView(text("适合随手处理的审核、查询与训练操作。",14));
        String[][] pages={{"posts","待审核话题"},{"reports","用户举报"},{"tasks","同步任务"},{"members","成员查询"},{"training","生成训练"},{"contests","复盘管理"},{"settings","比赛播报"}};
        for(String[] item:pages)body.addView(button(item[1],()->nav(item[0])));
        LinearLayout web=card(body);web.addView(text("完整管理后台",18));web.addView(text("批量开户、Excel 导入、角色授权、绑定修改、题库采集、CF 选题和 Wiki 编辑请到网页处理。浏览器需要单独登录。",13));web.addView(button("打开网页后台",()->{openExternal(api.getBaseUrl()+"/admin.html");}));}
    private void moderation(){body.addView(button("刷新",this::render));LinearLayout slot=card(body);slot.addView(text("正在读取…",14));String endpoint="/api/forum/moderation/"+mode;boolean posts="posts".equals(mode);
        read(endpoint,slot,true,value->{JSONArray rows=(JSONArray)value;if(rows.length()==0)slot.addView(text("没有待处理内容",16));for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.optString("title"),19));box.addView(text((posts?"投稿人：":"举报人：")+item.optString(posts?"author_name":"reporter_name"),12));
            if(!posts)box.addView(text("举报理由："+item.optString("reason"),14));if(!item.optString("body").isEmpty())box.addView(new ContentView(this,item.optString("body"),false,this::openExternal));
            equalButtons(box,button(posts?"通过并发布":"标记举报已处理",()->confirmDecision(endpoint,item,posts?"publish":"resolve",posts)),button(posts?"退回":"驳回举报",()->{if(posts)reject(endpoint,item);else confirmDecision(endpoint,item,"dismiss",false);}));}});
    }
    private void openExternal(String url){try{String checked=UpdateManifest.https(url);opening=true;startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(checked)));}catch(Exception e){opening=false;notice.show("打开链接",e);}}
    private void confirmDecision(String endpoint,JSONObject item,String decision,boolean posts){new ModalDialogs.Builder(this).setTitle("确认处理这条内容？").setMessage(item.optString("title")).setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->{JSONObject data=json("decision",decision);try{if(posts)data.put("content_version",item.getLong("content_version"));}catch(Exception e){notice.show("审核",e);return;}write("POST",endpoint+"/"+item.optInt("id"),data,true,this::render);}).show();}
    private void reject(String endpoint,JSONObject item){LinearLayout panel=column();EditText reason=input(panel,"退回原因（必填）","");reason.setSingleLine(false);reason.setMinLines(3);reason.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(1000)});
        android.app.AlertDialog dialog=new ModalDialogs.Builder(this).setTitle("退回话题").setView(panel).setNegativeButton("返回",null).setPositiveButton("确认退回",null).create();ModalDialogs.show(dialog);dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String text=reason.getText().toString().trim();if(text.isEmpty()){reason.setError("请填写退回原因");return;}try{JSONObject data=new JSONObject().put("decision","reject").put("reason",text).put("content_version",item.getLong("content_version"));dialog.dismiss();write("POST",endpoint+"/"+item.getInt("id"),data,true,this::render);}catch(Exception e){notice.show("退回",e);}});}
    private void tasks(){body.addView(button("刷新任务",this::render));LinearLayout slot=card(body);read("/api/tasks",slot,true,value->{JSONArray rows=(JSONArray)value;if(rows.length()==0)slot.addView(text("暂无同步任务",16));for(int i=rows.length()-1;i>=0;i--){JSONObject task=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(task.optString("kind")+" · #"+task.optString("id"),18));box.addView(text(task.optString("status")+" · "+task.optString("platform","全部平台"),14));box.addView(text("成员："+task.optString("qq_id","全部"),12));if(task.has("result"))box.addView(text(task.opt("result").toString(),13));if(Arrays.asList("queued","running").contains(task.optString("status")))box.addView(button("取消任务",()->new ModalDialogs.Builder(this).setTitle("确认取消此任务？").setNegativeButton("返回",null).setPositiveButton("确认取消",(d,w)->write("POST","/api/tasks/"+UrlEncoding.form(task.optString("id"))+"/cancel",new JSONObject(),true,this::render)).show()));}});}
    private void members(){LinearLayout form=card(body);EditText term=input(form,"昵称、QQ、学校或 OJ",query);form.addView(button("搜索成员",()->{query=term.getText().toString().trim();page=1;render();}));LinearLayout slot=card(body);read("/api/admin/members?search="+UrlEncoding.form(query)+"&page="+page+"&page_size=20",slot,true,value->{JSONObject data=(JSONObject)value;JSONArray rows=data.getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无成员",16));for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(row.optString("name")+" · "+row.optString("qq_id"),18));box.addView(text(row.optString("status")+" · "+row.optString("school"),13));box.addView(button("查看资料",()->{member=row.optString("qq_id");nav("member");}));}pager(slot,data.optInt("total"),20);});}
    private void member(){LinearLayout slot=card(body);read("/api/member/"+UrlEncoding.form(member),slot,true,value->{JSONObject data=(JSONObject)value,user=data.getJSONObject("user");slot.addView(text(user.optString("name"),22));slot.addView(text("QQ "+member+"\n学校："+user.optString("school")+"\n身份："+user.optString("status")+"\n姓名："+user.optString("real_name"),14));JSONObject counts=data.optJSONObject("platform_counts");if(counts!=null)for(Iterator<String> keys=counts.keys();keys.hasNext();){String key=keys.next();slot.addView(text(key+"："+counts.opt(key),14));}slot.addView(button("为该成员生成训练",()->nav("training")));slot.addView(button("查看该成员复盘",()->nav("contests")));slot.addView(text("资料、绑定和账号权限修改请到完整网页后台。",13));});}
    private boolean validMember(EditText input){String value=input.getText().toString().trim();if(!value.matches("[1-9][0-9]{3,11}")){input.setError("请输入有效成员 QQ");return false;}member=value;return true;}
    private void training() {
        LinearLayout form = card(body);
        EditText who = input(form, "成员 QQ", member);
        String[] ids = {"codeforces", "atcoder", "luogu", "nowcoder"};
        Spinner platform = new Spinner(this);
        platform.setContentDescription("训练平台");
        platform.setAdapter(MobileStyle.options(this, new String[]{"Codeforces", "AtCoder", "洛谷", "牛客"}));
        form.addView(platform);
        EditText tag = input(form, "标签、题名或题号（可空）", "");
        form.addView(text("难度（必选，已按平台预选）", 14));
        Spinner difficulty = new Spinner(this);
        difficulty.setContentDescription("训练难度");
        form.addView(difficulty);
        // Bind the choices and their platform together before the first click or a platform change.
        final String[] difficultyPlatform = {""};
        Runnable selectDefaults = () -> {
            int position = platform.getSelectedItemPosition();
            if (position < 0 || position >= ids.length) return;
            String selected = ids[position];
            if (selected.equals(difficultyPlatform[0])) return;
            List<String> values = ChallengeDifficulty.options(selected);
            difficulty.setAdapter(MobileStyle.options(this, values.toArray(new String[0])));
            difficulty.setSelection(values.indexOf(ChallengeDifficulty.defaultValue(selected)));
            difficultyPlatform[0] = selected;
        };
        selectDefaults.run();
        platform.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, android.view.View view, int position, long id) { selectDefaults.run(); }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        LinearLayout results = card(body);
        form.addView(button("生成训练题", () -> {
            if (!validMember(who)) return;
            try {
                int position = platform.getSelectedItemPosition();
                if (position < 0 || position >= ids.length) throw new IllegalArgumentException("请选择有效训练平台");
                String selected = ids[position];
                // A pending selection callback must not submit a difficulty from the previous platform.
                if (!selected.equals(difficultyPlatform[0])) { selectDefaults.run(); }
                String level = ChallengeDifficulty.require(selected, difficulty.getSelectedItem());
                JSONObject data = new JSONObject().put("owner_qq_id", member).put("platform", selected)
                        .put("tag", tag.getText().toString().trim()).put("difficulty", level).put("weak_tag", false);
                write("POST", "/api/challenge/start", data, true, () -> {
                    results.removeAllViews();
                    results.addView(text("训练已生成，可在挑战历史查看。", 15));
                    loadTraining(results);
                });
            } catch (Exception e) { notice.show("生成训练", e); }
        }));
        form.addView(button("查询挑战历史", () -> { if (validMember(who)) loadTraining(results); }));
        if (!member.isEmpty()) loadTraining(results);
    }
    private void loadTraining(LinearLayout slot){read("/api/challenge/list?qq_id="+UrlEncoding.form(member),slot,true,value->{JSONArray rows=(JSONArray)value;if(rows.length()==0)slot.addView(text("暂无挑战记录",15));for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.optString("problem_name",item.optString("problem_id")),17));box.addView(text(item.optString("platform")+" · "+item.optString("status"),13));box.addView(button("查看题面",()->{opening=true;startActivity(new Intent(this,MainActivity.class).putExtra("web_problem_platform",item.optString("platform")).putExtra("web_problem_id",item.optString("problem_id")));}));}});}
    private void contests(){LinearLayout form=card(body);EditText who=input(form,"成员 QQ",member),id=input(form,"比赛 ID",contest);form.addView(button("查询复盘",()->{if(!validMember(who))return;contest=id.getText().toString().trim();render();}));if(member.isEmpty()||contest.isEmpty())return;LinearLayout slot=card(body);String target=member,competition=contest;read("/api/contest/reviews?owner_qq_id="+UrlEncoding.form(target)+"&contest_id="+UrlEncoding.form(competition),slot,true,value->{JSONArray rows=(JSONArray)value;String[] keys={"todo","unsolved","queued","solved","reviewed","ignored"},names={"待处理","未通过","待补题","已解决","已复盘","忽略"};if(rows.length()==0)slot.addView(text("暂无比赛记录",16));for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.optString("problem_id"),18));box.addView(text(item.optString("verdict"),13));Spinner state=new Spinner(this);state.setAdapter(MobileStyle.options(this,names));state.setSelection(Math.max(0,Arrays.asList(keys).indexOf(item.optString("status"))));box.addView(state);box.addView(button("保存本题状态",()->{try{JSONObject data=new JSONObject().put("owner_qq_id",target).put("contest_id",competition).put("problem_id",item.getString("problem_id")).put("status",keys[state.getSelectedItemPosition()]);write("PUT","/api/contest/reviews",data,true,()->{item.remove("status");try{item.put("status",keys[state.getSelectedItemPosition()]);}catch(Exception ignored){} });}catch(Exception e){notice.show("保存复盘",e);}}));}});}
    private void settings(){LinearLayout slot=card(body);read("/api/settings/contest-report",slot,true,value->{JSONObject data=(JSONObject)value;slot.addView(text("每日 Codeforces 比赛播报",19));slot.addView(text("全站设置 · 北京时间 · 通知群 "+data.optString("group_id","未配置"),13));EditText time=input(slot,"HH:MM，例如 08:30",data.optString("time"));slot.addView(button("保存播报时间",()->{String next=time.getText().toString().trim();if(!next.matches("(?:[01][0-9]|2[0-3]):[0-5][0-9]")){time.setError("请输入 HH:MM");return;}confirmReport(next);}));slot.addView(button("关闭播报",()->confirmReport("")));});}
    private void confirmReport(String time){new ModalDialogs.Builder(this).setTitle(time.isEmpty()?"关闭全站比赛播报？":"修改全站比赛播报时间？").setMessage(time.isEmpty()?"此设置影响社团通知。":"北京时间 "+time).setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->write("PUT","/api/settings/contest-report",json("time",time),true,this::render)).show();}
    private void pager(LinearLayout parent,int total,int size){if(total<=size)return;parent.addView(text("第 "+page+" 页 / 共 "+Math.max(1,(total+size-1)/size)+" 页",12));equalButtons(parent,button("上一页",()->{if(page>1){page--;render();}}),button("下一页",()->{if(page*size<total){page++;render();}}));}
}
