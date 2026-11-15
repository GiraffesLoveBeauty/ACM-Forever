package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import java.io.*;
import java.net.*;
import java.util.*;
import org.json.JSONObject;

/** Public release transport: never attach a business Cookie, password or CSRF token. */
final class ModuleNetwork {
    interface Progress {void update(long bytes);}
    interface Cancelled {boolean get();}
    private static volatile Map<String,ModuleSpec> cached;private static volatile int cachedCode;private static String cachedVersion="";
    static InputStream connect(String address)throws Exception{
        URL url=new URL(address);
        for(int attempt=0;attempt<6;attempt++){
            String host=url.getHost();if(!url.getProtocol().equals("https")||url.getUserInfo()!=null||url.getRef()!=null||!(host.equals("gitee.com")||host.equals("foruda.gitee.com")||host.equals("files.gitee.com")||host.equals("github.com")||host.endsWith(".githubusercontent.com")))throw new IOException("模块地址不受支持");
            HttpURLConnection connection=(HttpURLConnection)url.openConnection();boolean keep=false;
            try{
                connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(10000);connection.setUseCaches(false);connection.setRequestProperty("User-Agent","ACMForever-OptionalModules/2");connection.setRequestProperty("Accept-Encoding","identity");int status=connection.getResponseCode();
                if(status==301||status==302||status==303||status==307||status==308){String next=connection.getHeaderField("Location");if(next==null)throw new IOException("下载重定向缺失");url=new URL(url,next);continue;}
                if(status!=200)throw new IOException(status==404?"此版本的模块尚未发布":"模块连接失败（HTTP "+status+"）");
                InputStream stream=connection.getInputStream();keep=true;
                return new FilterInputStream(stream){@Override public void close()throws IOException{try{super.close();}finally{connection.disconnect();}}};
            }finally{if(!keep)connection.disconnect();}
        }throw new IOException("模块下载重定向过多");
    }
    static Map<String,ModuleSpec> catalog(Context c)throws Exception{return catalog(c,ModuleStore.code(c),ModuleStore.version(c));}
    static synchronized Map<String,ModuleSpec> catalog(Context c,int code,String version)throws Exception{
        Map<String,ModuleSpec> ready=cached;if(ready!=null&&cachedCode==code&&version.equals(cachedVersion))return ready;
        File local=new File(ModuleStore.root(c,code),"catalog.json");byte[] bytes=null;Map<String,ModuleSpec> parsed=null;Exception failure=null;
        for(String address:ModuleSpec.indexUrls(version))try(InputStream in=connect(address)){
            byte[] candidate=read(in,65536);parsed=ModuleSpec.parse(new JSONObject(new String(candidate,java.nio.charset.StandardCharsets.UTF_8)),code,version);bytes=candidate;break;
        }catch(Exception issue){failure=issue;}
        if(parsed==null){
            if(!local.isFile())throw failure==null?new IOException("没有可用模块源"):failure;
            try(InputStream in=new FileInputStream(local)){parsed=ModuleSpec.parse(new JSONObject(new String(read(in,65536),java.nio.charset.StandardCharsets.UTF_8)),code,version);}
        }else{
            File parent=local.getParentFile();if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("无法缓存模块清单");File partial=File.createTempFile("catalog-",".part",parent);
            try{try(FileOutputStream out=new FileOutputStream(partial)){out.write(bytes);out.getFD().sync();}java.nio.file.Files.move(partial.toPath(),local.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE);}finally{partial.delete();}
        }
        cached=parsed;cachedCode=code;cachedVersion=version;return parsed;
    }
    static byte[] read(InputStream in,int max)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1){if(out.size()+n>max)throw new IOException("模块清单过大");out.write(bytes,0,n);}return out.toByteArray();}
    static void download(ModuleSpec spec,File destination,Progress progress,Cancelled cancelled)throws Exception{
        Exception failure=null;
        for(String address:spec.downloadUrls()){
            if(cancelled.get())throw new IOException("已取消下载");
            try{downloadFrom(spec,address,destination,progress,cancelled);return;}catch(Exception issue){if(cancelled.get())throw new IOException("已取消下载",issue);failure=issue;}
        }
        throw failure==null?new IOException("没有可用模块下载源"):failure;
    }
    private static void downloadFrom(ModuleSpec spec,String address,File destination,Progress progress,Cancelled cancelled)throws Exception{
        File parent=destination.getParentFile();if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("无法创建下载目录");File partial=File.createTempFile(destination.getName()+"-",".part",parent);boolean done=false;
        try(InputStream in=connect(address);FileOutputStream out=new FileOutputStream(partial)){
            byte[] bytes=new byte[16384];long total=0;int n;while((n=in.read(bytes))!=-1){if(cancelled.get())throw new IOException("已取消下载");total+=n;if(total>spec.size)throw new IOException("下载体积超过模块清单");out.write(bytes,0,n);progress.update(total);}out.getFD().sync();
            if(total!=spec.size||!ModuleFiles.hash(partial).equals(spec.sha256))throw new IOException("模块下载不完整或SHA-256不匹配");done=true;
        }finally{if(!done)java.nio.file.Files.deleteIfExists(partial.toPath());}
        try{java.nio.file.Files.move(partial.toPath(),destination.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE);}finally{java.nio.file.Files.deleteIfExists(partial.toPath());}
    }
}
