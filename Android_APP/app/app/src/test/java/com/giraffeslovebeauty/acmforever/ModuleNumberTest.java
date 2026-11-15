package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class ModuleNumberTest {
    @Test public void fullPinyinTonesAppVersionAndCanonicalRomanBuild(){
        assertEquals("guan_1_fang_1_zhu_3_ti_2_ku_4-0.2.29-I",ModuleNumber.create("official-themes","0.2.29","I"));
        assertEquals("shou_3_ji_1_bian_4_jie_2_guan_3_li_3-0.2.29-IV",ModuleNumber.create("admin","0.2.29","IV"));
        for(String bad:new String[]{"","iiii","IIII","VX","0","I-extra"})assertThrows(IllegalArgumentException.class,()->ModuleNumber.create("admin","0.2.29",bad));
    }
    @Test public void numbersCannotChangeModuleOrAppIdentity(){
        String number=ModuleNumber.create("admin","0.2.29","II");assertEquals(number,ModuleNumber.validate("admin","0.2.29",number));
        assertThrows(IllegalArgumentException.class,()->ModuleNumber.validate("advanced","0.2.29",number));
        assertThrows(IllegalArgumentException.class,()->ModuleNumber.validate("admin","0.2.28",number));
    }
    @Test public void catalogNumbersAreOptionalAndNeverReplaceContentIdentity()throws Exception{
        JSONArray rows=new JSONArray();for(String id:ModuleSpec.IDS)rows.put(new JSONObject().put("id",id).put("kind",ModuleSpec.nativeModule(id)?"native":"assets").put("url",UpdateSources.asset("0.2.29",ModuleSpec.filename(id),false)).put("sha256","a".repeat(64)).put("sizeBytes",1234).put("revision",(ModuleSpec.nativeModule(id)?"n1-":"a1-")+"b".repeat(64)).put("number",ModuleNumber.create(id,"0.2.29","I")));
        JSONObject catalog=new JSONObject().put("schemaVersion",1).put("versionCode",43).put("versionName","0.2.29").put("modules",rows);
        ModuleSpec spec=ModuleSpec.parse(catalog,43,"0.2.29").get("official-themes");assertTrue(spec.revision.startsWith("a1-"));assertTrue(spec.number.endsWith("-I"));
        rows.getJSONObject(0).put("number",JSONObject.NULL);assertThrows(Exception.class,()->ModuleSpec.parse(catalog,43,"0.2.29"));
        rows.getJSONObject(0).remove("number");assertEquals(4,ModuleSpec.parse(catalog,43,"0.2.29").size());
    }
}
