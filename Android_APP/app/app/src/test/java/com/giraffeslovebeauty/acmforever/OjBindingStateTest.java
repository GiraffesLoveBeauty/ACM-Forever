package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class OjBindingStateTest {
    private JSONObject summary(String account, boolean selfService) throws Exception {
        return new JSONObject().put("platform", "codeforces").put("account", account)
                .put("self_service", selfService).put("binding_status", "bound");
    }
    private OjBindingState state(JSONObject entry) throws Exception {
        return OjBindingState.fromProfile(new JSONObject().put("bindings", new JSONArray().put(entry)), "codeforces", 100);
    }
    private OjBindingState.Pending pending(long expires) throws Exception {
        return new OjBindingState.Pending(new JSONObject().put("account", "NewHandle").put("verification_id", "proof-1").put("code", "ACM-TEST").put("expires_at", expires));
    }
    @Test public void boundWithNoAcRemainsBound() throws Exception {
        JSONObject profile = new JSONObject().put("user", new JSONObject().put("cf_handle", "Known"))
                .put("platform_counts", new JSONObject()).put("total_count", 0);
        OjBindingState value = OjBindingState.fromProfile(profile, "codeforces", 100);
        assertTrue(value.bound()); assertFalse(value.available); assertFalse(value.selfService);
    }
    @Test public void missingAccountIsUnboundEvenIfOldCountsRemain() throws Exception {
        JSONObject profile = new JSONObject().put("bindings", new JSONArray().put(summary("", true)))
                .put("user", new JSONObject().put("cf_handle", "stale-handle"))
                .put("platform_counts", new JSONObject().put("codeforces", 42));
        assertFalse(OjBindingState.fromProfile(profile, "codeforces", 100).bound());
    }
    @Test public void summaryNullDoesNotBecomeLiteralNull() throws Exception {
        OjBindingState value = state(summary("", true).put("account", JSONObject.NULL));
        assertEquals("", value.account); assertFalse(value.bound());
    }
    @Test public void capabilitiesComeFromServerNotPlatformName() throws Exception {
        OjBindingState value = state(summary("", false));
        assertThrows(IllegalArgumentException.class, () -> value.verificationBody("NewHandle"));
        assertFalse(OjBindingState.known("all")); assertFalse(OjBindingState.known(null));
    }
    @Test public void firstBindingDoesNotSendAnOjOrLoginPassword() throws Exception {
        OjBindingState value = state(summary("", true));
        assertEquals("NewHandle", value.verificationBody(" NewHandle ").getString("account"));
        JSONObject payload = value.confirmationBody(pending(101), "should-not-be-sent", false, 100);
        assertFalse(payload.has("password")); assertEquals("", payload.getString("current_account"));
        assertEquals("proof-1", payload.getString("verification_id"));
    }
    @Test public void rebindRequiresPasswordAndExplicitConfirmation() throws Exception {
        OjBindingState value = state(summary("OldHandle", true));
        assertThrows(IllegalArgumentException.class, () -> value.confirmationBody(pending(101), "", true, 100));
        assertThrows(IllegalArgumentException.class, () -> value.confirmationBody(pending(101), "local-secret", false, 100));
        JSONObject payload = value.confirmationBody(pending(101), "local-secret", true, 100);
        assertEquals("OldHandle", payload.getString("current_account")); assertTrue(payload.getBoolean("confirmed"));
    }
    @Test public void staleProofAndInvalidHandlesAreRejected() throws Exception {
        OjBindingState value = state(summary("", true));
        assertThrows(IllegalArgumentException.class, () -> value.confirmationBody(pending(100), "", false, 100));
        assertThrows(IllegalArgumentException.class, () -> value.verificationBody("https://codeforces.com/profile/example"));
        assertThrows(IllegalArgumentException.class, () -> value.verificationBody("user/name"));
        assertThrows(IllegalArgumentException.class, () -> value.verificationBody(""));
    }
    @Test public void unbindWorksForBoundPlatformsWithoutSelfServiceVerification() throws Exception {
        OjBindingState value = state(summary("OldHandle", false));
        assertEquals("OldHandle", value.unbindBody("local-secret", true).getString("current_account"));
        assertThrows(IllegalArgumentException.class, () -> value.unbindBody("local-secret", false));
        assertThrows(IllegalArgumentException.class, () -> state(summary("", true)).unbindBody("secret", true));
    }
    @Test public void importedCurrentAccountMayBeVerifiedWithoutRebinding() throws Exception {
        OjBindingState value = state(summary("Current", true).put("provenance", new JSONObject().put("source", "admin_import").put("owner_verified_at", JSONObject.NULL)));
        assertTrue(value.needsOwnership); assertEquals("current", value.verificationBody("current").getString("account"));
        assertThrows(IllegalArgumentException.class, () -> state(summary("Current", true)).verificationBody("current"));
    }
    @Test public void pendingProofIsFilteredByExpiry() throws Exception {
        JSONObject entry = summary("", true).put("verification", new JSONObject().put("account", "Pending").put("verification_id", "id").put("code", "code").put("expires_at", 100));
        assertNull(state(entry).pending);
        entry.getJSONObject("verification").put("expires_at", 101);
        assertEquals("Pending", state(entry).pending.account);
    }
    @Test public void pathsCannotContainUnknownPlatformsOrActions() throws Exception {
        OjBindingState value = state(summary("", true));
        assertEquals("/api/me/bindings/codeforces/verification", value.path("verification"));
        assertThrows(IllegalArgumentException.class, () -> value.path("../admin"));
        assertThrows(IllegalArgumentException.class, () -> OjBindingState.fromProfile(new JSONObject(), "../admin", 100));
    }
}
