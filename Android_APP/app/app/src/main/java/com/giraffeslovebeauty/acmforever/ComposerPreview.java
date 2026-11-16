package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.text.*;
import android.view.*;
import android.widget.*;
import java.util.function.Consumer;

/** Inline sanitized Markdown preview; switching layout never replaces the editor or its cursor. */
final class ComposerPreview extends LinearLayout {
    private final EditText editor;
    private final LinearLayout panel,article;
    private final Button toggle;
    private final Consumer<String> openLink;
    private boolean opened,right;
    private final Runnable update=this::render;
    ComposerPreview(Context c,EditText editor,Consumer<String> openLink,boolean opened,boolean right) {
        super(c);this.editor=editor;this.openLink=openLink;this.opened=opened;this.right=right;
        setContentDescription("正文编辑与预览");setBaselineAligned(false);
        addView(editor);panel=new LinearLayout(c);panel.setOrientation(VERTICAL);
        panel.setContentDescription("正文预览区域");panel.setPadding(dp(8),dp(8),dp(8),dp(8));
        panel.setBackground(MobileStyle.panel(c,MobileStyle.MODULE,12,1));
        LinearLayout head=new LinearLayout(c);head.setGravity(Gravity.CENTER_VERTICAL);
        ImageButton close=new ImageButton(c);close.setImageDrawable(AppIcons.get(c,"close",MobileStyle.TEXT));
        close.setBackgroundColor(android.graphics.Color.TRANSPARENT);close.setPadding(dp(12),dp(12),dp(12),dp(12));close.setContentDescription("关闭正文预览");
        close.setOnClickListener(v->{this.opened=false;layoutMode();});head.addView(close,new LayoutParams(dp(48),dp(48)));
        Space space=new Space(c);head.addView(space,new LayoutParams(0,1,1));
        toggle=new Button(c);MobileStyle.button(toggle,false);toggle.setTextSize(12);toggle.setMinWidth(0);
        toggle.setOnClickListener(v->{this.right=!this.right;layoutMode();});head.addView(toggle,new LayoutParams(dp(56),dp(48)));
        panel.addView(head);article=new LinearLayout(c);article.setOrientation(VERTICAL);panel.addView(article,new LayoutParams(-1,-2));addView(panel);
        editor.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){removeCallbacks(update);if(ComposerPreview.this.opened)postDelayed(update,300);}public void afterTextChanged(Editable e){}});
        layoutMode();
    }
    boolean opened(){return opened;}
    boolean right(){return right;}
    void open(){opened=true;layoutMode();}
    private int dp(int n){return MobileStyle.dp(getContext(),n);}
    private void layoutMode(){
        removeCallbacks(update);setOrientation(opened&&right?HORIZONTAL:VERTICAL);
        LayoutParams edit=new LayoutParams(opened&&right?0:-1,-2,opened&&right?1:0);editor.setLayoutParams(edit);
        LayoutParams preview=new LayoutParams(right?0:-1,-2,right?1:0);if(right)preview.leftMargin=dp(8);else preview.topMargin=dp(12);panel.setLayoutParams(preview);
        panel.setVisibility(opened?VISIBLE:GONE);toggle.setText(right?"下方":"右侧");toggle.setContentDescription(right?"预览切换到下方":"预览切换到右侧");
        article.removeAllViews();if(opened)post(update);
    }
    private void render(){removeCallbacks(update);if(!opened||!isAttachedToWindow())return;article.removeAllViews();article.addView(new ContentView(getContext(),editor.getText().toString(),false,openLink),new LayoutParams(-1,-2));}
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();if(opened)post(update);}
    @Override protected void onDetachedFromWindow(){removeCallbacks(update);super.onDetachedFromWindow();}
}
