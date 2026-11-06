package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class AccountClosureTest {
    private JSONObject preview() throws Exception {
        return new JSONObject().put("request_id", "0123456789abcdef0123456789abcdef").put("receipt_token", "0123456789abcdefghijklmnopqrstuvwxyzABCDE")
                .put("policy_version", "closure-v2").put("account_epoch", 3).put("receipt_expires_at", 200)
                .put("can_close", true).put("retention_notice", new JSONObject().put("text", "私有数据删除，公共内容保留并匿名。"));
    }
    private AccountClosure.Ticket ticket() throws Exception { return new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview()); }
    private JSONObject result(String status, long committed) throws Exception {
        return new JSONObject().put("request_id", ticket().requestId).put("policy_version", "closure-v2").put("status", status).put("committed_at", committed);
    }
    @Test public void passwordAndExactIntentAreRequired() throws Exception {
        AccountClosure.Ticket ticket = ticket(); assertThrows(IllegalArgumentException.class, () -> ticket.body("", 100));
        JSONObject body = ticket.body(" My password ", 100);
        assertEquals(4, body.length()); assertEquals(" My password ", body.getString("current_password"));
        assertEquals("注销账号", body.getString("confirm_text")); assertEquals(3, body.getLong("expected_account_epoch"));
        assertFalse(body.has("qq_id")); assertFalse(body.has("receipt_token"));
    }
    @Test public void expiryIsCheckedBeforeSubmitting() throws Exception { assertThrows(IllegalArgumentException.class, () -> ticket().body("password", 200)); }
    @Test public void blockedPreviewCannotSubmit() throws Exception {
        AccountClosure.Ticket ticket = new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview().put("can_close", false));
        assertThrows(IllegalArgumentException.class, () -> ticket.body("password", 100));
    }
    @Test public void roundTripReceiptContainsNoPassword() throws Exception {
        AccountClosure.Ticket a = ticket(); a.body("private-password", 100);
        String saved = a.saved().toString(); assertFalse(saved.contains("private-password"));
        AccountClosure.Ticket b = AccountClosure.Ticket.restore(saved);
        assertEquals(a.origin, b.origin); assertEquals(a.account, b.account); assertEquals(a.token, b.token); assertEquals(a.epoch, b.epoch);
    }
    @Test public void futurePolicyIsRejected() throws Exception { assertThrows(IllegalArgumentException.class, () -> new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview().put("policy_version", "unknown"))); }
    @Test public void unsafeIdentifiersAreRejected() throws Exception {
        assertThrows(IllegalArgumentException.class, () -> new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview().put("request_id", "../another")));
        assertThrows(IllegalArgumentException.class, () -> new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview().put("receipt_token", "line\r\nbreak")));
    }
    @Test public void mustHaveServerRetentionNotice() throws Exception { assertThrows(IllegalArgumentException.class, () -> new AccountClosure.Ticket("https://closure.test.invalid", "90000001", preview().put("retention_notice", new JSONObject()))); }
    @Test public void successNeedsMatchingReceiptAndCommit() throws Exception {
        assertTrue(ticket().closed(result("closed", 100))); assertFalse(ticket().closed(result("pending", 0)));
        assertThrows(IllegalArgumentException.class, () -> ticket().closed(result("closed", 0)));
    }
    @Test public void cannotMistakeLogoutOrOtherReceiptForSuccess() throws Exception {
        assertThrows(Exception.class, () -> ticket().closed(new JSONObject().put("authenticated", false)));
        assertThrows(IllegalArgumentException.class, () -> ticket().closed(result("closed", 100).put("request_id", "abcdef0123456789abcdef0123456789")));
        assertThrows(IllegalArgumentException.class, () -> ticket().closed(result("closed", 100).put("policy_version", "other")));
    }
    @Test public void uncertainNetworkMustQueryReceipt() throws Exception {
        assertFalse(AccountClosure.refused(new java.net.SocketTimeoutException()));
        assertFalse(AccountClosure.refused(new ApiClient.ApiException(500, "Failed", false)));
        ApiClient.ApiException password = new ApiClient.ApiException(403, "Wrong password", false);
        password.details = new JSONObject().put("code", "REAUTH_FAILED"); assertTrue(AccountClosure.refused(password));
    }
    @Test public void explicitSubmitRateLimitIsPreCommitRefusal() throws Exception {
        ApiClient.ApiException limited = new ApiClient.ApiException(429, "操作过于频繁", false);
        limited.details = new JSONObject().put("code", "RATE_LIMITED");
        assertTrue(AccountClosure.refused(limited));
    }
    @Test public void unclassifiedThrottleOrServerFailureStillNeedsReceipt() throws Exception {
        ApiClient.ApiException limited = new ApiClient.ApiException(429, "Too many requests", false);
        assertFalse(AccountClosure.refused(limited));
        limited.details = new JSONObject().put("code", "UPSTREAM_BUSY");
        assertFalse(AccountClosure.refused(limited));
        ApiClient.ApiException failed = new ApiClient.ApiException(503, "Storage unavailable", false);
        failed.details = new JSONObject().put("code", "RATE_LIMITED");
        assertFalse(AccountClosure.refused(failed));
    }
    @Test public void featureDisabledIsNotMissingOrSuccess() throws Exception {
        ApiClient.ApiException failure = new ApiClient.ApiException(404, "Closed", false);
        assertFalse(AccountClosure.disabled(failure)); failure.details = new JSONObject().put("code", "FEATURE_DISABLED");
        assertTrue(AccountClosure.disabled(failure)); assertTrue(AccountClosure.refused(failure));
    }
}
