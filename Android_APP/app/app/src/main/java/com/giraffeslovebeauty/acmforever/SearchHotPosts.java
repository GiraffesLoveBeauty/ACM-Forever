package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** Reuses one bounded hot-list response; this is not a global views ranking API. */
final class SearchHotPosts {
    private SearchHotPosts() {}
    static List<JSONObject> select(JSONObject response) throws JSONException {
        JSONArray rows = response.optJSONArray("items");
        if (rows == null) rows = response.getJSONArray("rows");
        List<JSONObject> ranked = new ArrayList<>(); Set<Long> seen = new HashSet<>();
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null || row.optLong("id") <= 0 || row.optString("title").trim().isEmpty()
                    || !row.has("views_count") || row.optLong("views_count", -1) < 0) continue;
            if (seen.add(row.optLong("id"))) ranked.add(row);
        }
        ranked.sort(Comparator.comparingLong((JSONObject row) -> row.optLong("views_count")).reversed()
                .thenComparing(Comparator.comparingLong((JSONObject row) -> row.optLong("id")).reversed()));
        return new ArrayList<>(ranked.subList(0, Math.min(4, ranked.size())));
    }
}
