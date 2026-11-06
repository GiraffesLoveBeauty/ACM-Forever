package com.giraffeslovebeauty.acmforever;

import android.animation.*;
import android.app.Activity;
import android.graphics.*;
import android.graphics.drawable.Drawable;
import android.view.*;
import android.view.animation.DecelerateInterpolator;
import java.util.Arrays;
import java.util.WeakHashMap;

/** Matches internal subpages to Activity open/close animations; tabs stay immediate. */
final class PageMotion {
    private static final WeakHashMap<View, Animator> running = new WeakHashMap<>();
    private PageMotion() {}
    static boolean parallel(String from, String to) {
        return Arrays.asList("forum", "rank", "compose", "problems", "mine").contains(from)
                && Arrays.asList("forum", "rank", "compose", "problems", "mine").contains(to);
    }
    static void change(Activity activity, boolean entering, Runnable change) {
        ViewGroup stage = activity.findViewById(android.R.id.content);
        Animator previous = running.remove(stage);
        if (previous != null) previous.cancel();
        if (stage == null || !stage.isAttachedToWindow() || stage.getWidth() == 0 || stage.getHeight() == 0
                || !ValueAnimator.areAnimatorsEnabled()) { change.run(); return; }
        Bitmap bitmap;
        try { bitmap = Bitmap.createBitmap(stage.getWidth(), stage.getHeight(), Bitmap.Config.ARGB_8888); }
        catch (OutOfMemoryError e) { change.run(); return; }
        try { stage.draw(new Canvas(bitmap)); change.run(); }
        catch (RuntimeException | Error failure) { bitmap.recycle(); throw failure; }
        View current = stage.getChildAt(0);
        if (current == null) { bitmap.recycle(); return; }
        final class Snapshot extends Drawable {
            float progress;
            final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
            @Override public void draw(Canvas canvas) {
                int save = canvas.save();
                if (entering) canvas.clipRect(0, 0, bitmap.getWidth() * (1 - progress), bitmap.getHeight());
                else canvas.translate(bitmap.getWidth() * progress, 0);
                canvas.drawBitmap(bitmap, 0, 0, paint); canvas.restoreToCount(save);
            }
            @Override public void setAlpha(int value) { paint.setAlpha(value); }
            @Override public void setColorFilter(ColorFilter value) { paint.setColorFilter(value); }
            @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
        }
        Snapshot snapshot = new Snapshot(); snapshot.setBounds(0, 0, bitmap.getWidth(), bitmap.getHeight());
        stage.getOverlay().add(snapshot);
        if (entering) current.setTranslationX(bitmap.getWidth());
        ValueAnimator animation = ValueAnimator.ofFloat(0, 1);
        animation.setDuration(240); animation.setInterpolator(new DecelerateInterpolator());
        animation.addUpdateListener(value -> { snapshot.progress = (float) value.getAnimatedValue();
            if (entering) current.setTranslationX(bitmap.getWidth() * (1 - snapshot.progress));
            snapshot.invalidateSelf(); });
        animation.addListener(new AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(Animator value) {
                current.setTranslationX(0); stage.getOverlay().remove(snapshot); running.remove(stage); bitmap.recycle();
            }
        });
        running.put(stage, animation); animation.start();
    }
}
