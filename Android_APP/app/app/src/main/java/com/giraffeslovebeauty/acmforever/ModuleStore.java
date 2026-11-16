package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.content.pm.*;
import android.os.Build;
import java.io.*;
import java.util.*;
import org.json.JSONObject;

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
        if(ModuleHealth.damaged(id))return false;
        return new File(assets(c,id),".complete-api1").isFile();
    }
    static boolean current(Context c,String id){return ModuleSpec.nativeModule(id)?available(c,id):new File(assetsAt(c,id,code(c)),".complete-api1").isFile();}
    /** Read-only availability may fall back; destructive operations must use the checked query. */
    static Set<String> installedNative(Context c){try{return installedNativeChecked(c);}catch(IOException unavailable){return Collections.emptySet();}}
    static Set<String> installedNativeChecked(Context c)throws IOException{
        try{String[] names=c.getPackageManager().getPackageInfo(c.getPackageName(),0).splitNames;Set<String> found=new HashSet<>();
            if(names!=null)for(String id:names)if(ModuleSpec.nativeModule(id))found.add(id);return found;
        }catch(Exception failure){throw new IOException("无法确认系统模块状态，请稍后重试",failure);}
    }
    static void acquired(Context c,String id){Set<String> ids=acquired(c);ids.add(id);if(!c.getSharedPreferences("optional_modules",0).edit().putStringSet("acquired",ids).commit())throw new IllegalStateException("无法保存已下载模块记录，请检查存储空间");}
    static Set<String> acquired(Context c){Set<String> ids=new HashSet<>(c.getSharedPreferences("optional_modules",0).getStringSet("acquired",Collections.emptySet()));ids.retainAll(ModuleSpec.IDS);ids.addAll(installedNative(c));for(String id:ModuleSpec.IDS)if(!ModuleSpec.nativeModule(id)&&available(c,id))ids.add(id);return ids;}
    static Set<String> updateSelection(Context c)throws Exception{
        Set<String> ids=acquired(c);
        Set<String> pending=new HashSet<>();
        for(String id:ids)if(ModuleSpec.nativeModule(id)&&c.getSharedPreferences("module_installs",0).getBoolean("remove_"+id,false))pending.add(id);
        if(pending.isEmpty())return ids;
        // A completed system removal can survive process death before local cleanup.
        // Verify absence directly: a PackageManager failure must not count as absence.
        Set<String> installed=installedNativeChecked(c);
        for(String id:pending)if(!installed.contains(id))ids.remove(id);
        return ids;
    }
    static boolean updateTogether(Context c){return AppAppearance.prefs(c).getBoolean("app_update_modules",true);}
    static synchronized void removeLocal(Context c,String id)throws Exception{
        ModuleSpec.name(id);
        if(ModuleSpec.nativeModule(id)&&installedNativeChecked(c).contains(id))throw new IOException("原生模块仍已安装，请先完成系统卸载确认");
        ModuleRemovalFiles.remove(new File(c.getFilesDir(),"optional-modules"),id,ModuleSpec.filename(id));
        Set<String> ids=acquired(c);ids.remove(id);
        if(!c.getSharedPreferences("optional_modules",0).edit().putStringSet("acquired",ids).commit())throw new IOException("无法保存模块删除结果，请重试");
    }
    static void updateTogether(Context c,boolean on){AppAppearance.prefs(c).edit().putBoolean("app_update_modules",on).apply();}
    static InputStream open(Context c,String id,String relative)throws IOException{
        if(!available(c,id))throw new FileNotFoundException("尚未下载"+ModuleSpec.name(id));ModuleFiles.safePath(relative);File root=assets(c,id),file=new File(root,relative);
        if(!file.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))throw new IOException("模块路径越界");try{return new FileInputStream(file);}catch(IOException failure){ModuleHealth.bad(c,id,"资源读取失败，需要检查修复");throw failure;}
    }
    static Set<String> trusted(Context c)throws Exception{
        PackageInfo info=c.getPackageManager().getPackageInfo(c.getPackageName(),Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES);
        android.content.pm.Signature[] signatures=Build.VERSION.SDK_INT>=28?info.signingInfo.getApkContentsSigners():info.signatures;Set<String> out=new HashSet<>();
        for(android.content.pm.Signature signature:signatures)out.add(ModuleFiles.hex(java.security.MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())));return out;
    }
    static void installAssets(Context c,ModuleSpec spec)throws Exception{
        installAssets(c,spec,spec.versionCode);
    }
    private static synchronized void installAssets(Context c,ModuleSpec spec,int targetCode)throws Exception{
        File archive=archive(c,spec.id,spec.versionCode);ModuleFiles.verify(archive,spec,trusted(c));
        File target=assetsAt(c,spec.id,targetCode),parent=target.getParentFile();if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("无法创建模块目录");
        if(ModuleFiles.matches(archive,target)){receipt(target,spec);return;}
        if(targetCode==code(c))ModuleHealth.recovering(spec.id);
        File staging=new File(parent,spec.id+".staging-"+UUID.randomUUID());
        File backup=new File(parent,spec.id+".backup-"+UUID.randomUUID());boolean replaced=false;
        try{ModuleFiles.extract(archive,staging);if(!ModuleFiles.matches(archive,staging))throw new IOException("恢复后的资源仍不完整");receipt(staging,spec);
            if(target.exists())java.nio.file.Files.move(target.toPath(),backup.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE);
            try{java.nio.file.Files.move(staging.toPath(),target.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE);replaced=true;}finally{if(!replaced&&backup.exists())java.nio.file.Files.move(backup.toPath(),target.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE);}
        }finally{if(staging.exists())ModuleFiles.remove(staging);}
        if(replaced&&backup.exists())try{ModuleFiles.remove(backup);}catch(IOException ignored){} // A retained backup is safer than losing a completed repair.
    }
    private static void receipt(File target,ModuleSpec spec)throws Exception{
        try(FileOutputStream out=new FileOutputStream(new File(target,".source-code"))){out.write(String.valueOf(spec.versionCode).getBytes(java.nio.charset.StandardCharsets.US_ASCII));out.getFD().sync();}
        try(FileOutputStream out=new FileOutputStream(new File(target,".complete-api1"))){out.write(spec.sha256.getBytes(java.nio.charset.StandardCharsets.US_ASCII));out.getFD().sync();}
    }
    private static List<Integer> versions(Context c,int maximum){
        ArrayList<Integer> found=new ArrayList<>();File[] items=new File(c.getFilesDir(),"optional-modules").listFiles();if(items!=null)for(File item:items)try{int n=Integer.parseInt(item.getName());if(n>0&&n<=maximum)found.add(n);}catch(NumberFormatException ignored){}found.sort(Collections.reverseOrder());return found;
    }
    static ModuleSpec localSpec(Context c,String id,int code)throws Exception{
        File archive=archive(c,id,code),catalog=new File(root(c,code),"catalog.json");
        if(catalog.isFile())try(InputStream in=new FileInputStream(catalog)){
            JSONObject index=new JSONObject(new String(ModuleNetwork.read(in,65536),java.nio.charset.StandardCharsets.UTF_8));return ModuleSpec.parse(index,code,index.getString("versionName")).get(id);
        }catch(Exception invalidCatalog){/* Signed local archive remains the migration authority. */}
        // Migration also accepts an orphaned archive, but its real signer/id/API/code are still verified.
        return new ModuleSpec(id,"",ModuleFiles.hash(archive),"assets",archive.length(),code);
    }
    static final class Checked {final String revision;final int sourceCode;Checked(String r,int c){revision=r;sourceCode=c;}}
    /** Background only. Missing markers and interrupted replacements are inspected as well. */
    static synchronized Checked inspect(Context c,String id,boolean repair)throws Exception{
        Exception last=null;
        for(int n:versions(c,code(c))){File installed=assetsAt(c,id,n);if(!installed.exists())continue;
            try{int source=n;File reference=new File(installed,".source-code");if(reference.isFile()){if(reference.length()>10)throw new IOException("模块恢复记录过大");String value=new String(java.nio.file.Files.readAllBytes(reference.toPath()),java.nio.charset.StandardCharsets.US_ASCII);if(!value.matches("[0-9]{1,10}"))throw new IOException("模块恢复记录损坏");source=Integer.parseInt(value);if(source<1||source>n)throw new IOException("模块恢复记录越界");}
                ModuleSpec spec=localSpec(c,id,source);File archive=archive(c,id,source);ModuleFiles.verify(archive,spec,trusted(c));boolean complete=ModuleFiles.matches(archive,installed);
                if(!complete&&!repair)throw new IOException("模块内容缺失或损坏");if(repair)installAssets(c,spec,n);
                return new Checked(ModuleFiles.resourceRevision(archive),source);
            }catch(Exception failure){last=failure;java.nio.file.Files.deleteIfExists(new File(installed,".complete-api1").toPath());}
        }
        // An interrupted first installation can have an archive but no installed directory.
        if(repair)for(int n:versions(c,code(c)))try{if(!archive(c,id,n).isFile())continue;ModuleSpec spec=localSpec(c,id,n);installAssets(c,spec,n);return new Checked(ModuleFiles.resourceRevision(archive(c,id,n)),n);}catch(Exception failure){last=failure;}
        throw new IOException("模块需要修复"+(last==null?"":"："+last.getMessage()),last);
    }
    /** Reuse the original signed archive; only the local extraction is staged for the next App. */
    static synchronized boolean reuse(Context c,ModuleSpec target)throws Exception{
        if(ModuleSpec.nativeModule(target.id)||target.revision.isEmpty())return false;
        for(int n:versions(c,Math.min(code(c),target.versionCode)))try{File file=archive(c,target.id,n);if(!file.isFile())continue;ModuleSpec existing=localSpec(c,target.id,n);ModuleFiles.verify(file,existing,trusted(c));if(!target.revision.equals(ModuleFiles.resourceRevision(file)))continue;installAssets(c,existing,target.versionCode);return true;}catch(Exception ignored){}
        return false;
    }
}
