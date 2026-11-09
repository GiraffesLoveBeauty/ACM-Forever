package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.*;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.jar.*;

public class ModuleFilesTest {
    private static Path temp,key;private static Set<String> trusted;
    private static String tool(String name){return Path.of(System.getProperty("java.home"),"bin",name+(System.getProperty("os.name").startsWith("Windows")?".exe":"")).toString();}
    private static void run(String...args)throws Exception{Process p=new ProcessBuilder(args).redirectErrorStream(true).start();String log=new String(p.getInputStream().readAllBytes());if(p.waitFor()!=0)throw new AssertionError(log);}
    @BeforeClass public static void signingFixture()throws Exception{temp=Files.createTempDirectory("module-unit-");key=temp.resolve("test.jks");run(tool("keytool"),"-genkeypair","-keystore",key.toString(),"-storepass","fixture-pass","-keypass","fixture-pass","-alias","fixture","-keyalg","RSA","-keysize","2048","-validity","1","-dname","CN=Unit test only");KeyStore store=KeyStore.getInstance(KeyStore.getDefaultType());try(InputStream in=Files.newInputStream(key)){store.load(in,"fixture-pass".toCharArray());}trusted=Collections.singleton(ModuleFiles.hex(MessageDigest.getInstance("SHA-256").digest(store.getCertificate("fixture").getEncoded())));}
    @AfterClass public static void cleanup()throws Exception{ModuleFiles.remove(temp.toFile());}
    private File pack(String entry,int version)throws Exception{Path out=Files.createTempFile(temp,"pack-",".jar");try(JarOutputStream jar=new JarOutputStream(Files.newOutputStream(out))){jar.putNextEntry(new JarEntry("module.json"));jar.write(new JSONObject().put("id","cat-art").put("kind","assets").put("api",1).put("versionCode",version).toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));jar.closeEntry();jar.putNextEntry(new JarEntry(entry));jar.write("actual payload".getBytes());jar.closeEntry();}run(tool("jarsigner"),"-keystore",key.toString(),"-storepass","fixture-pass","-keypass","fixture-pass","-digestalg","SHA-256","-sigalg","SHA256withRSA",out.toString(),"fixture");return out.toFile();}
    private ModuleSpec spec(File f)throws Exception{return new ModuleSpec("cat-art","https://example.invalid/a",ModuleFiles.hash(f),"assets",f.length(),39);}
    @Test public void validSignedPackExtracts()throws Exception{File f=pack("payload/character/art.png",39);ModuleFiles.verify(f,spec(f),trusted);File dest=temp.resolve(UUID.randomUUID().toString()).toFile();ModuleFiles.extract(f,dest);assertEquals("actual payload",new String(Files.readAllBytes(dest.toPath().resolve("character/art.png"))));}
    @Test public void anotherSignerAndVersionDenied()throws Exception{File f=pack("payload/art.png",38);assertThrows(Exception.class,()->ModuleFiles.verify(f,spec(f),trusted));File good=pack("payload/art.png",39);assertThrows(SecurityException.class,()->ModuleFiles.verify(good,spec(good),Collections.singleton("b".repeat(64))));}
    @Test public void hashMismatchDenied()throws Exception{File f=pack("payload/art.png",39);ModuleSpec original=spec(f);try(OutputStream out=new FileOutputStream(f,true)){out.write(1);}assertThrows(Exception.class,()->ModuleFiles.verify(f,original,trusted));}
    @Test public void signedTraversalDenied()throws Exception{File f=pack("payload/../../outside",39);assertThrows(Exception.class,()->ModuleFiles.verify(f,spec(f),trusted));assertFalse(temp.getParent().resolve("outside").toFile().exists());}
    @Test public void unsignedExtraEntryDenied()throws Exception{File original=pack("payload/art.png",39);File modified=temp.resolve(UUID.randomUUID()+".jar").toFile();try(JarFile in=new JarFile(original);JarOutputStream out=new JarOutputStream(new FileOutputStream(modified))){for(Enumeration<JarEntry> e=in.entries();e.hasMoreElements();){JarEntry entry=e.nextElement();out.putNextEntry(new JarEntry(entry.getName()));try(InputStream bytes=in.getInputStream(entry)){bytes.transferTo(out);}out.closeEntry();}out.putNextEntry(new JarEntry("payload/injected.js"));out.write(1);out.closeEntry();}assertThrows(SecurityException.class,()->ModuleFiles.verify(modified,spec(modified),trusted));}
    @Test public void unsafeNamesDenied(){for(String path:new String[]{"../a","/a","a/../b","a\\b","a/./b",""})assertThrows(IOException.class,()->ModuleFiles.safePath(path));}
}
