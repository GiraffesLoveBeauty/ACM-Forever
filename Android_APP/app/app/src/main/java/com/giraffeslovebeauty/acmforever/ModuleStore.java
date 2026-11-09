package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.content.pm.*;
import android.os.Build;
import java.io.*;
import java.util.*;

/** Versioned storage is persistent user data, never part of temporary-cache cleanup. */
final class ModuleStore {
    private ModuleStore(){}
    static int code(Context c){try{return c.getPackageManager().getPackageInfo(c.getPackageName(),0).versionCode;}catch(Exception e){throw new IllegalStateException(e);}}
    static String version(Context c){try{return c.getPackageManager().getPackageInfo(c.getPackageName(),0).versionName;}catch(Exception e){throw new IllegalStateException(e);}}
    static File root(Context c){return root(c,code(c));}
    static File root(Context c,int code){if(code<1)throw new IllegalArgumentException("无效模块版本");return new File(c.getFilesDir(),"optional-modules/"+code);}
    static File archive(Context c,String id){return archive(c,id,code(c));}
    static File archive(Context c,String id,int code){ModuleSpec.name(id);return new File(root(c,code),"downloads/"+ModuleSpec.filename(id));}
    private static File assetsAt(Context c,String id,int code){return new File(root(c,code),"installed/"+id);}
    static File assets(Context c,String id){
        File best=assetsAt(c,id,code(c));int highest=0;File[] versions=new File(c.getFilesDir(),"optional-modules").listFiles();
        if(versions!=null)for(File version:versions)try{int n=Integer.parseInt(version.getName());File item=assetsAt(c,id,n);
            if(n<=code(c)&&n>highest&&new File(item,".complete-api1").isFile()){best=item;highest=n;}
        }catch(NumberFormatException ignored){}
        return best;
    }
    static boolean available(Context c,String id){
        if(!ModuleSpec.IDS.contains(id))return false;
        if(ModuleSpec.nativeModule(id))return installedNative(c).contains(id);
        return new File(assets(c,id),".complete-api1").isFile();
    }
    static boolean current(Context c,String id){return ModuleSpec.nativeModule(id)?available(c,id):new File(assetsAt(c,id,code(c)),".complete-api1").isFile();}
    static Set<String> installedNative(Context c){try{String[] names=c.getPackageManager().getPackageInfo(c.getPackageName(),0).splitNames;Set<String> found=new HashSet<>();if(names!=null)for(String id:names)if(ModuleSpec.nativeModule(id))found.add(id);return found;}catch(Exception e){return Collections.emptySet();}}
    static void acquired(Context c,String id){Set<String> ids=acquired(c);ids.add(id);if(!c.getSharedPreferences("optional_modules",0).edit().putStringSet("acquired",ids).commit())throw new IllegalStateException("无法保存已下载模块记录，请检查存储空间");}
    static Set<String> acquired(Context c){Set<String> ids=new HashSet<>(c.getSharedPreferences("optional_modules",0).getStringSet("acquired",Collections.emptySet()));ids.retainAll(ModuleSpec.IDS);ids.addAll(installedNative(c));for(String id:ModuleSpec.IDS)if(!ModuleSpec.nativeModule(id)&&available(c,id))ids.add(id);return ids;}
    static boolean updateTogether(Context c){return AppAppearance.prefs(c).getBoolean("app_update_modules",true);}
    static void updateTogether(Context c,boolean on){AppAppearance.prefs(c).edit().putBoolean("app_update_modules",on).apply();}
    static InputStream open(Context c,String id,String relative)throws IOException{
        if(!available(c,id))throw new FileNotFoundException("尚未下载"+ModuleSpec.name(id));ModuleFiles.safePath(relative);File root=assets(c,id),file=new File(root,relative);
        if(!file.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))throw new IOException("模块路径越界");return new FileInputStream(file);
    }
    static Set<String> trusted(Context c)throws Exception{
        PackageInfo info=c.getPackageManager().getPackageInfo(c.getPackageName(),Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES);
        android.content.pm.Signature[] signatures=Build.VERSION.SDK_INT>=28?info.signingInfo.getApkContentsSigners():info.signatures;Set<String> out=new HashSet<>();
        for(android.content.pm.Signature signature:signatures)out.add(ModuleFiles.hex(java.security.MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())));return out;
    }
    static void installAssets(Context c,ModuleSpec spec)throws Exception{
        File target=assetsAt(c,spec.id,spec.versionCode),parent=target.getParentFile();if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("无法创建模块目录");
        if(new File(target,".complete-api1").isFile())return;
        File staging=new File(parent,spec.id+".staging-"+UUID.randomUUID());
        try{ModuleFiles.extract(archive(c,spec.id,spec.versionCode),staging);try(FileOutputStream out=new FileOutputStream(new File(staging,".complete-api1"))){out.write(spec.sha256.getBytes(java.nio.charset.StandardCharsets.US_ASCII));out.getFD().sync();}
            if(target.exists())ModuleFiles.remove(target);java.nio.file.Files.move(staging.toPath(),target.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        }finally{if(staging.exists())ModuleFiles.remove(staging);}
    }
}
