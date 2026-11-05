package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.*;

/** Write failures are dismissible and never register an automatic POST retry. */
final class ActionNotice {
    private final LinearLayout banner;
    private final TextView text;
    ActionNotice(Context context,LinearLayout root,int index){
        banner=new LinearLayout(context);banner.setGravity(Gravity.CENTER_VERTICAL);
        banner.setPadding(MobileStyle.dp(context,16),MobileStyle.dp(context,6),MobileStyle.dp(context,4),MobileStyle.dp(context,6));
        ErrorModule.style(banner);
        text=new TextView(context);text.setTextColor(ErrorModule.ink());text.setTextSize(13);
        text.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        banner.addView(text,new LinearLayout.LayoutParams(0,-2,1));
        ImageButton close=new ImageButton(context);MobileStyle.flat(close);close.setBackgroundColor(Color.TRANSPARENT);
        close.setPadding(12,12,12,12);close.setImageDrawable(AppIcons.get(context,"close",ErrorModule.ink()));
        close.setContentDescription("关闭操作失败提示");close.setOnClickListener(v->hide());
        banner.addView(close,new LinearLayout.LayoutParams(MobileStyle.dp(context,48),MobileStyle.dp(context,48)));
        LinearLayout.LayoutParams bounds=new LinearLayout.LayoutParams(-1,-2);bounds.setMargins(MobileStyle.dp(context,12),MobileStyle.dp(context,16),MobileStyle.dp(context,12),MobileStyle.dp(context,8));root.addView(banner,index,bounds);hide();
    }
    void show(String operation,Exception error){
        text.setText(operation+"失败："+(error instanceof IllegalArgumentException?error.getMessage():FailureState.title(error))+"。请检查后手动操作；本次未自动重发。");
        banner.setVisibility(View.VISIBLE);
    }
    void hide(){banner.setVisibility(View.GONE);}
}
