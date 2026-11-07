package com.giraffeslovebeauty.acmforever;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.BasicFileAttributes;

/** Private cache accounting and narrow deletion rules; never traverses linked directories. */
final class TemporaryStorage {
    private TemporaryStorage() {}
    static long bytes(File directory) throws IOException {
        if (directory == null) return 0;
        File root = directory.getCanonicalFile();
        return size(root, root);
    }
    private static long size(File root, File directory) throws IOException {
        long total = 0; File[] entries = entries(directory);
        for (File entry : entries) {
            File resolved = entry.getCanonicalFile();
            if (!resolved.equals(entry.getAbsoluteFile()) || !resolved.toPath().startsWith(root.toPath())) continue;
            if (entry.isDirectory()) total += size(root, entry);
            else if (entry.isFile()) total += entry.length();
        }
        return total;
    }
    static void clearExpiredShares(File cache, long now) throws IOException {
        File directory = new File(cache.getCanonicalFile(), "theme-shares");
        if (!directory.getCanonicalFile().equals(directory.getAbsoluteFile())) return;
        deleteMatching(directory, "[a-f0-9]{32}\\.acmtheme", now - 7L*24*60*60*1000);
    }
    static void clearPackages(File cache, File downloads) throws IOException {
        File directory = new File(cache.getCanonicalFile(), "updates");
        if (!directory.getCanonicalFile().equals(directory.getAbsoluteFile())) throw new IOException("安装包目录无效");
        deleteMatching(directory, "verified-[A-Za-z0-9_-]+\\.apk", Long.MAX_VALUE);
        if (downloads != null) deleteMatching(downloads.getCanonicalFile(), "acmforever-[0-9]+-[0-9]+\\.apk", Long.MAX_VALUE);
    }
    private static void deleteMatching(File directory, String pattern, long cutoff) throws IOException {
        File root = directory.getCanonicalFile();
        if (!root.equals(directory.getAbsoluteFile())) throw new IOException("缓存目录无效");
        File[] entries = entries(directory);
        for (File entry : entries) {
            if (!entry.getName().matches(pattern) || !entry.isFile() || entry.lastModified() >= cutoff) continue;
            if (!entry.getCanonicalFile().equals(entry.getAbsoluteFile()) || !root.equals(entry.getCanonicalFile().getParentFile())) continue;
            if (!entry.delete() && entry.exists()) throw new IOException("部分缓存文件未能清理，请稍后重试");
        }
    }
    private static File[] entries(File directory) throws IOException {
        File[] entries = directory.listFiles();
        if (entries != null) return entries;
        // Only an absent optional directory is empty. Access/I/O failures must reach the UI.
        try { Files.readAttributes(directory.toPath(), BasicFileAttributes.class); }
        catch (NoSuchFileException absent) { return new File[0]; }
        throw new IOException("无法读取缓存目录，请稍后重试");
    }
}
