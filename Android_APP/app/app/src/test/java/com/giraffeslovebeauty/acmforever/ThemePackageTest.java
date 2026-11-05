package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.util.*;
import java.util.zip.*;

public class ThemePackageTest {
    private JSONObject settings()throws Exception{return new JSONObject().put("theme_source","acm").put("theme_primary",0xff83b8e5).put("theme_secondary",0xffeeeeee).put("theme_dark",false).put("theme_custom_color",true).put("secondary_custom_color",false).put("background_custom_color",true).put("bg_mode","image").put("bg_source","custom").put("bg_crop","[0.1,0.2,0.8,0.9]").put("bg_transparency",2).put("module_transparency",3).put("control_transparency",4);}
    @Test public void imageAndEverySettingSurviveByteExactRoundTrip()throws Exception{
        byte[] image=new byte[8192];new Random(19).nextBytes(image);JSONObject settings=settings();ThemePackage source=new ThemePackage("自定义主题",settings,null,image);ByteArrayOutputStream out=new ByteArrayOutputStream();source.write(out);ThemePackage imported=ThemePackage.read(new ByteArrayInputStream(out.toByteArray()));
        assertEquals(source.name,imported.name);assertArrayEquals(image,imported.image);assertEquals(ThemePackage.hash(image),ThemePackage.hash(imported.image));Iterator<String> names=settings.keys();while(names.hasNext()){String key=names.next();assertEquals(settings.get(key),imported.settings.get(key));}assertTrue(out.size()<image.length+1100);
    }
    @Test public void selectedWebTemplateBothProfilesAndOverridesSurvive()throws Exception{
        JSONObject colors=new JSONObject().put("primary","#123456").put("background","#ffffff").put("surface","#eeeeee").put("accent","#155bd8");JSONObject profile=new JSONObject().put("colors",colors).put("overrides",new JSONObject().put("hero","#151a1d").put("text","#112233"));JSONObject preset=new JSONObject().put("name","天使之城").put("design_template","angel-city").put("theme",new JSONObject().put("version",1).put("mode","dark").put("light",profile).put("dark",profile));
        ThemePackage source=new ThemePackage("官方配色",settings().put("theme_source","web").put("theme_dark",true),preset,new byte[]{1,2,3});ByteArrayOutputStream out=new ByteArrayOutputStream();source.write(out);ThemePackage restored=ThemePackage.read(new ByteArrayInputStream(out.toByteArray()));assertEquals("angel-city",restored.preset.getString("design_template"));assertEquals("#151a1d",restored.preset.getJSONObject("theme").getJSONObject("dark").getJSONObject("overrides").getString("hero"));assertTrue(restored.settings.getBoolean("theme_dark"));
    }
    @Test public void rejectsSecretsUnsupportedFieldsAndInvalidCrop()throws Exception{
        assertThrows(Exception.class,()->new ThemePackage("bad",settings().put("theme_custom_color",1),null,new byte[]{1}));
        assertThrows(Exception.class,()->new ThemePackage("bad",settings().put("saved_password","secret"),null,new byte[]{1}));assertThrows(Exception.class,()->new ThemePackage("bad",settings().put("bg_transparency",6),null,new byte[]{1}));assertThrows(Exception.class,()->ThemePackage.crop("[0,0,2,1]"));assertThrows(Exception.class,()->ThemePackage.crop("[0.8,0,0.1,1]"));assertThrows(Exception.class,()->new ThemePackage("bad",settings(),null,null));
    }
    @Test public void rejectsZipTraversalAndExpansion()throws Exception{
        ByteArrayOutputStream out=new ByteArrayOutputStream();try(ZipOutputStream zip=new ZipOutputStream(out)){zip.putNextEntry(new ZipEntry("../theme.json"));zip.write(1);zip.closeEntry();}assertThrows(Exception.class,()->ThemePackage.read(new ByteArrayInputStream(out.toByteArray())));
        ByteArrayOutputStream huge=new ByteArrayOutputStream();try(ZipOutputStream zip=new ZipOutputStream(huge)){zip.putNextEntry(new ZipEntry("theme.json"));zip.write(new byte[ThemePackage.MAX_JSON+1]);zip.closeEntry();}assertThrows(Exception.class,()->ThemePackage.read(new ByteArrayInputStream(huge.toByteArray())));
    }
    @Test public void rejectsTamperedImageAndLeavesDataUnmodified()throws Exception{
        JSONObject json=new JSONObject().put("format","acmforever.theme").put("version",1).put("name","篡改").put("settings",settings()).put("background",new JSONObject().put("path","background.bin").put("sizeBytes",3).put("sha256","0".repeat(64)));
        ByteArrayOutputStream out=new ByteArrayOutputStream();try(ZipOutputStream zip=new ZipOutputStream(out)){zip.putNextEntry(new ZipEntry("theme.json"));zip.write(json.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));zip.closeEntry();zip.putNextEntry(new ZipEntry("background.bin"));zip.write(new byte[]{1,2,3});zip.closeEntry();}assertThrows(Exception.class,()->ThemePackage.read(new ByteArrayInputStream(out.toByteArray())));
    }
}
