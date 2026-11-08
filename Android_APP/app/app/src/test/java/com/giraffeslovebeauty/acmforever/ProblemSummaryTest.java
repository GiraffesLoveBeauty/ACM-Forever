package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import java.util.Arrays;
import static org.junit.Assert.*;

public class ProblemSummaryTest {
    @Test public void supportsRealArraysAndLegacyTextWithoutSplittingAlgorithmNames() throws Exception {
        for (Object tags : new Object[]{new JSONArray("[\"digit dp\",\"math\",\" DP \",\"dp\",null,5]"),
                "[\"digit dp\",\"math\",\" DP \",\"dp\"]", "digit dp,math; DP |dp"}) {
            assertEquals(Arrays.asList("digit dp", "math", "DP"), ProblemSummary.tags(new JSONObject().put("tags", tags)));
        }
        assertEquals(Arrays.asList("动态规划", "图论"), ProblemSummary.tags(new JSONObject().put("tags", "动态规划，图论；动态规划")));
    }
    @Test public void missingAndEmptyMetadataStayHonest() throws Exception {
        assertEquals("算法标签未提供", ProblemSummary.emptyTags(new JSONObject()));
        assertEquals("暂无算法标签", ProblemSummary.emptyTags(new JSONObject().put("tags", new JSONArray())));
        assertTrue(ProblemSummary.tags(new JSONObject().put("tags", "[not-json")).isEmpty());
        for (Object value : new Object[]{JSONObject.NULL, "null", "", -1, "NaN", "Infinity", "unknown"})
            assertEquals("难度未知", ProblemSummary.difficulty(new JSONObject().put("problem_rating", value)));
        assertEquals("难度 0", ProblemSummary.difficulty(new JSONObject().put("problem_rating", 0)));
        assertEquals("难度 1200", ProblemSummary.difficulty(new JSONObject().put("problem_rating", "1200.0")));
        assertEquals("难度 400", ProblemSummary.difficulty(new JSONObject().put("problem_rating", 400)));
    }
}
