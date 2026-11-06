package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.os.Build;
import android.view.*;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;

/** A custom AlertDialog must explicitly allow its nested editors to use the IME. */
final class KeyboardInputs {
    private KeyboardInputs() {}
    static boolean hasEditor(View view) {
        if (view instanceof EditText) return true;
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup) view).getChildCount(); i++)
            if (hasEditor(((ViewGroup) view).getChildAt(i))) return true;
        return false;
    }
    static void allow(Window window) {
        if (window == null || !hasEditor(window.getDecorView())) return;
        window.clearFlags(WindowManager.LayoutParams.FLAG_ALT_FOCUSABLE_IM | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE);
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }
    static void show(Activity activity, EditText field) {
        if (field == null || !field.isAttachedToWindow() || !field.hasWindowFocus()) return;
        field.setShowSoftInputOnFocus(true); field.requestFocus();
        if (Build.VERSION.SDK_INT >= 30 && field.getWindowInsetsController() != null)
            field.getWindowInsetsController().show(WindowInsets.Type.ime());
        InputMethodManager ime = (InputMethodManager) activity.getSystemService(Activity.INPUT_METHOD_SERVICE);
        if (ime != null) ime.showSoftInput(field, InputMethodManager.SHOW_IMPLICIT);
    }
}
