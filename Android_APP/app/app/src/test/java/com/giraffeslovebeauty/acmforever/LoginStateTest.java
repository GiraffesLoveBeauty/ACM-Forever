package com.giraffeslovebeauty.acmforever;

import android.content.SharedPreferences;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;
import static org.junit.Assert.*;

/** Native client regressions. Fake HTTPS responses and preferences never enter the APK. */
public class LoginStateTest {
    private static int logoutStatus;
    private static int pdfStatus;
    private static byte[] pdfBody;
    private static int loginStatus,meStatus,opens,loginRequests,readStatus;
    private static java.util.function.Function<URL,String> response;
    private static FakeConnection lastConnection;
    private TestApplication application;
    private ApiClient api;

    @BeforeClass public static void installTransport() {
        URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
            @Override protected URLConnection openConnection(URL url) { return lastConnection = new FakeConnection(url); }
        } : null);
    }

    @Before public void login() throws Exception {
        logoutStatus = 200;
        loginStatus=200;meStatus=200;readStatus=200;opens=0;loginRequests=0;response=null;
        pdfStatus=200;pdfBody="%PDF-1.4\ntransport-test".getBytes(StandardCharsets.US_ASCII);
        application = new TestApplication();
        application.onCreate();
        api = application.api();
        api.setBaseUrl("https://test.invalid");
        api.setNetworkAvailable(() -> true);
        api.login("90000001", "Synthetic-Password!");
        assertTrue(api.isAdministrator());
        assertFalse(api.exportSession().isEmpty());
    }

    @Test public void manualLoginKeepsSharedClientAndNeverStoresPassword() {
        assertFalse(application.preferences.getBoolean("save_password", false));
        assertFalse(application.preferences.contains("password_cipher"));
        // Any screen in the same process receives the already authenticated client.
        assertSame(api, application.api());
        assertTrue(application.api().isLoggedIn());
    }

    @Test public void persistentServerCookieRestoresSessionWithoutPassword() throws Exception {
        String saved=api.exportSession();ApiClient restored=new ApiClient();restored.setBaseUrl(api.getBaseUrl());
        assertTrue(restored.restoreSession(saved));restored.refreshSession();assertTrue(restored.isLoggedIn());
        assertTrue(lastConnection.getRequestProperty("Cookie").contains("synthetic-session"));
        ApiClient other=new ApiClient();other.setBaseUrl("https://other.invalid");assertFalse(other.restoreSession(saved));assertFalse(other.isLoggedIn());
    }

    @Test public void offlineLogoutClearsSessionAndSavedLogin() throws Exception {
        seedSavedLogin();
        api.setNetworkAvailable(() -> false);
        try { api.logout(); fail("Expected offline failure"); }
        catch (ApiClient.NoNetworkException expected) { }
        assertLoggedOut();
    }

    @Test public void serverErrorLogoutClearsSessionAndSavedLogin() throws Exception {
        seedSavedLogin();
        logoutStatus = 500;
        try { api.logout(); fail("Expected server failure"); }
        catch (ApiClient.ApiException expected) { assertEquals(500, expected.status); }
        assertLoggedOut();
    }

    @Test public void successfulAndRepeatedLogoutClearSessionAndSavedLogin() throws Exception {
        seedSavedLogin();
        api.logout();
        assertEquals("/api/auth/logout", lastConnection.getURL().getPath());
        assertEquals("synthetic-csrf", lastConnection.getRequestProperty("X-CSRF-Token"));
        assertLoggedOut();
        api.logout();
        assertLoggedOut();
    }

    @Test public void encodingPreservesUnicodeAndSeparatesQueryFromPathSegments() {
        assertEquals("%E4%B8%AD%E6%96%87+%2B%26%2F%3F%23", UrlEncoding.form("中文 +&/?#"));
        assertEquals("/api/me/problems/luogu/a%20b%2Fc%2B", ApiClient.problemPath("luogu", "a b/c+"));
    }

    @Test public void pdfUsesAuthenticatedSameOriginWithoutRedirects() throws Exception {
        java.io.File file=java.io.File.createTempFile("acm-pdf-test-",".pdf");
        try {
            api.downloadPdf("luogu","P 1000",file);
            assertArrayEquals(pdfBody,java.nio.file.Files.readAllBytes(file.toPath()));
            assertEquals("/api/me/problems/luogu/P%201000/statement.pdf",lastConnection.getURL().getPath());
            assertEquals("application/pdf",lastConnection.getRequestProperty("Accept"));
            assertTrue(lastConnection.getRequestProperty("Cookie").contains("synthetic-session"));
            assertFalse(lastConnection.getInstanceFollowRedirects());
        } finally { file.delete(); }
    }

    @Test public void loginChoicesEnableDependenciesAndClearThemInReverse() {
        LoginOptions choices=new LoginOptions(false,false,false).change("automatic",true);
        assertTrue(choices.account&&choices.password&&choices.automatic);
        choices=choices.change("password",false);assertTrue(choices.account);assertFalse(choices.password||choices.automatic);
        choices=choices.change("password",true).change("account",false);assertFalse(choices.account||choices.password||choices.automatic);
    }

    @Test public void startupPreservesOptedInEncryptedPasswordEntries() {
        seedSavedLogin();application.onCreate();assertTrue(application.preferences.contains("password_cipher"));
        assertTrue(application.preferences.getBoolean("save_password",false));
    }

    private ApiClient fresh(){ApiClient client=new ApiClient();client.setBaseUrl("https://test.invalid");client.setNetworkAvailable(()->true);return client;}
    private static final class Stored implements LoginRecovery.StoredLogin {
        boolean enabled=true,invalid;String saved="",secret="Synthetic-Password!";
        public boolean automatic(){return enabled;}public String session(){return saved;}public String account(){return "90000001";}
        public String password(){return secret;}public void clearSession(){saved="";}public void invalidPassword(){invalid=true;enabled=false;secret="";}
    }
    @Test public void automaticRecoveryHonorsOptOutAndPrefersExistingSession() throws Exception {
        Stored stored=new Stored();stored.saved=api.exportSession();stored.enabled=false;ApiClient cold=fresh();int before=opens;
        assertFalse(LoginRecovery.restore(cold,stored));assertEquals(before,opens);
        stored.enabled=true;loginRequests=0;assertTrue(LoginRecovery.restore(cold,stored));assertEquals(0,loginRequests);
        stored.enabled=false;assertTrue(LoginRecovery.restore(cold,stored));assertTrue(cold.isLoggedIn());
    }
    @Test public void expiredSessionFallsBackToSavedPasswordOnceAndBadPasswordDisablesAutomatic() throws Exception {
        Stored stored=new Stored();stored.saved=api.exportSession();meStatus=401;loginRequests=0;
        assertTrue(LoginRecovery.restore(fresh(),stored));assertEquals(1,loginRequests);
        stored=new Stored();loginStatus=401;try{LoginRecovery.restore(fresh(),stored);fail("Bad password");}catch(ApiClient.ApiException expected){assertEquals(401,expected.status);}
        assertTrue(stored.invalid);assertFalse(stored.enabled);assertEquals("",stored.secret);
    }
    @Test public void serverFailureDoesNotReplayPasswordOrEraseIt() throws Exception {
        Stored stored=new Stored();stored.saved=api.exportSession();meStatus=500;loginRequests=0;
        try{LoginRecovery.restore(fresh(),stored);fail("Server error");}catch(ApiClient.ApiException expected){assertEquals(500,expected.status);}
        assertEquals(0,loginRequests);assertTrue(stored.enabled);assertFalse(stored.secret.isEmpty());
    }
    @Test public void cachedReadsAreImmediateImmutableAndInvalidatedByLogout() throws Exception {
        response=url->"{\"value\":1}";assertEquals(1,api.getObject("/api/test-cache").getInt("value"));int before=opens;
        api.beginReplay();try{org.json.JSONObject first=api.getObject("/api/test-cache");first.put("value",99);assertEquals(1,api.getObject("/api/test-cache").getInt("value"));assertTrue(api.replayReady());}finally{api.endReplay();}
        assertEquals(before,opens);api.logout();api.beginReplay();try{api.getObject("/api/test-cache");fail("Stale private response");}catch(ApiClient.CacheMissException expected){}finally{api.endReplay();}
    }
    @Test public void responseCacheEvictsWithinBudgetAndRemovesAffectedDrafts() throws Exception {
        ResponseCache cache=new ResponseCache(35);cache.put("/api/forum/drafts",new org.json.JSONObject().put("value","one"));cache.put("other",new org.json.JSONObject().put("value","two"));
        cache.removeContaining("/api/forum/drafts");assertNull(cache.get("/api/forum/drafts"));assertNotNull(cache.get("other"));
        cache.put("large",new org.json.JSONObject().put("value","0123456789012345678901234567890123456789"));assertNull(cache.get("large"));
    }
    @Test public void missingSectionReplaysAlongsideCachedDataAndRecoversWhenApiAppears() throws Exception {
        response=url->"{\"value\":7}";api.getObject("/api/test-good");readStatus=404;
        try{api.getObject("/api/test-missing");fail("Expected missing API");}catch(ApiClient.ApiException expected){assertEquals(404,expected.status);}
        int before=opens;api.beginReplay();try{
            assertEquals(7,api.getObject("/api/test-good").getInt("value"));
            try{api.getObject("/api/test-missing");fail("Expected cached missing API");}catch(ApiClient.ApiException expected){assertEquals(404,expected.status);}
            assertTrue(api.replayReady());
        }finally{api.endReplay();}
        assertEquals(before,opens);readStatus=200;api.getObject("/api/test-missing");
        api.beginReplay();try{assertEquals(7,api.getObject("/api/test-missing").getInt("value"));assertTrue(api.replayReady());}finally{api.endReplay();}
        api.logout();api.beginReplay();try{api.getObject("/api/test-missing");fail("Failure and data caches must clear on logout");}catch(ApiClient.CacheMissException expected){}finally{api.endReplay();}
    }
    @Test public void zeroAcFallbackRecalculatesTotalsAndPageAfterFiltering() throws Exception {
        response=url->{try{org.json.JSONArray rows=new org.json.JSONArray();for(int i=0;i<32;i++)rows.put(new org.json.JSONObject().put("name","test-"+i).put("total_count",i%2==0?0:100-i));return new org.json.JSONObject().put("rows",rows).put("total",32).put("page",2).toString();}catch(Exception e){throw new RuntimeException(e);}};
        org.json.JSONObject result=api.leaderboard("7","total_count","atcoder","",2,10);
        assertEquals(16,result.getInt("total"));assertEquals(2,result.getInt("page"));assertEquals(6,result.getJSONArray("rows").length());
        for(int i=0;i<result.getJSONArray("rows").length();i++)assertTrue(result.getJSONArray("rows").getJSONObject(i).getInt("total_count")>0);
        assertTrue(lastConnection.getURL().getQuery().contains("positive_only=1"));
    }

    @Test public void pdfRejectsHtmlAndDistinguishesMissingApiFromExpiredSession() throws Exception {
        java.io.File file=java.io.File.createTempFile("acm-pdf-test-",".pdf");
        try {
            pdfBody="<html>login</html>".getBytes(StandardCharsets.UTF_8);
            try{api.downloadPdf("luogu","P1000",file);fail("HTML is not a PDF");}
            catch(java.io.IOException expected){assertTrue(expected.getMessage().contains("PDF"));}
            pdfStatus=404;pdfBody="{}".getBytes(StandardCharsets.UTF_8);
            try{api.downloadPdf("luogu","P1000",file);fail("Missing API");}
            catch(ApiClient.ApiException expected){assertEquals(404,expected.status);assertFalse(expected.missingContent);}
            assertTrue(api.isLoggedIn());pdfStatus=401;
            try{api.downloadPdf("luogu","P1000",file);fail("Expired session");}
            catch(ApiClient.ApiException expected){assertEquals(401,expected.status);}
            assertFalse(api.isLoggedIn());
        } finally { file.delete(); }
    }

    private void seedSavedLogin() {
        application.preferences.edit().putBoolean("auto_login", true).putBoolean("save_password", true)
                .putString("session_cipher", "test-only-cipher").putString("session_iv", "test-only-iv")
                .putString("password_cipher", "test-only-cipher").putString("password_iv", "test-only-iv").apply();
    }

    private void assertLoggedOut() throws Exception {
        assertFalse(api.isLoggedIn());
        assertFalse(api.isAdministrator());
        assertFalse(api.requiresPasswordChange());
        assertEquals("", api.exportSession());
        assertFalse(application.preferences.getBoolean("auto_login", true));
        assertFalse(application.preferences.getBoolean("save_password", true));
        for (String key : new String[]{"session_cipher", "session_iv", "password_cipher", "password_iv"})
            assertFalse(key, application.preferences.contains(key));
        api.setNetworkAvailable(() -> true);
        api.getObject("/api/test-probe");
        String cookie = lastConnection.getRequestProperty("Cookie");
        assertTrue(cookie == null || !cookie.contains("synthetic-session"));
        assertNull(lastConnection.getRequestProperty("X-CSRF-Token"));
    }

    private static final class TestApplication extends AcmApplication {
        final MemoryPreferences preferences = new MemoryPreferences();
        @Override public SharedPreferences getSharedPreferences(String name, int mode) { return preferences; }
    }

    private static final class FakeConnection extends HttpURLConnection {
        private final int code;
        FakeConnection(URL url) { super(url);opens++;if(url.getPath().endsWith("/login"))loginRequests++;code=url.getPath().endsWith("/me")?meStatus:url.getPath().endsWith("/login")?loginStatus:url.getPath().endsWith("statement.pdf")?pdfStatus:url.getPath().endsWith("/logout")?logoutStatus:readStatus;if(url.getPath().endsWith("/me"))meStatus=200; }
        @Override public void connect() { }
        @Override public void disconnect() { }
        @Override public boolean usingProxy() { return false; }
        @Override public int getResponseCode() { return code; }
        @Override public OutputStream getOutputStream() { return new ByteArrayOutputStream(); }
        @Override public InputStream getInputStream() { return body(); }
        @Override public InputStream getErrorStream() { return body(); }
        @Override public Map<String, List<String>> getHeaderFields() {
            return url.getPath().endsWith("/login") ? Collections.singletonMap("Set-Cookie", Collections.singletonList(
                    "session=synthetic-session; Path=/; Max-Age=3600; Secure; HttpOnly")) : Collections.emptyMap();
        }
        private InputStream body() {
            if(url.getPath().endsWith("statement.pdf"))return new ByteArrayInputStream(pdfBody);
            if(response!=null)return new ByteArrayInputStream(response.apply(url).getBytes(StandardCharsets.UTF_8));
            String value = url.getPath().endsWith("/me")
                    ? "{\"authenticated\":true,\"csrf_token\":\"synthetic-csrf\",\"role\":\"admin\"}" : "{}";
            return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
        }
    }

    private static final class MemoryPreferences implements SharedPreferences {
        private final Map<String, Object> values = new HashMap<>();
        @Override public Map<String, ?> getAll() { return new HashMap<>(values); }
        @Override public String getString(String key, String fallback) { return (String) values.getOrDefault(key, fallback); }
        @SuppressWarnings("unchecked") @Override public Set<String> getStringSet(String key, Set<String> fallback) { return (Set<String>) values.getOrDefault(key, fallback); }
        @Override public int getInt(String key, int fallback) { return (int) values.getOrDefault(key, fallback); }
        @Override public long getLong(String key, long fallback) { return (long) values.getOrDefault(key, fallback); }
        @Override public float getFloat(String key, float fallback) { return (float) values.getOrDefault(key, fallback); }
        @Override public boolean getBoolean(String key, boolean fallback) { return (boolean) values.getOrDefault(key, fallback); }
        @Override public boolean contains(String key) { return values.containsKey(key); }
        @Override public void registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener listener) { }
        @Override public void unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener listener) { }
        @Override public Editor edit() {
            return new Editor() {
                final Map<String, Object> changes = new HashMap<>();
                final Set<String> removals = new HashSet<>();
                boolean clear;
                private Editor put(String key, Object value) { changes.put(key, value); return this; }
                @Override public Editor putString(String key, String value) { return put(key, value); }
                @Override public Editor putStringSet(String key, Set<String> value) { return put(key, value); }
                @Override public Editor putInt(String key, int value) { return put(key, value); }
                @Override public Editor putLong(String key, long value) { return put(key, value); }
                @Override public Editor putFloat(String key, float value) { return put(key, value); }
                @Override public Editor putBoolean(String key, boolean value) { return put(key, value); }
                @Override public Editor remove(String key) { removals.add(key); return this; }
                @Override public Editor clear() { clear = true; return this; }
                @Override public boolean commit() { apply(); return true; }
                @Override public void apply() {
                    if (clear) values.clear();
                    for (String key : removals) values.remove(key);
                    values.putAll(changes);
                }
            };
        }
    }
}
