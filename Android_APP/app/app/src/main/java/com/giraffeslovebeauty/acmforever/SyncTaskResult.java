package com.giraffeslovebeauty.acmforever;

/** Display labels for the existing platform synchronization result codes. */
final class SyncTaskResult {
    private SyncTaskResult() {}

    static String describeCount(int value) {
        if (value >= 0) return "新增 " + value + " 条";
        switch (value) {
            case -2: return "未绑定账号";
            case -3: return "抓取失败";
            case -5: return "已暂停，保留原记录";
            // Crawlers also return -1 for fetch failures on existing members.
            // The numeric result alone cannot establish that a member is missing.
            default: return "同步失败";
        }
    }
}
