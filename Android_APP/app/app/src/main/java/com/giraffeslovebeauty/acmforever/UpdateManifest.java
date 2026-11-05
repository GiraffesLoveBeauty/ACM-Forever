package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import java.net.URI;
import java.util.Locale;

/** Public release metadata. It never contains cookies, credentials or an executable instruction. */
final class UpdateManifest {
    static final long MAX_APK_BYTES=150L*1024*1024;
    final String packageName,versionName,apkUrl,sha256,notes,channel;
    final long versionCode,sizeBytes;
    final int minSdk;
    private final String json;
    UpdateManifest(JSONObject value,String expectedPackage)throws Exception{
        packageName=value.getString("packageName");
        if(!expectedPackage.equals(packageName))throw new IllegalArgumentException("更新包名与当前 App 不一致。");
        channel=value.optString("channel","");
        if(!channel.isEmpty()&&!channel.equals("debug")&&!channel.equals("release"))throw new IllegalArgumentException("更新渠道无效。");
        versionCode=value.getLong("versionCode");versionName=value.getString("versionName");
        if(versionCode<1||versionCode>2100000000L||!versionName.matches("[0-9]+\\.[0-9]+(?:\\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?"))throw new IllegalArgumentException("更新版本无效。");
        apkUrl=https(value.getString("apkUrl"));sha256=value.getString("sha256").toLowerCase(Locale.ROOT);
        if(!sha256.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("版本清单缺少有效 SHA-256。");
        sizeBytes=value.optLong("sizeBytes",0);minSdk=value.optInt("minSdk",26);
        if(sizeBytes<0||sizeBytes>MAX_APK_BYTES||minSdk<1)throw new IllegalArgumentException("安装包大小或系统版本要求无效。");
        notes=value.optString("notes","");if(notes.length()>8000)throw new IllegalArgumentException("更新说明过长。");
        json=value.toString();
    }
    String json(){return json;}
    void requireChannel(String current){if(!channel.isEmpty()&&!channel.equals(current))throw new IllegalArgumentException("更新清单与当前 App 渠道不同，请安装对应渠道的版本。");}
    static String https(String value){
        try{
            URI uri=new URI(value.trim());
            if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getFragment()!=null)throw new IllegalArgumentException("更新地址必须是 HTTPS，且不能包含账号密码或片段。");
            return uri.toASCIIString();
        }catch(java.net.URISyntaxException e){throw new IllegalArgumentException("更新地址格式无效。",e);}
    }
    static String endpoint(String base,String override,String channel){
        if(override!=null&&!override.trim().isEmpty())return https(override);
        if(base==null||base.trim().isEmpty())return "";
        return https(base.replaceAll("/+$","")+"/api/mobile/v1/releases/latest?channel="+channel);
    }
    static String redirected(String address,String location){
        if(location==null||location.trim().isEmpty())throw new IllegalArgumentException("更新清单重定向缺少地址。");
        return https(URI.create(https(address)).resolve(location.trim()).toString());
    }
}
