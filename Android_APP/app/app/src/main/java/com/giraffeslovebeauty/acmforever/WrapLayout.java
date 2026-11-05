package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** Content-sized tools wrap within the page; no horizontal scrolling or clipped labels. */
final class WrapLayout extends ViewGroup {
    private final int gap;
    WrapLayout(Context context){super(context);gap=MobileStyle.dp(context,8);}
    @Override protected void onMeasure(int widthSpec,int heightSpec){
        int limit=MeasureSpec.getMode(widthSpec)==MeasureSpec.UNSPECIFIED?Integer.MAX_VALUE:MeasureSpec.getSize(widthSpec);
        int available=Math.max(0,limit-getPaddingLeft()-getPaddingRight());
        int x=0,y=0,rowHeight=0,used=0;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            LayoutParams params=child.getLayoutParams();int desired=params.width>=0?Math.min(params.width,available):params.width;
            child.measure(getChildMeasureSpec(MeasureSpec.makeMeasureSpec(available,MeasureSpec.AT_MOST),0,desired),getChildMeasureSpec(heightSpec,getPaddingTop()+getPaddingBottom(),params.height));
            int w=child.getMeasuredWidth(),h=child.getMeasuredHeight();
            if(x>0&&x+gap+w>available){used=Math.max(used,x);y+=rowHeight+gap;x=0;rowHeight=0;}
            if(x>0)x+=gap;x+=w;rowHeight=Math.max(rowHeight,h);
        }
        used=Math.max(used,x);
        setMeasuredDimension(resolveSize(used+getPaddingLeft()+getPaddingRight(),widthSpec),resolveSize(y+rowHeight+getPaddingTop()+getPaddingBottom(),heightSpec));
    }
    @Override protected void onLayout(boolean changed,int left,int top,int right,int bottom){
        int available=right-left-getPaddingLeft()-getPaddingRight(),x=0,y=getPaddingTop(),rowHeight=0;
        boolean rtl=getLayoutDirection()==LAYOUT_DIRECTION_RTL;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;int w=child.getMeasuredWidth(),h=child.getMeasuredHeight();
            if(x>0&&x+gap+w>available){y+=rowHeight+gap;x=0;rowHeight=0;}
            if(x>0)x+=gap;int start=rtl?right-left-getPaddingRight()-x-w:getPaddingLeft()+x;
            child.layout(start,y,start+w,y+h);x+=w;rowHeight=Math.max(rowHeight,h);
        }
    }
    @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(LayoutParams.WRAP_CONTENT,LayoutParams.WRAP_CONTENT);}
}
