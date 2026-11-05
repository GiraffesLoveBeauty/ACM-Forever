package com.giraffeslovebeauty.acmforever;

/** Cold-start recovery. Network/server errors never trigger a second password request. */
final class LoginRecovery {
    interface StoredLogin {
        boolean automatic();
        String session() throws Exception;
        String account();
        String password();
        void clearSession();
        void invalidPassword();
    }
    static boolean restore(ApiClient api,StoredLogin stored) throws Exception {
        synchronized(api){
            // A recreated Activity shares this client even when automatic login is disabled.
            if(api.isLoggedIn())return true;
            if(!stored.automatic())return false;
            String session="";
            try{session=stored.session();}catch(Exception ignored){stored.clearSession();}
            if(!session.isEmpty()){
                try{
                    if(api.restoreSession(session)){api.refreshSession();return true;}
                    stored.clearSession();
                }catch(Exception e){
                    if(api.isLoggedIn())return true; // A valid session can require an initial password change.
                    if(!(e instanceof ApiClient.ApiException)||((ApiClient.ApiException)e).status!=401)throw e;
                }
            }
            String account=stored.account(),password=stored.password();
            if(!stored.automatic()||account.isEmpty()||password.isEmpty())return false;
            try{api.login(account,password);return true;}
            catch(Exception e){
                if(e instanceof ApiClient.ApiException&&((ApiClient.ApiException)e).status==401)stored.invalidPassword();
                throw e;
            }
        }
    }
}
