package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class ModuleSpecTest {
    private JSONObject catalog()throws Exception{
        JSONArray modules=new JSONArray();for(String id:ModuleSpec.IDS)modules.put(new JSONObject().put("id",id).put("kind",ModuleSpec.nativeModule(id)?"native":"assets").put("url",ModuleSpec.indexUrl("0.2.25").replace("modules.json",ModuleSpec.filename(id))).put("sha256","a".repeat(64)).put("sizeBytes",1234));
        return new JSONObject().put("schemaVersion",1).put("versionCode",39).put("versionName","0.2.25").put("modules",modules);
    }
    @Test public void exactSizesAndNames()throws Exception{java.util.Map<String,ModuleSpec> rows=ModuleSpec.parse(catalog(),39,"0.2.25");assertEquals(4,rows.size());assertEquals("此模块未下载，预计大小2KB，是否下载？",rows.get("advanced").confirmation());}
    @Test public void versionMustMatch()throws Exception{assertThrows(Exception.class,()->ModuleSpec.parse(catalog(),40,"0.2.25"));assertThrows(Exception.class,()->ModuleSpec.parse(catalog(),39,"0.2.26"));}
    @Test public void missingDuplicateAndUnknownDenied()throws Exception{JSONObject c=catalog();c.getJSONArray("modules").remove(0);assertThrows(Exception.class,()->ModuleSpec.parse(c,39,"0.2.25"));JSONObject d=catalog();d.getJSONArray("modules").put(1,d.getJSONArray("modules").getJSONObject(0));assertThrows(Exception.class,()->ModuleSpec.parse(d,39,"0.2.25"));}
    @Test public void untrustedUrlAndSizeDenied()throws Exception{for(Object size:new Object[]{0,-1,ModuleSpec.MAX_BYTES+1,"1234",1.2}){JSONObject c=catalog();c.getJSONArray("modules").getJSONObject(0).put("sizeBytes",size);assertThrows(Exception.class,()->ModuleSpec.parse(c,39,"0.2.25"));}JSONObject c=catalog();c.getJSONArray("modules").getJSONObject(0).put("url","https://elsewhere.invalid/m.apk");assertThrows(Exception.class,()->ModuleSpec.parse(c,39,"0.2.25"));}
    @Test public void manifestCannotSwitchModuleVersion()throws Exception{JSONObject v=new JSONObject().put("packageName","com.giraffeslovebeauty.acmforever").put("versionCode",39).put("versionName","0.2.25").put("apkUrl","https://example.invalid/base.apk").put("sha256","a".repeat(64)).put("modulesUrl",ModuleSpec.indexUrl("0.2.26"));assertThrows(Exception.class,()->new UpdateManifest(v,"com.giraffeslovebeauty.acmforever"));}
}
