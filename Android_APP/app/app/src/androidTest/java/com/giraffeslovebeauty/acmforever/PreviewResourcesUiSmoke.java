package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Real signed, changed preview resources at the same code as a retained public catalog. */
final class PreviewResourcesUiSmoke {
    static void run(Instrumentation test,boolean restart){
        Context c=test.getTargetContext();Bundle result=new Bundle();int status=Activity.RESULT_CANCELED;
        try{
            check(AppDistribution.installed(c).preview,"must run on actual preview APK");
            if(restart)verifyRestart(c);else exercise(test,c);
            result.putString("stream","PASS: preview-resources"+(restart?"-restart":"")+"; signed changed private archive, public catalog isolation, exact local metadata, repair and future staging verified.\n");status=Activity.RESULT_OK;
        }catch(Throwable e){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e)+"\n");}
        test.finish(status,result);
    }
    private static byte[] fixture(Instrumentation test,String file)throws Exception{
        try(ParcelFileDescriptor fd=test.getUiAutomation().executeShellCommand("cat /data/local/tmp/"+file);InputStream in=new FileInputStream(fd.getFileDescriptor())){return in.readAllBytes();}
    }
    private static void exercise(Instrumentation test,Context c)throws Exception{
        JSONObject publicIndex=new JSONObject(new String(fixture(test,"acm-old-modules.json"),StandardCharsets.UTF_8));
        ModuleSpec original=ModuleSpec.parse(publicIndex,44,"0.2.30").get("cat-art");
        File publicRoot=ModuleStore.root(c,44);publicRoot.mkdirs();
        java.nio.file.Files.write(new File(publicRoot,"catalog.json").toPath(),publicIndex.toString().getBytes(StandardCharsets.UTF_8));
        File publicArchive=ModuleStore.archive(c,"cat-art",44);publicArchive.getParentFile().mkdirs();
        java.nio.file.Files.write(publicArchive.toPath(),fixture(test,"old-module-cat-art.acmpack"));ModuleStore.installAssets(c,original);
        String retainedHash=ModuleFiles.hash(publicArchive);
        JSONObject index=new JSONObject(new String(fixture(test,"acm-preview-modules.json"),StandardCharsets.UTF_8));
        JSONObject metadata=new JSONObject(new String(fixture(test,"acm-preview-manifest.json"),StandardCharsets.UTF_8)).put("moduleCatalog",index);
        byte[] changed=fixture(test,"module-cat-art.acmpack");
        URL.setURLStreamHandlerFactory(protocol->!"https".equals(protocol)?null:new URLStreamHandler(){protected URLConnection openConnection(URL url)throws IOException{
            if(!url.getHost().equals("preview-resources.test.invalid"))throw new IOException("External traffic forbidden");
            return new HttpURLConnection(url){
                public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}public int getResponseCode(){return 200;}
                public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
                public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=synthetic-preview; Path=/; Secure; HttpOnly")):Collections.emptyMap();}
                public long getContentLengthLong(){return url.getPath().contains("/assets/")?changed.length:-1;}
                public InputStream getInputStream()throws IOException{
                    String path=url.getPath();String response=path.endsWith("/latest")?metadata.toString():path.endsWith("/me")?"{\"authenticated\":true,\"role\":\"admin\",\"csrf_token\":\"synthetic\",\"qq_id\":\"90000001\"}":"{}";
                    if(path.contains("/assets/")){check(path.endsWith("module-cat-art.acmpack")&&getRequestProperty("Cookie")!=null&&!getInstanceFollowRedirects(),"private resource uses authenticated, nonredirecting transport");return new ByteArrayInputStream(changed);}
                    return new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8));
                }
            };
        }});
        ApiClient api=((AcmApplication)c.getApplicationContext()).api();api.setBaseUrl("https://preview-resources.test.invalid");api.setNetworkAvailable(()->true);api.login("90000001","Synthetic-Only!");
        ModuleSpec preview=ModuleNetwork.catalog(c,UpdateManifest.administrator(metadata,api.getBaseUrl())).get("cat-art");
        check(preview.versionCode==original.versionCode&&!preview.sha256.equals(original.sha256)&&!preview.revision.equals(original.revision),"same-code fixture really changes resource bytes");
        File archive=ModuleStore.archive(c,preview);check(!archive.equals(publicArchive),"download paths separated by channel/revision");
        ModuleNetwork.download(c,preview,archive,n->{},()->false);ModuleStore.installAssets(c,preview);ModuleStore.acquired(c,"cat-art");
        check(ModuleHealth.verify(c,"cat-art").intact,"private download passes immediate health verification beside old public catalog");
        check(ModuleStore.assets(c,"cat-art").equals(new File(ModuleStore.root(c,preview),"installed/cat-art")),"installed preview selects its exact resource namespace");
        check(retainedHash.equals(ModuleFiles.hash(publicArchive)),"public archive bytes retained");
        check(new JSONObject(read(new File(publicRoot,"catalog.json"))).getString("versionName").equals("0.2.30"),"public catalog retained");
        ModuleSpec offline=ModuleStore.localSpec(c,"cat-art",ModuleStore.installedScope(c));check(offline.sha256.equals(preview.sha256)&&offline.previewTag.equals(preview.previewTag)&&offline.owner==-1&&offline.url.isEmpty(),"private local catalog restores integrity without credentials");
        boolean denied=false;try{ModuleNetwork.download(c,offline,new File(c.getCacheDir(),"must-not-download"),n->{},()->false);}catch(IOException expected){denied=true;}check(denied,"offline metadata cannot authorize private download");
        JSONObject future=new JSONObject(index.toString());String nextTag="v1.0.0-preview.99";future.put("previewTag",nextTag);
        for(int i=0;i<future.getJSONArray("modules").length();i++){JSONObject row=future.getJSONArray("modules").getJSONObject(i);row.put("url",row.getString("url").replace(preview.previewTag,nextTag));}
        ModuleSpec target=ModuleSpec.storedCatalog(future,preview.versionCode,"1.0.0",nextTag).get("cat-art");
        check(ModuleStore.reuse(c,target),"unchanged resources reuse original signed private archive");
        check(!new File(ModuleStore.root(c,target),".activated").exists(),"future preview remains staged");
        check(ModuleStore.assets(c,"cat-art").equals(new File(ModuleStore.root(c,preview),"installed/cat-art")),"staging next preview does not switch active resources");
        JSONObject proof=new JSONObject().put("revision",preview.revision).put("sha256",preview.sha256).put("publicSha256",retainedHash).put("tag",preview.previewTag);
        write(new File(c.getFilesDir(),"preview-resource-proof.json"),proof.toString());
        File payload=new File(ModuleStore.assets(c,"cat-art"),"preview-review-proof.txt");check(payload.isFile(),"fixture includes genuinely new signed payload");
        write(payload,"damaged");
        check(ModuleHealth.verify(c,"cat-art").intact,"local repair uses private archive and matching catalog");
        check(read(payload).equals("signed preview resource regression\n"),"damaged private resource restored exactly");
    }
    private static void verifyRestart(Context c)throws Exception{
        JSONObject proof=new JSONObject(read(new File(c.getFilesDir(),"preview-resource-proof.json")));
        ModuleHealth.Status health=ModuleHealth.verify(c,"cat-art");check(health.intact&&health.revision.equals(proof.getString("revision")),"process restart restores exact private resource revision without network");
        check(read(new File(ModuleStore.assets(c,"cat-art"),"preview-review-proof.txt")).equals("signed preview resource regression\n"),"private payload preserved across restart");
        ModuleSpec offline=ModuleStore.localSpec(c,"cat-art",ModuleStore.installedScope(c));check(offline.sha256.equals(proof.getString("sha256"))&&offline.owner==-1,"offline private spec restored without session");
        check(ModuleFiles.hash(ModuleStore.archive(c,"cat-art",44)).equals(proof.getString("publicSha256")),"ordinary archive remains usable after private restart");
    }
    private static String read(File file)throws IOException{return new String(java.nio.file.Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8);}
    private static void write(File file,String value)throws IOException{java.nio.file.Files.write(file.toPath(),value.getBytes(StandardCharsets.UTF_8));}
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
}
