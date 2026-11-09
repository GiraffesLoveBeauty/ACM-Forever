package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.*;

/** Only these four entries use opt-in delivery; all calls are initiated by the user. */
final class OptionalModules {
    private static final ExecutorService io=Executors.newSingleThreadExecutor();
    private static final Set<Activity> pending=Collections.newSetFromMap(new WeakHashMap<>());
    static boolean allowed(Context c,String id){ApiClient api=((AcmApplication)c.getApplicationContext()).api();return api.isLoggedIn()&&(!"admin".equals(id)||api.isAdministrator());}
    static Intent target(Context c,String id){String cls="advanced".equals(id)?"AdvancedAppearanceActivity":"admin".equals(id)?"AdminQuickActivity":"AppearanceActivity";Intent intent=new Intent().setClassName(c,c.getPackageName()+"."+cls);if("official-themes".equals(id))intent.putExtra("page","library");return intent;}
    static void open(Activity activity,String id,Intent target){
        open(activity,id,target,null);
    }
    /** Notify the owner only after an Activity actually starts, never for consent/cancellation. */
    static void open(Activity activity,String id,Intent target,Runnable started){
        if(!ModuleSpec.IDS.contains(id)||!allowed(activity,id)||activity.isFinishing()||activity.isDestroyed()||ModalDialogs.isShowing(activity)||pending.contains(activity))return;
        if(ModuleStore.available(activity,id)){if(target!=null)start(activity,target,started);return;}
        if(ModuleStore.archive(activity,id).isFile()){download(activity,id,target,started);return;}
        pending.add(activity);long owner=((AcmApplication)activity.getApplication()).api().sessionGeneration();Context app=activity.getApplicationContext();
        io.execute(()->{ModuleSpec spec=null;Exception failure=null;try{spec=ModuleNetwork.catalog(app).get(id);}catch(Exception e){failure=e;}ModuleSpec selected=spec;Exception error=failure;
            activity.runOnUiThread(()->{pending.remove(activity);if(activity.isFinishing()||activity.isDestroyed()||!allowed(activity,id)||owner!=((AcmApplication)activity.getApplication()).api().sessionGeneration()||ModalDialogs.isShowing(activity))return;
                if(error!=null){failure(activity,error);return;}
                LinearLayout body=new SpacedLayout(activity);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(dp(activity,8),dp(activity,8),dp(activity,8),dp(activity,8));
                TextView question=new TextView(activity);question.setText(selected.confirmation());question.setTextSize(16);question.setTextColor(MobileStyle.TEXT);question.setPadding(0,0,0,dp(activity,18));body.addView(question);
                LinearLayout actions=new SpacedLayout(activity);Button yes=new Button(activity),no=new Button(activity);yes.setText("下载喵");no.setText("点错了喵");MobileStyle.button(yes,true);MobileStyle.button(no,false);yes.setCompoundDrawables(null,null,null,null);no.setCompoundDrawables(null,null,null,null);
                actions.addView(yes,new LinearLayout.LayoutParams(0,dp(activity,56),1));actions.addView(no,new LinearLayout.LayoutParams(0,dp(activity,56),1));body.addView(actions);
                AlertDialog dialog=new ModalDialogs.Builder(activity).setTitle(ModuleSpec.name(id)).setView(body).create();no.setOnClickListener(v->dialog.dismiss());yes.setOnClickListener(v->{if(!dialog.isShowing())return;dialog.dismiss();if(allowed(activity,id))download(activity,id,target,started);});ModalDialogs.show(dialog);
            });
        });
    }
    static void download(Activity activity,String id,Intent next){download(activity,id,next,null);}
    private static void download(Activity activity,String id,Intent next,Runnable started){Intent intent=new Intent(activity,ModuleDownloadActivity.class).putExtra("module_id",id);if(next!=null)intent.putExtra("next",next);start(activity,intent,started);}
    private static void start(Activity activity,Intent intent,Runnable started){
        if(activity.isFinishing()||activity.isDestroyed())return;
        try{activity.startActivity(intent);}catch(RuntimeException error){failure(activity,error);return;}
        if(started!=null)started.run();
    }
    static void failure(Activity activity,Exception error){LinearLayout panel=new SpacedLayout(activity);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(activity,16),dp(activity,16),dp(activity,16),dp(activity,16));ErrorModule.style(panel);TextView text=new TextView(activity);text.setText("模块下载失败："+error.getMessage());text.setTextColor(ErrorModule.ink());text.setTextSize(15);panel.addView(text);new ModalDialogs.Builder(activity).setTitle("连接失败").setView(panel).setPositiveButton("知道了",null).show();}
    private static int dp(Context c,int n){return MobileStyle.dp(c,n);}
}
