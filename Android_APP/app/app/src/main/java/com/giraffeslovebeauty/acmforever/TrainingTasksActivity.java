package com.giraffeslovebeauty.acmforever;

import android.content.Intent;
import android.os.*;
import android.widget.*;
import org.json.*;

/** Personal assigned training. Separate Activities retain the list underneath each detail. */
public final class TrainingTasksActivity extends MobilePageActivity {
    private String mode="list",tab="active";private int page=1;private long id;private int restoreY;private JSONObject lastDetail;
    private final Handler timer=new Handler(Looper.getMainLooper());private boolean visible,first=true;private final Runnable poll=this::render;
    @Override public void onCreate(Bundle state){super.onCreate(state);mode=getIntent().getStringExtra("mode");if(mode==null)mode="list";id=getIntent().getLongExtra("task_id",0);if(state!=null){tab=state.getString("tab","active");page=state.getInt("page",1);restoreY=state.getInt("scroll");}createPage("社团题单");render();}
    @Override protected void onSaveInstanceState(Bundle b){super.onSaveInstanceState(b);b.putString("tab",tab);b.putInt("page",page);b.putInt("scroll",scroll.getScrollY());}
    @Override protected void onResume(){super.onResume();visible=true;if(first)first=false;else render();}
    @Override protected void onPause(){visible=false;timer.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){timer.removeCallbacksAndMessages(null);super.onDestroy();}
    private void position(){final int y=Math.max(0,restoreY);scroll.post(()->scroll.scrollTo(0,y));restoreY=-1;}
    private void render(){timer.removeCallbacks(poll);if(scroll!=null&&restoreY<0)restoreY=scroll.getScrollY();resetPage(id>0?"题单详情":"schedule".equals(mode)?"我的训练安排":"社团题单");if(id>0)detail();else if("schedule".equals(mode))schedule();else list();}
    private void open(long task){opening=true;startActivity(new Intent(this,TrainingTasksActivity.class).putExtra("task_id",task));}
    private void summary(LinearLayout parent,JSONObject t){LinearLayout b=card(parent);TrainingUi.task(this,b,t);TrainingUi.progress(this,b,t.optJSONObject("recipient"));b.addView(button("打开题单",()->open(t.optLong("id"))));}
    private void list(){LinearLayout filters=card(body);String[] keys={"active","upcoming","history"},names={"进行中","未开始","历史"};for(int i=0;i<keys.length;i++){String key=keys[i];Button b=button(names[i],()->{tab=key;page=1;restoreY=0;render();});MobileStyle.button(b,tab.equals(key));filters.addView(b);}LinearLayout slot=card(body);read("/api/me/training-tasks?tab="+tab+"&page="+page+"&page_size=20",slot,false,value->{JSONObject data=(JSONObject)value;JSONArray rows=data.getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无题单",16));for(int i=0;i<rows.length();i++)summary(slot,rows.getJSONObject(i));int total=data.optInt("total");slot.addView(text("第 "+page+" 页 · 共 "+total+" 份",12));equalButtons(slot,button("上一页",()->{if(page>1){page--;restoreY=0;render();}}),button("下一页",()->{if(page*20<total){page++;restoreY=0;render();}}));position();});}
    private void schedule(){LinearLayout slot=card(body);read(()->{JSONObject data=api.getObject("/api/me/training-tasks?tab=active&page_size=1");if(data.getJSONArray("items").length()==0)data=api.getObject("/api/me/training-tasks?tab=upcoming&page_size=1");return data;},slot,false,value->{JSONArray rows=((JSONObject)value).getJSONArray("items");if(rows.length()==0)slot.addView(text("暂无训练安排",17));else summary(slot,rows.getJSONObject(0));position();});body.addView(button("查看全部题单",()->startActivity(new Intent(this,TrainingTasksActivity.class))));body.addView(button("本地提醒设置",()->startActivity(new Intent(this,ClubActivity.class).putExtra("page","checkin"))));}
    private void refreshProgress(){writeRequest(()->{try{return api.writeObject("POST","/api/me/training-tasks/"+id+"/refresh",new JSONObject());}catch(ApiClient.ApiException e){if(e.status==429&&e.details!=null)throw new ApiClient.ApiException(429,e.getMessage()+"（"+Math.max(1,e.details.optInt("retry_after",60))+"秒后可重试）",false);throw e;}},false,response->render());}
    private void detail(){LinearLayout slot=card(body);read(()->{if(api.isReplay()&&lastDetail!=null)return lastDetail;return api.getObject("/api/me/training-tasks/"+id);},slot,true,value->{JSONObject t=(JSONObject)value;lastDetail=t;TrainingUi.task(this,slot,t);TrainingUi.progress(this,slot,t.optJSONObject("recipient"));String description=t.optString("description");if(!description.isEmpty())slot.addView(new ContentView(this,description,false,url->{try{startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(UpdateManifest.https(url))));}catch(Exception e){notice.show("打开链接",e);}}));JSONObject r=t.optJSONObject("refresh");if(r!=null){slot.addView(text("同步状态："+TrainingUi.label(r.optString("status")),14));if(!r.isNull("error")&&!r.optString("error").isEmpty())slot.addView(text(r.optString("error"),13));}
        if("published".equals(t.optString("state"))){Button sync=button(TrainingUi.polling(t)?"正在同步，请稍候":"刷新进度",this::refreshProgress);sync.setEnabled(!TrainingUi.polling(t));slot.addView(sync);}
        slot.addView(button("查看 / 绑定 OJ 账号",()->{opening=true;startActivity(new Intent(this,OjBindingsActivity.class));}));TrainingUi.problems(this,slot,t.optJSONArray("problems"));position();timer.removeCallbacks(poll);if(visible&&TrainingUi.polling(t))timer.postDelayed(poll,3000);
    });}
}
