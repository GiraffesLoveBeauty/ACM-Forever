package com.giraffeslovebeauty.acmforever;

import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Device-bound encrypted, opt-in login persistence; credentials are bound to origin and account. */
final class SessionVault {
    private static final String ALIAS = "acmforever.session.v1";
    private final SharedPreferences prefs;
    SessionVault(SharedPreferences prefs) { this.prefs = prefs; }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }
    synchronized void clear() { prefs.edit().remove("session_cipher").remove("session_iv").apply(); }
    synchronized void clearPassword() {
        prefs.edit().remove("password_cipher").remove("password_iv").remove("password_origin").remove("password_account")
                .putBoolean("save_password", false).putBoolean("auto_login",false).apply();
        clear();
    }
    synchronized boolean savePassword(String origin, String account, String password) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
            cipher.updateAAD(("password\n" + origin + "\n" + account).getBytes(StandardCharsets.UTF_8));
            prefs.edit().putString("password_cipher", Base64.encodeToString(cipher.doFinal(password.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP))
                    .putString("password_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                    .putString("password_origin",origin).putString("password_account",account).putBoolean("save_password", true).apply();
            return true;
        } catch (Exception e) { clearPassword(); return false; }
    }
    synchronized String readPassword(String origin, String account) {
        if (!prefs.getBoolean("save_password", false) || account.isEmpty()) return "";
        if(!origin.equals(prefs.getString("password_origin",""))||!account.equals(prefs.getString("password_account","")))return "";
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(prefs.getString("password_iv", ""), Base64.NO_WRAP)));
            cipher.updateAAD(("password\n" + origin + "\n" + account).getBytes(StandardCharsets.UTF_8));
            return new String(cipher.doFinal(Base64.decode(prefs.getString("password_cipher", ""), Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) { clearPassword(); return ""; }
    }
    synchronized boolean save(String origin, String value) {
        if (!prefs.getBoolean("auto_login",false)||value.isEmpty()) { clear(); return true; }
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
            cipher.updateAAD(origin.getBytes(StandardCharsets.UTF_8));
            prefs.edit().putString("session_cipher", Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP))
                    .putString("session_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).apply();
            return true;
        } catch (Exception e) { clear(); prefs.edit().putBoolean("auto_login", false).apply(); return false; }
    }
    synchronized String read(String origin) throws Exception {
        if(!prefs.getBoolean("auto_login",false))return "";
        String data = prefs.getString("session_cipher", "");
        if (data.isEmpty()) return "";
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(prefs.getString("session_iv", ""), Base64.NO_WRAP)));
            cipher.updateAAD(origin.getBytes(StandardCharsets.UTF_8));
            return new String(cipher.doFinal(Base64.decode(data, Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) { clear(); throw e; }
    }
}
