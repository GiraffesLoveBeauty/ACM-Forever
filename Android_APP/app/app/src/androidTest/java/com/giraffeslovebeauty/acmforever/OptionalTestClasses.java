package com.giraffeslovebeauty.acmforever;
final class OptionalTestClasses {
    static void login(android.app.Instrumentation test){try{
        test.runOnMainSync(()->{}); // Wait for Application.onCreate before configuring the synthetic session.
        java.net.URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new java.net.URLStreamHandler(){
            @Override protected java.net.URLConnection openConnection(java.net.URL url)throws java.io.IOException{
                if(!"optional-ui.test.invalid".equals(url.getHost()))throw new java.io.IOException("External test traffic blocked");
                return new java.net.HttpURLConnection(url){
                    public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
                    public int getResponseCode(){return 200;}
                    public java.io.OutputStream getOutputStream(){return new java.io.ByteArrayOutputStream();}
                    public java.util.Map<String,java.util.List<String>> getHeaderFields(){return java.util.Collections.singletonMap("Set-Cookie",java.util.Collections.singletonList("session=optional-ui; Path=/; Secure; HttpOnly"));}
                    public java.io.InputStream getInputStream(){return new java.io.ByteArrayInputStream("{\"authenticated\":true,\"csrf_token\":\"test-only\",\"qq_id\":\"90000001\",\"role\":\"member\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                };
            }
        }:null);
        AcmApplication app=(AcmApplication)test.getTargetContext().getApplicationContext();
        app.api().setBaseUrl("https://optional-ui.test.invalid");app.api().setNetworkAvailable(()->true);app.api().login("90000001","Synthetic-Only!");
        test.waitForIdleSync();if(!app.api().isLoggedIn())throw new AssertionError("Synthetic login did not remain active");android.os.Bundle trace=new android.os.Bundle();trace.putString("stream","STEP: isolated optional UI login active\n");test.sendStatus(0,trace);
    }catch(Exception error){throw new AssertionError(error);}}
    static Class<?> type(String simple){try{return Class.forName("com.giraffeslovebeauty.acmforever."+simple);}catch(Exception e){throw new AssertionError("Install optional split for this smoke test: "+simple,e);}}
    static Object call(Object o,String name,Class<?>[] types,Object...args){try{java.lang.reflect.Method method=o.getClass().getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(o,args);}catch(Exception e){throw new AssertionError(e);}}
}
