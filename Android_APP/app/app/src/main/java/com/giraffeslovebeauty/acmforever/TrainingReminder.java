package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.Build;
import org.json.JSONArray;

/** Opt-in, inexact local alarms. Never polls a server or claims a task is completed. */
public final class TrainingReminder extends BroadcastReceiver {
    private static android.content.SharedPreferences prefs(Context c){return c.getSharedPreferences("acmforever_settings",Context.MODE_PRIVATE);}
    private static PendingIntent alarm(Context c,int id,boolean daily){Intent intent=new Intent(c,TrainingReminder.class).setAction("acm.training.reminder").putExtra("id",id).putExtra("daily",daily).putExtra("generation",prefs(c).getInt("reminder_generation",0));return PendingIntent.getBroadcast(c,id,intent,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    public static void disable(Context c){android.content.SharedPreferences p=prefs(c);p.edit().putBoolean("training_reminder",false).putInt("reminder_generation",p.getInt("reminder_generation",0)+1).remove("cached_review_reminders").apply();AlarmManager am=(AlarmManager)c.getSystemService(Context.ALARM_SERVICE);if(am==null)return;am.cancel(alarm(c,3900,true));for(int i=0;i<64;i++)am.cancel(alarm(c,4000+i,false));}
    static boolean notificationsAllowed(Context c){NotificationManager manager=(NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);NotificationChannel channel=manager.getNotificationChannel("training");return manager.areNotificationsEnabled()&&(Build.VERSION.SDK_INT<33||c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)==android.content.pm.PackageManager.PERMISSION_GRANTED)&&(channel==null||channel.getImportance()!=NotificationManager.IMPORTANCE_NONE);}
    static void scheduleDaily(Context c){if(!prefs(c).getBoolean("training_reminder",false))return;java.util.Calendar at=java.util.Calendar.getInstance();at.set(java.util.Calendar.HOUR_OF_DAY,prefs(c).getInt("reminder_hour",20));at.set(java.util.Calendar.MINUTE,prefs(c).getInt("reminder_minute",0));at.set(java.util.Calendar.SECOND,0);at.set(java.util.Calendar.MILLISECOND,0);if(at.getTimeInMillis()<=System.currentTimeMillis())at.add(java.util.Calendar.DATE,1);((AlarmManager)c.getSystemService(Context.ALARM_SERVICE)).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,at.getTimeInMillis(),alarm(c,3900,true));}
    static void scheduleReviews(Context c,JSONArray reviews){
        if(!prefs(c).getBoolean("training_reminder",false))return;
        prefs(c).edit().putString("cached_review_reminders",reviews.toString()).apply();
        AlarmManager am=(AlarmManager)c.getSystemService(Context.ALARM_SERVICE);for(int i=0;i<64;i++)am.cancel(alarm(c,4000+i,false));
        int index=0;long now=System.currentTimeMillis();for(int i=0;i<reviews.length()&&index<64;i++){org.json.JSONObject row=reviews.optJSONObject(i);if(row==null)continue;long due=row.optLong("due_at")*1000;if(due<=now)continue;am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,due,alarm(c,4000+index++,false));}
    }
    @Override public void onReceive(Context c,Intent intent){
        if(!prefs(c).getBoolean("training_reminder",false))return;
        if(Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())){scheduleDaily(c);try{scheduleReviews(c,new JSONArray(prefs(c).getString("cached_review_reminders","[]")));}catch(Exception ignored){}return;}
        if(intent.getIntExtra("generation",-1)!=prefs(c).getInt("reminder_generation",0))return;
        boolean daily=intent.getBooleanExtra("daily",false);if(daily)scheduleDaily(c);
        NotificationManager manager=(NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel("training","训练与补题提醒",NotificationManager.IMPORTANCE_DEFAULT));
        if(!manager.areNotificationsEnabled()||Build.VERSION.SDK_INT>=33&&c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED)return;
        Intent open=new Intent(c,MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP).putExtra("club_page",daily?"checkin":"reviews");PendingIntent click=PendingIntent.getActivity(c,daily?3900:4000,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification notice=new Notification.Builder(c,"training").setSmallIcon(R.drawable.ic_cat_notification).setContentTitle("ACMforever 训练提醒").setContentText(daily?"查看今日训练、到期补题及打卡目标。":"已缓存的复习计划到期，请打开 App 核对最新计划。").setContentIntent(click).setAutoCancel(true).build();
        manager.notify(intent.getIntExtra("id",3900),notice);
    }
}
