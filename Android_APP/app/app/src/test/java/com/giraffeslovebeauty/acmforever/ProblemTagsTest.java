package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class ProblemTagsTest {
    @Test public void exactLabelHasIndependentEncodedParameter() {
        assertEquals("&problem_tag=dp",ProblemTags.parameter(" dp "));
        assertEquals("&problem_tag=%25_%26+%E4%B8%AD%E6%96%87",ProblemTags.parameter("%_& 中文"));
        assertEquals("&problem_tag=digit+dp",ProblemTags.parameter("digit dp"));
        assertEquals("",ProblemTags.parameter(" "));assertEquals("",ProblemTags.parameter(null));
    }
    @Test public void labelsRemainOpaqueRatherThanSplitOrTranslated() {
        assertEquals(" DP, graphs ".trim(),ProblemTags.checked(" DP, graphs "));
        assertEquals("&problem_tag=DP%2C+graphs",ProblemTags.parameter("DP, graphs"));
    }
    @Test public void candidatesComeOnlyFromActualResponse() throws Exception {
        assertTrue(ProblemTags.options(new JSONObject().put("tags",new JSONArray())).isEmpty());
        assertEquals(Arrays.asList("dp","digit dp","math"),ProblemTags.options(new JSONObject().put("tags",new JSONArray(Arrays.asList("dp","digit dp","DP"," "," math ")))));
    }
    @Test public void malformedCandidatesDoNotBecomeInventedOptions() throws Exception {
        assertThrows(Exception.class,()->ProblemTags.options(new JSONObject()));
        assertThrows(Exception.class,()->ProblemTags.options(new JSONObject().put("tags",new JSONArray().put(123))));
        assertThrows(Exception.class,()->ProblemTags.options(new JSONObject().put("tags",new JSONArray().put(JSONObject.NULL))));
    }
    @Test public void pickerSearchOnlyNarrowsCandidateList() {
        List<String> tags=Arrays.asList("dp","digit dp","math");
        assertEquals(Arrays.asList("dp","digit dp"),ProblemTags.search(tags,"DP"));
        assertEquals(Collections.singletonList("math"),ProblemTags.search(tags,"ath"));
        assertEquals(tags,ProblemTags.search(tags," "));assertEquals(3,tags.size());
    }
    @Test public void exactLabelLimitCountsUnicodeCodePoints() {
        String emoji=new String(Character.toChars(0x1f431));String hundred=String.join("",Collections.nCopies(100,emoji));
        assertEquals(hundred,ProblemTags.checked(hundred));
        assertThrows(IllegalArgumentException.class,()->ProblemTags.checked(hundred+"x"));assertEquals("",ProblemTags.restore(hundred+"x"));
    }
    @Test public void keywordTrimLimitDoesNotCutSurrogatePairs() {
        String emoji=new String(Character.toChars(0x1f431));String hundred=String.join("",Collections.nCopies(100,emoji));
        assertEquals(hundred,ProblemTags.keyword(" "+hundred+"x "));assertEquals("Round A",ProblemTags.keyword(" Round A "));
    }
    @Test public void candidateLookupIsScopedToPlatform() {
        assertEquals("/api/me/problems/tags?platform=codeforces",ProblemTags.path("codeforces"));
        assertEquals("/api/me/problems/tags?platform=",ProblemTags.path(""));
        assertThrows(IllegalArgumentException.class,()->ProblemTags.path("all"));
    }
    @Test public void globalProblemAndTrackerSearchCombineBothParametersOnEveryPage() {
        for(String id:Arrays.asList("problems","tracker")){
            String path=SearchModules.path(id,"A&B",2,"digit dp");
            assertTrue(path.contains("tag=A%26B"));assertTrue(path.contains("problem_tag=digit+dp"));assertTrue(path.contains("page=2"));assertTrue(path.contains("scope=all"));
        }
    }
    @Test public void exactProblemLabelsNeverLeakToOtherSearchModules() {
        for(String id:Arrays.asList("users","forum","wiki","posts","bookmarks","drafts"))
            assertEquals(SearchModules.path(id,"A&B",1),SearchModules.path(id,"A&B",1,"dp"));
    }
}
