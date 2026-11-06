package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.Intent;
import android.os.*;
import android.view.View;
import java.lang.ref.WeakReference;

/** UI access boundary. Backend authorization remains mandatory for every API. */
final class LoginGate implements Application.ActivityLifecycleCallbacks {
    private final AcmApplication app;
    private final Handler main = new Handler(Looper.getMainLooper());
    private WeakReference<Activity> foreground = new WeakReference<>(null);
    LoginGate(AcmApplication app) { this.app = app; }
    static boolean permits(boolean loggedIn, boolean loginHost, boolean closureRecovery, boolean hasReceipt) {
        return loggedIn || loginHost || closureRecovery && hasReceipt;
    }
    void sessionChanged() {
        main.post(() -> {
            Activity current = foreground.get();
            if (current == null || current.isFinishing() || current.isDestroyed()) return;
            if (current instanceof MainActivity) ((MainActivity) current).enforceLogin();
            else check(current);
        });
    }
    void receiptChanged() {
        main.post(() -> {
            Activity current = foreground.get();
            if (current instanceof MainActivity) ((MainActivity) current).enforceLogin();
        });
    }
    private void check(Activity activity) {
        if (activity instanceof MainActivity) { ((MainActivity) activity).enforceLogin(); return; }
        boolean recovery = activity instanceof AccountClosureActivity;
        if (permits(app.api().isLoggedIn(), false, recovery, app.vault().hasClosure())) return;
        if (activity.isFinishing() || activity.isDestroyed()) return;
        ModalDialogs.close(activity);
        activity.getWindow().getDecorView().setVisibility(View.INVISIBLE);
        activity.startActivity(new Intent(activity, MainActivity.class)
                .putExtra("force_login", true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
        activity.finish();
    }
    @Override public void onActivityStarted(Activity activity) { check(activity); }
    @Override public void onActivityResumed(Activity activity) { foreground = new WeakReference<>(activity); check(activity); }
    @Override public void onActivityPaused(Activity activity) { if (foreground.get() == activity) foreground.clear(); }
    @Override public void onActivityCreated(Activity activity, Bundle state) {}
    @Override public void onActivityStopped(Activity activity) {}
    @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
    @Override public void onActivityDestroyed(Activity activity) { if (foreground.get() == activity) foreground.clear(); }
}
