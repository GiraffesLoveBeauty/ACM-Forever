package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

/** One visible dialog per Activity. A repeated dialog keeps its current inputs. */
final class ModalDialogs {
    private static final WeakHashMap<Context, WeakReference<AlertDialog>> visible = new WeakHashMap<>();
    private static final WeakHashMap<AlertDialog, String> keys = new WeakHashMap<>();
    static boolean isShowing(Context owner) {
        WeakReference<AlertDialog> entry=visible.get(owner);
        AlertDialog dialog=entry==null?null:entry.get();return dialog!=null&&dialog.isShowing();
    }
    static AlertDialog show(AlertDialog dialog) {
        Context owner=dialog.getOwnerActivity();
        if(owner==null)owner=dialog.getContext();
        if(owner instanceof Activity && (((Activity)owner).isFinishing()||((Activity)owner).isDestroyed()))return dialog;
        WeakReference<AlertDialog> entry=visible.get(owner);
        AlertDialog previous=entry==null?null:entry.get();
        if(previous!=null&&previous.isShowing()){
            if(previous==dialog||keys.getOrDefault(previous,"").equals(keys.getOrDefault(dialog,"")))return previous;
            previous.dismiss();
        }
        visible.put(owner,new WeakReference<>(dialog));dialog.show();return dialog;
    }
    static void close(Context owner){WeakReference<AlertDialog> entry=visible.remove(owner);AlertDialog dialog=entry==null?null:entry.get();if(dialog!=null)dialog.dismiss();}
    static final class Builder extends AlertDialog.Builder {
        private final Context owner;
        private String key="dialog";
        Builder(Context context){super(context);owner=context;}
        @Override public Builder setTitle(CharSequence value){key="title:"+value;super.setTitle(value);return this;}
        @Override public Builder setMessage(CharSequence value){if(!key.startsWith("title:"))key="message:"+value;super.setMessage(value);return this;}
        @Override public AlertDialog create(){AlertDialog dialog=super.create();if(owner instanceof Activity)dialog.setOwnerActivity((Activity)owner);keys.put(dialog,key);return dialog;}
        @Override public AlertDialog show(){return ModalDialogs.show(create());}
    }
}
