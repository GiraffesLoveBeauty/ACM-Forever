package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.view.ViewGroup;
import android.widget.*;

/** The same ordinary eye everywhere. Neither the secret nor its visibility enters view state. */
final class PasswordFields {
    private PasswordFields() {}
    static void attach(EditText input) {
        if (!(input.getParent() instanceof ViewGroup)) throw new IllegalArgumentException("密码框尚未加入表单");
        ViewGroup parent=(ViewGroup)input.getParent(); int index=parent.indexOfChild(input);
        ViewGroup.LayoutParams bounds=input.getLayoutParams(); Context c=input.getContext();
        input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        input.setSingleLine(true);input.setSaveEnabled(false);input.setSaveFromParentEnabled(false);
        input.setTransformationMethod(PasswordTransformationMethod.getInstance());
        ImageButton eye=new ImageButton(c); eye.setBackgroundColor(android.graphics.Color.TRANSPARENT);
        eye.setPadding(MobileStyle.dp(c,12),MobileStyle.dp(c,12),MobileStyle.dp(c,12),MobileStyle.dp(c,12));
        Runnable hide=()->{input.setTransformationMethod(PasswordTransformationMethod.getInstance());eye.setImageDrawable(AppIcons.get(c,"eye",MobileStyle.MUTED));eye.setContentDescription("显示密码");};
        LinearLayout row=new LinearLayout(c){@Override protected void onDetachedFromWindow(){hide.run();super.onDetachedFromWindow();}};
        row.setGravity(android.view.Gravity.CENTER_VERTICAL);row.setSaveFromParentEnabled(false);
        parent.removeViewAt(index); row.addView(input,new LinearLayout.LayoutParams(0,MobileStyle.dp(c,52),1));
        row.addView(eye,new LinearLayout.LayoutParams(MobileStyle.dp(c,48),MobileStyle.dp(c,48)));
        parent.addView(row,index,bounds);hide.run();
        eye.setOnClickListener(v->{if(!input.isEnabled())return;int start=input.getSelectionStart(),end=input.getSelectionEnd();
            boolean visible=input.getTransformationMethod() instanceof PasswordTransformationMethod;
            input.setTransformationMethod(visible?null:PasswordTransformationMethod.getInstance());
            if(start>=0&&end>=0)input.setSelection(Math.min(start,input.length()),Math.min(end,input.length()));
            eye.setImageDrawable(AppIcons.get(c,visible?"eye-off":"eye",MobileStyle.MUTED));eye.setContentDescription(visible?"隐藏密码":"显示密码");
        });
    }
}
