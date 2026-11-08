package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Catalog metadata only: never infer an algorithm or a rating from the title. */
final class ProblemSummary {
    static String difficulty(JSONObject problem) {
        Object raw = problem.opt("problem_rating");
        if (raw == null || raw == JSONObject.NULL) return "难度未知";
        String value = String.valueOf(raw).trim();
        try {
            double rating = Double.parseDouble(value);
            if (!Double.isFinite(rating) || rating < 0) return "难度未知";
            return "难度 " + (rating == Math.rint(rating) ? String.format(Locale.ROOT, "%.0f", rating) : value);
        } catch (NumberFormatException ignored) { return "难度未知"; }
    }

    static List<String> tags(JSONObject problem) {
        Object raw = problem.opt("tags");
        if (raw instanceof String && ((String) raw).trim().startsWith("[")) {
            try { raw = new JSONArray((String) raw); }
            catch (org.json.JSONException ignored) { return new ArrayList<>(); }
        }
        List<String> values = new ArrayList<>();
        if (raw instanceof JSONArray) {
            JSONArray array = (JSONArray) raw;
            for (int i = 0; i < array.length(); i++) if (array.opt(i) instanceof String) values.add((String) array.opt(i));
        } else if (raw instanceof String) {
            java.util.Collections.addAll(values, ((String) raw).split("[,|;，；]"));
        }
        List<String> result = new ArrayList<>(); Set<String> seen = new LinkedHashSet<>();
        for (String value : values) {
            String tag = value.trim();
            if (!tag.isEmpty() && seen.add(tag.toLowerCase(Locale.ROOT))) result.add(tag);
        }
        return result;
    }

    static String description(JSONObject problem) {
        List<String> tags = tags(problem);
        return difficulty(problem) + " · " + (tags.isEmpty() ? emptyTags(problem) : "算法标签：" + String.join("、", tags));
    }

    static String emptyTags(JSONObject problem) {
        return !problem.has("tags") || problem.isNull("tags") ? "算法标签未提供" : "暂无算法标签";
    }
}
