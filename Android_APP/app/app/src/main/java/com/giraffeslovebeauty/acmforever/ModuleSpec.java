package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** The index supplies sizes, never executable authority. Every payload must also be signed. */
final class ModuleSpec {
    static final String REPOSITORY="GiraffesLoveBeauty/ACM-Forever";
    static final long MAX_BYTES=16L*1024*1024;
    static final Set<String> IDS=Collections.unmodifiableSet(new HashSet<>(Arrays.asList("official-themes","advanced","admin","cat-art")));
    final String id,url,sha256,kind;final long size;final int versionCode;
    ModuleSpec(String id,String url,String sha256,String kind,long size,int code){this.id=id;this.url=url;this.sha256=sha256;this.kind=kind;this.size=size;versionCode=code;}
    static String name(String id){switch(id){case "official-themes":return "官方主题库";case "advanced":return "高级个性化";case "admin":return "手机便捷管理";case "cat-art":return "分层猫娘素材";default:throw new IllegalArgumentException("未知模块");}}
    static boolean nativeModule(String id){return "advanced".equals(id)||"admin".equals(id);}
    static String filename(String id){if(!IDS.contains(id))throw new IllegalArgumentException("未知模块");return "module-"+id+(nativeModule(id)?".apk":".acmpack");}
    static String indexUrl(String version){if(!version.matches("[0-9]+\\.[0-9]+\\.[0-9]+"))throw new IllegalArgumentException("无效版本");return "https://github.com/"+REPOSITORY+"/releases/download/v"+version+"/modules.json";}
    static Map<String,ModuleSpec> parse(JSONObject index,int code,String version)throws Exception{
        if(index.getInt("schemaVersion")!=1||index.getInt("versionCode")!=code||!version.equals(index.getString("versionName")))throw new IllegalArgumentException("模块清单与当前App版本不匹配");
        Map<String,ModuleSpec> result=new LinkedHashMap<>();JSONArray rows=index.getJSONArray("modules");
        if(rows.length()!=IDS.size())throw new IllegalArgumentException("模块清单不完整");
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);String id=row.getString("id"),kind=row.getString("kind"),hash=row.getString("sha256");
            if(!IDS.contains(id)||result.containsKey(id))throw new IllegalArgumentException("模块身份重复或未知");
            String url="https://github.com/"+REPOSITORY+"/releases/download/v"+version+"/"+filename(id);
            Object rawSize=row.get("sizeBytes");if(!(rawSize instanceof Integer||rawSize instanceof Long))throw new IllegalArgumentException("模块大小无效");long size=((Number)rawSize).longValue();
            if(size<=0||size>MAX_BYTES||!hash.matches("[0-9a-f]{64}")||!url.equals(row.getString("url"))||!kind.equals(nativeModule(id)?"native":"assets"))throw new IllegalArgumentException("模块清单无效");
            result.put(id,new ModuleSpec(id,url,hash,kind,size,code));
        }
        return result;
    }
    String confirmation(){return "此模块未下载，预计大小"+((size+1023)/1024)+"KB，是否下载？";}
}
