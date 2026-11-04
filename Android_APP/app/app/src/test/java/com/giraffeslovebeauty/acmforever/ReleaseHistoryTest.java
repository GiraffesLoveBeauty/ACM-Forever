package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import static org.junit.Assert.*;

public class ReleaseHistoryTest {
    private JSONObject entry(String version)throws Exception{return new JSONObject().put("versionName",version).put("summary","本版摘要").put("changes",new JSONArray().put("本版变更")).put("notes",new JSONArray().put("使用说明"));}
    private JSONObject history(String... versions)throws Exception{JSONArray entries=new JSONArray();for(String version:versions)entries.put(entry(version));return new JSONObject().put("schemaVersion",1).put("entries",entries);}
    @Test public void parsesNumericallyOrderedHistoryAndReadableDetails()throws Exception{
        ReleaseHistory parsed=ReleaseHistory.parse(history("0.2.13","0.2.9","0.1.12").toString(),"0.2.13");
        assertEquals(3,parsed.entries.size());String details=parsed.entries.get(0).details();
        assertTrue(details.contains("更新日志\n• 本版变更"));assertTrue(details.contains("更新说明\n• 使用说明"));assertTrue(details.contains("不代表服务器"));
    }
    @Test public void rejectsStaleOrFutureFirstEntry()throws Exception{assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.12").toString(),"0.2.13"));assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.14").toString(),"0.2.13"));}
    @Test public void rejectsDuplicatesAndAscendingOrder()throws Exception{assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.13","0.2.13").toString(),"0.2.13"));assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.13","0.2.9","0.2.10").toString(),"0.2.13"));}
    @Test public void rejectsInvalidSchemaVersionOrEmptyHistory()throws Exception{assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.13").put("schemaVersion",2).toString(),"0.2.13"));assertThrows(JSONException.class,()->ReleaseHistory.parse(history("0.2.beta").toString(),"0.2.beta"));assertThrows(JSONException.class,()->ReleaseHistory.parse(history().toString(),"0.2.13"));}
    @Test public void rejectsMissingOrBlankChanges()throws Exception{
        JSONObject root=history("0.2.13");root.getJSONArray("entries").getJSONObject(0).put("changes",new JSONArray());assertThrows(JSONException.class,()->ReleaseHistory.parse(root.toString(),"0.2.13"));
        root.getJSONArray("entries").getJSONObject(0).put("changes",new JSONArray().put("  "));assertThrows(JSONException.class,()->ReleaseHistory.parse(root.toString(),"0.2.13"));
    }
    @Test public void historyCannotBeMutatedAfterParsing()throws Exception{ReleaseHistory parsed=ReleaseHistory.parse(history("0.2.13").toString(),"0.2.13");assertThrows(UnsupportedOperationException.class,()->parsed.entries.clear());assertThrows(UnsupportedOperationException.class,()->parsed.entries.get(0).changes.clear());}
    @Test public void bundledHistoryMatchesBuildAndIncludesEarlierReleases()throws Exception{
        String config=new String(Files.readAllBytes(Paths.get("build.gradle")),StandardCharsets.UTF_8);
        java.util.regex.Matcher version=java.util.regex.Pattern.compile("versionName '([^']+)'").matcher(config);assertTrue(version.find());
        JSONObject root=new JSONObject(new String(Files.readAllBytes(Paths.get("src/main/assets/"+ReleaseHistory.ASSET)),StandardCharsets.UTF_8));
        ReleaseHistory parsed=ReleaseHistory.parse(root.toString(),version.group(1));assertTrue(parsed.entries.size()>=27);assertEquals("0.1.0",parsed.entries.get(parsed.entries.size()-1).versionName);
        java.util.regex.Matcher code=java.util.regex.Pattern.compile("versionCode ([0-9]+)").matcher(config);assertTrue(code.find());assertEquals(Integer.parseInt(code.group(1)),root.getInt("currentVersionCode"));
    }
}
