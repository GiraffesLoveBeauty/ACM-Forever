package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Data-only compatibility with the Web theme export. No styles, scripts or remote assets. */
final class WebThemes {
    static final int MAX_BYTES=32768,MAX_SCHEMES=12;
    private static final String[] BASE={"primary","background","surface","accent"},OVERRIDES={"text","muted","border","link","selected","hero"};
    private static void keys(JSONObject object,String[] allowed,String... required)throws JSONException{
        Set<String> accepted=new HashSet<>(Arrays.asList(allowed));Iterator<String> names=object.keys();while(names.hasNext())if(!accepted.contains(names.next()))throw new JSONException("主题含不支持的字段");for(String key:required)if(!object.has(key)||object.isNull(key))throw new JSONException("主题缺少 "+key);
    }
    static String color(Object raw)throws JSONException{if(!(raw instanceof String)||!((String)raw).trim().matches("#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?"))throw new JSONException("主题颜色仅接受 #RGB 或 #RRGGBB");String value=((String)raw).trim().toLowerCase(Locale.ROOT);return value.length()==4?"#"+value.charAt(1)+value.charAt(1)+value.charAt(2)+value.charAt(2)+value.charAt(3)+value.charAt(3):value;}
    static JSONObject validate(JSONObject theme)throws JSONException{
        keys(theme,new String[]{"version","mode","light","dark"},"version","mode","light","dark");
        if(!(theme.get("version") instanceof Number)||theme.getDouble("version")!=1||!Arrays.asList("light","dark","system").contains(theme.get("mode")))throw new JSONException("不支持的主题版本或模式");
        JSONObject result=new JSONObject().put("version",1).put("mode",theme.getString("mode"));
        for(String mode:new String[]{"light","dark"}){
            JSONObject profile=theme.getJSONObject(mode);keys(profile,new String[]{"colors","overrides"},"colors");JSONObject source=profile.getJSONObject("colors");keys(source,BASE,BASE);JSONObject colors=new JSONObject(),overrides=new JSONObject();for(String name:BASE)colors.put(name,color(source.get(name)));
            if(profile.has("overrides")){JSONObject custom=profile.getJSONObject("overrides");keys(custom,OVERRIDES);for(String name:OVERRIDES)if(custom.has(name))overrides.put(name,color(custom.get(name)));}
            result.put(mode,new JSONObject().put("colors",colors).put("overrides",overrides));
        }
        return result;
    }
    static JSONArray parse(String text,String filename)throws Exception{
        if(text.getBytes(StandardCharsets.UTF_8).length>MAX_BYTES)throw new JSONException("主题文件不得超过 32 KB");JSONObject input=new JSONObject(text);JSONArray incoming;
        if(input.has("schemes")){keys(input,new String[]{"version","schemes"},"version","schemes");if(!(input.get("version") instanceof Number)||input.getDouble("version")!=1)throw new JSONException("不支持的主题库版本");incoming=input.getJSONArray("schemes");}
        else{incoming=new JSONArray().put(new JSONObject().put("name",filename==null?"网页主题":filename.replaceFirst("(?i)\\.json$","")).put("theme",input));}
        if(incoming.length()==0||incoming.length()>MAX_SCHEMES)throw new JSONException("一次可导入 1–12 套主题");JSONArray output=new JSONArray();
        for(int i=0;i<incoming.length();i++){JSONObject item=incoming.getJSONObject(i);keys(item,new String[]{"id","name","theme"},"name","theme");Object rawName=item.get("name");if(!(rawName instanceof String))throw new JSONException("主题名称必须是文字");String name=((String)rawName).replaceAll("[\\p{Cntrl}]","").trim();if(name.isEmpty())name="网页主题";if(name.length()>40)name=name.substring(0,40);JSONObject theme=validate(item.getJSONObject("theme"));byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(theme.toString().getBytes(StandardCharsets.UTF_8));StringBuilder id=new StringBuilder("import-");for(int n=0;n<8;n++)id.append(String.format(Locale.ROOT,"%02x",digest[n]&255));output.put(new JSONObject().put("id",id.toString()).put("name",name).put("theme",theme));}
        return output;
    }
    static JSONArray merge(JSONArray existing,JSONArray incoming)throws Exception{
        LinkedHashMap<String,JSONObject> items=new LinkedHashMap<>();for(JSONArray list:new JSONArray[]{existing,incoming})for(int i=0;i<list.length();i++){JSONObject item=list.getJSONObject(i);items.put(item.getString("id"),item);}if(items.size()>MAX_SCHEMES)throw new JSONException("本机最多保存 12 套导入主题");JSONArray out=new JSONArray();for(JSONObject item:items.values())out.put(item);return out;
    }
    static JSONObject profile(JSONObject preset,boolean dark)throws JSONException{
        if(preset.has("theme"))return validate(preset.getJSONObject("theme")).getJSONObject(dark?"dark":"light");
        JSONArray values=preset.getJSONArray(dark?"dark":"light");JSONObject colors=new JSONObject();for(int i=0;i<BASE.length;i++)colors.put(BASE[i],color(values.get(i)));return new JSONObject().put("colors",colors).put("overrides",new JSONObject());
    }
    static int[] overrides(JSONObject profile)throws JSONException{
        JSONObject source=profile.optJSONObject("overrides");int[] result=new int[6];if(source!=null)for(int i=0;i<OVERRIDES.length;i++)if(source.has(OVERRIDES[i]))result[i]=(int)(0xff000000L|Long.parseLong(color(source.get(OVERRIDES[i])).substring(1),16));return result;
    }
}
