package com.giraffeslovebeauty.acmforever;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Delete exactly one module's archives/extractions across versions; never follow a link outside. */
final class ModuleRemovalFiles {
    private ModuleRemovalFiles() {}
    static List<File> targets(File root,String id,String filename)throws IOException {
        if(!Arrays.asList("official-themes","advanced","admin","cat-art").contains(id)
            ||!filename.equals("module-"+id+((id.equals("admin")||id.equals("advanced"))?".apk":".acmpack")))throw new IOException("无效模块");
        List<File> result=new ArrayList<>();if(!root.exists())return result;
        File[] versions=root.listFiles();if(versions==null)throw new IOException("无法读取模块目录");
        for(File version:versions){if(!version.getName().matches("[1-9][0-9]*"))continue;inside(root,version);
            for(String dir:new String[]{"downloads","installed"}){File folder=new File(version,dir);inside(root,folder);if(!folder.exists())continue;
                File[] files=folder.listFiles();if(files==null)throw new IOException("无法读取模块文件");
                for(File file:files){String name=file.getName();boolean selected=dir.equals("downloads")?(name.equals(filename)||(name.startsWith(filename+"-")&&name.endsWith(".part"))):(name.equals(id)||name.startsWith(id+".staging-")||name.startsWith(id+".backup-"));
                    if(selected){inside(root,file);result.add(file);}
                }
            }
        }return result;
    }
    private static void inside(File root,File target)throws IOException {
        if(!target.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))throw new IOException("模块路径越界");
        if(Files.isSymbolicLink(target.toPath()))throw new IOException("模块路径不能是链接");
    }
    static void remove(File root,String id,String filename)throws IOException {
        for(File target:targets(root,id,filename)){
            inside(root,target);
            try(java.util.stream.Stream<Path> paths=Files.walk(target.toPath())){
                for(Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator)Files.delete(path);
            }
        }
    }
}
