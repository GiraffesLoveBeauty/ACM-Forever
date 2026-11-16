package com.giraffeslovebeauty.acmforever;

import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.XmlResourceParser;
import java.io.File;
import java.io.IOException;
import org.xmlpull.v1.XmlPullParser;

/** Read the archive itself: Android 15 archive ApplicationInfo can omit its flags. */
final class ApkManifest {
    private static final String ANDROID="http://schemas.android.com/apk/res/android";

    static boolean debuggable(PackageManager pm,File apk,PackageInfo info)throws Exception{
        ApplicationInfo archive=new ApplicationInfo(info.applicationInfo);
        archive.sourceDir=apk.getAbsolutePath();
        archive.publicSourceDir=archive.sourceDir;
        try(XmlResourceParser xml=pm.getResourcesForApplication(archive).getAssets().openXmlResourceParser("AndroidManifest.xml")){
            boolean manifest=false;
            for(int event=xml.next();event!=XmlPullParser.END_DOCUMENT;event=xml.next()){
                if(event!=XmlPullParser.START_TAG)continue;
                if(xml.getDepth()==1&&"manifest".equals(xml.getName())){
                    manifest=info.packageName.equals(xml.getAttributeValue(null,"package"));
                    if(!manifest)throw new IOException("安装包清单与包名不符。");
                }else if(manifest&&xml.getDepth()==2&&"application".equals(xml.getName())){
                    if(xml.getAttributeResourceValue(ANDROID,"debuggable",0)!=0)
                        throw new IOException("安装包的调试标志必须为明确的布尔值。");
                    return xml.getAttributeBooleanValue(ANDROID,"debuggable",false);
                }
            }
        }
        throw new IOException("无法读取安装包的应用清单。");
    }
    private ApkManifest(){}
}
