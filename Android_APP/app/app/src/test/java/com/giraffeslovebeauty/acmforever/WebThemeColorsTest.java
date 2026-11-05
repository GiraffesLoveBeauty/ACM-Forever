package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

public class WebThemeColorsTest {
    @Test public void officialAndDerivedNativeColoursMatchTheWebAlgorithm()throws Exception{
        JSONArray cases;try(java.io.InputStream in=getClass().getResourceAsStream("/web-theme-colors.json")){assertNotNull(in);cases=new JSONArray(new String(in.readAllBytes(),StandardCharsets.UTF_8));}
        for(int i=0;i<cases.length();i++){
            JSONObject example=cases.getJSONObject(i),profile=example.getJSONObject("profile"),c=profile.getJSONObject("colors"),t=example.getJSONObject("tokens");
            ThemePalette palette=new ThemePalette(argb(c.getString("primary")),argb(c.getString("background")),argb(c.getString("surface")),argb(c.getString("accent")),example.getBoolean("dark"),false,WebThemes.overrides(profile));
            String[] keys={"--bg","--panel","--text","--muted","--line","--link","--hero-bg","--hero-text","--on-accent","--selected-fg","--subtle-bg"};
            int[] actual={palette.background,palette.surface,palette.text,palette.muted,palette.line,palette.brand,palette.hero,palette.onHero,palette.onAccent,palette.onSelected,palette.selected};
            for(int j=0;j<keys.length;j++)assertEquals(example.getString("name")+" "+keys[j],t.getString(keys[j]),String.format(java.util.Locale.ROOT,"#%06x",actual[j]&0xffffff));
        }
    }
    private int argb(String color){return (int)(0xff000000L|Long.parseLong(color.substring(1),16));}
}
