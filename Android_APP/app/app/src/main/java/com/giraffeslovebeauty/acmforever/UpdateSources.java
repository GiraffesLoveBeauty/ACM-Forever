package com.giraffeslovebeauty.acmforever;

import java.io.IOException;
import java.util.*;
import org.json.JSONObject;

/** Public mirrors share artifact identity; source selection never supplies credentials. */
final class UpdateSources {
    static final String GITEE_REPOSITORY="MJJ13445/ACM-Forever";
    static final String GITEE_LATEST="https://gitee.com/api/v5/repos/"+GITEE_REPOSITORY+"/releases/latest";
    static final String GITHUB_LATEST="https://github.com/"+ModuleSpec.REPOSITORY+"/releases/latest/download/update.json";
    interface Reader {JSONObject read(String address,int limit)throws Exception;}
    static final class Checked {
        final UpdateManifest manifest;final String endpoint;
        Checked(UpdateManifest manifest,String endpoint){this.manifest=manifest;this.endpoint=endpoint;}
    }
    static String asset(String version,String filename,boolean gitee){
        if(!version.matches("[0-9]+\\.[0-9]+\\.[0-9]+")||!filename.matches("[A-Za-z0-9_.-]+"))throw new IllegalArgumentException("无效发布路径");
        return (gitee?"https://gitee.com/"+GITEE_REPOSITORY:"https://github.com/"+ModuleSpec.REPOSITORY)+"/releases/download/v"+version+"/"+filename;
    }
    static List<String> endpoints(String configured){
        String checked=UpdateManifest.https(configured);
        return GITEE_LATEST.equals(checked)?Arrays.asList(GITEE_LATEST,GITHUB_LATEST):Collections.singletonList(checked);
    }
    static Checked check(String configured,String packageName,String channel,long installedCode,Reader reader)throws Exception{
        Exception failure=null;Checked ready=null;List<String> sources=endpoints(configured);
        for(String endpoint:sources)try{
            String version=null,address=endpoint;
            if(GITEE_LATEST.equals(endpoint)){
                JSONObject metadata=reader.read(endpoint,65536);
                String tag=metadata.getString("tag_name");
                if(!Boolean.FALSE.equals(metadata.get("prerelease"))||metadata.optBoolean("draft",false)||!tag.matches("v[0-9]+\\.[0-9]+\\.[0-9]+"))throw new IOException("Gitee 正式发布信息无效");
                version=tag.substring(1);address=asset(version,"update.json",true);
            }
            UpdateManifest found=new UpdateManifest(reader.read(address,32768),packageName);found.requireChannel(channel);
            if(version!=null&&(!version.equals(found.versionName)||!found.apkUrl.equals(asset(version,found.apkFilename(),true))
                    ||!found.modulesUrl.equals(asset(version,"modules.json",true))))throw new IOException("Gitee 更新清单与发布版本不一致");
            if(ready==null||found.versionCode>ready.manifest.versionCode)ready=new Checked(found,endpoint);
            // An already-installed mirror may lag behind publication. Probe the fallback
            // for a newer version, but a fallback outage does not invalidate a valid mirror.
            if(ready.manifest.versionCode>installedCode||sources.size()==1)return ready;
        }catch(Exception failed){if(failure!=null)failed.addSuppressed(failure);failure=failed;}
        if(ready!=null)return ready;
        throw failure==null?new IOException("没有可用更新源"):failure;
    }
    static String label(String endpoint){return GITEE_LATEST.equals(endpoint)?"Gitee":GITHUB_LATEST.equals(endpoint)?"GitHub":"自定义地址";}
    static boolean retryDownload(int reason,int attempt,int total){
        // Storage errors require user action; only transport failures may switch mirrors.
        return attempt+1<total&&reason!=1006&&reason!=1007&&reason!=1009;
    }
    private UpdateSources(){}
}
