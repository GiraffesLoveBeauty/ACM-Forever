package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import java.io.*;
import java.util.*;
import static org.junit.Assert.*;

public class UpdateSourcesTest {
    private static final String PACKAGE="com.giraffeslovebeauty.acmforever",VERSION="0.2.27";
    private JSONObject manifest(boolean gitee,int code)throws Exception{
        return new JSONObject().put("packageName",PACKAGE).put("versionName",VERSION).put("versionCode",code).put("channel","debug")
            .put("apkUrl",UpdateSources.asset(VERSION,"acmforever-0.2.27-debug.apk",gitee)).put("sha256","a".repeat(64))
            .put("modulesUrl",UpdateSources.asset(VERSION,"modules.json",gitee));
    }
    private final class Reader implements UpdateSources.Reader {
        final List<String> calls=new ArrayList<>();final Map<String,Object> values=new HashMap<>();
        Reader()throws Exception{values.put(UpdateSources.GITEE_LATEST,new JSONObject().put("tag_name","v"+VERSION).put("prerelease",false));values.put(UpdateSources.asset(VERSION,"update.json",true),manifest(true,41));values.put(UpdateSources.GITHUB_LATEST,manifest(false,41));}
        public JSONObject read(String address,int limit)throws Exception{calls.add(address);Object value=values.get(address);if(value instanceof Exception)throw (Exception)value;if(!(value instanceof JSONObject))throw new IOException("missing");assertTrue(limit==32768||limit==65536);return (JSONObject)value;}
        UpdateSources.Checked check(long code)throws Exception{return UpdateSources.check(UpdateSources.GITEE_LATEST,PACKAGE,"debug",code,this);}
    }
    @Test public void giteeFirstUsesPublishedTagAndAvoidsGithubWhenNewer()throws Exception{Reader r=new Reader();assertEquals(UpdateSources.GITEE_LATEST,r.check(40).endpoint);assertEquals(Arrays.asList(UpdateSources.GITEE_LATEST,UpdateSources.asset(VERSION,"update.json",true)),r.calls);}
    @Test public void metadataOutageAndHtmlAndInvalidManifestFallBack()throws Exception{
        for(String key:Arrays.asList(UpdateSources.GITEE_LATEST,UpdateSources.asset(VERSION,"update.json",true))){Reader r=new Reader();r.values.put(key,new IOException("404/timeout/HTML"));assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);}
        Reader r=new Reader();r.values.put(UpdateSources.asset(VERSION,"update.json",true),manifest(true,41).put("sha256","bad"));assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);
    }
    @Test public void fallbackExplainsMissingGiteeReleaseAndBothSourceFailures()throws Exception{
        Reader r=new Reader();r.values.put(UpdateSources.GITEE_LATEST,new IOException("HTTP 404"));
        assertTrue(r.check(40).diagnostics.contains("Gitee：HTTP 404"));
        r.values.put(UpdateSources.GITHUB_LATEST,new IOException("timeout"));
        UpdateSources.Unavailable failure=assertThrows(UpdateSources.Unavailable.class,()->r.check(40));
        assertTrue(failure.getMessage().contains("Gitee：HTTP 404"));assertTrue(failure.getMessage().contains("GitHub：timeout"));
    }
    @Test public void prereleaseAndWrongTagAndCrossVersionUrlsNeverSelected()throws Exception{
        for(String tag:new String[]{"v0.2.26","../../main","v0.2.27#x"}){Reader r=new Reader();r.values.put(UpdateSources.GITEE_LATEST,new JSONObject().put("tag_name",tag).put("prerelease",false));assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);}
        Reader r=new Reader();((JSONObject)r.values.get(UpdateSources.GITEE_LATEST)).put("prerelease",true);assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);
        Reader bad=new Reader();bad.values.put(UpdateSources.asset(VERSION,"update.json",true),manifest(false,41));assertEquals(UpdateSources.GITHUB_LATEST,bad.check(40).endpoint);
    }
    @Test public void wrongPackageAndChannelTryFallbackWithoutRelaxingValidation()throws Exception{
        Reader r=new Reader();r.values.put(UpdateSources.asset(VERSION,"update.json",true),manifest(true,41).put("channel","release"));assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);
        r.values.put(UpdateSources.GITHUB_LATEST,manifest(false,41).put("packageName","bad.app"));assertThrows(Exception.class,()->r.check(40));
    }
    @Test public void staleMirrorCannotHideNewGithubRelease()throws Exception{Reader r=new Reader();r.values.put(UpdateSources.asset(VERSION,"update.json",true),manifest(true,40));assertEquals(UpdateSources.GITHUB_LATEST,r.check(40).endpoint);}
    @Test public void githubOutageDoesNotInvalidateCurrentGitee()throws Exception{Reader r=new Reader();r.values.put(UpdateSources.GITHUB_LATEST,new IOException("offline"));assertEquals(UpdateSources.GITEE_LATEST,r.check(41).endpoint);}
    @Test public void customSourceIsNeverSilentlyReplaced()throws Exception{Reader r=new Reader();String url="https://example.invalid/update.json";r.values.put(url,manifest(false,41));assertEquals(url,UpdateSources.check(url,PACKAGE,"debug",40,r).endpoint);assertEquals(Collections.singletonList(url),r.calls);r.values.clear();r.calls.clear();assertThrows(Exception.class,()->UpdateSources.check(url,PACKAGE,"debug",40,r));assertEquals(Collections.singletonList(url),r.calls);}
    @Test public void apkFallbackUsesSameVersionAndChannelOnlyForKnownMirror()throws Exception{
        UpdateManifest mirrored=new UpdateManifest(manifest(true,41),PACKAGE);assertEquals(Arrays.asList(mirrored.apkUrl,UpdateSources.asset(VERSION,mirrored.apkFilename(),false)),mirrored.downloadUrls());
        UpdateManifest github=new UpdateManifest(manifest(false,41),PACKAGE);assertEquals(Collections.singletonList(github.apkUrl),github.downloadUrls());
        UpdateManifest custom=new UpdateManifest(manifest(true,41).put("apkUrl","https://elsewhere.invalid/custom.apk"),PACKAGE);assertEquals(Collections.singletonList(custom.apkUrl),custom.downloadUrls());
        UpdateManifest stable=new UpdateManifest(manifest(true,41).put("channel","release").put("apkUrl",UpdateSources.asset(VERSION,"acmforever-0.2.27.apk",true)),PACKAGE);assertTrue(stable.downloadUrls().get(1).endsWith("/acmforever-0.2.27.apk"));
    }
    @Test public void storageAndExhaustedDownloadDoNotLoop(){assertTrue(UpdateSources.retryDownload(503,0,2));assertTrue(UpdateSources.retryDownload(1004,0,2));for(int reason:new int[]{1006,1007,1009})assertFalse(UpdateSources.retryDownload(reason,0,2));assertFalse(UpdateSources.retryDownload(503,1,2));assertFalse(UpdateSources.retryDownload(503,0,1));}
    @Test public void modulesAcceptOnlyExactRepositoryVersionAndFilename()throws Exception{
        for(boolean gitee:new boolean[]{true,false}){JSONArray rows=new JSONArray();for(String id:ModuleSpec.IDS)rows.put(new JSONObject().put("id",id).put("kind",ModuleSpec.nativeModule(id)?"native":"assets").put("url",UpdateSources.asset(VERSION,ModuleSpec.filename(id),gitee)).put("sha256","a".repeat(64)).put("sizeBytes",1234));JSONObject catalog=new JSONObject().put("schemaVersion",1).put("versionCode",41).put("versionName",VERSION).put("modules",rows);Map<String,ModuleSpec> parsed=ModuleSpec.parse(catalog,41,VERSION);assertEquals(4,parsed.size());assertEquals(gitee?2:1,parsed.get("advanced").downloadUrls().size());for(String bad:new String[]{"https://gitee.com/attacker/repo/releases/download/v0.2.27/module-advanced.apk",UpdateSources.asset("0.2.26","module-advanced.apk",true),UpdateSources.asset(VERSION,"module-admin.apk",true)}){JSONObject changed=new JSONObject(catalog.toString());for(int i=0;i<rows.length();i++)if(changed.getJSONArray("modules").getJSONObject(i).getString("id").equals("advanced"))changed.getJSONArray("modules").getJSONObject(i).put("url",bad);assertThrows(Exception.class,()->ModuleSpec.parse(changed,41,VERSION));}}
    }
}
