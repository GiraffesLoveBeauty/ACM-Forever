package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Isolated transport for the split mirror PR; never downloads an APK or contacts a server. */
final class MirrorUpdatesUiSmoke {
    static void run(Instrumentation test){
        Context context=test.getTargetContext();SharedPreferences prefs=AppAppearance.prefs(context);Map<String,?> saved=new HashMap<>(prefs.getAll());
        Bundle result=new Bundle();int code=Activity.RESULT_CANCELED;List<String> requests=Collections.synchronizedList(new ArrayList<>());boolean[] malformed={false};
        try{
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){@Override protected URLConnection openConnection(URL url)throws IOException{
                if(!Arrays.asList("cjluacmpanel.tail1b9e55.ts.net","github.com","mirror.test.invalid").contains(url.getHost()))throw new IOException("External traffic forbidden");
                return new HttpURLConnection(url){public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
                    public int getResponseCode(){requests.add(url.toString());return url.getHost().equals("github.com")||malformed[0]&&url.getHost().equals("cjluacmpanel.tail1b9e55.ts.net")?200:503;}
                    public InputStream getErrorStream(){return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));}
                    public InputStream getInputStream(){String json=url.getHost().equals("github.com")?"{\"packageName\":\"com.giraffeslovebeauty.acmforever\",\"versionCode\":1,\"versionName\":\"0.0.1\",\"channel\":\"debug\",\"apkUrl\":\"https://mirror.test.invalid/app.apk\",\"sha256\":\""+String.join("",Collections.nCopies(64,"a"))+"\"}":"{}";return new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8));}
                };
            }}:null);
            AppUpdates updates=((AcmApplication)context.getApplicationContext()).updates();
            main(test,()->{updates.source("");updates.check(false);});waitDone(test,updates);
            check(updates.error().isEmpty()&&requests.size()==2&&requests.get(0).contains("cjluacmpanel.tail1b9e55.ts.net")&&requests.get(1).contains("github.com"),"primary HTTP failure falls back once to GitHub");
            requests.clear();main(test,()->{updates.source("https://mirror.test.invalid/custom-update");updates.check(false);});waitDone(test,updates);
            check(!updates.error().isEmpty()&&requests.size()==1&&requests.get(0).contains("mirror.test.invalid"),"custom source failure never contacts official sources");
            requests.clear();malformed[0]=true;main(test,()->{updates.source("");updates.check(false);});waitDone(test,updates);
            check(!updates.error().isEmpty()&&requests.size()==1&&requests.get(0).contains("cjluacmpanel.tail1b9e55.ts.net"),"invalid manifest is rejected without fallback");
            result.putString("stream","PASS: self-hosted HTTP failure uses GitHub fallback; custom source isolated; malformed primary fails closed; no APK download or production traffic.\n");code=Activity.RESULT_OK;
        }catch(Throwable failure){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(failure));}
        finally{SharedPreferences.Editor edit=prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){Object v=entry.getValue();String k=entry.getKey();if(v instanceof String)edit.putString(k,(String)v);else if(v instanceof Boolean)edit.putBoolean(k,(Boolean)v);else if(v instanceof Integer)edit.putInt(k,(Integer)v);else if(v instanceof Long)edit.putLong(k,(Long)v);else if(v instanceof Float)edit.putFloat(k,(Float)v);}edit.commit();}test.finish(code,result);
    }
    private static void main(Instrumentation test,Runnable work){Throwable[] failure={null};test.runOnMainSync(()->{try{work.run();}catch(Throwable e){failure[0]=e;}});if(failure[0]!=null)throw new AssertionError(failure[0]);}
    private static void waitDone(Instrumentation test,AppUpdates updates)throws Exception{long end=SystemClock.uptimeMillis()+8000;while(SystemClock.uptimeMillis()<end){boolean[] busy={false};main(test,()->busy[0]=updates.busy());if(!busy[0])return;Thread.sleep(50);}throw new AssertionError("update check timeout");}
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
}
