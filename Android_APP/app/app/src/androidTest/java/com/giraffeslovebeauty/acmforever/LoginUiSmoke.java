package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Test APK only. Uses Android Keystore and the real login/cache UI with isolated responses. */
final class LoginUiSmoke {
    private final Instrumentation test;
    private Activity activity;
    private LoginUiSmoke(Instrumentation test){this.test=test;}
    static void run(Instrumentation test){new LoginUiSmoke(test).execute();}
    private void execute(){
        Bundle output=new Bundle();int result=Activity.RESULT_CANCELED;
        AcmApplication app=(AcmApplication)test.getTargetContext().getApplicationContext();ApiClient api=app.api();
        SharedPreferences prefs=app.getSharedPreferences("acmforever_settings",Context.MODE_PRIVATE);String original=api.getBaseUrl();
        try {
            URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
                @Override protected URLConnection openConnection(URL url)throws IOException{
                    if(!"login.test.invalid".equals(url.getHost()))throw new IOException("External traffic forbidden by test");
                    return new Fake(url);
                }
            }:null);
            prefs.edit().putString("api_base_url","https://login.test.invalid").putBoolean("auto_login",false).putBoolean("save_password",false).putString("remembered_account","").apply();
            api.setBaseUrl("https://login.test.invalid");api.setNetworkAvailable(()->true);
            activity=test.startActivitySync(new Intent().setClassName(test.getTargetContext(),MainActivity.class.getName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            await(()->find("Cache verification topic")!=null,4000,"initial forum load");
            clickDescription("排名");await(()->find("每一题，都算数")!=null,4000,"rank navigation");
            java.util.concurrent.atomic.AtomicBoolean online=new java.util.concurrent.atomic.AtomicBoolean(false);java.util.concurrent.atomic.AtomicInteger checks=new java.util.concurrent.atomic.AtomicInteger();
            api.setNetworkAvailable(()->{checks.incrementAndGet();return online.get();});clickDescription("主页");
            await(()->find("Cache verification topic")!=null,1500,"cached page must render before network recovery");
            await(()->find("API连接失败")!=null,12000,"ten second warning");Thread.sleep(5500);check(findOnMain("API连接失败"),"warning stays visible during retries");clickDescription("关闭API连接失败提示");
            await(()->find("API连接失败")==null,1000,"dismiss warning");
            int previousChecks=checks.get();await(()->checks.get()>previousChecks,12000,"retry continues after warning dismissal");online.set(true);
            await(()->find("重连成功")!=null,12000,"automatic reconnect reports success without navigation");
            long recovered=android.os.SystemClock.uptimeMillis();await(()->find("重连成功")==null,4200,"recovery banner closes after three seconds");check(android.os.SystemClock.uptimeMillis()-recovered>=2400,"recovery banner remains visible for three seconds");
            api.setNetworkAvailable(()->true);clickDescription("进入账号设置");await(()->find("自动登录")!=null,4000,"login choices");
            test.runOnMainSync(()->{
                EditText user=field("用户名 / QQ"),password=field("密码");user.setText("90000001");password.setText("Native-Test-Password!");password.setSelection(4);
                View eye=description("显示密码");eye.performClick();check(password.getTransformationMethod() instanceof android.text.method.HideReturnsTransformationMethod,"eye reveals password");check(password.getSelectionStart()==4,"eye preserves selection");
                description("隐藏密码").performClick();check(password.getTransformationMethod() instanceof android.text.method.PasswordTransformationMethod,"eye masks password");
                ((CheckBox)find("自动登录")).setChecked(true);check(((CheckBox)find("记住账号")).isChecked()&&((CheckBox)find("记住密码")).isChecked(),"automatic dependencies");
            });
            clickText("登录");await(()->api.isLoggedIn()&&prefs.contains("password_cipher"),7000,"encrypted login save");
            SessionVault reopened=new SessionVault(prefs);check("Native-Test-Password!".equals(reopened.readPassword(api.getBaseUrl(),"90000001")),"password survives new vault instance");
            check(reopened.readPassword(api.getBaseUrl(),"90000002").isEmpty(),"password cannot cross accounts");
            check("Native-Test-Password!".equals(reopened.readPassword(api.getBaseUrl(),"90000001")),"other account lookup does not erase password");
            check(!prefs.getString("password_cipher","").contains("Native-Test-Password!"),"no plaintext password");
            ApiClient cold=new ApiClient();cold.setBaseUrl(api.getBaseUrl());cold.setNetworkAvailable(()->true);
            check(LoginRecovery.restore(cold,new LoginRecovery.StoredLogin(){
                public boolean automatic(){return prefs.getBoolean("auto_login",false);}public String session()throws Exception{return reopened.read(cold.getBaseUrl());}
                public String account(){return "90000001";}public String password(){return reopened.readPassword(cold.getBaseUrl(),account());}
                public void clearSession(){reopened.clear();}public void invalidPassword(){reopened.clearPassword();}
            }),"cold client recovers encrypted session");
            api.setNetworkAvailable(()->false);try{api.logout();}catch(ApiClient.NoNetworkException expected){}
            check(!prefs.contains("password_cipher")&&!prefs.contains("session_cipher")&&!prefs.getBoolean("auto_login",true),"offline logout clears persisted login");
            output.putString("stream","PASS: cache before refresh, ten-second persistent warning, continuous retries after dismissal, green recovery, login choices, eye/cursor, Android Keystore password, account binding, cold session recovery, offline logout.\n");output.putBoolean("passed",true);result=Activity.RESULT_OK;
        }catch(Throwable e){output.putString("stream","FAIL: "+android.util.Log.getStackTraceString(e));output.putBoolean("passed",false);}
        finally{if(activity!=null)test.runOnMainSync(()->activity.finish());try{api.logout();}catch(Exception ignored){}prefs.edit().remove("api_base_url").remove("remembered_account").putBoolean("remember_account",false).apply();api.setBaseUrl(original);}
        test.finish(result,output);
    }
    private void check(boolean okay,String reason){if(!okay)throw new AssertionError(reason);}
    private boolean findOnMain(String text){boolean[] found={false};test.runOnMainSync(()->found[0]=find(text)!=null);return found[0];}
    private void await(java.util.function.BooleanSupplier condition,long timeout,String reason)throws Exception{
        long end=System.currentTimeMillis()+timeout;while(System.currentTimeMillis()<end){boolean[] okay={false};test.runOnMainSync(()->okay[0]=condition.getAsBoolean());if(okay[0])return;Thread.sleep(60);}throw new AssertionError(reason);
    }
    private View walk(View v,java.util.function.Predicate<View> match){if(v.isShown()&&match.test(v))return v;if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){View found=walk(g.getChildAt(i),match);if(found!=null)return found;}}return null;}
    private View find(String text){return walk(activity.getWindow().getDecorView(),v->v instanceof TextView&&text.equals(((TextView)v).getText().toString()));}
    private View description(String value){return walk(activity.getWindow().getDecorView(),v->value.contentEquals(v.getContentDescription()==null?"":v.getContentDescription()));}
    private EditText field(String hint){return (EditText)walk(activity.getWindow().getDecorView(),v->v instanceof EditText&&hint.contentEquals(((EditText)v).getHint()));}
    private void clickText(String text){test.runOnMainSync(()->{View v=find(text);check(v!=null,"Missing "+text);v.performClick();});}
    private void clickDescription(String text){test.runOnMainSync(()->{View v=description(text);check(v!=null,"Missing "+text);v.performClick();});}
    private static final class Fake extends HttpURLConnection {
        Fake(URL url){super(url);}@Override public void connect(){}@Override public void disconnect(){}@Override public boolean usingProxy(){return false;}@Override public int getResponseCode(){return url.getPath().equals("/api/mobile/v1/capabilities")?404:200;}
        @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public Map<String,List<String>> getHeaderFields(){return url.getPath().endsWith("/login")?Collections.singletonMap("Set-Cookie",Collections.singletonList("session=isolated-native; Path=/; Secure; HttpOnly; Max-Age=600")):Collections.emptyMap();}
        @Override public InputStream getInputStream(){
            String p=url.getPath(),body=p.endsWith("/auth/me")?"{\"authenticated\":true,\"csrf_token\":\"native-test\",\"qq_id\":\"90000001\",\"role\":\"member\"}":p.endsWith("/forum/posts")?"{\"rows\":[{\"id\":1,\"title\":\"Cache verification topic\",\"excerpt\":\"Test APK only\"}],\"total\":1,\"page\":1}":p.endsWith("/leaderboard")?"{\"rows\":[],\"total\":0,\"page\":1,\"positive_only\":true}":p.endsWith("/me/profile")?"{\"user\":{\"name\":\"Isolated test\",\"qq_id\":\"90000001\"}}":p.contains("/mine/")||p.endsWith("/drafts")?"[]":"{}";
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
        }
    }
}
