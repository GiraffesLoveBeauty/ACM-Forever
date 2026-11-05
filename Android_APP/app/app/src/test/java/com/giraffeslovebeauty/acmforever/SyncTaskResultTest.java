package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class SyncTaskResultTest {
    @Test public void existingMemberCrawlerFailureDoesNotClaimMemberMissing() {
        // Luogu missing credentials and an AtCoder fetch failure can both return -1.
        assertEquals("同步失败", SyncTaskResult.describeCount(-1));
    }

    @Test public void successfulSyncIncludesZeroAndActualAddedCount() {
        assertEquals("新增 0 条", SyncTaskResult.describeCount(0));
        assertEquals("新增 27 条", SyncTaskResult.describeCount(27));
    }

    @Test public void unboundAndFetchExceptionRemainDistinct() {
        assertEquals("未绑定账号", SyncTaskResult.describeCount(-2));
        assertEquals("抓取失败", SyncTaskResult.describeCount(-3));
    }

    @Test public void pausedPlatformKeepsPreservationMessage() {
        assertEquals("已暂停，保留原记录", SyncTaskResult.describeCount(-5));
    }

    @Test public void unknownNegativeCodeDoesNotInventSpecificCause() {
        assertEquals("同步失败", SyncTaskResult.describeCount(-4));
        assertEquals("同步失败", SyncTaskResult.describeCount(-99));
    }
}
