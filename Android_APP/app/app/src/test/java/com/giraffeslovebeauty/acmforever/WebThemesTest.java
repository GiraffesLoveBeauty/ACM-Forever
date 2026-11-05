package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class WebThemesTest {
    private JSONObject theme()throws Exception{
        JSONObject colors=new JSONObject().put("primary","#123").put("background","#ffffff").put("surface","#eeeeee").put("accent","#155bd8");
        JSONObject profile=new JSONObject().put("colors",colors).put("overrides",new JSONObject().put("hero","#151a1d").put("selected","#202020"));
        return new JSONObject().put("version",1).put("mode","system").put("light",profile).put("dark",new JSONObject(profile.toString()));
    }
    @Test public void actualWebExportPreservesBothModesAndOverrides()throws Exception{
        JSONArray schemes=WebThemes.parse(theme().toString(),"天使之城.json");JSONObject item=schemes.getJSONObject(0);
        assertEquals("天使之城",item.getString("name"));assertTrue(item.getString("id").startsWith("import-"));
        JSONObject profile=WebThemes.profile(item,false);assertEquals("#112233",profile.getJSONObject("colors").getString("primary"));
        assertEquals(0xff151a1d,WebThemes.overrides(profile)[5]);assertEquals(0xff202020,WebThemes.overrides(profile)[4]);
    }
    @Test public void libraryDeduplicatesIdenticalImports()throws Exception{
        JSONObject a=new JSONObject().put("name","one").put("theme",theme());
        JSONArray imported=WebThemes.parse(new JSONObject().put("version",1).put("schemes",new JSONArray().put(a).put(a)).toString(),"library.json");
        assertEquals(1,WebThemes.merge(new JSONArray(),imported).length());
    }
    @Test public void rejectsScriptsForeignFieldsAndInvalidColours()throws Exception{
        JSONObject t=theme();t.put("css","url(https://example.invalid)");assertThrows(JSONException.class,()->WebThemes.parse(t.toString(),"x.json"));
        JSONObject bad=theme();bad.getJSONObject("light").getJSONObject("colors").put("primary","red");assertThrows(JSONException.class,()->WebThemes.validate(bad));
        assertThrows(JSONException.class,()->WebThemes.color("#ffffffff"));
    }
    @Test public void limitsSizeAndNumberOfSchemes()throws Exception{
        assertThrows(JSONException.class,()->WebThemes.parse(" ".repeat(32769),"x.json"));
        JSONArray entries=new JSONArray();for(int i=0;i<13;i++)entries.put(new JSONObject().put("id","id-"+i));
        assertThrows(JSONException.class,()->WebThemes.merge(new JSONArray(),entries));
        JSONObject unsupported=theme().put("version",2);assertThrows(JSONException.class,()->WebThemes.validate(unsupported));
    }
    @Test public void moduleTransparencyHasSixIndependentStops(){
        int[] alpha={255,204,153,102,51,0};for(int i=0;i<6;i++){int colour=ThemePalette.module(0xffabcdef,i);assertEquals(alpha[i],colour>>>24);assertEquals(0xabcdef,colour&0xffffff);}
        assertEquals(255,ThemePalette.module(0xffffffff,-5)>>>24);assertEquals(0,ThemePalette.module(0xffffffff,10)>>>24);
    }
    @Test public void industrialBothModesRetainEveryColourAfterPortablePackageRoundTrip()throws Exception{
        JSONObject preset=new JSONObject().put("id","industrial").put("light",new JSONArray("[\"#292c29\",\"#e8e9e4\",\"#f8f8f3\",\"#f1f547\"]")).put("dark",new JSONArray("[\"#e2e5d8\",\"#1a1d19\",\"#242823\",\"#f1f547\"]"));
        JSONObject snapshot=new JSONObject().put("name","工业黄").put("design_template","original").put("theme",new JSONObject().put("version",1).put("mode","system").put("light",WebThemes.profile(preset,false)).put("dark",WebThemes.profile(preset,true)));
        ThemePackage pack=new ThemePackage("工业黄",new JSONObject().put("theme_source","web").put("bg_mode","solid").put("bg_source","theme"),snapshot,null);
        java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();pack.write(out);JSONObject portable=ThemePackage.read(new java.io.ByteArrayInputStream(out.toByteArray())).preset.put("id","portable-roundtrip");
        for(boolean dark:new boolean[]{false,true}){
            JSONObject original=new JSONObject().put("colors",WebThemes.profile(preset,dark).getJSONObject("colors")).put("overrides",new JSONObject());
            ThemePalette expected=palette(original,dark,true),actual=palette(WebThemes.profile(portable,dark),dark,false);
            assertEquals(dark?0xff151814:0xff20231f,actual.hero);
            assertArrayEquals(colours(expected),colours(actual));
            assertEquals(6,WebThemes.profile(portable,dark).getJSONObject("overrides").length());
        }
    }
    @Test public void industrialSnapshotPreservesExplicitOverrides()throws Exception{
        JSONObject preset=new JSONObject().put("id","industrial").put("theme",theme());
        for(boolean dark:new boolean[]{false,true}){
            JSONObject resolved=WebThemes.profile(preset,dark).getJSONObject("overrides");
            assertEquals("#151a1d",resolved.getString("hero"));assertEquals("#202020",resolved.getString("selected"));assertEquals(6,resolved.length());
        }
        assertEquals(2,preset.getJSONObject("theme").getJSONObject("light").getJSONObject("overrides").length());
    }
    private ThemePalette palette(JSONObject profile,boolean dark,boolean industrial)throws Exception{
        JSONObject c=profile.getJSONObject("colors");int[] base=new int[4];String[] keys={"primary","background","surface","accent"};for(int i=0;i<keys.length;i++)base[i]=(int)(0xff000000L|Long.parseLong(c.getString(keys[i]).substring(1),16));return new ThemePalette(base[0],base[1],base[2],base[3],dark,industrial,WebThemes.overrides(profile));
    }
    private int[] colours(ThemePalette p){return new int[]{p.primary,p.background,p.surface,p.accent,p.text,p.muted,p.line,p.brand,p.hero,p.onHero,p.onAccent,p.onSelected,p.selected,p.cat};}
}
