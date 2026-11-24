package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.os.Bundle;
import android.text.*;
import android.widget.*;
import java.util.*;
import org.json.*;

/** All writes use the reviewed server's optimistic versions, previews and idempotency contract. */
public final class AdminTrainingActivity extends AdminPageActivity {
    private static final String API="/api/admin/training-tasks";
    private String mode="list",search="",state="",identity="",completion="",order="none",key="";private int page=1,step=1,previewPage=1;private long id,recipient;
    private JSONObject task=new JSONObject(),draft=new JSONObject(),preview=null,options=null;private String problemText="";private boolean progressFiltersOpen;
    @Override public void onCreate(Bundle b){super.onCreate(b);if(b!=null)progressFiltersOpen=b.getBoolean("progressFiltersOpen",false);id=getIntent().getLongExtra("task_id",0);recipient=getIntent().getLongExtra("recipient_id",0);if(id>0)mode=recipient>0?"recipient":"detail";if(b!=null)try{mode=b.getString("mode","list");id=b.getLong("id");recipient=b.getLong("recipient");page=b.getInt("page",1);step=b.getInt("step",1);previewPage=b.getInt("previewPage",1);search=b.getString("search","");state=b.getString("state","");identity=b.getString("identity","");completion=b.getString("completion","");order=b.getString("progress_order","none");key=b.getString("key","");problemText=b.getString("problems","");draft=new JSONObject(b.getString("draft","{}"));task=new JSONObject(b.getString("task","{}"));if(b.containsKey("preview"))preview=new JSONObject(b.getString("preview"));}catch(Exception ignored){mode="list";}}
    @Override protected void onAccessLost(){
        ModalDialogs.close(this);progressFiltersOpen=false;task=new JSONObject();draft=new JSONObject();preview=null;options=null;
        id=recipient=0;page=step=previewPage=1;mode="list";order="none";
        search=state=identity=completion=key=problemText="";
    }
    @Override protected void onSaveInstanceState(Bundle b){super.onSaveInstanceState(b);b.putBoolean("progressFiltersOpen",progressFiltersOpen);b.putString("mode",mode);b.putLong("id",id);b.putLong("recipient",recipient);b.putInt("page",page);b.putInt("step",step);b.putInt("previewPage",previewPage);b.putString("search",search);b.putString("state",state);b.putString("identity",identity);b.putString("completion",completion);b.putString("progress_order",order);b.putString("key",key);b.putString("problems",problemText);b.putString("draft",draft.toString());b.putString("task",task.toString());if(preview!=null)b.putString("preview",preview.toString());}
    @Override protected void renderAdmin(){if(!access()){finish();return;}resetPage("社团题单管理");if("edit".equals(mode))editor();else if("preview".equals(mode))preview();else if("progress".equals(mode))progress();else if("recipient".equals(mode))recipient();else if("detail".equals(mode))detail();else list();}
    private void go(String next){PageMotion.change(this,true,()->{mode=next;renderAdmin();});}
    @Override public void onBackPressed(){if("edit".equals(mode)&&step>1){step--;renderAdmin();return;}if("edit".equals(mode)||"preview".equals(mode)||"progress".equals(mode)){mode=id>0?"detail":"list";renderAdmin();return;}super.onBackPressed();}
    private void open(long taskId){opening=true;startActivity(new Intent(this,AdminTrainingActivity.class).putExtra("task_id",taskId));}
    private void list(){LinearLayout form=card(body);EditText q=input(form,"题单标题",search);Spinner status=spinner(form,new String[]{"全部","草稿","已发布","已取消"});String[] states={"","draft","published","cancelled"};status.setSelection(Arrays.asList(states).indexOf(state));form.addView(button("筛选",()->{search=q.getText().toString().trim();state=states[status.getSelectedItemPosition()];page=1;renderAdmin();}));form.addView(button("新建题单",()->{id=0;task=new JSONObject();draft=new JSONObject();problemText="";step=1;preview=null;key="";go("edit");}));LinearLayout slot=card(body);read(API+"?page="+page+"&page_size=20&state="+state+"&search="+UrlEncoding.form(search),slot,true,result->{JSONObject data=(JSONObject)result;JSONArray rows=data.getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无题单",16));for(int i=0;i<rows.length();i++){JSONObject t=rows.getJSONObject(i);LinearLayout b=card(slot);TrainingUi.task(this,b,t);overview(b,t.optJSONObject("summary"));b.addView(button("管理题单",()->open(t.optLong("id"))));}pager(slot,data.optInt("total"),()->renderAdmin());});}
    private void detail(){LinearLayout slot=card(body);read(API+"/"+id,slot,true,result->{task=(JSONObject)result;TrainingUi.task(this,slot,task);slot.addView(text("发布人："+task.optString("creator_name","未提供"),13));overview(slot,task.optJSONObject("summary"));String d=task.optString("description");if(!d.isEmpty())slot.addView(text(d,14));if("draft".equals(task.optString("state"))){slot.addView(button("编辑草稿",()->{try{draft=new JSONObject(task.toString());problemText=problemLines(task.optJSONArray("problems"));step=1;preview=null;key="";go("edit");}catch(Exception e){notice.show("编辑",e);}}));slot.addView(button("预览发放名单",()->audience(1)));slot.addView(button("删除草稿",()->confirm("删除此草稿？",()->write("DELETE",API+"/"+id,json("version",task.optInt("version")),true,()->{id=0;go("list");}))));}else{slot.addView(button("完成情况",()->{page=1;go("progress");}));if("published".equals(task.optString("state"))){slot.addView(button("延期",()->lifecycle(false)));slot.addView(button("取消题单",()->lifecycle(true)));}}TrainingUi.problems(this,slot,task.optJSONArray("problems"));JSONArray audit=task.optJSONArray("audit");slot.addView(text("操作记录（最近 50 条）",18));if(audit!=null)for(int i=0;i<audit.length();i++){JSONObject row=audit.getJSONObject(i);slot.addView(text(TrainingUi.date(row.optLong("created_at"))+" · "+row.optString("action")+" · "+row.optString("reason"),12));}});}
    private void editor(){LinearLayout form=card(body);form.addView(text("步骤 "+step+" / 3 · "+(step==1?"任务与题目":"身份与周期"),20));if(step==1){field(form,"题单标题（1–100字）","title",false);field(form,"Markdown 说明（最多5000字）","description",true);EditText problems=input(form,"每行一个标准题号：1843A 或 codeforces 1843A",problemText);problems.setSingleLine(false);problems.setMinLines(4);watch(problems,()->problemText=problems.getText().toString());form.addView(text("首期仅 Codeforces 可发布；其他平台可保存草稿。每行：平台 + 空格 + 标准题号，最多 50 题。",12));form.addView(button("校验题目，下一步",()->{try{JSONArray items=parseProblems(problemText);if(draft.optString("title").trim().isEmpty()||draft.optString("title").length()>100||draft.optString("description").length()>5000)throw new IllegalArgumentException("请检查标题与说明长度");writeResult("POST",API+"/resolve-problems",json("problems",items),true,result->{JSONObject r=(JSONObject)result;JSONArray errors=r.getJSONArray("errors");if(errors.length()>0){StringBuilder msg=new StringBuilder();for(int n=0;n<errors.length();n++)msg.append("第 ").append(errors.getJSONObject(n).optInt("index")+1).append(" 行：").append(errors.getJSONObject(n).optString("message")).append('\n');throw new IllegalArgumentException(msg.toString());}draft.put("problems",r.getJSONArray("items"));step=2;renderAdmin();});}catch(Exception e){notice.show("校验题目",e);}}));return;}
        LinearLayout choices=column();form.addView(choices);read(API+"/options",choices,true,result->{options=(JSONObject)result;choices.addView(text(options.optBoolean("enabled")?"训练任务已开放":"当前服务器关闭发布，仍可保存草稿。",13));JSONArray statuses=options.optJSONArray("statuses");if(statuses!=null)for(int i=0;i<statuses.length();i++){String s=statuses.getString(i);CheckBox box=new CheckBox(this);box.setText(s);box.setChecked(contains(draft.optJSONArray("statuses"),s));box.setOnCheckedChangeListener((b,on)->{JSONArray selected=new JSONArray();if(statuses!=null)for(int n=0;n<choices.getChildCount();n++)if(choices.getChildAt(n) instanceof CheckBox&&((CheckBox)choices.getChildAt(n)).isChecked())selected.put(((CheckBox)choices.getChildAt(n)).getText().toString());put("statuses",selected);});choices.addView(box);}});
        dateField(form,"开始时间（北京时间 yyyy-MM-dd HH:mm，可空）","starts_at");dateField(form,"截止时间（北京时间 yyyy-MM-dd HH:mm，可空）","due_at");Spinner rule=spinner(form,new String[]{"周期内 AC","历史 AC 可计入"});rule.setSelection("historical_ac".equals(draft.optString("rule"))?1:0);rule.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,android.view.View v,int position,long item){put("rule",position==1?"historical_ac":"period_ac");}public void onNothingSelected(AdapterView<?> p){}});form.addView(button("保存草稿",()->saveDraft(rule,false)));form.addView(button("保存并预览发布",()->saveDraft(rule,true)));
    }
    private void saveDraft(Spinner rule,boolean publish){try{JSONObject data=new JSONObject();for(String field:new String[]{"title","description","statuses","starts_at","due_at","problems"})if(draft.has(field))data.put(field,draft.get(field));data.put("rule",rule.getSelectedItemPosition()==1?"historical_ac":"period_ac");if(id>0)data.put("version",task.getInt("version"));writeResult(id>0?"PATCH":"POST",API+(id>0?"/"+id:""),data,true,result->{task=(JSONObject)result;id=task.getLong("id");draft=new JSONObject(task.toString());key="";preview=null;if(publish)audience(1);else go("detail");});}catch(Exception e){notice.show("保存草稿",e);}}
    private void audience(int p){writeResult("POST",API+"/"+id+"/audience-preview?page="+p+"&page_size=20",json("version",task.optInt("version")),true,result->{preview=(JSONObject)result;previewPage=p;key=UUID.randomUUID().toString();go("preview");});}
    private void preview(){LinearLayout b=card(body);b.addView(text("步骤 3 / 3 · 发布确认",20));if(preview==null){b.addView(button("重新预览名单",()->audience(1)));return;}b.addView(text("接收 "+preview.optInt("recipient_count")+" 人 · 排除 "+preview.optInt("excluded_count")+" 人 · 未绑定 "+preview.optInt("unbound_count")+" 人",15));b.addView(text("预览10分钟有效。名单、账号或绑定变化后须重新预览。发布结果未知时，请用相同发布按钮重试，不要重新创建。",12));JSONArray members=preview.optJSONArray("items");if(members!=null)for(int i=0;i<members.length();i++){JSONObject r=members.optJSONObject(i);if(r==null)continue;b.addView(text(r.optString("name")+" · "+r.optString("qq_id")+" · "+r.optString("status")+(r.isNull("excluded_reason")?"":" · 排除："+r.optString("excluded_reason"))+(r.optBoolean("unbound")?" · 未绑定":""),13));}equalButtons(b,button("上一页",()->{if(previewPage>1)audience(previewPage-1);}),button("下一页",()->{if(previewPage*20<preview.optInt("total"))audience(previewPage+1);}));CheckBox exclusions=new CheckBox(this);exclusions.setText("已核对名单与排除原因，同意排除上述账号");b.addView(exclusions);b.addView(button("确认发布",()->{if(preview.optInt("excluded_count")>0&&!exclusions.isChecked()){notice.show("发布",new IllegalArgumentException("请先确认排除名单"));return;}try{JSONObject payload=new JSONObject().put("version",task.getInt("version")).put("preview_token",preview.getString("preview_token")).put("confirm_exclusions",exclusions.isChecked());writeRequest(()->api.publishTraining(id,payload,key),true,result->{task=(JSONObject)result;preview=null;key="";go("detail");});}catch(Exception e){notice.show("发布",e);}}));b.addView(button("重新预览",()->audience(1)));}
    private void lifecycle(boolean cancel){LinearLayout form=column();EditText due=cancel?null:input(form,"新截止（北京时间 yyyy-MM-dd HH:mm）",dateInput(task.optLong("due_at")));EditText why=input(form,"原因（必填）","");new ModalDialogs.Builder(this).setTitle(cancel?"确认取消题单？":"延长截止时间").setView(form).setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->{try{String reason=why.getText().toString().trim();if(reason.isEmpty())throw new IllegalArgumentException("原因必填");JSONObject data=new JSONObject().put("version",task.getInt("version")).put("reason",reason);if(!cancel)data.put("due_at",parseDate(due.getText().toString()));write("POST",API+"/"+id+(cancel?"/cancel":"/extend-deadline"),data,true,this::renderAdmin);}catch(Exception e){notice.show("维护题单",e);}}).show();}
    private void progress(){
        if("completed".equals(order))order="xcpc";
        LinearLayout tools=card(body);tools.setPadding(dp(8),dp(6),dp(8),dp(6));
        LinearLayout form=column();form.setVisibility(progressFiltersOpen?android.view.View.VISIBLE:android.view.View.GONE);
        Button expand=button(progressFiltersOpen?"收起筛选":"筛选与排序",()->{});
        expand.setOnClickListener(v->{progressFiltersOpen=!progressFiltersOpen;form.setVisibility(progressFiltersOpen?android.view.View.VISIBLE:android.view.View.GONE);expand.setText(progressFiltersOpen?"收起筛选":"筛选与排序");});
        tools.addView(expand,new LinearLayout.LayoutParams(-1,dp(40)));tools.addView(form);
        EditText who=input(form,"姓名、QQ",search),cohort=input(form,"业务身份（空为全部）",identity);
        String[] keys={"","on_time","late","incomplete","not_started","pending","abnormal"};
        Spinner filter=spinner(form,new String[]{"全部","按时完成","逾期完成","未完成","未开始","待核验","账号异常"});
        filter.setSelection(Arrays.asList(keys).indexOf(completion));form.addView(text("排列方式",13));
        Spinner ordering=spinner(form,new String[]{"不排名（默认）","按过题数、总用时排名"});ordering.setContentDescription("完成情况排列方式");ordering.setSelection("xcpc".equals(order)?1:0);
        form.addView(button("筛选",()->{search=who.getText().toString().trim();identity=cohort.getText().toString().trim();completion=keys[filter.getSelectedItemPosition()];order=ordering.getSelectedItemPosition()==1?"xcpc":"none";page=1;progressFiltersOpen=false;renderAdmin();}));
        LinearLayout slot=card(body);slot.setPadding(dp(8),dp(8),dp(8),dp(8));
        read(API+"/"+id+"/progress?page="+page+"&page_size=20&search="+UrlEncoding.form(search)+"&identity="+UrlEncoding.form(identity)+"&status="+completion+"&order="+order+"&view=xcpc",slot,true,result->{
            JSONObject data=(JSONObject)result;
            if("xcpc".equals(order)&&!"xcpc".equals(data.optString("order")))throw new ApiClient.UnavailableEndpointException("当前服务器不支持全体 XCPC 排名");
            JSONObject scoreboard=data.optJSONObject("scoreboard");
            if(scoreboard!=null&&scoreboard.has("columns"))xcpc(slot,scoreboard);
            else {
                JSONArray rows=data.getJSONArray("items");
                for(int i=0;i<rows.length();i++){
                    JSONObject r=rows.getJSONObject(i);LinearLayout box=card(slot);
                    if("xcpc".equals(order)){if(!r.has("rank"))throw new IllegalArgumentException("服务器未返回全体名次");box.addView(text("第 "+r.getInt("rank")+" 名 · 完成 "+r.optInt("completed_problems")+" / "+r.optInt("problem_count"),17));}
                    box.addView(text(r.optString("name")+" · 姓名："+(r.isNull("real_name")?"未填写":r.optString("real_name"))+" · "+r.optString("status_snapshot"),16));
                    TrainingUi.progress(this,box,r);box.addView(button("逐题证据",()->startActivity(new Intent(this,AdminTrainingActivity.class).putExtra("task_id",id).putExtra("recipient_id",r.optLong("id")))));
                }
            }
            overview(slot,data.optJSONObject("summary"));pager(slot,data.optInt("total"),this::renderAdmin);
        });
    }
    private TextView scoreCell(String value,int width,int height,int fill,int ink,boolean header){
        TextView cell=text(value,header?11:12);cell.setGravity(android.view.Gravity.CENTER);cell.setTextColor(ink);
        cell.setPadding(dp(2),dp(3),dp(2),dp(3));cell.setBackground(MobileStyle.panel(this,fill,0,MobileStyle.LINE));
        cell.setContentDescription(value);cell.setMaxLines(2);cell.setEllipsize(android.text.TextUtils.TruncateAt.END);
        cell.setLayoutParams(new LinearLayout.LayoutParams(width<0?-1:dp(width),dp(height)));return cell;
    }
    private LinearLayout scoreMember(JSONObject member,int width,int height,int fill){
        LinearLayout box=row();box.setPadding(dp(4),dp(4),dp(4),dp(4));box.setBackground(MobileStyle.panel(this,fill,0,MobileStyle.LINE));
        TextView rank=scoreCell(TrainingScoreboardData.rank(member),24,height-8,fill,MobileStyle.MUTED,false);rank.setBackground(null);box.addView(rank);
        LinearLayout names=column();
        TextView name=text(TrainingScoreboardData.name(member),13),real=text(TrainingScoreboardData.realName(member),11);
        name.setTextColor(MobileStyle.TEXT);real.setTextColor(MobileStyle.MUTED);
        for(TextView line:new TextView[]{name,real}){line.setPadding(0,dp(2),0,dp(2));line.setSingleLine(true);line.setEllipsize(android.text.TextUtils.TruncateAt.END);names.addView(line);}
        box.addView(names,new LinearLayout.LayoutParams(0,-2,1));
        box.setContentDescription("名次 "+TrainingScoreboardData.rank(member)+" · "+TrainingScoreboardData.name(member)+" · 姓名："+TrainingScoreboardData.realName(member));
        box.setLayoutParams(new LinearLayout.LayoutParams(width<0?-1:dp(width),dp(height)));return box;
    }
    private void xcpc(LinearLayout parent,JSONObject board){
        JSONArray columns=board.optJSONArray("columns"),rows=board.optJSONArray("rows");if(columns==null||rows==null)return;
        parent.addView(text("XCPC 计分板",16));
        parent.addView(text("左右固定，题目横滑；点题查看首次 AC",11));
        LinearLayout left=column(),right=column(),middle=column();
        ArrayList<TextView> problemViews=new ArrayList<>();
        LinearLayout table=new LinearLayout(this){
            @Override protected void onMeasure(int width,int height){
                int available=MeasureSpec.getSize(width);
                int member=Math.min(dp(124),Math.max(dp(96),Math.round(available*.36f)));
                int score=Math.min(dp(84),Math.max(dp(64),Math.round(available*.24f)));
                left.getLayoutParams().width=member;right.getLayoutParams().width=score;
                int cell=Math.max(dp(42),Math.min(dp(56),(available-member-score)/Math.max(1,columns.length())));
                for(TextView view:problemViews)view.getLayoutParams().width=cell;
                super.onMeasure(width,height);
            }
        };
        left.setContentDescription("计分板固定左侧");right.setContentDescription("计分板固定右侧");
        HorizontalScrollView horizontal=new HorizontalScrollView(this);horizontal.setHorizontalScrollBarEnabled(true);
        horizontal.setContentDescription("计分板题目列横向滑动区域");horizontal.addView(middle);
        int head=Math.max(42,(int)Math.ceil(30*getResources().getConfiguration().fontScale));
        int rowHeight=Math.max(58,(int)Math.ceil(44*getResources().getConfiguration().fontScale));
        table.addView(left,new LinearLayout.LayoutParams(dp(124),-2));
        table.addView(horizontal,new LinearLayout.LayoutParams(0,-2,1));table.addView(right,new LinearLayout.LayoutParams(dp(84),-2));
        left.addView(scoreCell("# / 用户名\n真实姓名",-1,head,MobileStyle.PANEL,MobileStyle.MUTED,true));
        right.addView(scoreCell("过题 / 总题\n用时（分）",-1,head,MobileStyle.PANEL,MobileStyle.MUTED,true));
        LinearLayout mh=row();
        for(int i=0;i<columns.length();i++){
            JSONObject column=columns.optJSONObject(i);
            TextView label=scoreCell(column==null?String.valueOf(i+1):column.optString("label",String.valueOf(i+1)),42,head,MobileStyle.PANEL,MobileStyle.TEXT,true);
            problemViews.add(label);mh.addView(label);
        }
        middle.addView(mh,new LinearLayout.LayoutParams(-2,dp(head)));
        for(int i=0;i<rows.length();i++){
            JSONObject member=rows.optJSONObject(i);if(member==null)continue;
            int stripe=i%2==0?MobileStyle.PANEL:MobileStyle.BACKGROUND;
            left.addView(scoreMember(member,-1,rowHeight,stripe));
            JSONArray cells=member.optJSONArray("cells");LinearLayout mr=row();
            for(int c=0;c<columns.length();c++){
                JSONObject column=columns.optJSONObject(c),cell=cells==null?null:cells.optJSONObject(c);
                boolean solved="solved".equals(TrainingScoreboardData.state(cell));
                TextView problem=scoreCell(TrainingScoreboardData.cellLabel(task,cell),42,rowHeight,solved?MobileStyle.SELECTED:stripe,solved?MobileStyle.ON_SELECTED:MobileStyle.MUTED,false);
                problem.setContentDescription(TrainingScoreboardData.description(member,column,cell));
                problem.setOnClickListener(v->{if(access())new ModalDialogs.Builder(this).setTitle("题目完成详情")
                    .setMessage(TrainingScoreboardData.details(task,member,column,cell)).setPositiveButton("确认",null).show();});
                problemViews.add(problem);mr.addView(problem);
            }
            middle.addView(mr,new LinearLayout.LayoutParams(-2,dp(rowHeight)));
            TextView total=scoreCell(TrainingScoreboardData.score(member),-1,rowHeight,stripe,MobileStyle.BRAND,false);
            total.setContentDescription("已通过 "+member.optInt("completed_problems")+" / "+member.optInt("problem_count")+" · "+TrainingScoreboardData.totalTime(member));
            total.setTextSize(11);right.addView(total);
        }
        left.addView(scoreCell("总 AC 人数",-1,head,MobileStyle.PANEL,MobileStyle.TEXT,true));
        LinearLayout totals=row();
        for(int c=0;c<columns.length();c++){
            JSONObject column=columns.optJSONObject(c);String count=TrainingScoreboardData.acceptedCount(board,column);
            TextView total=scoreCell(count,42,head,MobileStyle.PANEL,MobileStyle.BRAND,true);
            total.setContentDescription("题目 "+(column==null?c+1:column.optString("label"))+" · 全题单总 AC 人数 "+count);
            problemViews.add(total);totals.addView(total);
        }
        middle.addView(totals,new LinearLayout.LayoutParams(-2,dp(head)));
        right.addView(scoreCell(board.has("participant_count")?"共 "+board.optInt("participant_count")+" 人":"—",-1,head,MobileStyle.PANEL,MobileStyle.MUTED,true));
        parent.addView(table,new LinearLayout.LayoutParams(-1,-2));
        parent.addView(text("总用时为各题首次已核验 AC 用时之和；历史 AC 不计用时。",11));
        parent.addView(text("task".equals(board.optString("totals_scope"))?"每题总 AC 人数按整份题单统计，与分页、筛选无关。":"当前服务器尚未提供全题单 AC 汇总。",11));
    }
    private void recipient(){LinearLayout slot=card(body);read(API+"/"+id+"/progress/"+recipient,slot,true,result->{JSONObject data=(JSONObject)result;TrainingUi.progress(this,slot,data.optJSONObject("recipient"));TrainingUi.problems(this,slot,data.optJSONArray("problems"));});}
    private void overview(LinearLayout b,JSONObject s){if(s!=null)b.addView(text("人数 "+s.optInt("recipient_count")+" · 按时 "+s.optInt("on_time_count")+" · 逾期 "+s.optInt("late_count")+" · 待核验 "+s.optInt("pending_count")+" · 异常 "+s.optInt("abnormal_count"),13));}
    private Spinner spinner(LinearLayout b,String[] names){Spinner s=new Spinner(this);s.setAdapter(MobileStyle.options(this,names));s.setBackground(MobileStyle.panel(this,MobileStyle.PANEL,12,MobileStyle.LINE));b.addView(s,new LinearLayout.LayoutParams(-1,dp(52)));return s;}
    private void field(LinearLayout b,String hint,String key,boolean multiline){EditText e=input(b,hint,draft.optString(key));if(multiline){e.setSingleLine(false);e.setMinLines(3);}watch(e,()->put(key,e.getText().toString()));}
    private void dateField(LinearLayout b,String hint,String key){EditText e=input(b,hint,draft.opt(key) instanceof String?draft.optString(key):dateInput(draft.optLong(key)));watch(e,()->{try{put(key,parseDate(e.getText().toString()));e.setError(null);}catch(Exception ex){put(key,e.getText().toString());e.setError(ex.getMessage());}});}
    private void put(String k,Object v){try{draft.put(k,v);}catch(Exception e){throw new IllegalArgumentException(e);}}
    private void watch(EditText e,Runnable r){e.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int c,int a){}public void onTextChanged(CharSequence s,int st,int before,int c){r.run();}public void afterTextChanged(Editable v){}});}
    private static boolean contains(JSONArray a,String s){if(a!=null)for(int i=0;i<a.length();i++)if(s.equals(a.optString(i)))return true;return false;}
    static String dateInput(long sec){if(sec<=0)return "";java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.CHINA);f.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));return f.format(new Date(sec*1000));}
    static Object parseDate(String value)throws Exception{if(value.trim().isEmpty())return JSONObject.NULL;java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.CHINA);f.setLenient(false);f.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));java.text.ParsePosition pos=new java.text.ParsePosition(0);Date date=f.parse(value,pos);if(date==null||pos.getIndex()!=value.length())throw new IllegalArgumentException("请输入 yyyy-MM-dd HH:mm");return date.getTime()/1000;}
    static JSONArray parseProblems(String text)throws Exception{JSONArray out=new JSONArray();for(String line:text.split("[\\r\\n]+")){String[] parts=line.trim().split("\\s+",2);if(parts[0].isEmpty())continue;out.put(new JSONObject().put("platform",parts.length==1?"codeforces":parts[0]).put("problem_id",parts.length==1?parts[0]:parts[1]));}if(out.length()>500)throw new IllegalArgumentException("最多500条原始输入，去重后最多50题");return out;}
    private String problemLines(JSONArray a){StringBuilder b=new StringBuilder();if(a!=null)for(int i=0;i<a.length();i++){JSONObject p=a.optJSONObject(i);if(p!=null)b.append(p.optString("platform")).append(' ').append(p.optString("problem_id").replaceFirst("^cf_","")).append('\n');}return b.toString();}
    private void confirm(String heading,Runnable work){new ModalDialogs.Builder(this).setTitle(heading).setNegativeButton("返回",null).setPositiveButton("确认",(d,w)->work.run()).show();}
    private void pager(LinearLayout b,int total,Runnable render){b.addView(text("第 "+page+" 页 · 共 "+total+" 条",12));equalButtons(b,button("上一页",()->{if(page>1){page--;render.run();}}),button("下一页",()->{if(page*20<total){page++;render.run();}}));}
}
