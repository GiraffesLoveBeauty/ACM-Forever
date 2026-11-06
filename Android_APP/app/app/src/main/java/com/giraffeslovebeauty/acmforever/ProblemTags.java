package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;

/** Original catalog labels stay separate from keyword search and processed taxonomy IDs. */
final class ProblemTags {
    static String keyword(String text) {
        String value = text == null ? "" : text.trim();
        return value.codePointCount(0, value.length()) > 100 ? value.substring(0, value.offsetByCodePoints(0, 100)) : value;
    }
    static String checked(String text) {
        String value = text == null ? "" : text.trim();
        if (value.codePointCount(0, value.length()) > 100) throw new IllegalArgumentException("题目标签最多100个字符。");
        return value;
    }
    static String restore(String text) { try { return checked(text); } catch (IllegalArgumentException ignored) { return ""; } }
    static String parameter(String selected) { String value = checked(selected); return value.isEmpty() ? "" : "&problem_tag=" + UrlEncoding.form(value); }
    static String path(String platform) {
        if (!Arrays.asList("", "codeforces", "atcoder", "luogu", "nowcoder", "cjlu").contains(platform)) throw new IllegalArgumentException("无效的题目平台。");
        return "/api/me/problems/tags?platform=" + UrlEncoding.form(platform);
    }
    static List<String> options(JSONObject result) throws Exception {
        JSONArray values = result.getJSONArray("tags"); List<String> tags = new ArrayList<>(); Set<String> seen = new HashSet<>();
        for (int i = 0; i < values.length(); i++) {
            if (!(values.get(i) instanceof String)) throw new org.json.JSONException("题目标签格式异常");
            String value = checked(values.getString(i));
            if (!value.isEmpty() && seen.add(value.toLowerCase(Locale.ROOT))) tags.add(value);
        }
        return tags;
    }
    static List<String> search(List<String> options, String term) {
        String needle = term.trim().toLowerCase(Locale.ROOT); List<String> matches = new ArrayList<>();
        for (String label : options) if (label.toLowerCase(Locale.ROOT).contains(needle)) matches.add(label);
        return matches;
    }
}
