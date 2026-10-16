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
        application = new TestApplication();
        application.onCreate();
        api = application.api();
        api.setBaseUrl("https://test.invalid");
        api.setNetworkAvailable(() -> true);
        api.login("90000001", "Synthetic-Password!");
        assertTrue(api.isAdministrator());
        assertFalse(api.exportSession().isEmpty());
    }

    @Test public void manualLoginKeepsMemorySessionWithoutPersistingCredentials() {
        assertFalse(application.preferences.getBoolean("auto_login", false));
        assertFalse(application.preferences.contains("session_cipher"));
        assertFalse(application.preferences.contains("session_iv"));
        // Any screen in the same process receives the already authenticated client.
        assertSame(api, application.api());
        assertTrue(application.api().isLoggedIn());
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
        FakeConnection(URL url) { super(url); }
        @Override public void connect() { }
        @Override public void disconnect() { }
        @Override public boolean usingProxy() { return false; }
        @Override public int getResponseCode() { return url.getPath().endsWith("/logout") ? logoutStatus : 200; }
        @Override public OutputStream getOutputStream() { return new ByteArrayOutputStream(); }
        @Override public InputStream getInputStream() { return body(); }
        @Override public InputStream getErrorStream() { return body(); }
        @Override public Map<String, List<String>> getHeaderFields() {
            return url.getPath().endsWith("/login") ? Collections.singletonMap("Set-Cookie", Collections.singletonList(
                    "session=synthetic-session; Path=/; Max-Age=3600; Secure; HttpOnly")) : Collections.emptyMap();
        }
        private InputStream body() {
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
