package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import java.io.File;
import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.util.LinkedHashMap;
import static org.junit.Assert.*;

public final class PdfFilesTest {
    @Rule public TemporaryFolder temporary=new TemporaryFolder();
    private File source() throws IOException {
        File file=temporary.newFile("acm-statement-working.pdf");
        Files.write(file.toPath(),new byte[]{1,2,3});return file;
    }
    @SuppressWarnings("unchecked")
    private LinkedHashMap<String,File> index(PdfFiles cache) throws Exception {
        Field field=PdfFiles.class.getDeclaredField("files");field.setAccessible(true);
        return (LinkedHashMap<String,File>)field.get(cache);
    }
    private File refuseOnce(File file) {
        return new File(file.getPath()) {
            private boolean refuse=true;
            @Override public boolean delete(){if(refuse){refuse=false;return false;}return super.delete();}
        };
    }
    @Test public void checkedCleanupPreservesWorkingCopy() throws Exception {
        File working=source();PdfFiles cache=new PdfFiles(temporary.getRoot());cache.save("a",working);
        File cached=index(cache).get("a");cache.clearChecked();
        assertFalse(cached.exists());assertTrue(working.exists());
        assertFalse(cache.copyTo("a",new File(temporary.getRoot(),"copy.pdf")));
    }
    @Test public void failedDeletionRetainsIndexAndCanBeRetried() throws Exception {
        File working=source();PdfFiles cache=new PdfFiles(temporary.getRoot());cache.save("a",working);
        File cached=index(cache).get("a");index(cache).put("a",refuseOnce(cached));
        assertThrows(IOException.class,cache::clearChecked);
        assertTrue(cached.exists());
        File copy=new File(temporary.getRoot(),"copy.pdf");assertTrue(cache.copyTo("a",copy));
        assertArrayEquals(Files.readAllBytes(working.toPath()),Files.readAllBytes(copy.toPath()));
        cache.clearChecked();assertFalse(cached.exists());assertTrue(working.exists());
        assertFalse(cache.copyTo("a",copy));
    }
    @Test public void partialFailureStillCleansOtherIndexedFiles() throws Exception {
        File working=source();PdfFiles cache=new PdfFiles(temporary.getRoot());
        cache.save("failed",working);cache.save("other",working);
        File failed=index(cache).get("failed"), other=index(cache).get("other");
        index(cache).put("failed",refuseOnce(failed));
        assertThrows(IOException.class,cache::clearChecked);
        assertTrue(failed.exists());assertFalse(other.exists());
        assertEquals(1,index(cache).size());assertTrue(index(cache).containsKey("failed"));
    }
    @Test public void alreadyMissingCacheDoesNotFailCleanup() throws Exception {
        File working=source();PdfFiles cache=new PdfFiles(temporary.getRoot());cache.save("a",working);
        assertTrue(index(cache).get("a").delete());cache.clearChecked();assertTrue(index(cache).isEmpty());
    }
    @Test public void logoutStillDropsAllIndexedAccessWhenDeletionFails() throws Exception {
        File working=source();PdfFiles cache=new PdfFiles(temporary.getRoot());cache.save("a",working);
        File cached=index(cache).get("a");index(cache).put("a",refuseOnce(cached));cache.clear();
        assertTrue(cached.exists());assertTrue(index(cache).isEmpty());
        assertFalse(cache.copyTo("a",new File(temporary.getRoot(),"after-logout.pdf")));
    }
}
