package com.giraffeslovebeauty.acmforever;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import org.junit.BeforeClass;
import org.junit.ClassRule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import static org.junit.Assert.*;

/** Compile the real lifecycle against tiny UI adapters, without a device or Android mock methods. */
public class AdminAccessLifecycleTest {
    @ClassRule public static final TemporaryFolder temporary=new TemporaryFolder();
    private static Path classes;
    @BeforeClass public static void compileLifecycle() throws Exception {
        Path sources=temporary.newFolder("sources").toPath();classes=temporary.newFolder("classes").toPath();
        ArrayList<String> files=new ArrayList<>();
        write(sources,files,"android/os/Bundle.java","package android.os; public class Bundle {}");
        write(sources,files,"android/widget/LinearLayout.java","package android.widget; public class LinearLayout {}");
        String pkg="com/giraffeslovebeauty/acmforever/";
        write(sources,files,pkg+"MobilePageActivity.java","""
            package com.giraffeslovebeauty.acmforever;
            import android.os.Bundle; import android.widget.LinearLayout; import java.util.concurrent.Callable;
            class MobilePageActivity {
                protected ApiClient api=new ApiClient(); protected LinearLayout body=new LinearLayout();
                protected boolean writing; protected Exception failure; protected int resets;
                interface Display { void show(Object value) throws Exception; }
                public void onCreate(Bundle state) {} protected void onResume() {}
                protected void createPage(String title) {} protected void resetPage(String title) { resets++; }
                protected LinearLayout card(LinearLayout parent) { return new LinearLayout(); }
                protected void runOnUiThread(Runnable work) { work.run(); }
                protected void read(Callable<Object> request,LinearLayout slot,boolean cache,Display display) {
                    try { display.show(request.call()); } catch(Exception error) { failure=error; }
                }
            }
            """);
        write(sources,files,pkg+"ApiClient.java","""
            package com.giraffeslovebeauty.acmforever;
            class ApiClient {
                boolean admin=true,passwordChange,networkFailure,sawDialogDuringRefresh; long generation=7; int reads;
                long sessionGeneration() { return generation; }
                void refreshSession() throws Exception {
                    reads++; sawDialogDuringRefresh=ModalDialogs.visible;
                    if(networkFailure)throw new java.io.IOException("Synthetic offline");
                }
                boolean isAdministrator() { return admin; } boolean requiresPasswordChange() { return passwordChange; }
                static class ApiException extends Exception { ApiException(int status,String message,boolean retry) { super(message); } }
            }
            """);
        write(sources,files,pkg+"ModalDialogs.java","""
            package com.giraffeslovebeauty.acmforever;
            class ModalDialogs { static boolean visible; static void close(Object owner) { visible=false; } }
            """);
        write(sources,files,pkg+"AdminLifecycleProbe.java","""
            package com.giraffeslovebeauty.acmforever;
            public class AdminLifecycleProbe extends AdminPageActivity {
                private int cleanups,renders;
                protected void onAccessLost() { cleanups++; }
                protected void renderAdmin() { renders++; }
                public static void run(String mode) {
                    AdminLifecycleProbe page=new AdminLifecycleProbe();page.onCreate(null);ModalDialogs.visible=true;
                    if(mode.equals("demotion"))page.api.admin=false;
                    if(mode.equals("account-switch"))page.api.generation++;
                    if(mode.equals("password-change"))page.api.passwordChange=true;
                    if(mode.equals("offline"))page.api.networkFailure=true;
                    if(mode.equals("writing"))page.writing=true;
                    page.onResume();
                    if(ModalDialogs.visible)throw new AssertionError("Sensitive dialog survived foreground revalidation: "+mode);
                    if(page.api.sawDialogDuringRefresh)throw new AssertionError("Dialog remained visible during session request");
                    if(mode.equals("admin")) {
                        if(page.renders!=1||page.cleanups!=0||!page.access())throw new AssertionError("Valid admin cannot resume");
                    } else if(mode.equals("writing")) {
                        if(page.api.reads!=0||page.renders!=0)throw new AssertionError("Inflight write must not be reset or replayed");
                    } else if(mode.equals("offline")) {
                        if(page.failure==null||page.renders!=0)throw new AssertionError("Failed verification must not render data");
                    } else if(page.access()||page.cleanups!=1||page.renders!=0||page.failure==null||page.resets!=1) {
                        throw new AssertionError("Rejected management access must clean snapshots and hide page");
                    }
                }
            }
            """);
        files.add(Path.of("src/main/java",pkg,"AdminPageActivity.java").toAbsolutePath().toString());
        String executable=System.getProperty("os.name").toLowerCase(java.util.Locale.ROOT).contains("win")?"javac.exe":"javac";
        Path compiler=Path.of(System.getProperty("java.home"),"bin",executable);
        assertTrue("Tests require a JDK",Files.isRegularFile(compiler));
        ArrayList<String> args=new ArrayList<>();
        java.util.Collections.addAll(args,compiler.toString(),"-proc:none","-encoding","UTF-8","-classpath",classes.toString(),"-d",classes.toString());
        args.addAll(files);Process process=new ProcessBuilder(args).redirectErrorStream(true).start();
        String diagnostics=new String(process.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
        assertEquals(diagnostics,0,process.waitFor());
    }
    private static void write(Path root,ArrayList<String> files,String name,String value) throws Exception {
        Path source=root.resolve(name);Files.createDirectories(source.getParent());Files.write(source,value.getBytes(StandardCharsets.UTF_8));files.add(source.toString());
    }
    private void verify(String mode) throws Exception {
        try(URLClassLoader loader=new URLClassLoader(new URL[]{classes.toUri().toURL()},null)) {
            loader.loadClass("com.giraffeslovebeauty.acmforever.AdminLifecycleProbe").getMethod("run",String.class).invoke(null,mode);
        }
    }
    @Test public void successfulAdminRevalidationClosesPreviousDetailsFirst() throws Exception { verify("admin"); }
    @Test public void demotionClosesDetailsAndInvokesSnapshotCleanup() throws Exception { verify("demotion"); }
    @Test public void accountSwitchClosesDetailsAndRejectsOldOwner() throws Exception { verify("account-switch"); }
    @Test public void mandatoryPasswordChangeClearsManagementDetails() throws Exception { verify("password-change"); }
    @Test public void failedNetworkCheckCannotKeepDetailsVisible() throws Exception { verify("offline"); }
    @Test public void returningDuringWriteClosesDetailsWithoutRestartingWrite() throws Exception { verify("writing"); }
}
