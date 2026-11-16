package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.os.*;
import android.widget.*;
import org.json.*;

/** Personal assigned training. Separate Activities retain the list underneath each detail. */
public final class TrainingTasksActivity extends MobilePageActivity {
    private String mode="list",tab="active",adminState="";private boolean allTasks;private int page=1;private long id;private int restoreY;private JSONObject lastDetail;
    private final Handler timer=new Handler(Looper.getMainLooper());private boolean visible,first=true;private final Runnable poll=()->{if(visible&&!writing&&refresh.canRefresh())render();};
    @Override public void onCreate(Bundle state){super.onCreate(state);mode=getIntent().getStringExtra("mode");if(mode==null)mode="list";id=getIntent().getLongExtra("task_id",0);createPage("社团题单");allTasks=getIntent().getBooleanExtra("all_tasks",id==0&&!"schedule".equals(mode)&&api.isAdministrator());if(state!=null){tab=state.getString("tab","active");adminState=state.getString("admin_state","");allTasks=state.getBoolean("all_tasks",allTasks);page=state.getInt("page",1);restoreY=state.getInt("scroll");}render();}
    @Override protected void onSaveInstanceState(Bundle b){super.onSaveInstanceState(b);b.putString("tab",tab);b.putString("admin_state",adminState);b.putBoolean("all_tasks",allTasks);b.putInt("page",page);b.putInt("scroll",scroll.getScrollY());}
    @Override protected void onResume(){super.onResume();visible=true;if(first)first=false;else render();}
    @Override protected void onPause(){visible=false;timer.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){timer.removeCallbacksAndMessages(null);super.onDestroy();}
    private void position(){final int token=serial,y=restoreY>=0?restoreY:scroll.getScrollY();restoreY=-1;scroll.post(()->{if(token==serial&&!isDestroyed())scroll.scrollTo(0,y);});}
    private void schedulePoll(){timer.removeCallbacks(poll);if(visible&&lastDetail!=null&&TrainingUi.polling(lastDetail))timer.postDelayed(poll,3000);}
    private void render(){timer.removeCallbacks(poll);if(scroll!=null&&restoreY<0)restoreY=scroll.getScrollY();resetPage(id>0?"题单详情":"schedule".equals(mode)?"我的训练安排":"社团题单");if(id>0)detail();else if("schedule".equals(mode))schedule();else list();}
    private void open(long task){opening=true;startActivity(new Intent(this,TrainingTasksActivity.class).putExtra("task_id",task).putExtra("all_tasks",allTasks));}
    private void overview(LinearLayout b,JSONObject t){JSONObject s=t.optJSONObject("summary");if(s!=null)b.addView(text("人数 "+s.optInt("recipient_count")+" · 按时 "+s.optInt("on_time_count")+" · 逾期 "+s.optInt("late_count")+" · 待核验 "+s.optInt("pending_count"),13));}
    private void summary(LinearLayout parent,JSONObject t){LinearLayout b=card(parent);TrainingUi.task(this,b,t);if(allTasks)overview(b,t);else TrainingUi.progress(this,b,t.optJSONObject("recipient"));b.addView(button("打开题单",()->open(t.optLong("id"))));}
    private void list(){LinearLayout filters=card(body);
        if(api.isAdministrator())equalButtons(filters,button(allTasks?"✓ 全部题单":"全部题单",()->scope(true)),button(allTasks?"我的题单":"✓ 我的题单",()->scope(false)));
        String[] keys=allTasks?new String[]{"","draft","published","cancelled"}:new String[]{"active","upcoming","history"};String[] names=allTasks?new String[]{"全部状态","草稿","已发布","已取消"}:new String[]{"进行中","未开始","历史"};
        for(int i=0;i<keys.length;i++){String key=keys[i];Button b=button(names[i],()->{if(allTasks)adminState=key;else tab=key;page=1;restoreY=0;render();});MobileStyle.button(b,(allTasks?adminState:tab).equals(key));filters.addView(b);}
        LinearLayout slot=card(body);String path=allTasks?"/api/admin/training-tasks?state="+adminState:"/api/me/training-tasks?tab="+tab;
        read(path+"&page="+page+"&page_size=20",slot,allTasks,value->{JSONObject data=(JSONObject)value;JSONArray rows=data.getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无题单",16));for(int i=0;i<rows.length();i++)summary(slot,rows.getJSONObject(i));int total=data.optInt("total");slot.addView(text("第 "+page+" 页 · 共 "+total+" 份",12));equalButtons(slot,button("上一页",()->{if(page>1){page--;restoreY=0;render();}}),button("下一页",()->{if(page*20<total){page++;restoreY=0;render();}}));position();});}
    private void scope(boolean all){if(all&&!api.isAdministrator())return;allTasks=all;page=1;restoreY=0;render();}
    private void schedule(){LinearLayout slot=card(body);read(()->{JSONObject data=api.getObject("/api/me/training-tasks?tab=active&page_size=1");if(data.getJSONArray("items").length()==0)data=api.getObject("/api/me/training-tasks?tab=upcoming&page_size=1");return data;},slot,false,value->{JSONArray rows=((JSONObject)value).getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无训练安排",17));else summary(slot,rows.getJSONObject(0));position();});body.addView(button("查看全部题单",()->startActivity(new Intent(this,TrainingTasksActivity.class))));body.addView(button("本地提醒设置",()->startActivity(new Intent(this,ClubActivity.class).putExtra("page","checkin"))));}
    private void refreshProgress(){writeRequest(()->{try{return api.writeObject("POST","/api/me/training-tasks/"+id+"/refresh",new JSONObject());}catch(ApiClient.ApiException e){if(e.status==429&&e.details!=null)throw new ApiClient.ApiException(429,e.getMessage()+"（"+Math.max(1,e.details.optInt("retry_after",60))+"秒后可重试）",false);throw e;}},false,response->render());}
    private void detail(){LinearLayout slot=card(body);read(()->{if(allTasks){synchronized(api){api.refreshSession();return api.adminRequest("GET","/api/admin/training-tasks/"+id,null);}}if(api.isReplay()&&lastDetail!=null)return lastDetail;return api.getObject("/api/me/training-tasks/"+id);},slot,!allTasks,value->{JSONObject t=(JSONObject)value;lastDetail=t;TrainingUi.task(this,slot,t);if(allTasks)overview(slot,t);else TrainingUi.progress(this,slot,t.optJSONObject("recipient"));String description=t.optString("description");if(!description.isEmpty())slot.addView(new ContentView(this,description,false,url->{try{startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(UpdateManifest.https(url))));}catch(Exception e){notice.show("打开链接",e);}}));JSONObject r=t.optJSONObject("refresh");if(r!=null){slot.addView(text("同步状态："+TrainingUi.label(r.optString("status")),14));if(!r.isNull("error")&&!r.optString("error").isEmpty())slot.addView(text(r.optString("error"),13));}
        if(allTasks)slot.addView(button("管理题单 / 查看成员进度",()->OptionalModules.open(this,"admin",new Intent().setClassName(this,getPackageName()+".AdminTrainingActivity").putExtra("task_id",id))));
        if(!allTasks&&"published".equals(t.optString("state"))){Button sync=button(TrainingUi.polling(t)?"正在同步，请稍候":"刷新进度",this::refreshProgress);sync.setEnabled(!TrainingUi.polling(t));slot.addView(sync);}
        slot.addView(button("查看 / 绑定 OJ 账号",()->{opening=true;startActivity(new Intent(this,OjBindingsActivity.class));}));TrainingUi.problems(this,slot,t.optJSONArray("problems"));position();
    },this::schedulePoll);}
}
