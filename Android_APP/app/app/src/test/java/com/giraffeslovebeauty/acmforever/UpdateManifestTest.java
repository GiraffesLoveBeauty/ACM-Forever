package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class UpdateManifestTest {
    private static final String PACKAGE="com.giraffeslovebeauty.acmforever";
    private JSONObject release()throws Exception{return new JSONObject().put("packageName",PACKAGE).put("versionCode",23).put("versionName","0.2.9").put("apkUrl","https://updates.example.org/app.apk").put("sha256",new String(new char[64]).replace('\0','a')).put("sizeBytes",1000).put("minSdk",26);}
    @Test public void parsesCompatibleRelease()throws Exception{UpdateManifest p=new UpdateManifest(release(),PACKAGE);assertEquals(23,p.versionCode);assertEquals(1000,p.sizeBytes);assertEquals(26,p.minSdk);}
    @Test public void rejectsAnotherChannelBeforeDownload()throws Exception{UpdateManifest p=new UpdateManifest(release().put("channel","release"),PACKAGE);p.requireChannel("release");p.requireChannel("debug");assertThrows(IllegalArgumentException.class,()->p.requireChannel("preview"));assertThrows(IllegalArgumentException.class,()->new UpdateManifest(release().put("channel","other"),PACKAGE));}
    @Test public void acceptsOlderManifestsWithoutChannel()throws Exception{UpdateManifest p=new UpdateManifest(release(),PACKAGE);p.requireChannel("debug");p.requireChannel("release");}
    @Test public void administratorManifestIsBoundToCurrentServerAndPackage()throws Exception{
        JSONObject value=release().put("distribution","preview").put("releaseVersionCode",24).put("previewRevision",1).put("previewTag","v0.2.9-preview.1").put("apkPath","/api/admin/android/releases/v0.2.9-preview.1/apk");value.remove("apkUrl");
        UpdateManifest parsed=UpdateManifest.administrator(value,"https://example.org");parsed.requireChannel("preview");
        assertEquals("https://example.org/api/admin/android/releases/v0.2.9-preview.1/apk",parsed.apkUrl);
        assertThrows(IllegalArgumentException.class,()->parsed.requireChannel("release"));
        value.put("apkPath","//evil.example/a");assertThrows(IllegalArgumentException.class,()->UpdateManifest.administrator(value,"https://example.org"));
    }
    @Test public void sameCodeSwitchingIsExplicitAndPreviewRevisionIsIndependent()throws Exception{
        UpdateManifest stable=new UpdateManifest(release(),PACKAGE);
        assertFalse(stable.installable(23,false,0,23,false));
        assertTrue(stable.installable(23,true,1,24,false));
        assertFalse(stable.installable(24,true,1,25,false));
        JSONObject value=release().put("distribution","preview").put("releaseVersionCode",24).put("previewRevision",2).put("previewTag","v0.2.9-preview.2");
        UpdateManifest preview=new UpdateManifest(value,PACKAGE);
        assertTrue(preview.installable(23,false,0,23,true));
        assertTrue(preview.installable(23,true,1,24,true));
        assertFalse(preview.installable(23,true,2,24,true));
        assertFalse(preview.installable(24,false,0,24,true));
        assertFalse(preview.installable(23,false,0,23,false));
    }
    @Test public void formalManifestHasLegacyMigrationCompatibility()throws Exception{
        JSONObject value=release().put("distribution","release").put("schemaVersion",2);UpdateManifest parsed=new UpdateManifest(value,PACKAGE);
        parsed.requireChannel("release");assertEquals("",parsed.channel);
        String legacy=value.optString("channel","");assertFalse(!legacy.isEmpty()&&!legacy.equals("debug"));
        assertThrows(IllegalArgumentException.class,()->new UpdateManifest(value,PACKAGE+".admin"));
    }
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
