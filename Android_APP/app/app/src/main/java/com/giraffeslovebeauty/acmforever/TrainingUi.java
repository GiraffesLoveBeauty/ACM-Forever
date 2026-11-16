package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.widget.*;
import java.util.*;
import org.json.*;

/** Assigned tasks use backend evidence; absence of verification never means a confirmed failure. */
final class TrainingUi {
    static String date(long seconds){if(seconds<=0)return "未设置";java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.CHINA);f.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));return f.format(new Date(seconds*1000))+" 北京时间";}
    static String label(String key){switch(key){
        case "draft":return "草稿";case "published":return "已发布";case "active":return "进行中";case "upcoming":return "未开始";case "ended":return "已结束";case "cancelled":return "已取消";
        case "on_time":return "按时完成";case "late":return "逾期完成";case "history_ac":return "历史已通过";case "incomplete":return "尚未完成";case "not_started":return "未有完成记录";
        case "verified":return "证据已核验";case "pending":case "pending_sync":return "待同步核验";case "coverage_missing":return "提交历史覆盖不足，待核验";
        case "unbound":return "未绑定账号";case "binding_changed":return "绑定已变化，待核验";case "sync_failed":return "同步失败，原有进度保留";case "sync_paused":return "同步已暂停";
        case "account_closed":return "账号已注销";case "account_changed":return "账号代际变化";case "account_disabled":return "账号已停用";case "queued":return "排队中";case "running":return "同步中";
        case "completed":case "success":return "同步完成";case "failed":case "error":return "同步失败";case "interrupted":return "同步已中断";default:return key.isEmpty()?"未提供":key;
    }}
    static boolean polling(JSONObject task){JSONObject r=task.optJSONObject("refresh");return r!=null&&Arrays.asList("queued","running").contains(r.optString("status"));}
    static void progress(MobilePageActivity a,LinearLayout box,JSONObject r){if(r==null)return;
        box.addView(a.text("已完成 "+(r.optInt("on_time_problems")+r.optInt("late_problems"))+" / "+r.optInt("problem_count")+" · "+label(r.optString("completion")),15));
        box.addView(a.text("按时 "+r.optInt("on_time_problems")+" · 逾期 "+r.optInt("late_problems")+" · 待核验 "+r.optInt("pending_problems"),13));
        ProgressBar bar=new ProgressBar(a,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(Math.max(1,r.optInt("problem_count")));bar.setProgress(r.optInt("on_time_problems"));bar.setSecondaryProgress(r.optInt("on_time_problems")+r.optInt("late_problems"));box.addView(bar);
        if(r.optLong("checked_at")>0)box.addView(a.text("核验："+date(r.optLong("checked_at")),12));if(r.optLong("last_success_at")>0)box.addView(a.text("最近同步成功："+date(r.optLong("last_success_at")),12));
    }
    static void task(MobilePageActivity a,LinearLayout box,JSONObject t){box.addView(a.text(t.optString("title"),21));box.addView(a.text(label(t.optString("phase",t.optString("state")))+" · "+("historical_ac".equals(t.optString("rule"))?"历史 AC 计入完成":"周期内 AC 才计入按时完成"),14));if(t.has("creator_name"))box.addView(a.text("发布人："+t.optString("creator_name"),13));box.addView(a.text("开始："+date(t.optLong("starts_at"))+"\n截止："+date(t.optLong("due_at")),13));if(t.optLong("original_due_at")>0&&t.optLong("original_due_at")!=t.optLong("due_at"))box.addView(a.text("原截止："+date(t.optLong("original_due_at")),12));}
    static void problems(MobilePageActivity a,LinearLayout parent,JSONArray items){if(items==null)return;for(int i=0;i<items.length();i++){JSONObject p=items.optJSONObject(i);if(p==null)continue;LinearLayout b=a.card(parent);b.addView(a.text((i+1)+". "+p.optString("problem_name",p.optString("problem_id")),18));b.addView(a.text(p.optString("platform")+" · "+p.optString("problem_id"),13));ProblemBadges.append(a,b,p);
        if(p.has("verification")){b.addView(a.text(label(p.optString("status"))+" · "+label(p.optString("verification")),14));JSONObject e=p.optJSONObject("evidence");if(e!=null)b.addView(a.text("AC："+date(e.optLong("accepted_at"))+" · 提交 "+e.optString("external_submission_id","未提供"),12));if(p.optLong("sync_success_at")>0)b.addView(a.text("同步："+date(p.optLong("sync_success_at")),12));}
        b.addView(a.button("查看题面与样例",()->{a.opening=true;a.startActivity(new Intent(a,MainActivity.class).putExtra("web_problem_platform",p.optString("platform")).putExtra("web_problem_id",p.optString("problem_id")));}));
    }}
}
