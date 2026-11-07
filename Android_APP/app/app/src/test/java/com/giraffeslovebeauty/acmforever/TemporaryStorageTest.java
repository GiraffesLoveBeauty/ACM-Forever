package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import static org.junit.Assert.*;

public final class TemporaryStorageTest {
    @Rule public TemporaryFolder temporary = new TemporaryFolder();
    private File data(File parent, String name) throws Exception {
        File file = new File(parent, name); Files.write(file.toPath(), new byte[]{1, 2, 3}); return file;
    }
    @Test public void packageCleanupPreservesWorkingDocumentsAndUnknownFiles() throws Exception {
        File cache = temporary.newFolder("cache"), downloads = temporary.newFolder("downloads");
        File updates = new File(cache,"updates"); assertTrue(updates.mkdir());
        File apk = data(updates,"verified-1234.apk"), source = data(downloads,"acmforever-37-1234.apk");
        File document = data(cache,"acm-statement-reader.pdf"), unknown = data(updates,"keep.txt");
        File theme = data(downloads,"theme.acmtheme");
        TemporaryStorage.clearPackages(cache,downloads);
        assertFalse(apk.exists()); assertFalse(source.exists());
        assertTrue(document.exists()); assertTrue(unknown.exists()); assertTrue(theme.exists());
    }
    @Test public void expiredSharesDoNotInvalidateRecentSharesOrOriginals() throws Exception {
        File cache=temporary.newFolder("cache"), shares=new File(cache,"theme-shares"); assertTrue(shares.mkdir());
        File expired=data(shares,"0123456789abcdef0123456789abcdef.acmtheme");
        File recent=data(shares,"ffffffffffffffffffffffffffffffff.acmtheme"), original=data(cache,"profile-cover.jpg");
        long now=System.currentTimeMillis(); assertTrue(expired.setLastModified(now-8L*86400000));
        TemporaryStorage.clearExpiredShares(cache,now);
        assertFalse(expired.exists()); assertTrue(recent.exists()); assertTrue(original.exists());
        assertEquals(6,TemporaryStorage.bytes(cache));
    }
    @Test public void packageCleanupDoesNotFollowFileLinks() throws Exception {
        File cache=temporary.newFolder("cache"), updates=new File(cache,"updates");assertTrue(updates.mkdir());
        File outside=data(temporary.getRoot(),"outside.apk");
        try {Files.createSymbolicLink(new File(updates,"verified-linked.apk").toPath(),outside.toPath());}
        catch(UnsupportedOperationException|java.io.IOException|SecurityException unavailable){org.junit.Assume.assumeNoException(unavailable);}
        assertEquals(0,TemporaryStorage.bytes(cache));
        TemporaryStorage.clearPackages(cache,null); assertTrue(outside.exists());
    }
    @Test public void unsupportedImageIsNotAConnectionFailure() {
        assertEquals("图片无法显示",FailureState.title(new ApiClient.MediaFormatException("invalid")));
        assertFalse(PageRefresh.isConnectionFailure(FailureState.title(new ApiClient.MediaFormatException("invalid"))));
    }
    @Test public void missingOptionalDirectoriesAreEmpty() throws Exception {
        File cache=temporary.newFolder("cache"), downloads=new File(temporary.getRoot(),"missing-downloads");
        assertEquals(0,TemporaryStorage.bytes(downloads));
        TemporaryStorage.clearPackages(cache,downloads);
        TemporaryStorage.clearExpiredShares(cache,System.currentTimeMillis());
    }
    @Test public void unreadableDirectoryDoesNotReportZeroBytes() throws Exception {
        File unreadable=unreadable(temporary.newFolder("unreadable"));
        assertThrows(IOException.class,()->TemporaryStorage.bytes(unreadable));
    }
    @Test public void unreadableNestedDirectoryFailsAccounting() throws Exception {
        File root=temporary.newFolder("cache"), child=temporary.newFolder("cache","unreadable");
        File unreadable=unreadable(child);
        File parent=new File(root.getPath()) {
            @Override public File getCanonicalFile(){return this;}
            @Override public File[] listFiles(){return new File[]{unreadable};}
        };
        assertThrows(IOException.class,()->TemporaryStorage.bytes(parent));
    }
    @Test public void unreadableDownloadsDoNotReportCleanupSuccess() throws Exception {
        File cache=temporary.newFolder("cache"), downloads=temporary.newFolder("downloads");
        File apk=data(downloads,"acmforever-37-1234.apk");
        assertThrows(IOException.class,()->TemporaryStorage.clearPackages(cache,unreadable(downloads)));
        assertTrue(apk.exists());
        TemporaryStorage.clearPackages(cache,downloads);
        assertFalse(apk.exists());
    }
    @Test public void existingNonDirectoryDoesNotReportAnEmptyDirectory() throws Exception {
        File file=data(temporary.getRoot(),"not-a-directory");
        assertThrows(IOException.class,()->TemporaryStorage.bytes(file));
        assertThrows(IOException.class,()->TemporaryStorage.clearPackages(temporary.newFolder("cache"),file));
        assertTrue(file.exists());
    }
    private File unreadable(File directory) throws IOException {
        return new File(directory.getCanonicalPath()) {
            @Override public File getCanonicalFile(){return this;}
            @Override public File getAbsoluteFile(){return this;}
            @Override public File[] listFiles(){return null;}
        };
    }
}
