package com.giraffeslovebeauty.acmforever;

import android.content.SharedPreferences;

/** Dependencies apply only to the user's persistence choices, never the active in-memory session. */
final class LoginOptions {
    final boolean account, password, automatic;
    LoginOptions(boolean account, boolean password, boolean automatic) {
        this.automatic=automatic;
        this.password=password||automatic;
        this.account=account||this.password;
    }
    static LoginOptions read(SharedPreferences prefs) {
        return new LoginOptions(prefs.getBoolean("remember_account",false),prefs.getBoolean("save_password",false),prefs.getBoolean("auto_login",false));
    }
    LoginOptions change(String name,boolean checked) {
        switch(name){
            case "account":return checked?new LoginOptions(true,password,automatic):new LoginOptions(false,false,false);
            case "password":return checked?new LoginOptions(true,true,automatic):new LoginOptions(account,false,false);
            case "automatic":return new LoginOptions(account,password,checked);
            default:throw new IllegalArgumentException("Unknown login option");
        }
    }
    void save(SharedPreferences prefs,String identifier) {
        prefs.edit().putBoolean("remember_account",account).putBoolean("save_password",password).putBoolean("auto_login",automatic)
                .putString("remembered_account",account?identifier:"").apply();
    }
}
