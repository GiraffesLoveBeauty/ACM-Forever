package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import java.net.URI;
import java.util.Locale;

/** Public release metadata. It never contains cookies, credentials or an executable instruction. */
final class UpdateManifest {
    static final long MAX_APK_BYTES=150L*1024*1024;
    final String packageName,versionName,apkUrl,sha256,notes,channel,modulesUrl,distribution,previewTag;
    final long versionCode,sizeBytes,releaseVersionCode;
    final int minSdk,previewRevision;
    private final String json;
    UpdateManifest(JSONObject value,String expectedPackage)throws Exception{
        packageName=value.getString("packageName");
        if(!expectedPackage.equals(packageName))throw new IllegalArgumentException("更新包名与当前 App 不一致。");
        channel=value.optString("channel","");
        distribution=value.optString("distribution",channel.isEmpty()?"release":channel);
        if(!distribution.equals("release")&&!distribution.equals("debug")&&!distribution.equals("preview"))throw new IllegalArgumentException("更新分发类型无效。");
        if(!channel.isEmpty()&&!channel.equals("debug")&&!channel.equals("release"))throw new IllegalArgumentException("更新渠道无效。");
        versionCode=value.getLong("versionCode");versionName=value.getString("versionName");
        if(versionCode<1||versionCode>2100000000L||!versionName.matches("[0-9]+\\.[0-9]+(?:\\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?"))throw new IllegalArgumentException("更新版本无效。");
        previewTag=value.optString("previewTag","");previewRevision=value.optInt("previewRevision",0);releaseVersionCode=value.optLong("releaseVersionCode",versionCode);
        if(distribution.equals("preview")&&(previewRevision<1||releaseVersionCode<=versionCode||releaseVersionCode>2100000000L||!previewTag.equals("v"+versionName+"-preview."+previewRevision)))throw new IllegalArgumentException("测试版身份或覆盖版本号无效。");
        apkUrl=https(value.getString("apkUrl"));sha256=value.getString("sha256").toLowerCase(Locale.ROOT);
        if(!sha256.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("版本清单缺少有效 SHA-256。");
        sizeBytes=value.optLong("sizeBytes",0);minSdk=value.optInt("minSdk",26);
        if(sizeBytes<0||sizeBytes>MAX_APK_BYTES||minSdk<1)throw new IllegalArgumentException("安装包大小或系统版本要求无效。");
        notes=value.optString("notes","");if(notes.length()>8000)throw new IllegalArgumentException("更新说明过长。");
        modulesUrl=value.optString("modulesUrl","");
        if(!modulesUrl.isEmpty()&&!(distribution.equals("preview")?modulesUrl.endsWith("/api/admin/android/releases/"+previewTag+"/modules"):ModuleSpec.indexUrls(versionName).contains(modulesUrl)))throw new IllegalArgumentException("模块清单地址与版本不一致。");
        json=value.toString();
    }
    String json(){return json;}
    String apkFilename(){return "acmforever-"+versionName+("debug".equals(channel)?"-debug":"")+".apk";}
    java.util.List<String> downloadUrls(){
        if(versionName.matches("[0-9]+\\.[0-9]+\\.[0-9]+")&&apkUrl.equals(UpdateSources.asset(versionName,apkFilename(),true)))
            return java.util.Arrays.asList(apkUrl,UpdateSources.asset(versionName,apkFilename(),false));
        return java.util.Collections.singletonList(apkUrl);
    }
    void requireChannel(String current){
        if(!current.equals("release")&&!current.equals("debug")&&!current.equals("preview"))throw new IllegalArgumentException("未知更新渠道。");
        boolean allowed="preview".equals(current)?"preview".equals(distribution):"release".equals(distribution)||legacyPublicDebug();
        if(!allowed)throw new IllegalArgumentException("更新清单与当前 App 渠道不同，请安装对应渠道的版本。");
    }
    boolean legacyPublicDebug(){return distribution.equals("debug")&&versionCode<=44&&versionName.matches("0\\.2\\.[0-9]+")&&channel.equals("debug");}
    boolean installable(long installedCode,boolean installedPreview,int installedRevision,long installedTarget,boolean previewChannel){
        if(versionCode<installedCode)return false;
        if(previewChannel)return distribution.equals("preview")&&(!installedPreview||releaseVersionCode>installedTarget||releaseVersionCode==installedTarget&&previewRevision>installedRevision);
        return !distribution.equals("preview")&&(versionCode>installedCode||installedPreview&&versionCode==installedCode);
    }
    static UpdateManifest administrator(JSONObject value,String base)throws Exception{
        String tag=value.getString("previewTag");
        if(!"preview".equals(value.optString("distribution"))||!tag.matches("v[0-9]+\\.[0-9]+\\.[0-9]+-preview\\.[1-9][0-9]*")||!value.optString("apkPath").equals("/api/admin/android/releases/"+tag+"/apk"))throw new IllegalArgumentException("测试版更新地址无效。");
        JSONObject local=new JSONObject(value.toString());local.put("apkUrl",https(base+value.getString("apkPath")));
        if(!value.optString("modulesPath").isEmpty()){
            if(!value.getString("modulesPath").equals("/api/admin/android/releases/"+tag+"/modules"))throw new IllegalArgumentException("测试模块地址无效");
            local.put("modulesUrl",https(base+value.getString("modulesPath")));
        }
        return new UpdateManifest(local,"com.giraffeslovebeauty.acmforever");
    }
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
