package com.giraffeslovebeauty.acmforever;

import android.content.*;
import org.json.*;
import java.io.*;
import java.util.*;

/** Appearance-only snapshots. Credentials, sessions and server settings never enter this store. */
final class LocalThemes {
    static final String EXTRA="local_theme_id";
    private static final String[] KEYS={"theme_source","theme_preset","theme_dark","theme_primary","theme_secondary","theme_custom_color","secondary_custom_color","background_custom_color","web_imported_themes","bg_mode","bg_source","bg_color","bg_crop","bg_transparency","module_transparency","control_transparency"};
    static boolean valid(String id){return id!=null&&id.matches("[a-f0-9]{32}");}
    static SharedPreferences prefs(Context c,String id){if(!valid(id))throw new IllegalArgumentException("主题不存在");return c.getSharedPreferences("local_theme_"+id,0);}
    private static SharedPreferences registry(Context c){return c.getSharedPreferences("local_theme_library",0);}
    static JSONArray list(Context c){try{return new JSONArray(registry(c).getString("items","[]"));}catch(JSONException e){return new JSONArray();}}
    static boolean exists(Context c,String id){JSONArray items=list(c);for(int i=0;i<items.length();i++)if(id.equals(items.optJSONObject(i).optString("id")))return true;return false;}
    static String name(Context c,String id){JSONArray items=list(c);for(int i=0;i<items.length();i++)if(id.equals(items.optJSONObject(i).optString("id")))return items.optJSONObject(i).optString("name");return "我的主题";}
    static Context scope(Context c,String id){
        if(!valid(id)||!exists(c,id))return c;
        return new ContextWrapper(c){@Override public SharedPreferences getSharedPreferences(String name,int mode){return "acmforever_settings".equals(name)?LocalThemes.prefs(getBaseContext(),id):super.getSharedPreferences(name,mode);}};
    }
    static File image(Context c,String id){if(!valid(id))throw new IllegalArgumentException("无效主题");File dir=new File(c.getFilesDir(),"local-themes");if(!dir.isDirectory())dir.mkdirs();return new File(dir,id+".jpg");}
    private static void copy(File from,File to)throws IOException{
        File temp=new File(to.getParentFile(),to.getName()+".tmp");
        try{try(InputStream in=new FileInputStream(from);FileOutputStream out=new FileOutputStream(temp)){byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);out.getFD().sync();}if(!temp.renameTo(to))throw new IOException("无法保存背景图片");}finally{if(temp.exists())temp.delete();}
    }
    private static SharedPreferences.Editor snapshot(SharedPreferences source,SharedPreferences target){
        SharedPreferences.Editor edit=target.edit();Map<String,?> values=source.getAll();
        for(String key:KEYS){edit.remove(key);Object v=values.get(key);if(v instanceof String)edit.putString(key,(String)v);else if(v instanceof Integer)edit.putInt(key,(Integer)v);else if(v instanceof Boolean)edit.putBoolean(key,(Boolean)v);}
        return edit;
    }
    static synchronized String save(Context c)throws Exception{
        String id=UUID.randomUUID().toString().replace("-","");SharedPreferences source=AppAppearance.prefs(c),target=prefs(c,id);
        if(ProfileCover.file(c).isFile())copy(ProfileCover.file(c),image(c,id));
        if(!snapshot(source,target).putString("bg_image_id",id).commit())throw new IOException("主题保存失败");
        SharedPreferences registry=registry(c);int next=registry.getInt("next_name",1);JSONArray items=list(c);items.put(new JSONObject().put("id",id).put("name","未命名"+next));
        if(!registry.edit().putString("items",items.toString()).putInt("next_name",next+1).commit())throw new IOException("主题目录保存失败");return id;
    }
    static synchronized void apply(Context c,String id)throws Exception{
        if(!exists(c,id))throw new IOException("主题不存在");SharedPreferences from=prefs(c,id);
        if("image".equals(from.getString("bg_mode","solid"))&&!image(c,id).isFile())throw new IOException("该主题的本地背景图片已丢失");
        if(image(c,id).isFile())copy(image(c,id),new File(c.getFilesDir(),"profile-cover.jpg"));
        ProfileCover.invalidate();AppAppearance.changed(c,snapshot(from,AppAppearance.prefs(c)).remove("bg_image_id"));
    }
    static synchronized ThemePackage pack(Context c,String id)throws Exception{
        if(!exists(c,id))throw new IOException("主题不存在");SharedPreferences source=prefs(c,id);JSONObject data=new JSONObject();
        for(String key:KEYS){Object value=source.getAll().get(key);if(value!=null&&!"web_imported_themes".equals(key))data.put(key,value);}
        if(!data.has("theme_source"))data.put("theme_source","acm");if(!data.has("bg_mode"))data.put("bg_mode","solid");if(!data.has("bg_source"))data.put("bg_source","custom");
        JSONObject preset=null;if("web".equals(data.getString("theme_source"))){JSONObject selected=AppAppearance.findPreset(scope(c,id),source.getString("theme_preset","industrial"));JSONObject theme=new JSONObject().put("version",1).put("mode",source.getBoolean("theme_dark",false)?"dark":"light").put("light",WebThemes.profile(selected,false)).put("dark",WebThemes.profile(selected,true));preset=new JSONObject().put("name",selected.getString("name")).put("design_template",selected.optString("design_template","original")).put("theme",theme);}
        byte[] bytes=null;if(image(c,id).isFile())try(InputStream in=new FileInputStream(image(c,id))){bytes=ThemePackage.readLimited(in,ThemePackage.MAX_IMAGE);}
        return new ThemePackage(name(c,id),data,preset,bytes);
    }
    static synchronized String install(Context c,ThemePackage pack)throws Exception{
        if(pack.image!=null){android.graphics.BitmapFactory.Options bounds=new android.graphics.BitmapFactory.Options();bounds.inJustDecodeBounds=true;android.graphics.BitmapFactory.decodeByteArray(pack.image,0,pack.image.length,bounds);if(bounds.outWidth<=0||bounds.outHeight<=0||bounds.outWidth>100000||bounds.outHeight>100000)throw new IOException("主题背景不是有效图片");}
        String id=UUID.randomUUID().toString().replace("-","");boolean registered=false;SharedPreferences target=prefs(c,id);
        try{
            SharedPreferences.Editor edit=target.edit();Iterator<String> keys=pack.settings.keys();while(keys.hasNext()){String key=keys.next();Object value=pack.settings.get(key);if(value instanceof String)edit.putString(key,(String)value);else if(value instanceof Boolean)edit.putBoolean(key,(Boolean)value);else if(value instanceof Number)edit.putInt(key,((Number)value).intValue());}
            if(pack.preset!=null){String presetId="portable-"+id;JSONObject selected=new JSONObject(pack.preset.toString()).put("id",presetId);edit.putString("web_imported_themes",new JSONArray().put(selected).toString()).putString("theme_preset",presetId);}
            if(pack.image!=null)try(FileOutputStream out=new FileOutputStream(image(c,id))){out.write(pack.image);out.getFD().sync();}
            if(!edit.putString("bg_image_id",id).commit())throw new IOException("主题设置保存失败");
            JSONArray items=list(c);items.put(new JSONObject().put("id",id).put("name",pack.name));if(!registry(c).edit().putString("items",items.toString()).commit())throw new IOException("主题目录保存失败");registered=true;return id;
        }finally{if(!registered){image(c,id).delete();c.getApplicationContext().deleteSharedPreferences("local_theme_"+id);}}
    }
    static synchronized void rename(Context c,String id,String name)throws Exception{
        name=name.trim();if(name.isEmpty()||name.length()>40)throw new IllegalArgumentException("主题名需要 1–40 字");JSONArray items=list(c);boolean found=false;
        for(int i=0;i<items.length();i++)if(id.equals(items.getJSONObject(i).optString("id"))){items.getJSONObject(i).put("name",name);found=true;}
        if(!found)throw new IllegalArgumentException("主题不存在");if(!registry(c).edit().putString("items",items.toString()).commit())throw new IOException("重命名失败");
    }
    static synchronized void delete(Context c,String id)throws Exception{
        if(!valid(id)||!exists(c,id))throw new IllegalArgumentException("主题不存在");
        JSONArray old=list(c),remaining=new JSONArray();for(int i=0;i<old.length();i++)if(!id.equals(old.getJSONObject(i).optString("id")))remaining.put(old.getJSONObject(i));
        File original=image(c,id),staged=new File(original.getParentFile(),id+".deleting");boolean moved=original.isFile();
        if(moved&&!original.renameTo(staged))throw new IOException("无法删除主题背景图片");
        if(!registry(c).edit().putString("items",remaining.toString()).commit()){if(moved)staged.renameTo(original);throw new IOException("删除主题失败");}
        // Applied themes own a separate copy of their background and remain unchanged.
        c.getApplicationContext().deleteSharedPreferences("local_theme_"+id);
        if(staged.exists()&&!staged.delete())staged.deleteOnExit();
    }
}
