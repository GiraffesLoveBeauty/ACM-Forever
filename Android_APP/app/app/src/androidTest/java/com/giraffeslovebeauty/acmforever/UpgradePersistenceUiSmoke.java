package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.util.Arrays;

/** Only for an isolated emulator: seed an actual old APK, then verify covering without clearing data. */
final class UpgradePersistenceUiSmoke {
    private static final String ORIGIN="https://upgrade.test.invalid",ACCOUNT="90000001",PASSWORD="Synthetic-Only!";
    static void run(Instrumentation test,boolean seed){
        test.runOnMainSync(()->{});Context context=test.getTargetContext();SharedPreferences prefs=AppAppearance.prefs(context);
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        try{
            String version=context.getPackageManager().getPackageInfo(context.getPackageName(),0).versionName;
            check(version.equals(seed?"0.2.23":"0.2.24"),"expected covering version installed");
            File proof=new File(context.getFilesDir(),"v024-upgrade-proof.bin");
            if(seed){
                check(prefs.edit().putString("remembered_account",ACCOUNT).putBoolean("remember_account",true).putBoolean("auto_login",false)
                    .putBoolean("app_update_automatic",false).putString("api_base_url",ORIGIN).putInt("theme_primary",0xff4488cc)
                    .putInt("module_transparency",2).putString("search_history","[\"v024-upgrade-proof\"]").commit(),"seed settings");
                check(new SessionVault(prefs).savePassword(ORIGIN,ACCOUNT,PASSWORD),"seed encrypted password");
                check(prefs.edit().commit(),"flush asynchronous password save before covering");
                try(FileOutputStream out=new FileOutputStream(proof)){out.write(new byte[]{2,4,6,8});}
            }
            check(ACCOUNT.equals(prefs.getString("remembered_account","")),"account retained");
            check(PASSWORD.equals(new SessionVault(prefs).readPassword(ORIGIN,ACCOUNT)),"encrypted password and Keystore key retained");
            check(prefs.getInt("theme_primary",0)==0xff4488cc&&prefs.getInt("module_transparency",0)==2,"theme retained");
            check(prefs.getString("search_history","").contains("v024-upgrade-proof"),"search history retained");
            try(FileInputStream in=new FileInputStream(proof)){check(Arrays.equals(in.readAllBytes(),new byte[]{2,4,6,8}),"private file retained");}
            output.putString("stream","PASS: "+(seed?"seed024":"verify024")+"; real 0.2.23 to 0.2.24 covering retains account, encrypted password, theme, history and private files.\n");result=Activity.RESULT_OK;
        }catch(Throwable error){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));}
        test.finish(result,output);
    }
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
}
