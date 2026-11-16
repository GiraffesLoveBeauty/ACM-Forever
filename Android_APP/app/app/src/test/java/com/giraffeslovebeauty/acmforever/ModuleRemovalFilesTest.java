package com.giraffeslovebeauty.acmforever;

import org.junit.*;
import org.junit.rules.TemporaryFolder;
import java.io.*;
import java.nio.file.*;
import static org.junit.Assert.*;

public class ModuleRemovalFilesTest {
    @Rule public TemporaryFolder tmp=new TemporaryFolder();
    private File file(File root,String rel)throws Exception{File f=new File(root,rel);f.getParentFile().mkdirs();Files.write(f.toPath(),new byte[]{1,2,3});return f;}
    @Test public void selectedModuleAcrossAllVersionsOnly()throws Exception{
        File root=tmp.newFolder("optional-modules");
        for(String version:new String[]{"41","43","99"}){file(root,version+"/downloads/module-cat-art.acmpack");file(root,version+"/downloads/module-cat-art.acmpack-xyz.part");file(root,version+"/installed/cat-art/image.png");file(root,version+"/installed/cat-art.backup-123/image.png");file(root,version+"/installed/cat-art.staging-123/image.png");}
        File other=file(root,"43/installed/official-themes/payload.png"),catalog=file(root,"43/catalog.json"),theme=file(root,"personal/background.jpg");
        ModuleRemovalFiles.remove(root,"cat-art","module-cat-art.acmpack");
        assertTrue(ModuleRemovalFiles.targets(root,"cat-art","module-cat-art.acmpack").isEmpty());assertTrue(other.exists());assertTrue(catalog.exists());assertTrue(theme.exists());
    }
    @Test public void missingRootAndRepeatedDeleteAreSafe()throws Exception{File root=new File(tmp.getRoot(),"missing");ModuleRemovalFiles.remove(root,"admin","module-admin.apk");assertFalse(root.exists());}
    @Test public void rejectsWrongIdAndFilename()throws Exception{for(String[] row:new String[][]{{"../secret","module-secret.apk"},{"cat-art","module-admin.apk"}})try{ModuleRemovalFiles.remove(tmp.getRoot(),row[0],row[1]);fail();}catch(IOException expected){}}
    @Test public void refusesLinkedVersionDirectory()throws Exception{
        File root=tmp.newFolder("modules"),outside=tmp.newFolder("outside");File secret=file(outside,"downloads/module-cat-art.acmpack");
        try{Files.createSymbolicLink(new File(root,"43").toPath(),outside.toPath());}catch(IOException|UnsupportedOperationException|SecurityException unsupported){Assume.assumeNoException(unsupported);}
        try{ModuleRemovalFiles.remove(root,"cat-art","module-cat-art.acmpack");fail();}catch(IOException expected){assertTrue(secret.exists());}
    }
}
