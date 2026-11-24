package com.giraffeslovebeauty.acmforever;

import android.os.Bundle;
import android.widget.LinearLayout;

/** Feature installation is not an authorization credential. Revalidate on every foreground entry. */
public abstract class AdminPageActivity extends MobilePageActivity {
    private long owner;private boolean first=true;
    @Override public void onCreate(Bundle state){super.onCreate(state);createPage("便捷管理");owner=api.sessionGeneration();}
    @Override protected void onResume(){super.onResume();if(first)first=false;verifyAccess();}
    private void verifyAccess(){ModalDialogs.close(this);if(writing)return;resetPage("正在确认管理权限…");LinearLayout slot=card(body);read(()->{api.refreshSession();if(owner!=api.sessionGeneration()||!api.isAdministrator()||api.requiresPasswordChange()){runOnUiThread(this::onAccessLost);throw new ApiClient.ApiException(403,"管理权限已失效",false);}return true;},slot,false,result->renderAdmin());}
    protected final boolean access(){return owner==api.sessionGeneration()&&api.isAdministrator()&&!api.requiresPasswordChange();}
    protected void onAccessLost(){}
    protected abstract void renderAdmin();
}
