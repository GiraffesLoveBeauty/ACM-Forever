package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class ChallengeDifficultyTest {
    @Test public void defaultsMatchWebAndCanBeSubmitted() {
        String[][] expected = {{"codeforces", "1000"}, {"atcoder", "800"}, {"luogu", "普及-"}, {"nowcoder", "2星"}};
        for (String[] row : expected) {
            assertEquals(row[1], ChallengeDifficulty.defaultValue(row[0]));
            assertEquals(row[1], ChallengeDifficulty.require(row[0], ChallengeDifficulty.defaultValue(row[0])));
        }
    }

    @Test public void numericChoicesStayWithinBackendBoundsAndIncludeZero() {
        for (String platform : new String[]{"codeforces", "atcoder"}) {
            int min = "codeforces".equals(platform) ? 800 : 0;
            int max = "codeforces".equals(platform) ? 3500 : 4000;
            assertEquals(String.valueOf(min), ChallengeDifficulty.options(platform).get(0));
            assertTrue(ChallengeDifficulty.options(platform).contains(String.valueOf(max)));
            for (String value : ChallengeDifficulty.options(platform)) {
                int number = Integer.parseInt(value);
                assertTrue(number >= min && number <= max);
            }
        }
        assertEquals("0", ChallengeDifficulty.require("atcoder", "0"));
    }

    @Test public void absentInvalidAndCrossPlatformSelectionsAreRejected() {
        for (String platform : new String[]{"codeforces", "atcoder", "luogu", "nowcoder"})
            for (Object value : new Object[]{null, "", " ", "invalid", "-1", "4001", "1.5", "99999999999999999999", 1000})
                assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require(platform, value));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require("codeforces", "0"));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require("codeforces", "2星"));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require("luogu", "1000"));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require("nowcoder", "普及-"));
    }

    @Test public void unsupportedPlatformsCannotUseAnotherPlatformsChoices() {
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.options(""));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.defaultValue("other"));
        assertThrows(IllegalArgumentException.class, () -> ChallengeDifficulty.require("other", "1000"));
    }
}
