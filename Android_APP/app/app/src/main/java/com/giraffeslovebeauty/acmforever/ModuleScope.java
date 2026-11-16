package com.giraffeslovebeauty.acmforever;

import java.io.*;
import java.nio.file.Files;
import java.util.*;

/** Public storage keeps its legacy path; every preview revision has a separate namespace. */
final class ModuleScope {
    final int code;final String tag;
    ModuleScope(int code,String tag){
        if(code<1||(!tag.isEmpty()&&!validTag(tag)))throw new IllegalArgumentException("无效模块存储归属");
        this.code=code;this.tag=tag;
    }
    static boolean validTag(String tag){return tag.matches("v[0-9]+\\.[0-9]+\\.[0-9]+-preview\\.[1-9][0-9]*");}
    File root(File modules){File version=new File(modules,String.valueOf(code));return tag.isEmpty()?version:new File(version,"previews/"+tag);}
    boolean same(ModuleScope other){return code==other.code&&tag.equals(other.tag);}
    static List<ModuleScope> all(File modules,int maximum){
        List<ModuleScope> found=new ArrayList<>();File[] versions=modules.listFiles();if(versions==null)return found;
        for(File version:versions)try{
            if(!version.getName().matches("[1-9][0-9]*")||Files.isSymbolicLink(version.toPath()))continue;
            int n=Integer.parseInt(version.getName());if(n>maximum)continue;found.add(new ModuleScope(n,""));
            File previews=new File(version,"previews");if(Files.isSymbolicLink(previews.toPath()))continue;
            File[] revisions=previews.listFiles();if(revisions!=null)for(File revision:revisions)if(validTag(revision.getName())&&revision.isDirectory()&&!Files.isSymbolicLink(revision.toPath()))found.add(new ModuleScope(n,revision.getName()));
        }catch(NumberFormatException ignored){}
        found.sort(Comparator.comparingInt((ModuleScope s)->s.code).reversed().thenComparing(s->s.tag));return found;
    }
    static List<ModuleScope> active(File modules,ModuleScope installed){
        List<ModuleScope> scopes=all(modules,installed.code);
        // A staged future preview must never become active before that base APK is installed.
        scopes.removeIf(s->!s.tag.isEmpty()&&!s.same(installed)&&!new File(s.root(modules),".activated").isFile());
        scopes.sort(Comparator.comparingInt((ModuleScope s)->s.same(installed)?0:1)
            .thenComparing(Comparator.comparingInt((ModuleScope s)->s.code).reversed())
            .thenComparingInt(s->s.tag.isEmpty()?0:1).thenComparing(s->s.tag));
        return scopes;
    }
}
