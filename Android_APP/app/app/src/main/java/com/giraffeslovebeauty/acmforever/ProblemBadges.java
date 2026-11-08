package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.Typeface;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.util.List;

/** Shared, wrapping difficulty and algorithm labels for catalog, tracker and statement. */
final class ProblemBadges {
    static void append(Context context, LinearLayout parent, JSONObject problem) {
        WrapLayout wrap = new WrapLayout(context);
        wrap.setContentDescription("题目难度与算法标签");
        wrap.setPadding(0, MobileStyle.dp(context, 6), 0, MobileStyle.dp(context, 8));
        TextView difficulty = chip(context, ProblemSummary.difficulty(problem), true);
        difficulty.setContentDescription(ProblemSummary.difficulty(problem));
        wrap.addView(difficulty);
        List<String> tags = ProblemSummary.tags(problem);
        if (tags.isEmpty()) wrap.addView(chip(context, ProblemSummary.emptyTags(problem), false));
        else for (String tag : tags) {
            TextView label = chip(context, tag, false);
            label.setContentDescription("算法标签：" + tag);
            wrap.addView(label);
        }
        parent.addView(wrap, new LinearLayout.LayoutParams(-1, -2));
    }

    private static TextView chip(Context context, String value, boolean accent) {
        TextView label = new TextView(context);
        label.setText(value); label.setTextSize(13);
        label.setLineSpacing(MobileStyle.dp(context, 1), 1);
        if (accent) label.setTypeface(null, Typeface.BOLD);
        MobileStyle.control(label, false, accent, 10);
        label.setPadding(MobileStyle.dp(context, 9), MobileStyle.dp(context, 6), MobileStyle.dp(context, 9), MobileStyle.dp(context, 6));
        return label;
    }
}
