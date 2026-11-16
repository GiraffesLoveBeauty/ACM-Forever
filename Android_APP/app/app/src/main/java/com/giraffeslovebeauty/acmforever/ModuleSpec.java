package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** The index supplies sizes, never executable authority. Every payload must also be signed. */
final class ModuleSpec {
    static final String REPOSITORY="GiraffesLoveBeauty/ACM-Forever";
    static final long MAX_BYTES=16L*1024*1024;
    static final Set<String> IDS=Collections.unmodifiableSet(new HashSet<>(Arrays.asList("official-themes","advanced","admin","cat-art")));
    final String id,url,sha256,kind,revision,number,previewTag;final long size,owner;final int versionCode;
    ModuleSpec(String id,String url,String sha256,String kind,long size,int code){this(id,url,sha256,kind,size,code,"");}
    ModuleSpec(String id,String url,String sha256,String kind,long size,int code,String revision){this(id,url,sha256,kind,size,code,revision,"");}
    ModuleSpec(String id,String url,String sha256,String kind,long size,int code,String revision,String number){this(id,url,sha256,kind,size,code,revision,number,"",-1);}
    private ModuleSpec(String id,String url,String sha256,String kind,long size,int code,String revision,String number,String previewTag,long owner){this.id=id;this.url=url;this.sha256=sha256;this.kind=kind;this.size=size;versionCode=code;this.revision=revision;this.number=number;this.previewTag=previewTag;this.owner=owner;}
    static String name(String id){switch(id){case "official-themes":return "官方主题库";case "advanced":return "高级个性化";case "admin":return "手机便捷管理";case "cat-art":return "分层猫娘素材";default:throw new IllegalArgumentException("未知模块");}}
    static boolean nativeModule(String id){return "advanced".equals(id)||"admin".equals(id);}
    static String filename(String id){if(!IDS.contains(id))throw new IllegalArgumentException("未知模块");return "module-"+id+(nativeModule(id)?".apk":".acmpack");}
    static String indexUrl(String version){if(!version.matches("[0-9]+\\.[0-9]+\\.[0-9]+"))throw new IllegalArgumentException("无效版本");return "https://github.com/"+REPOSITORY+"/releases/download/v"+version+"/modules.json";}
    static List<String> indexUrls(String version){return Arrays.asList(UpdateSources.asset(version,"modules.json",true),indexUrl(version));}
    List<String> downloadUrls(){
        if(!previewTag.isEmpty())return Collections.singletonList(url);
        String version=java.net.URI.create(url).getPath().split("/releases/download/v",2)[1].split("/",2)[0];
        String github=UpdateSources.asset(version,filename(id),false);
        return url.equals(github)?Collections.singletonList(url):Arrays.asList(url,github);
    }
    static Map<String,ModuleSpec> parse(JSONObject index,int code,String version)throws Exception{
        return parse(index,code,version,"","",-1);
    }
    static Map<String,ModuleSpec> privateCatalog(JSONObject index,int code,String version,String tag,String base,long owner)throws Exception{
        if(!tag.matches("v"+java.util.regex.Pattern.quote(version)+"-preview\\.[1-9][0-9]*")||!tag.equals(index.getString("previewTag")))throw new IllegalArgumentException("测试模块修订不一致");
        return parse(index,code,version,tag,UpdateManifest.https(base),owner);
    }
    /** Offline integrity metadata is not authorization to download a private asset. */
    static Map<String,ModuleSpec> storedCatalog(JSONObject index,int code,String version,String tag)throws Exception{
        if(tag.isEmpty())return parse(index,code,version);
        if(!tag.matches("v"+java.util.regex.Pattern.quote(version)+"-preview\\.[1-9][0-9]*")||!tag.equals(index.getString("previewTag")))throw new IllegalArgumentException("本地测试模块修订不一致");
        return parse(index,code,version,tag,"",-1);
    }
    static ModuleSpec localArchive(String id,String hash,long size,int code,String tag){
        return new ModuleSpec(id,"",hash,nativeModule(id)?"native":"assets",size,code,"","",tag,-1);
    }
    private static Map<String,ModuleSpec> parse(JSONObject index,int code,String version,String tag,String base,long owner)throws Exception{
        if(index.getInt("schemaVersion")!=1||index.getInt("versionCode")!=code||!version.equals(index.getString("versionName")))throw new IllegalArgumentException("模块清单与当前App版本不匹配");
        if(tag.isEmpty()&&index.has("previewTag"))throw new IllegalArgumentException("公开模块源不能包含测试修订");
        Map<String,ModuleSpec> result=new LinkedHashMap<>();JSONArray rows=index.getJSONArray("modules");
        if(rows.length()!=IDS.size())throw new IllegalArgumentException("模块清单不完整");
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);String id=row.getString("id"),kind=row.getString("kind"),hash=row.getString("sha256");
            if(!IDS.contains(id)||result.containsKey(id))throw new IllegalArgumentException("模块身份重复或未知");
            String url=row.getString("url");
            Object rawSize=row.get("sizeBytes");if(!(rawSize instanceof Integer||rawSize instanceof Long))throw new IllegalArgumentException("模块大小无效");long size=((Number)rawSize).longValue();
            boolean validUrl=tag.isEmpty()?(url.equals(UpdateSources.asset(version,filename(id),true))||url.equals(UpdateSources.asset(version,filename(id),false))):url.equals("https://github.com/"+REPOSITORY+"/releases/download/"+tag+"/"+filename(id));
            if(size<=0||size>MAX_BYTES||!hash.matches("[0-9a-f]{64}")||!validUrl||!kind.equals(nativeModule(id)?"native":"assets"))throw new IllegalArgumentException("模块清单无效");
            if(row.has("revision")&&!(row.get("revision") instanceof String))throw new IllegalArgumentException("模块编号必须为字符串");String revision=row.optString("revision","");if(!revision.isEmpty()&&!revision.matches((nativeModule(id)?"n1-":"a1-")+"[0-9a-f]{64}"))throw new IllegalArgumentException("模块编号无效");
            String number="";if(row.has("number")){Object value=row.get("number");if(!(value instanceof String))throw new IllegalArgumentException("模块编号必须为字符串");number=ModuleNumber.validate(id,version,(String)value);}
            if(!tag.isEmpty())url=base.isEmpty()?"":base+"/api/admin/android/releases/"+tag+"/assets/"+filename(id);
            result.put(id,new ModuleSpec(id,url,hash,kind,size,code,revision,number,tag,owner));
        }
        return result;
    }
    String confirmation(){return "此模块未下载，预计大小"+((size+1023)/1024)+"KB，是否下载？";}
}
