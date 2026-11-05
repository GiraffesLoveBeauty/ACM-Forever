package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;

/** Give adjacent controls visible breathing room, including dynamically added ones. */
class SpacedLayout extends LinearLayout {
    SpacedLayout(Context context){super(context);}
    @Override protected void onMeasure(int width,int height){
        View previous=null;
        for(int i=0;i<getChildCount();i++){
            View current=getChildAt(i);if(current.getVisibility()==GONE)continue;
            if(previous!=null&&(control(previous)||control(current))&&current.getLayoutParams() instanceof LayoutParams){
                LayoutParams params=(LayoutParams)current.getLayoutParams();int gap=MobileStyle.dp(getContext(),8);
                if(getOrientation()==HORIZONTAL){params.setMarginStart(Math.max(gap,params.getMarginStart()));params.resolveLayoutDirection(getLayoutDirection());}
                else params.topMargin=Math.max(gap,params.topMargin);
            }
            previous=current;
        }
        super.onMeasure(width,height);
    }
    private boolean control(View view){return view instanceof Button||view instanceof Spinner||view instanceof WrapLayout;}
}
