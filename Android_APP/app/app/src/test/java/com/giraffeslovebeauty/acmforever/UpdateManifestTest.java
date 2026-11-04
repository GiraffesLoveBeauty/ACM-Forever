package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class UpdateManifestTest {
    private static final String PACKAGE="com.giraffeslovebeauty.acmforever";
    private JSONObject release()throws Exception{return new JSONObject().put("packageName",PACKAGE).put("versionCode",23).put("versionName","0.2.9").put("apkUrl","https://updates.example.org/app.apk").put("sha256",new String(new char[64]).replace('\0','a')).put("sizeBytes",1000).put("minSdk",26);}
    @Test public void parsesCompatibleRelease()throws Exception{UpdateManifest p=new UpdateManifest(release(),PACKAGE);assertEquals(23,p.versionCode);assertEquals(1000,p.sizeBytes);assertEquals(26,p.minSdk);}
    @Test public void channelUsesCurrentServerWithoutCredentials(){assertEquals("https://example.org/api/mobile/v1/releases/latest?channel=debug",UpdateManifest.endpoint("https://example.org/","","debug"));}
    @Test public void explicitManifestSupportsSeparateReleaseServer(){assertEquals("https://releases.example.org/latest.json",UpdateManifest.endpoint("https://example.org","https://releases.example.org/latest.json","release"));}
    @Test public void rejectsWrongPackage()throws Exception{assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("packageName","another.app"),PACKAGE));}
    @Test public void rejectsCleartextApk()throws Exception{assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("apkUrl","http://example.org/a.apk"),PACKAGE));}
    @Test public void rejectsCredentialsAndFragments(){assertThrows(IllegalArgumentException.class,()->UpdateManifest.https("https://account:password@example.org/a"));assertThrows(IllegalArgumentException.class,()->UpdateManifest.https("https://example.org/a#part"));}
    @Test public void rejectsMissingHash()throws Exception{assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("sha256",""),PACKAGE));}
    @Test public void rejectsUnboundedDownloadAndBadVersion()throws Exception{assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("sizeBytes",UpdateManifest.MAX_APK_BYTES+1),PACKAGE));assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("versionCode",0),PACKAGE));}
    @Test public void resolvesRelativeAndCrossHostHttpsRedirects(){assertEquals("https://releases.example.org/channel/latest.json",UpdateManifest.redirected("https://releases.example.org/channel/current.json","latest.json"));assertEquals("https://cdn.example.org/update.json",UpdateManifest.redirected("https://releases.example.org/current.json","https://cdn.example.org/update.json"));}
    @Test public void rejectsUnsafeOrMissingRedirects(){for(String target:new String[]{"http://example.org/a","https://user:secret@example.org/a","https://example.org/a#part","",null})assertThrows(IllegalArgumentException.class,()->UpdateManifest.redirected("https://releases.example.org/current.json",target));}
}
