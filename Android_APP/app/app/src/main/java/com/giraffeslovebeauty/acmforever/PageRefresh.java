package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import java.util.ArrayList;

/** Page-scoped serial read retries. Closing a warning never stops reconnection. */
final class PageRefresh {
    static final int DELAY_MS=10000;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final LinearLayout banner;
    private final TextView title;
    private final ImageButton close;
    private final ArrayList<Runnable> reads=new ArrayList<>();
    private int generation,pending;
    private boolean failed,cached,started,dismissed,everFailed,retryQueued,closed,userAction;
    PageRefresh(Context context,LinearLayout root,int index){
        banner=new LinearLayout(context);banner.setGravity(Gravity.CENTER_VERTICAL);banner.setPadding(MobileStyle.dp(context,14),0,MobileStyle.dp(context,4),0);
        title=new TextView(context);title.setTextSize(14);title.setTypeface(null,android.graphics.Typeface.BOLD);banner.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        close=new ImageButton(context);MobileStyle.flat(close);close.setPadding(12,12,12,12);close.setBackgroundColor(Color.TRANSPARENT);banner.addView(close,new LinearLayout.LayoutParams(MobileStyle.dp(context,48),MobileStyle.dp(context,48)));
        close.setOnClickListener(v->{dismissed=true;banner.setVisibility(View.GONE);});LinearLayout.LayoutParams bounds=new LinearLayout.LayoutParams(-1,-2);bounds.setMargins(MobileStyle.dp(context,12),MobileStyle.dp(context,16),MobileStyle.dp(context,12),MobileStyle.dp(context,8));root.addView(banner,index,bounds);banner.setVisibility(View.GONE);
    }
    void reset(int generation){this.generation=generation;userAction=false;pending=0;failed=false;cached=false;started=false;dismissed=false;everFailed=false;retryQueued=false;closed=false;reads.clear();handler.removeCallbacksAndMessages(null);banner.setVisibility(View.GONE);}
    void userAction(){userAction=true;}
    void register(int generation,Runnable read){if(!closed&&this.generation==generation)reads.add(read);}
    void start(int generation){
        if(closed||this.generation!=generation)return;pending++;if(started)return;started=true;
        handler.postDelayed(()->{if(!closed&&this.generation==generation&&(pending>0||failed)){everFailed=true;if(!dismissed)show(false);}},DELAY_MS);
    }
    void cached(int generation){if(this.generation==generation)cached=true;}
    boolean failure(String reason){if(!isConnectionFailure(reason))return false;failed=true;everFailed=true;if(userAction&&!cached&&!dismissed)show(false);return cached;}
    void actionFailure(String reason){if(!isConnectionFailure(reason))return;failed=true;everFailed=true;dismissed=false;show(false);if(pending==0)queueRetry(generation);}
    void finish(int generation){
        if(closed||this.generation!=generation)return;pending=Math.max(0,pending-1);if(pending!=0)return;
        if(failed){queueRetry(generation);return;}
        handler.removeCallbacksAndMessages(null);retryQueued=false;
        if(everFailed){show(true);everFailed=false;handler.postDelayed(()->banner.setVisibility(View.GONE),3000);}else banner.setVisibility(View.GONE);
    }
    private void queueRetry(int revision){
        if(retryQueued||reads.isEmpty())return;retryQueued=true;
        handler.postDelayed(()->{retryQueued=false;if(closed||generation!=revision||pending!=0)return;failed=false;started=false;for(Runnable read:new ArrayList<>(reads))read.run();},DELAY_MS);
    }
    private void show(boolean success){title.setText(success?"重连成功":"API连接失败");int color=success?ThemePalette.readable(new int[]{MobileStyle.PANEL,MobileStyle.BACKGROUND},0xff285b32,4.5):ErrorModule.ink();title.setTextColor(color);close.setImageDrawable(AppIcons.get(banner.getContext(),"close",color));banner.setBackground(ErrorModule.background(banner.getContext(),success));close.setContentDescription(success?"关闭重连成功提示":"关闭API连接失败提示");banner.setVisibility(View.VISIBLE);}
    void close(){closed=true;reads.clear();handler.removeCallbacksAndMessages(null);}
    static boolean isConnectionFailure(String reason){return java.util.Arrays.asList("无网络","请求超时","安全连接失败","无法连接服务器","服务器异常").contains(reason);}
}
