package com.giraffeslovebeauty.acmforever;

import android.app.Application;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import java.util.concurrent.atomic.AtomicBoolean;

/** Process-local login state; neither the API callbacks nor its network check retain an Activity. */
public class AcmApplication extends Application {
    private final ApiClient api = new ApiClient();
    private final CloudDrafts drafts = new CloudDrafts(api::saveDraftBound);
    private final AtomicBoolean sessionSaveFailed = new AtomicBoolean();
    private SessionVault vault;
    private SharedPreferences preferences;
    private java.util.concurrent.CompletableFuture<Boolean> restoring;
    private PdfFiles pdfFiles;
    private AppUpdates updates;
    private AccountClosureFlow closure;
    private LoginGate loginGate;

    @Override public void onCreate() {
        super.onCreate();
        AppAppearance.load(this);
        preferences = getSharedPreferences("acmforever_settings", MODE_PRIVATE);
        vault = new SessionVault(preferences);
        loginGate = new LoginGate(this);
        registerActivityLifecycleCallbacks(loginGate);
        try {
            String base=ApiClient.checkedBaseUrl(preferences.getString("api_base_url",""));
            api.setBaseUrl(base.isEmpty()?getString(R.string.default_api_base_url):base);
        } catch(IllegalArgumentException e){
            preferences.edit().remove("api_base_url").apply();
            api.setBaseUrl(getString(R.string.default_api_base_url));
        }
        api.setNetworkAvailable(this::networkAvailable);
        api.setSessionChanged(() -> {
            loginGate.sessionChanged();
            drafts.bind(api.isLoggedIn()?api.getBaseUrl()+"/"+api.accountKey():"",api.sessionGeneration());
            if(!api.isLoggedIn())clearPdfFiles();
            try { if(api.isLoggedIn()&&!vault.save(api.getBaseUrl(),api.exportSession()))sessionSaveFailed.set(true);
                else if(!api.isLoggedIn())vault.clear();
            } catch(Exception e){sessionSaveFailed.set(true);}
        });
        api.setLoggedOut(() -> {
            TrainingReminder.disable(this);
            preferences.edit().putBoolean("auto_login", false).apply();
            vault.clear();
            vault.clearPassword();
        });
    }

    ApiClient api() { return api; }
    void closureReceiptChanged() { loginGate.receiptChanged(); }
    synchronized AccountClosureFlow closure() { if (closure == null) closure = new AccountClosureFlow(this); return closure; }
    synchronized AppUpdates updates(){if(updates==null)updates=new AppUpdates(this,api);return updates;}
    CloudDrafts drafts() { return drafts; }
    SessionVault vault() { return vault; }
    boolean consumeSessionSaveFailure() { return sessionSaveFailed.getAndSet(false); }
    synchronized PdfFiles pdfFiles(){if(pdfFiles==null)pdfFiles=new PdfFiles(getCacheDir());return pdfFiles;}
    private synchronized void clearPdfFiles(){if(pdfFiles!=null)pdfFiles.clear();}

    synchronized java.util.concurrent.CompletableFuture<Boolean> restoreSavedLogin(){
        if(restoring!=null&&!restoring.isDone())return restoring;
        restoring=java.util.concurrent.CompletableFuture.supplyAsync(()->{
            try{return LoginRecovery.restore(api,new LoginRecovery.StoredLogin(){
                public boolean automatic(){return preferences.getBoolean("auto_login",false);}
                public String session() throws Exception{return vault.read(api.getBaseUrl());}
                public String account(){return preferences.getString("remembered_account","");}
                public String password(){return vault.readPassword(api.getBaseUrl(),account());}
                public void clearSession(){vault.clear();}
                public void invalidPassword(){vault.clearPassword();}
            });}catch(Exception e){throw new java.util.concurrent.CompletionException(e);}
        });return restoring;
    }

    private boolean networkAvailable() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
}
