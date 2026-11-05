package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import java.util.concurrent.*;
import org.json.JSONObject;

/** Shared lifecycle and presentation for native utility pages. Writes are never retried. */
abstract class MobilePageActivity extends Activity {
    interface Display {void show(Object value)throws Exception;}
    protected ApiClient api;protected LinearLayout root,body;protected ScrollView scroll;protected TextView title;
    protected PageRefresh refresh;protected ActionNotice notice;protected int serial;protected boolean writing,opening;
    protected final ExecutorService io=Executors.newSingleThreadExecutor();
    protected int dp(float n){return MobileStyle.dp(this,n);}
    protected LinearLayout column(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.VERTICAL);return b;}
    protected LinearLayout row(){LinearLayout b=new SpacedLayout(this);b.setGravity(Gravity.CENTER_VERTICAL);return b;}
    protected TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(size<14?MobileStyle.MUTED:MobileStyle.TEXT);t.setPadding(0,dp(5),0,dp(5));if(size>=17)t.setTypeface(null,android.graphics.Typeface.BOLD);return t;}
    protected Button button(String name,Runnable work){Button b=new Button(this);b.setText(name);MobileStyle.button(b,false);b.setOnClickListener(v->{if(!writing&&!opening&&!ModalDialogs.isShowing(this))work.run();});return b;}
    protected LinearLayout card(LinearLayout parent){LinearLayout b=column();b.setPadding(dp(14),dp(14),dp(14),dp(14));b.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(14);parent.addView(b,p);return b;}
    protected EditText input(LinearLayout parent,String hint,String value){EditText e=new EditText(this);e.setHint(hint);e.setText(value);e.setSingleLine(true);e.setContentDescription(hint);parent.addView(e,new LinearLayout.LayoutParams(-1,dp(52)));return e;}
    protected void equalButtons(LinearLayout parent,Button a,Button b){LinearLayout r=row();r.addView(a,new LinearLayout.LayoutParams(0,dp(48),1));r.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));parent.addView(r);}
    protected void createPage(String heading){
        AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();
        root=column();root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        LinearLayout header=row();header.setBackgroundColor(MobileStyle.CHROME);header.setPadding(dp(10),dp(8),dp(12),dp(8));header.addView(button("返回",this::onBackPressed));title=text(heading,21);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        refresh=new PageRefresh(this,root,1);notice=new ActionNotice(this,root,2);scroll=new ScrollView(this);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));body=column();body.setPadding(dp(14),dp(16),dp(14),dp(24));scroll.addView(body);
    }
    protected void resetPage(String heading){serial++;refresh.reset(serial);refresh.userAction();notice.hide();title.setText(heading);body.removeAllViews();}
    protected void error(LinearLayout slot,Exception failure){slot.removeAllViews();ErrorModule.style(slot);if(slot.getContentDescription()!=null)slot.addView(text(slot.getContentDescription().toString(),17));TextView message=text(FailureState.title(failure),14);message.setTextColor(ErrorModule.ink());slot.addView(message);}
    protected void read(String path,LinearLayout slot,boolean admin,Display display){
        read(()->admin?api.adminRequest("GET",path,null):api.get(path),slot,!admin,display);
    }
    protected void read(Callable<Object> request,LinearLayout slot,boolean cache,Display display){
        int token=serial;long owner=api.sessionGeneration();final boolean[] loaded={false};final Object binding=new Object();slot.setTag(binding);
        java.util.function.Consumer<Object> show=data->{if(token!=serial||owner!=api.sessionGeneration()||isDestroyed()||slot.getTag()!=binding)return;slot.removeAllViews();slot.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));try{display.show(data);loaded[0]=true;AppAppearance.paintFields(slot);}catch(Exception e){error(slot,e);}};
        Runnable network=()->{if(token!=serial||isDestroyed()||slot.getTag()!=binding)return;refresh.start(token);io.execute(()->{
            Object data=null;Exception failure=null;
            try{if(owner!=api.sessionGeneration())throw new ApiClient.ApiException(401,"登录账号已切换",false);data=request.call();}catch(Exception e){failure=e;}
            Object value=data;Exception issue=failure;runOnUiThread(()->{if(token!=serial||isDestroyed())return;if(slot.getTag()!=binding){refresh.finish(token);return;}if(owner!=api.sessionGeneration()){error(slot,new ApiClient.ApiException(401,"登录账号已切换",false));refresh.finish(token);return;}
                if(issue==null)show.accept(value);else{boolean retain=refresh.failure(FailureState.title(issue));if(!retain||!loaded[0])error(slot,issue);}refresh.finish(token);});
        });};
        refresh.register(token,network);
        if(!cache){network.run();return;}
        io.execute(()->{api.beginReplay();try{Object cached=request.call();runOnUiThread(()->{if(token==serial&&owner==api.sessionGeneration()&&!isDestroyed()&&slot.getTag()==binding){refresh.cached(token);show.accept(cached);}});}catch(Exception ignored){}finally{api.endReplay();}runOnUiThread(()->{if(token==serial&&!isDestroyed())network.run();});});
    }
    protected void write(String method,String path,JSONObject payload,boolean admin,Runnable done){
        if(writing)return;writing=true;int token=serial;long owner=api.sessionGeneration();notice.hide();
        io.execute(()->{Exception failure=null;try{synchronized(api){if(owner!=api.sessionGeneration())throw new IllegalArgumentException("登录账号已切换");if(admin)api.refreshSession();if(owner!=api.sessionGeneration())throw new IllegalArgumentException("登录账号已切换");if(admin)api.adminRequest(method,path,payload);else api.writeObject(method,path,payload);}}catch(Exception e){failure=e;}
            Exception issue=failure;runOnUiThread(()->{writing=false;if(isDestroyed()||token!=serial)return;if(owner!=api.sessionGeneration()){resetPage("登录已失效");error(card(body),new ApiClient.ApiException(401,"登录账号已切换，请返回重新登录",false));return;}if(issue!=null)notice.show("操作",issue);else done.run();});});
    }
    protected JSONObject json(String key,Object value){try{return new JSONObject().put(key,value);}catch(Exception e){throw new IllegalArgumentException(e);}}
    @Override protected void onResume(){super.onResume();opening=false;}
    @Override protected void onDestroy(){serial++;io.shutdownNow();if(refresh!=null)refresh.close();ModalDialogs.close(this);super.onDestroy();}
}
