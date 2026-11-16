package com.giraffeslovebeauty.acmforever;

import java.io.*;
import java.nio.file.Files;
import java.util.*;
import org.junit.*;
import org.junit.rules.TemporaryFolder;
import static org.junit.Assert.*;

public class ModuleScopeTest {
    @Rule public TemporaryFolder tmp=new TemporaryFolder();
    private final ModuleScope public44=new ModuleScope(44,""),preview1=new ModuleScope(44,"v1.0.0-preview.1"),preview2=new ModuleScope(44,"v1.0.0-preview.2");
    private void stage(File root,ModuleScope scope,boolean activated)throws Exception{File folder=scope.root(root);assertTrue(folder.mkdirs());if(activated)Files.write(new File(folder,".activated").toPath(),new byte[0]);}
    @Test public void namespacesDoNotOverwriteSameCodePublicOrOtherRevisions()throws Exception{
        File root=tmp.newFolder();stage(root,public44,false);stage(root,preview1,true);stage(root,preview2,false);
        assertNotEquals(public44.root(root),preview1.root(root));assertNotEquals(preview1.root(root),preview2.root(root));
        assertEquals(3,ModuleScope.all(root,44).size());assertTrue(public44.root(root).getPath().endsWith("44"));
    }
    @Test public void stagedPreviewIsInactiveUntilItsExactBaseIsInstalled()throws Exception{
        File root=tmp.newFolder();stage(root,public44,false);stage(root,preview1,true);stage(root,preview2,false);stage(root,new ModuleScope(45,""),false);
        List<ModuleScope> ready=ModuleScope.active(root,preview1);
        assertTrue(ready.get(0).same(preview1));assertFalse(ready.stream().anyMatch(s->s.same(preview2)||s.code>44));
        assertTrue(ModuleScope.active(root,preview2).get(0).same(preview2));
    }
    @Test public void ordinaryReturnPrefersPublicAndFormalCanRetainPreviouslyActivePreview()throws Exception{
        File root=tmp.newFolder();stage(root,public44,false);stage(root,preview1,true);stage(root,preview2,false);
        assertTrue(ModuleScope.active(root,public44).get(0).same(public44));
        List<ModuleScope> formal=ModuleScope.active(root,new ModuleScope(45,""));
        assertTrue(formal.stream().anyMatch(s->s.same(preview1)));assertFalse(formal.stream().anyMatch(s->s.same(preview2)));
    }
    @Test public void scopeRejectsPathInjectionAndInvalidCodes(){
        for(String tag:new String[]{"../44","v1.0.0-preview.0","v1.0.0-preview.1/..","v1.0.0-preview.01","release"})assertThrows(IllegalArgumentException.class,()->new ModuleScope(44,tag));
        assertThrows(IllegalArgumentException.class,()->new ModuleScope(0,""));
    }
}
