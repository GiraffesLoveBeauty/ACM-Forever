package com.giraffeslovebeauty.acmforever;

import java.util.regex.Pattern;

/** Plain card summaries; keep in step with feat/web/src/lib/post-images.js postExcerpt. */
final class ForumExcerpt {
    private static final Pattern IMAGE=Pattern.compile("!\\[[^\\]]*\\]\\([^)]*\\)");
    private static final Pattern IMAGE_TAIL=Pattern.compile("!\\[[\\s\\S]*$");
    private static final Pattern LINK=Pattern.compile("\\[([^\\]]+)\\]\\([^)]*\\)");
    private static final Pattern MARKS=Pattern.compile("[#*_>`~]");
    // JavaScript's \s also includes these Unicode whitespace characters.
    private static final Pattern SPACE=Pattern.compile("[\\s\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+");
    private ForumExcerpt() {}
    static String text(String source) {
        String value=source==null?"":source;
        value=IMAGE.matcher(value).replaceAll("");
        value=IMAGE_TAIL.matcher(value).replaceAll("");
        value=LINK.matcher(value).replaceAll("$1");
        value=MARKS.matcher(value).replaceAll("");
        return SPACE.matcher(value).replaceAll(" ").trim();
    }
}
