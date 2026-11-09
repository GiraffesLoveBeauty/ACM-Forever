package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public final class ForumExcerptTest {
    @Test public void headingsEmphasisQuotesAndCodeBecomeReadableWords() {
        assertEquals("训练 重要内容 引用 代码 删除线",ForumExcerpt.text("# 训练\n\n**重要内容**\n> 引用 `代码` ~~删除线~~"));
    }
    @Test public void linksKeepLabelsAndImagesDoNotExposeUploadAddresses() {
        assertEquals("先看 题解 然后讨论",ForumExcerpt.text("先看 [题解](https://example.invalid/wiki) ![图片](/api/forum/images/0123456789abcdef0123456789abcdef) 然后讨论"));
    }
    @Test public void serverTruncatedImagesDoNotLeakPartialMarkdownOrUrls() {
        assertEquals("正文",ForumExcerpt.text("正文 ![插图](/api/forum/images/0123"));
        assertEquals("正文",ForumExcerpt.text("正文 ![尚未截完的替代文本"));
    }
    @Test public void whitespaceMatchesWebIncludingUnicodeSpaces() {
        assertEquals("甲 乙 丙 丁",ForumExcerpt.text("\ufeff甲\u00a0乙\u3000丙\t\n丁\u202f"));
    }
    @Test public void ordinaryTextAndNonBmpCharactersRemainIntact() {
        assertEquals("一起交流，一起 AC 🐱",ForumExcerpt.text("一起交流，一起 AC 🐱"));
    }
    @Test public void emptyOrImageOnlySummariesStayEmpty() {
        assertEquals("",ForumExcerpt.text(null));
        assertEquals("",ForumExcerpt.text("\n\t"));
        assertEquals("",ForumExcerpt.text("![图片](https://example.invalid/image.png)"));
    }
}
