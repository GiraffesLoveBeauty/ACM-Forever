package com.giraffeslovebeauty.acmforever;

import org.json.*;

/** Captured when an account is displayed, never refreshed silently at confirmation time. */
final class AdminAccountSnapshot {
    static JSONObject bind(JSONObject snapshot,JSONObject operation)throws JSONException{
        if(!(snapshot.opt("account_epoch") instanceof Number)||!(snapshot.opt("credential_version") instanceof Number))throw new IllegalArgumentException("账号快照不完整，请刷新后重选");
        return new JSONObject(operation.toString()).put("expected_account_epoch",snapshot.getLong("account_epoch")).put("expected_credential_version",snapshot.getLong("credential_version"));
    }
}
