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
    protected ApiClient api;protected LinearLayout root,body,header;protected ScrollView scroll;protected TextView title;
    protected PageRefresh refresh;protected ActionNotice notice;protected volatile int serial;protected boolean writing,opening;
    protected PageReads pageReads;private boolean paused;
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
        AppAppearance.load(this);AppAppearance.window(this);api=((AcmApplication)getApplication()).api();pageReads=new PageReads(api);
        root=column();root.setFitsSystemWindows(true);root.setBackground(ProfileCover.drawable(this));AppAppearance.content(this,root);
        header=row();header.setBackgroundColor(MobileStyle.CHROME);header.setPadding(dp(10),dp(8),dp(12),dp(8));Button back=button("返回",this::onBackPressed);back.setOnClickListener(v->onBackPressed());header.addView(back);title=text(heading,21);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        refresh=new PageRefresh(this,root,1);notice=new ActionNotice(this,root,2);scroll=new ScrollView(this);root.addView(PullRefreshLayout.forPage(this,scroll,refresh,()->!writing),new LinearLayout.LayoutParams(-1,0,1));body=column();body.setPadding(dp(14),dp(16),dp(14),dp(24));scroll.addView(body);
    }
    protected void resetPage(String heading){pageReads.cancel();serial++;refresh.reset(serial);refresh.userAction();notice.hide();title.setText(heading);body.removeAllViews();}
    protected void error(LinearLayout slot,Exception failure){slot.removeAllViews();ErrorModule.style(slot);if(slot.getContentDescription()!=null)slot.addView(text(slot.getContentDescription().toString(),17));TextView message=text(FailureState.title(failure),14);message.setTextColor(ErrorModule.ink());slot.addView(message);}
    protected void read(String path,LinearLayout slot,boolean admin,Display display){
        read(()->{if(!admin)return api.get(path);api.refreshSession();return api.adminRequest("GET",path,null);},slot,!admin,display);
    }
    protected void read(Callable<Object> request,LinearLayout slot,boolean cache,Display display){
        read(request,slot,cache,display,()->{});
    }
    /** Cache replay only paints; polling may resume after an accepted live response has finished. */
    protected void read(Callable<Object> request,LinearLayout slot,boolean cache,Display display,Runnable onNetworkSuccess){
        int token=serial;long owner=api.sessionGeneration();final boolean[] loaded={false};final Object binding=new Object();slot.setTag(binding);
        java.util.function.Function<Object,Boolean> show=data->{if(token!=serial||owner!=api.sessionGeneration()||isDestroyed()||slot.getTag()!=binding)return false;slot.removeAllViews();slot.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));try{display.show(data);loaded[0]=true;AppAppearance.paintFields(slot);return true;}catch(Exception e){error(slot,e);return false;}};
        Runnable network=()->{if(token!=serial||isDestroyed()||slot.getTag()!=binding)return;refresh.start(token);pageReads.network(()->{
            Object data=null;Exception failure=null;
            try{if(owner!=api.sessionGeneration())throw new ApiClient.ApiException(401,"登录账号已切换",false);data=request.call();}catch(Exception e){failure=e;}
            Object value=data;Exception issue=failure;runOnUiThread(()->{if(token!=serial||isDestroyed())return;if(slot.getTag()!=binding){refresh.finish(token);return;}if(owner!=api.sessionGeneration()){error(slot,new ApiClient.ApiException(401,"登录账号已切换",false));refresh.finish(token);return;}
                boolean shown=false;if(issue==null)shown=show.apply(value);else{boolean retain=refresh.failure(FailureState.title(issue));if(!retain||!loaded[0])error(slot,issue);}refresh.finish(token);
                if(shown&&token==serial&&owner==api.sessionGeneration()&&!isDestroyed()&&slot.getTag()==binding)onNetworkSuccess.run();});
        });};
        refresh.register(token,network);
        if(!cache){network.run();return;}
        pageReads.preview(()->{api.beginReplay();try{Object cached=request.call();runOnUiThread(()->{if(token==serial&&owner==api.sessionGeneration()&&!isDestroyed()&&slot.getTag()==binding){refresh.cached(token);show.apply(cached);}});}catch(Exception ignored){}finally{api.endReplay();}runOnUiThread(()->{if(token==serial&&!isDestroyed())network.run();});});
    }
    protected void write(String method,String path,JSONObject payload,boolean admin,Runnable done){
        writeResult(method,path,payload,admin,value->done.run());
    }
    protected void writeResult(String method,String path,JSONObject payload,boolean admin,Display done){
        writeRequest(()->admin?api.adminRequest(method,path,payload):api.writeObject(method,path,payload),admin,done);
    }
    protected void writeRequest(Callable<Object> request,boolean admin,Display done){
        if(writing)return;writing=true;int token=serial;long owner=api.sessionGeneration();notice.hide();
        io.execute(()->{Exception failure=null;Object response=null;try(ApiClient.OwnerScope ignored=api.bind(owner)){if(owner!=api.sessionGeneration())throw new IllegalArgumentException("登录账号已切换");if(admin)api.refreshSession();if(owner!=api.sessionGeneration())throw new IllegalArgumentException("登录账号已切换");response=request.call();}catch(Exception e){failure=e;}
            Exception issue=failure;Object result=response;runOnUiThread(()->{writing=false;if(isDestroyed()||token!=serial)return;if(owner!=api.sessionGeneration()){resetPage("登录已失效");error(card(body),new ApiClient.ApiException(401,"登录账号已切换，请返回重新登录",false));return;}if(issue!=null)notice.show("操作",issue);else try{done.show(result);}catch(Exception e){notice.show("处理结果",e);}});});
    }
    protected JSONObject json(String key,Object value){try{return new JSONObject().put(key,value);}catch(Exception e){throw new IllegalArgumentException(e);}}
    @Override protected void onResume(){super.onResume();opening=false;if(refresh!=null){refresh.resume();if(paused)refresh.refreshNow();}paused=false;}
    @Override protected void onPause(){paused=true;if(refresh!=null)refresh.pause();super.onPause();}
    @Override protected void onDestroy(){serial++;io.shutdown();if(pageReads!=null)pageReads.close();if(refresh!=null)refresh.close();ModalDialogs.close(this);super.onDestroy();}
}
