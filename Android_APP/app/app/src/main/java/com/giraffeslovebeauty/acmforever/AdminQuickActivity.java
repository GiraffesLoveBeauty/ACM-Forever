package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.*;
import org.json.*;
import java.util.*;

/** Small native management tasks. Bulk credentials and long editors stay on Web. */
public final class AdminQuickActivity extends MobilePageActivity {
    private String mode="home",member="",contest="",query="",school="",statusFilter="",taskFilter="全部";private int page=1;
    private final ArrayDeque<String> back=new ArrayDeque<>();private boolean verified,firstResume=true;private long account;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);if(saved!=null){mode=saved.getString("mode","home");member=saved.getString("member","");contest=saved.getString("contest","");query=saved.getString("query","");page=saved.getInt("page",1);school=saved.getString("school","");statusFilter=saved.getString("statusFilter","");taskFilter=saved.getString("taskFilter","全部");ArrayList<String> stack=saved.getStringArrayList("back");if(stack!=null)back.addAll(stack);}createPage("便捷管理");account=api.sessionGeneration();verify();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("mode",mode);out.putString("member",member);out.putString("contest",contest);out.putString("query",query);out.putInt("page",page);out.putString("school",school);out.putString("statusFilter",statusFilter);out.putString("taskFilter",taskFilter);out.putStringArrayList("back",new ArrayList<>(back));}
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
        LinearLayout web=card(body);web.addView(text("完整管理后台",18));web.addView(text("批量开户、Excel 导入、题库采集、CF 选题、校 OJ 与 Wiki 编辑请到网页处理。浏览器需要单独登录。",13));web.addView(button("打开网页后台",()->{openExternal(api.getBaseUrl()+"/admin.html");}));}
    private void moderation(){body.addView(button("刷新",this::render));LinearLayout slot=card(body);slot.addView(text("正在读取…",14));String endpoint="/api/forum/moderation/"+mode;boolean posts="posts".equals(mode);
        read(endpoint,slot,true,value->{JSONArray rows=(JSONArray)value;if(rows.length()==0)slot.addView(text("没有待处理内容",16));for(int i=0;i<rows.length();i++){JSONObject item=rows.getJSONObject(i);LinearLayout box=card(slot);box.addView(text(item.optString("title"),19));box.addView(text((posts?"投稿人：":"举报人：")+item.optString(posts?"author_name":"reporter_name"),12));
            if(!posts)box.addView(text("举报理由："+item.optString("reason"),14));if(!item.optString("body").isEmpty())box.addView(new ContentView(this,item.optString("body"),false,this::openExternal));
            equalButtons(box,button(posts?"通过并发布":"标记举报已处理",()->confirmDecision(endpoint,item,posts?"publish":"resolve",posts)),button(posts?"退回":"驳回举报",()->{if(posts)reject(endpoint,item);else confirmDecision(endpoint,item,"dismiss",false);}));}});
    }
    private void openExternal(String url){try{String checked=UpdateManifest.https(url);opening=true;startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(checked)));}catch(Exception e){opening=false;notice.show("打开链接",e);}}
    private void confirmDecision(String endpoint,JSONObject item,String decision,boolean posts){new ModalDialogs.Builder(this).setTitle("确认处理这条内容？").setMessage(item.optString("title")).setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->{JSONObject data=json("decision",decision);try{if(posts)data.put("content_version",item.getLong("content_version"));}catch(Exception e){notice.show("审核",e);return;}write("POST",endpoint+"/"+item.optInt("id"),data,true,this::render);}).show();}
    private void reject(String endpoint,JSONObject item){LinearLayout panel=column();EditText reason=input(panel,"退回原因（必填）","");reason.setSingleLine(false);reason.setMinLines(3);reason.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(1000)});
        android.app.AlertDialog dialog=new ModalDialogs.Builder(this).setTitle("退回话题").setView(panel).setNegativeButton("返回",null).setPositiveButton("确认退回",null).create();ModalDialogs.show(dialog);dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String text=reason.getText().toString().trim();if(text.isEmpty()){reason.setError("请填写退回原因");return;}try{JSONObject data=new JSONObject().put("decision","reject").put("reason",text).put("content_version",item.getLong("content_version"));dialog.dismiss();write("POST",endpoint+"/"+item.getInt("id"),data,true,this::render);}catch(Exception e){notice.show("退回",e);}});}
    private String platformName(String id){switch(id){case "codeforces":case "cf":return "Codeforces";case "atcoder":return "AtCoder";case "luogu":return "洛谷";case "nowcoder":return "牛客";case "cjlu":return "校 OJ";default:return id.isEmpty()?"全部平台":id;}}
    private String taskStatus(String status){switch(status){case "queued":return "等待执行";case "running":return "正在执行";case "completed":return "已完成";case "partial":return "部分失败";case "failed":return "失败";case "cancelled":return "已取消";default:return status;}}
    private String syncResult(Object value){if(value==null||value==JSONObject.NULL)return "";if(value instanceof JSONObject){JSONObject obj=(JSONObject)value;ArrayList<String> lines=new ArrayList<>();for(Iterator<String> keys=obj.keys();keys.hasNext();){String key=keys.next();lines.add(platformName(key)+"："+syncResult(obj.opt(key)));}return android.text.TextUtils.join(" · ",lines);}if(value instanceof Number){int n=((Number)value).intValue();return n>=0?"新增 "+n+" 条":n==-1?"成员不存在":n==-2?"未绑定账号":n==-3?"抓取失败":n==-5?"已暂停，保留原记录":"同步失败";}return String.valueOf(value);}
    private void tasks(){
        LinearLayout intro=card(body);intro.addView(text("后台采集进度",22));intro.addView(text("查看 OJ 做题记录同步、题目采集等后台任务。离开页面不会中止任务；这里只查看与取消，不会自动重新采集。",14));
        WrapLayout filters=new WrapLayout(this);intro.addView(filters);for(String value:new String[]{"全部","进行中","已结束"}){Button b=button(value,()->{taskFilter=value;render();});MobileStyle.control(b,false,value.equals(taskFilter),12);filters.addView(b);}
        intro.addView(button("刷新任务",this::render));LinearLayout slot=card(body);read("/api/tasks",slot,true,value->{JSONArray rows=(JSONArray)value;int shown=0;
            for(int i=rows.length()-1;i>=0;i--){JSONObject task=rows.getJSONObject(i);String state=task.optString("status");boolean active=Arrays.asList("queued","running").contains(state);if("进行中".equals(taskFilter)&&!active||"已结束".equals(taskFilter)&&active)continue;shown++;
                LinearLayout box=card(slot);box.addView(text(task.optString("kind","同步任务"),19));box.addView(text(taskStatus(state)+" · "+platformName(task.optString("platform")),14));box.addView(text("成员："+task.optString("qq_id","全部"),13));
                JSONObject progress=task.optJSONObject("progress"),result=task.optJSONObject("result");
                if(progress!=null){boolean metadata="metadata".equals(progress.optString("phase"));int done=progress.optInt(metadata?"metadata_done":"done"),total=progress.optInt(metadata?"metadata_total":"total");box.addView(text((metadata?"导入题目目录：":"处理进度：")+done+" / "+total,14));if(total>0){ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(total);bar.setProgress(done);bar.setProgressTintList(android.content.res.ColorStateList.valueOf(MobileStyle.BRAND));box.addView(bar,new LinearLayout.LayoutParams(-1,dp(8)));}}
                if("题目采集".equals(task.optString("kind"))&&result!=null){box.addView(text("成功 "+result.optInt("success_count")+" · 失败 "+result.optInt("failure_count")+" · 跳过 "+result.optInt("skipped_count")+" · 样例 "+result.optInt("sample_count")+" 组",13));if(!result.optString("error").isEmpty())box.addView(text(result.optString("error"),14));JSONArray errors=result.optJSONArray("failures");if(errors!=null&&errors.length()>0)box.addView(button("查看失败原因",()->{LinearLayout details=column();for(int n=0;n<errors.length();n++){JSONObject e=errors.optJSONObject(n);if(e!=null)details.addView(text(e.optString("problem_id")+"："+e.optString("error"),14));}new ModalDialogs.Builder(this).fullPage().setTitle("采集失败原因").setView(details).show();}));}
                else{String summary=syncResult(task.opt("result"));if(!summary.isEmpty())box.addView(text(summary,14));}
                long time=task.optLong("finished_at",task.optLong("started_at"));if(time>0)box.addView(text(new java.text.SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(time*1000)),12));
                box.addView(text("任务编号 · "+task.optString("id"),11));if(active)box.addView(button("取消任务",()->new ModalDialogs.Builder(this).setTitle("确认取消此任务？").setMessage("已采集的数据会保留。").setNegativeButton("返回",null).setPositiveButton("确认取消",(d,w)->write("POST","/api/tasks/"+UrlEncoding.form(task.optString("id"))+"/cancel",new JSONObject(),true,this::render)).show()));
            }if(shown==0)slot.addView(text("暂无符合条件的任务",16));});
    }
    private void memberSummary(LinearLayout box,JSONObject row){
        box.addView(text(row.optString("name","未命名成员"),20));
        String[][] fields={{"qq_id","QQ"},{"real_name","真实姓名"},{"school","学校"},{"status","身份"},{"cf_handle","Codeforces"},{"atcoder_handle","AtCoder"},{"luogu_id","洛谷 UID"},{"nowcoder_id","牛客 UID"},{"cjlu_username","校 OJ"},{"role","Web 角色"}};
        for(String[] field:fields)box.addView(text(field[1]+"："+(row.isNull(field[0])||row.optString(field[0]).isEmpty()?"未设置":row.optString(field[0])),13));
        box.addView(text("Web 账号："+(row.isNull("role")?"未发放":AdminMemberEdits.active(row)?"已启用":"已停用"),13));
    }
    private void members(){
        LinearLayout form=card(body);form.addView(text("成员筛选",20));EditText term=input(form,"用户名、姓名、QQ 或 OJ",query);
        LinearLayout options=column();form.addView(options);Spinner schools=new Spinner(this),statuses=new Spinner(this);schools.setContentDescription("学校筛选");statuses.setContentDescription("身份筛选");options.addView(schools,new LinearLayout.LayoutParams(-1,dp(50)));options.addView(statuses,new LinearLayout.LayoutParams(-1,dp(50)));schools.setEnabled(false);statuses.setEnabled(false);
        LinearLayout choices=column();form.addView(choices);read("/api/admin/members/options",choices,true,value->{JSONObject data=(JSONObject)value;bindFilter(schools,data.optJSONArray("schools"),"全部学校",school);bindFilter(statuses,data.optJSONArray("statuses"),"全部身份",statusFilter);});
        form.addView(button("筛选成员",()->{query=term.getText().toString().trim();school=filterValue(schools,school);statusFilter=filterValue(statuses,statusFilter);page=1;render();}));
        LinearLayout slot=card(body);read("/api/admin/members?search="+UrlEncoding.form(query)+"&school="+UrlEncoding.form(school)+"&status="+UrlEncoding.form(statusFilter)+"&page="+page+"&page_size=20",slot,true,value->{JSONObject data=(JSONObject)value;page=data.optInt("page",page);JSONArray rows=data.getJSONArray("items");slot.addView(text("共 "+data.optInt("total")+" 位成员 · 点击成员卡片进行管理",13));if(rows.length()==0)slot.addView(text("暂无成员",16));for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);LinearLayout box=card(slot);memberSummary(box,row);box.setContentDescription("管理成员 "+row.optString("name"));box.setFocusable(true);box.setOnClickListener(v->{if(writing||opening)return;member=row.optString("qq_id");nav("member");});}pager(slot,data.optInt("total"),20);});
    }
    private String filterValue(Spinner s,String fallback){return !s.isEnabled()?fallback:s.getSelectedItemPosition()<=0?"":s.getSelectedItem().toString();}
    private void bindFilter(Spinner spinner,JSONArray values,String all,String selected){ArrayList<String> choices=new ArrayList<>();choices.add(all);if(values!=null)for(int i=0;i<values.length();i++)choices.add(values.optString(i));if(!selected.isEmpty()&&!choices.contains(selected))choices.add(selected);spinner.setAdapter(MobileStyle.options(this,choices.toArray(new String[0])));spinner.setSelection(Math.max(0,choices.indexOf(selected)));spinner.setEnabled(true);roundSpinner(spinner);}
    private void member(){
        final String target=member;LinearLayout profile=card(body),details=card(body);profile.addView(text("正在读取成员资料…",14));details.addView(text("正在读取训练资料…",14));
        read("/api/admin/members/"+UrlEncoding.form(target),profile,true,value->{JSONObject snapshot=(JSONObject)value;memberSummary(profile,snapshot);profile.addView(button("修改成员资料",()->editMember(target,snapshot)));
            String role=snapshot.isNull("role")?"":snapshot.optString("role","");if(role.isEmpty()){profile.addView(text("尚未发放 Web 登录账号，请到网页后台开户。",13));}else if(AdminMemberEdits.canManageAccount(api.isRoot(),role)){
                profile.addView(button("重置登录密码",()->resetPassword(target)));
                boolean enabled=AdminMemberEdits.active(snapshot);profile.addView(button(enabled?"停用登录账号":"启用登录账号",()->confirmAccount(target,json("is_active",!enabled),enabled?"停用此成员登录账号？":"启用此成员登录账号？")));
                if(api.isRoot())profile.addView(button("修改账号角色",()->{String[] roles={"member","admin","root"};new ModalDialogs.Builder(this).setTitle("修改账号角色").setItems(new String[]{"普通成员","管理员","Root"},(d,w)->confirmAccount(target,json("role",roles[w]),"将账号角色设为 "+roles[w]+"？")).setNegativeButton("返回",null).show();}));
            }else profile.addView(text("仅 Root 可以修改管理员的登录权限与密码。",13));
        });
        read("/api/member/"+UrlEncoding.form(target),details,true,value->{JSONObject data=(JSONObject)value;details.addView(text("训练资料",20));JSONObject user=data.optJSONObject("user");if(user!=null)details.addView(text("挑战分："+user.optInt("challenge_rating",data.optInt("challenge_rating",1000)),14));JSONObject counts=data.optJSONObject("platform_counts");if(counts!=null)for(Iterator<String> keys=counts.keys();keys.hasNext();){String key=keys.next();details.addView(text(platformName(key)+" 通过："+counts.opt(key),14));}
            JSONArray recent=data.optJSONArray("recent_ac");details.addView(text("最近 AC",18));if(recent==null||recent.length()==0)details.addView(text("暂无内容",14));else for(int i=0;i<recent.length();i++){JSONObject problem=recent.getJSONObject(i);details.addView(button(platformName(problem.optString("platform"))+" · "+problem.optString("problem_name",problem.optString("problem_id")),()->{opening=true;startActivity(new Intent(this,MainActivity.class).putExtra("web_problem_platform",problem.optString("platform")).putExtra("web_problem_id",problem.optString("problem_id")));}));}
            for(String key:new String[]{"cf","atcoder","nowcoder"}){JSONObject platform=data.optJSONObject(key);if(platform!=null){details.addView(text(platformName(key)+" 比赛资料",17));if(!platform.isNull("rating"))details.addView(text("Rating："+platform.opt("rating"),14));JSONArray contests=platform.optJSONArray("contests");if(contests!=null)for(int n=0;n<contests.length();n++){JSONObject record=contests.optJSONObject(n);if(record!=null)details.addView(text(record.optString("name",record.optString("contest_name"))+" · 排名 "+record.optString("rank","—")+" · Rating "+record.optString("rating","—"),13));}}}
        });
        body.addView(button("为该成员生成训练",()->nav("training")));body.addView(button("查看该成员复盘",()->nav("contests")));
    }
    private void editMember(String target,JSONObject snapshot){
        LinearLayout form=column();LinkedHashMap<String,EditText> inputs=new LinkedHashMap<>();for(int i=0;i<AdminMemberEdits.FIELDS.length;i++){String field=AdminMemberEdits.FIELDS[i];form.addView(text(AdminMemberEdits.LABELS[i],14));EditText input=input(form,AdminMemberEdits.LABELS[i],snapshot.optString(field,""));inputs.put(field,input);}form.addView(text("QQ 和校 OJ 不在此修改。修改 OJ 绑定会清理该平台旧证据并发起同步。",13));
        TextView validation=text("",14);validation.setTextColor(ErrorModule.ink());form.addView(validation);Button review=button("核对修改",()->{});form.addView(review,new LinearLayout.LayoutParams(-1,dp(52)));android.app.AlertDialog dialog=new ModalDialogs.Builder(this).fullPage().setTitle("修改成员资料").setView(form).create();ModalDialogs.show(dialog);
        review.setOnClickListener(v->{try{LinkedHashMap<String,String> values=new LinkedHashMap<>();for(Map.Entry<String,EditText> item:inputs.entrySet())values.put(item.getKey(),item.getValue().getText().toString());JSONObject payload=AdminMemberEdits.payload(snapshot,values);StringBuilder summary=new StringBuilder();for(int i=0;i<AdminMemberEdits.FIELDS.length;i++){String field=AdminMemberEdits.FIELDS[i];if(payload.has(field))summary.append(AdminMemberEdits.LABELS[i]).append("：").append(snapshot.optString(field,"未设置")).append(" → ").append(payload.optString(field).isEmpty()?"清空":payload.optString(field)).append('\n');}if(payload.has("confirm_bindings"))summary.append("OJ 绑定变化将清理旧平台证据并重新同步。\n");dialog.dismiss();new ModalDialogs.Builder(this).setTitle("确认保存成员资料？").setMessage(summary.toString()).setNegativeButton("返回",null).setPositiveButton("确认保存",(d,w)->writeResult("PATCH","/api/admin/members/"+UrlEncoding.form(target),payload,true,result->{verify();if(result instanceof JSONObject){JSONArray warnings=((JSONObject)result).optJSONArray("warnings");if(warnings!=null&&warnings.length()>0){ArrayList<String> messages=new ArrayList<>();for(int n=0;n<warnings.length();n++)messages.add(warnings.optString(n));new ModalDialogs.Builder(this).setTitle("资料已保存，仍需处理").setMessage(android.text.TextUtils.join("\n",messages)).setPositiveButton("确认",null).show();}}})).show();}catch(Exception e){validation.setText(e.getMessage());}});
    }
    private void resetPassword(String target){
        LinearLayout form=column();form.addView(text("设置新的初始密码，成员下次登录必须修改。旧密码和登录会话会失效。",14));EditText password=input(form,"新初始密码（12–128字符，至少三类字符）","");password.setInputType(129);password.setSaveEnabled(false);
        android.app.AlertDialog dialog=new ModalDialogs.Builder(this).setTitle("重置登录密码").setView(form).setNegativeButton("返回",null).setPositiveButton("确认重置",null).create();ModalDialogs.show(dialog);
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String value=password.getText().toString();int length=value.codePointCount(0,value.length()),classes=(value.matches("(?s).*[a-z].*")?1:0)+(value.matches("(?s).*[A-Z].*")?1:0)+(value.matches("(?s).*[0-9].*")?1:0)+(value.matches("(?s).*[^A-Za-z0-9].*")?1:0);if(length<12||length>128||classes<3||value.codePoints().anyMatch(Character::isWhitespace)){password.setError("12–128字符，不含空白，小写/大写/数字/符号至少三类");return;}password.setText("");dialog.dismiss();write("POST","/api/admin/web-accounts/"+UrlEncoding.form(target)+"/reset-password",json("initial_password",value),true,this::verify);});
    }
    private void confirmAccount(String target,JSONObject data,String heading){new ModalDialogs.Builder(this).setTitle(heading).setMessage("账号："+target+"。该操作会使旧会话失效；最后一个 Root 由服务端保护。").setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->write("PATCH","/api/admin/web-accounts/"+UrlEncoding.form(target),data,true,this::verify)).show();}
    private void roundSpinner(Spinner spinner){android.graphics.drawable.GradientDrawable fill=new android.graphics.drawable.GradientDrawable();fill.setColor(MobileStyle.controlFill(MobileStyle.PANEL));fill.setCornerRadius(dp(12));fill.setStroke(dp(1),MobileStyle.LINE);spinner.setBackground(fill);spinner.setPadding(dp(12),dp(5),dp(12),dp(5));spinner.setClipToOutline(true);}
    private boolean validMember(EditText input){String value=input.getText().toString().trim();if(!value.matches("[1-9][0-9]{3,11}")){input.setError("请输入有效成员 QQ");return false;}member=value;return true;}
    private void training() {
        LinearLayout form = card(body);
        EditText who = input(form, "成员 QQ", member);
        String[] ids = {"codeforces", "atcoder", "luogu", "nowcoder"};
        Spinner platform = new Spinner(this);
        platform.setContentDescription("训练平台");
        platform.setAdapter(MobileStyle.options(this, new String[]{"Codeforces", "AtCoder", "洛谷", "牛客"}));
        form.addView(platform,new LinearLayout.LayoutParams(-1,dp(52)));roundSpinner(platform);
        EditText tag = input(form, "标签、题名或题号（可空）", "");
        form.addView(text("难度（必选，已按平台预选）", 14));
        Spinner difficulty = new Spinner(this);
        difficulty.setContentDescription("训练难度");
        form.addView(difficulty,new LinearLayout.LayoutParams(-1,dp(52)));roundSpinner(difficulty);
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
