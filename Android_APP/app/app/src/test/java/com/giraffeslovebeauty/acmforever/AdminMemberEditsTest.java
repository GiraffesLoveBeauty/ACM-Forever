package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class AdminMemberEditsTest {
    private JSONObject snapshot()throws Exception{return new JSONObject().put("account_epoch",3).put("profile_revision",String.join("",Collections.nCopies(64,"a"))).put("name","Old").put("cf_handle","old_handle").put("binding_versions",new JSONObject().put("codeforces",7));}
    @Test public void profileEditCarriesExactEpochAndRevision()throws Exception{JSONObject before=snapshot(),body=AdminMemberEdits.payload(before,Collections.singletonMap("name"," New "));assertEquals(3,body.getInt("expected_account_epoch"));assertEquals(before.getString("profile_revision"),body.getString("profile_revision"));assertEquals("New",body.getString("name"));assertFalse(body.has("confirm_bindings"));assertEquals("Old",before.getString("name"));}
    @Test public void changedBindingCarriesOldAccountAndVersion()throws Exception{JSONObject body=AdminMemberEdits.payload(snapshot(),Collections.singletonMap("cf_handle","new_handle"));assertTrue(body.getBoolean("confirm_bindings"));assertEquals("old_handle",body.getJSONObject("expected_bindings").getString("cf_handle"));assertEquals(7,body.getJSONObject("binding_versions").getInt("codeforces"));}
    @Test public void unbindingIsExplicitAndCaseOnlyDoesNotClearEvidence()throws Exception{JSONObject body=AdminMemberEdits.payload(snapshot(),Collections.singletonMap("cf_handle",""));assertEquals("",body.getString("cf_handle"));assertTrue(body.getBoolean("confirm_bindings"));assertThrows(IllegalArgumentException.class,()->AdminMemberEdits.payload(snapshot(),Collections.singletonMap("cf_handle","OLD_HANDLE")));}
    @Test public void rejectsMissingRevisionUnknownFieldsEmptyNameAndUrls()throws Exception{JSONObject invalid=snapshot();invalid.remove("profile_revision");assertThrows(Exception.class,()->AdminMemberEdits.payload(invalid,Collections.singletonMap("name","New")));for(Map<String,String> values:Arrays.asList(Collections.singletonMap("name"," "),Collections.singletonMap("role","root"),Collections.singletonMap("cf_handle","https://example.invalid/u"))){assertThrows(IllegalArgumentException.class,()->AdminMemberEdits.payload(snapshot(),values));}}
    @Test public void administratorCannotManagePrivilegedAccounts(){assertTrue(AdminMemberEdits.canManageAccount(false,"member"));assertFalse(AdminMemberEdits.canManageAccount(false,"admin"));assertFalse(AdminMemberEdits.canManageAccount(false,"root"));assertTrue(AdminMemberEdits.canManageAccount(true,"root"));}
    @Test public void sqliteAccountFlagsAreNumbersInProfileResponses()throws Exception{assertTrue(AdminMemberEdits.active(new JSONObject().put("is_active",1)));assertTrue(AdminMemberEdits.active(new JSONObject().put("is_active",true)));assertFalse(AdminMemberEdits.active(new JSONObject().put("is_active",0)));assertFalse(AdminMemberEdits.active(new JSONObject().put("is_active",JSONObject.NULL)));}
}
