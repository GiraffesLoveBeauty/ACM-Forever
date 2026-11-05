package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Portable appearance data only. Images are copied byte-for-byte, never transcoded. */
final class ThemePackage {
    static final int MAX_JSON=65536, MAX_IMAGE=20*1024*1024;
    static final String EXTENSION=".acmtheme";
    static final Set<String> STRINGS=new HashSet<>(Arrays.asList("theme_source","theme_preset","bg_mode","bg_source","bg_crop"));
    static final Set<String> COLORS=new HashSet<>(Arrays.asList("theme_primary","theme_secondary","bg_color"));
    static final Set<String> FLAGS=new HashSet<>(Arrays.asList("theme_dark","theme_custom_color","secondary_custom_color","background_custom_color"));
    static final Set<String> STOPS=new HashSet<>(Arrays.asList("bg_transparency","module_transparency","control_transparency"));
    final JSONObject settings,preset;final String name;final byte[] image;
    ThemePackage(String name,JSONObject settings,JSONObject preset,byte[] image)throws Exception{
        this.name=name.trim();if(this.name.isEmpty()||this.name.length()>40||this.name.matches(".*[\\p{Cntrl}].*"))throw new IOException("主题名称需要 1–40 字");
        this.settings=validateSettings(settings);this.preset=preset==null?null:validatePreset(preset);this.image=image;
        if(image!=null&&(image.length==0||image.length>MAX_IMAGE))throw new IOException("背景图片须在 20 MB 以内");
        if("image".equals(settings.optString("bg_mode"))&&image==null)throw new IOException("主题缺少背景原图");
        if("web".equals(settings.optString("theme_source"))&&this.preset==null)throw new IOException("主题缺少网页模板配色");
    }
    private static void only(JSONObject object,Set<String> keys)throws Exception{
        Iterator<String> names=object.keys();while(names.hasNext())if(!keys.contains(names.next()))throw new IOException("主题包含不支持的字段");
    }
    static JSONObject validateSettings(JSONObject source)throws Exception{
        Set<String> allowed=new HashSet<>(STRINGS);allowed.addAll(COLORS);allowed.addAll(STOPS);allowed.addAll(FLAGS);only(source,allowed);
        JSONObject out=new JSONObject();Iterator<String> names=source.keys();while(names.hasNext()){
            String key=names.next();Object value=source.get(key);
            if(STRINGS.contains(key)){if(!(value instanceof String)||((String)value).length()>256)throw new IOException("主题文字字段无效");}
            else if(FLAGS.contains(key)){if(!(value instanceof Boolean))throw new IOException("主题选项无效");}
            else {if(!(value instanceof Number)||!Double.isFinite(((Number)value).doubleValue())||((Number)value).doubleValue()!=((Number)value).intValue())throw new IOException("主题数值无效");if(STOPS.contains(key)&&(((Number)value).intValue()<0||((Number)value).intValue()>5))throw new IOException("透明度必须为六档之一");}
            out.put(key,value);
        }
        if(!Arrays.asList("acm","web").contains(out.optString("theme_source"))||!Arrays.asList("solid","gradient","image").contains(out.optString("bg_mode"))||!Arrays.asList("theme","custom").contains(out.optString("bg_source")))throw new IOException("主题或背景类型无效");
        crop(out.optString("bg_crop","[0,0,1,1]"));return out;
    }
    static float[] crop(String json)throws Exception{
        JSONArray a=new JSONArray(json);if(a.length()!=4)throw new IOException("裁剪范围无效");float[] c=new float[4];
        for(int i=0;i<4;i++){double v=a.getDouble(i);if(!Double.isFinite(v)||v<0||v>1)throw new IOException("裁剪范围无效");c[i]=(float)v;}
        if(c[2]<=c[0]||c[3]<=c[1])throw new IOException("裁剪范围无效");return c;
    }
    static JSONObject validatePreset(JSONObject p)throws Exception{
        only(p,new HashSet<>(Arrays.asList("name","design_template","theme")));String design=p.getString("design_template");
        if(!Arrays.asList("original","phase","angel-city","minecraft").contains(design))throw new IOException("当前版本不支持该模板");
        String name=p.getString("name");if(name.length()>40)throw new IOException("模板名称过长");
        return new JSONObject().put("name",name).put("design_template",design).put("theme",WebThemes.validate(p.getJSONObject("theme")));
    }
    static String hash(byte[] bytes)throws Exception{byte[] digest=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder result=new StringBuilder();for(byte b:digest)result.append(String.format(Locale.ROOT,"%02x",b&255));return result.toString();}
    void write(OutputStream stream)throws Exception{
        JSONObject json=new JSONObject().put("format","acmforever.theme").put("version",1).put("name",name).put("settings",settings);
        if(preset!=null)json.put("webPreset",preset);
        if(image!=null)json.put("background",new JSONObject().put("path","background.bin").put("sizeBytes",image.length).put("sha256",hash(image)));
        byte[] metadata=json.toString().getBytes(StandardCharsets.UTF_8);if(metadata.length>MAX_JSON)throw new IOException("主题配置过大");
        try(ZipOutputStream zip=new ZipOutputStream(stream)){
            zip.putNextEntry(new ZipEntry("theme.json"));zip.write(metadata);zip.closeEntry();
            if(image!=null){ZipEntry entry=new ZipEntry("background.bin");CRC32 crc=new CRC32();crc.update(image);entry.setMethod(ZipEntry.STORED);entry.setSize(image.length);entry.setCompressedSize(image.length);entry.setCrc(crc.getValue());zip.putNextEntry(entry);zip.write(image);zip.closeEntry();}
        }
    }
    static ThemePackage read(InputStream stream)throws Exception{
        byte[] metadata=null,image=null;Set<String> seen=new HashSet<>();
        try(ZipInputStream zip=new ZipInputStream(stream)){
            ZipEntry entry;while((entry=zip.getNextEntry())!=null){String name=entry.getName();if(entry.isDirectory()||!Arrays.asList("theme.json","background.bin").contains(name)||!seen.add(name))throw new IOException("主题包含非法或重复文件");
                byte[] bytes=readLimited(zip,"theme.json".equals(name)?MAX_JSON:MAX_IMAGE);if("theme.json".equals(name))metadata=bytes;else image=bytes;zip.closeEntry();}
        }
        if(metadata==null)throw new IOException("主题包缺少 theme.json");JSONObject json=new JSONObject(new String(metadata,StandardCharsets.UTF_8));
        only(json,new HashSet<>(Arrays.asList("format","version","name","settings","webPreset","background")));
        if(!"acmforever.theme".equals(json.getString("format"))||!(json.get("version") instanceof Number)||json.getDouble("version")!=1)throw new IOException("不支持的主题包格式");
        if(json.has("background")){JSONObject bg=json.getJSONObject("background");only(bg,new HashSet<>(Arrays.asList("path","sizeBytes","sha256")));if(image==null||!"background.bin".equals(bg.getString("path"))||bg.getLong("sizeBytes")!=image.length||!hash(image).equals(bg.getString("sha256")))throw new IOException("背景原图校验失败");}else if(image!=null)throw new IOException("主题包含未声明图片");
        return new ThemePackage(json.getString("name"),json.getJSONObject("settings"),json.optJSONObject("webPreset"),image);
    }
    static byte[] readLimited(InputStream in,int limit)throws IOException{if(in==null)throw new IOException("无法打开文件");ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>limit)throw new IOException("文件超过大小限制");out.write(buffer,0,n);}return out.toByteArray();}
}
