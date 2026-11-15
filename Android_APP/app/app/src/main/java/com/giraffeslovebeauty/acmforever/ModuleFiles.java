package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.security.cert.Certificate;
import java.util.*;
import java.util.jar.*;

/** Strict v1/JAR verification is additional to Android's native split installer checks. */
final class ModuleFiles {
    static String hash(File file)throws Exception{MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){byte[] block=new byte[16384];int n;while((n=in.read(block))!=-1)hash.update(block,0,n);}return hex(hash.digest());}
    static String hex(byte[] bytes){StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format(Locale.ROOT,"%02x",b&255));return out.toString();}
    static String safePath(String value)throws IOException{
        if(value.isEmpty()||value.startsWith("/")||value.contains("\\")||!value.matches("[A-Za-z0-9_./-]+"))throw new IOException("模块路径无效");
        for(String part:value.split("/"))if(part.equals("..")||part.equals("."))throw new IOException("模块路径越界");return value;
    }
    static void verify(File file,ModuleSpec spec,Set<String> trusted)throws Exception{
        if(file.length()!=spec.size||!hash(file).equals(spec.sha256))throw new IOException("模块大小或SHA-256校验失败");
        String metadata=ModuleSpec.nativeModule(spec.id)?"assets/modules/"+spec.id+".json":"module.json";
        Set<String> seen=new HashSet<>();long total=0;int count=0;byte[] info=null;byte[] block=new byte[16384];
        try(JarFile jar=new JarFile(file,true)){
            for(Enumeration<JarEntry> entries=jar.entries();entries.hasMoreElements();){
                JarEntry entry=entries.nextElement();String name=safePath(entry.getName());if(!seen.add(name))throw new IOException("模块存在重复条目");if(entry.isDirectory())continue;
                if(++count>2048)throw new IOException("模块条目过多");ByteArrayOutputStream capture=name.equals(metadata)?new ByteArrayOutputStream():null;
                try(InputStream in=jar.getInputStream(entry)){int n;long size=0;while((n=in.read(block))!=-1){size+=n;total+=n;if(size>ModuleSpec.MAX_BYTES||total>48L*1024*1024)throw new IOException("模块展开体积过大");if(capture!=null){if(size>4096)throw new IOException("模块元数据过大");capture.write(block,0,n);}}}
                if(!name.startsWith("META-INF/")){
                    CodeSigner[] signers=entry.getCodeSigners();boolean accepted=false;
                    if(signers!=null)for(CodeSigner signer:signers){List<? extends Certificate> chain=signer.getSignerCertPath().getCertificates();if(!chain.isEmpty()&&trusted.contains(hex(MessageDigest.getInstance("SHA-256").digest(chain.get(0).getEncoded()))))accepted=true;}
                    if(!accepted)throw new SecurityException("模块签名与当前App不一致");
                }
                if(capture!=null)info=capture.toByteArray();
            }
        }
        if(info==null)throw new IOException("缺少已签名的模块身份");JSONObject value=new JSONObject(new String(info,java.nio.charset.StandardCharsets.UTF_8));
        if(!spec.id.equals(value.getString("id"))||value.getInt("api")!=1||value.getInt("versionCode")!=spec.versionCode||!spec.kind.equals(value.getString("kind")))throw new IOException("模块版本或身份不兼容");
        if(ModuleSpec.nativeModule(spec.id)&&!spec.id.equals(value.getString("splitName")))throw new IOException("原生功能包身份不兼容");
        if(!spec.revision.isEmpty()&&!ModuleSpec.nativeModule(spec.id)){
            if(!spec.revision.equals(value.optString("revision"))||!spec.revision.equals(resourceRevision(file)))throw new IOException("资源编号与签名内容不一致");
        }
    }
    /** Independent of ZIP timestamps, signatures and the enclosing App version. */
    static String resourceRevision(File archive)throws Exception{
        TreeMap<String,String> files=new TreeMap<>();
        try(JarFile jar=new JarFile(archive,true)){
            for(Enumeration<JarEntry> entries=jar.entries();entries.hasMoreElements();){JarEntry entry=entries.nextElement();String name=safePath(entry.getName());if(entry.isDirectory()||!name.startsWith("payload/"))continue;
                MessageDigest digest=MessageDigest.getInstance("SHA-256");long size=0;try(InputStream in=jar.getInputStream(entry)){byte[] buffer=new byte[16384];int n;while((n=in.read(buffer))!=-1){size+=n;if(size>ModuleSpec.MAX_BYTES)throw new IOException("资源过大");digest.update(buffer,0,n);}}
                if(files.put(name.substring(8),size+"\0"+hex(digest.digest()))!=null)throw new IOException("重复资源");
            }
        }
        if(files.isEmpty())throw new IOException("资源包为空");MessageDigest digest=MessageDigest.getInstance("SHA-256");digest.update("ACM-MODULE-ASSETS/1\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        for(Map.Entry<String,String> item:files.entrySet())digest.update((item.getKey()+"\0"+item.getValue()+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));return "a1-"+hex(digest.digest());
    }
    /** Compare actual installed bytes to an already verified signed archive, not its marker. */
    static boolean matches(File archive,File directory)throws Exception{
        if(!directory.isDirectory())return false;Set<String> expected=new HashSet<>();
        try(JarFile jar=new JarFile(archive,true)){
            byte[] a=new byte[16384],b=new byte[16384];
            for(Enumeration<JarEntry> entries=jar.entries();entries.hasMoreElements();){JarEntry entry=entries.nextElement();String name=safePath(entry.getName());if(entry.isDirectory()||!name.startsWith("payload/"))continue;
                String relative=safePath(name.substring(8));File file=new File(directory,relative);if(!file.getCanonicalPath().startsWith(directory.getCanonicalPath()+File.separator)||!file.isFile()||Files.isSymbolicLink(file.toPath())||file.length()!=entry.getSize())return false;expected.add(relative);
                try(InputStream actual=new FileInputStream(file);InputStream wanted=jar.getInputStream(entry)){int n;while((n=wanted.read(a))!=-1){int offset=0;while(offset<n){int m=actual.read(b,offset,n-offset);if(m<0)return false;offset+=m;}for(int i=0;i<n;i++)if(a[i]!=b[i])return false;}if(actual.read()!=-1)return false;}
            }
        }
        try(java.util.stream.Stream<Path> files=Files.walk(directory.toPath())){for(Path path:(Iterable<Path>)files::iterator){if(Files.isSymbolicLink(path))return false;if(Files.isRegularFile(path)){String relative=directory.toPath().relativize(path).toString().replace(File.separatorChar,'/');if(!expected.contains(relative)&&!relative.equals(".complete-api1")&&!relative.equals(".source-code"))return false;}}}
        return !expected.isEmpty();
    }
    static void extract(File archive,File destination)throws Exception{
        if(destination.exists()||!destination.mkdirs())throw new IOException("无法创建模块安装目录");boolean completed=false;
        try(JarFile jar=new JarFile(archive,true)){
            for(Enumeration<JarEntry> entries=jar.entries();entries.hasMoreElements();){JarEntry entry=entries.nextElement();String name=safePath(entry.getName());if(entry.isDirectory()||!name.startsWith("payload/"))continue;
                String relative=name.substring(8);safePath(relative);File target=new File(destination,relative);if(!target.getCanonicalPath().startsWith(destination.getCanonicalPath()+File.separator))throw new IOException("模块路径越界");
                File parent=target.getParentFile();if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("无法写入模块目录");try(InputStream in=jar.getInputStream(entry);OutputStream out=new FileOutputStream(target)){byte[] block=new byte[16384];int n;while((n=in.read(block))!=-1)out.write(block,0,n);}
            }completed=true;
        }finally{if(!completed)remove(destination);}
    }
    static void remove(File directory)throws IOException{if(!directory.exists())return;try(java.util.stream.Stream<Path> paths=Files.walk(directory.toPath())){for(Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator)Files.delete(path);}}
}
