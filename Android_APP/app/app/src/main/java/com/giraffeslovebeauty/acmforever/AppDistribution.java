package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Bundle;

/** A preview is a signed replacement of the same app, never a second installation. */
final class AppDistribution {
    final boolean preview;
    final int revision;
    final long releaseCode;
    AppDistribution(boolean preview,int revision,long releaseCode){this.preview=preview;this.revision=revision;this.releaseCode=releaseCode;}
    static AppDistribution installed(Context context){
        try{return from(context.getPackageManager().getApplicationInfo(context.getPackageName(),PackageManager.GET_META_DATA).metaData);}
        catch(Exception e){throw new IllegalStateException("无法读取当前安装渠道",e);}
    }
    static AppDistribution archive(PackageInfo info){return from(info.applicationInfo.metaData);}
    private static AppDistribution from(Bundle metadata){
        if(metadata==null||!metadata.containsKey("acmforever.distribution"))return new AppDistribution(false,0,0); // Legacy public packages.
        String kind=metadata.getString("acmforever.distribution","");
        if(!kind.equals("release")&&!kind.equals("preview"))throw new IllegalArgumentException("安装包渠道标志无效");
        int revision=Integer.parseInt(String.valueOf(metadata.get("acmforever.preview_revision")));
        long code=Long.parseLong(String.valueOf(metadata.get("acmforever.release_version_code")));
        if(code<1||revision<0||kind.equals("preview")&&revision<1)throw new IllegalArgumentException("安装包测试版本标志无效");
        return new AppDistribution(kind.equals("preview"),revision,code);
    }
}
