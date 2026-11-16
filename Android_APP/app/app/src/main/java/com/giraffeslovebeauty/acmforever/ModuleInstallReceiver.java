package com.giraffeslovebeauty.acmforever;
import android.content.*;
import android.content.pm.PackageInstaller;

/** Explicit, private PendingIntent callback; session ownership is persisted before commit. */
public final class ModuleInstallReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){int session=intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID,-1);SharedPreferences receipts=context.getSharedPreferences("module_installs",0);String id=receipts.getString("session_"+session,"");boolean removal=id.startsWith("remove:")&&ModuleSpec.nativeModule(id.substring(7));boolean preview=id.startsWith("preview-app-update:");if(!removal&&!ModuleSpec.nativeModule(id)&&!"app-update".equals(id)&&!preview)return;
        int status=intent.getIntExtra(PackageInstaller.EXTRA_STATUS,PackageInstaller.STATUS_FAILURE);Intent confirmation=intent.getParcelableExtra(Intent.EXTRA_INTENT);
        if(status!=PackageInstaller.STATUS_PENDING_USER_ACTION)receipts.edit().remove("session_"+session).apply();
        if("app-update".equals(id)||preview){
            AcmApplication app=(AcmApplication)context.getApplicationContext();AppUpdates updates=preview?app.adminUpdates():app.updates();
            if(!updates.ownsInstallReceipt(id)){receipts.edit().remove("session_"+session).apply();return;}
            updates.installerResult(id,status,intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE),confirmation);return;
        }
        if(removal){ModuleDownloads.get(context).removalResult(id.substring(7),status,intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE),confirmation);return;}
        ModuleDownloads.get(context).installerResult(id,status,intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE),confirmation);
    }
}
