package com.giraffeslovebeauty.acmforever;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Difficulty choices follow acm_api.difficulty; defaults match the Web training form. */
final class ChallengeDifficulty {
    private ChallengeDifficulty() { }

    static List<String> options(String platform) {
        if ("luogu".equals(platform)) return Arrays.asList(
                "未评定", "入门", "普及-", "普及/提高-", "普及+/提高",
                "提高+/省选-", "省选/NOI-", "NOI/NOI+/CTSC");
        if ("nowcoder".equals(platform)) return Arrays.asList("1星", "2星", "3星", "4星", "5星");
        if (!"codeforces".equals(platform) && !"atcoder".equals(platform))
            throw new IllegalArgumentException("请选择有效训练平台");
        List<String> values = new ArrayList<>();
        int min = "codeforces".equals(platform) ? 800 : 0;
        int max = "codeforces".equals(platform) ? 3500 : 4000;
        for (int n = min; n <= max; n += 100) values.add(String.valueOf(n));
        return values;
    }

    static String defaultValue(String platform) {
        switch (platform) {
            case "codeforces": return "1000";
            case "atcoder": return "800";
            case "luogu": return "普及-";
            case "nowcoder": return "2星";
            default: throw new IllegalArgumentException("请选择有效训练平台");
        }
    }

    static String require(String platform, Object selected) {
        if (!(selected instanceof String) || !options(platform).contains(selected))
            throw new IllegalArgumentException("请选择该平台的有效难度后再生成训练");
        return (String) selected;
    }
}
