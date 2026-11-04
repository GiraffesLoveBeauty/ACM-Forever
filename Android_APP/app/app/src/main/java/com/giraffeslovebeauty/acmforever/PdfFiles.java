package com.giraffeslovebeauty.acmforever;

import java.io.*;
import java.util.LinkedHashMap;

/** Process-indexed private file cache. Active readers always hold a separate working copy. */
final class PdfFiles {
    private final File directory;
    private final LinkedHashMap<String,File> files=new LinkedHashMap<>(8,.75f,true);
    PdfFiles(File directory){this.directory=directory;File[] old=directory.listFiles((dir,name)->name.startsWith("acm-pdf-cache-"));if(old!=null)for(File file:old)file.delete();}
    synchronized boolean copyTo(String key,File destination)throws IOException{File source=files.get(key);if(source==null||!source.isFile())return false;copy(source,destination);return true;}
    synchronized void save(String key,File source)throws IOException{
        File saved=File.createTempFile("acm-pdf-cache-",".pdf",directory);try{copy(source,saved);}catch(IOException e){saved.delete();throw e;}
        File previous=files.put(key,saved);if(previous!=null)previous.delete();
        while(files.size()>5||size()>64L*1024*1024){String first=files.keySet().iterator().next();files.remove(first).delete();}
    }
    private long size(){long total=0;for(File file:files.values())total+=file.length();return total;}
    synchronized void clear(){for(File file:files.values())file.delete();files.clear();}
    private static void copy(File source,File destination)throws IOException{try(InputStream in=new FileInputStream(source);OutputStream out=new FileOutputStream(destination)){byte[] buffer=new byte[8192];int count;while((count=in.read(buffer))!=-1)out.write(buffer,0,count);}}
}
