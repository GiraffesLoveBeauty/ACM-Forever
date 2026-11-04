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
}
