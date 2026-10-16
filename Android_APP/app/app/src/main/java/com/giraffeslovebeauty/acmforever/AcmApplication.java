package com.giraffeslovebeauty.acmforever;

import android.app.Application;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import java.util.concurrent.atomic.AtomicBoolean;

/** Process-local login state; neither the API callbacks nor its network check retain an Activity. */
public class AcmApplication extends Application {
    private final ApiClient api = new ApiClient();
    private final AtomicBoolean sessionSaveFailed = new AtomicBoolean();
    private SessionVault vault;
    private SharedPreferences preferences;

    @Override public void onCreate() {
        super.onCreate();
        preferences = getSharedPreferences("acmforever_settings", MODE_PRIVATE);
        vault = new SessionVault(preferences);
        api.setNetworkAvailable(this::networkAvailable);
        api.setSessionChanged(() -> {
            try { if (!vault.save(api.getBaseUrl(), api.exportSession())) sessionSaveFailed.set(true); }
            catch (Exception e) { vault.clear(); sessionSaveFailed.set(true); }
        });
        api.setLoggedOut(() -> {
            preferences.edit().putBoolean("auto_login", false).apply();
            vault.clear();
            vault.clearPassword();
        });
    }

    ApiClient api() { return api; }
    SessionVault vault() { return vault; }
    boolean consumeSessionSaveFailure() { return sessionSaveFailed.getAndSet(false); }

    private boolean networkAvailable() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
}
