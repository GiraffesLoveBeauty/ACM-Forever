package com.giraffeslovebeauty.acmforever;

import java.util.TimeZone;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class TrainingScoreboardDataTest {
    public TrainingScoreboardDataTest() throws Exception {}
    private final JSONObject task=new JSONObject("{\"starts_at\":1704067200}");
    private final JSONObject member=new JSONObject("{\"name\":\"Nick\",\"real_name\":\"Student\",\"penalty_minutes\":42}");
    private final JSONObject problem=new JSONObject("{\"label\":\"A\",\"problem_id\":\"cf_1843A\",\"problem_name\":\"Practice\",\"platform\":\"codeforces\"}");

    @Test public void verifiedAcShowsBeijingTimeAndElapsedMinutesRegardlessOfDeviceZone() throws Exception {
        TimeZone original=TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("America/Los_Angeles"));
            JSONObject solved=new JSONObject("{\"state\":\"solved\",\"accepted_at\":1704069779}");
            String details=TrainingScoreboardData.details(task,member,problem,solved);
            assertTrue(details.contains("首次已核验 AC：2024-01-01 08:42:59 北京时间"));
            assertTrue(details.contains("本题罚时：42 分"));
            assertTrue(details.contains("累计罚时 42 分"));
            assertTrue(details.contains("姓名：Student"));
            assertTrue(details.contains("题目 A · Practice"));
            assertTrue(details.contains("不代表平台全部历史中的最早提交"));
            assertTrue(details.contains("罚时不含错误提交加罚"));
        } finally { TimeZone.setDefault(original); }
    }
    @Test public void historicalAcWithoutTimestampNeverShowsEpochDate() throws Exception {
        for(String raw:new String[]{"{\"state\":\"solved\"}","{\"state\":\"solved\",\"accepted_at\":null}","{\"state\":\"solved\",\"accepted_at\":0}"}) {
            String details=TrainingScoreboardData.details(task,member,problem,new JSONObject(raw));
            assertTrue(details.contains("接口未提供时间"));
            assertTrue(details.contains("无时间的历史 AC 不计罚时"));
            assertFalse(details.contains("1970"));
        }
    }
    @Test public void historyBeforeStartHasNoElapsedPenalty() throws Exception {
        String details=TrainingScoreboardData.details(task,member,problem,new JSONObject("{\"state\":\"solved\",\"accepted_at\":1704067199}"));
        assertTrue(details.contains("本题罚时：0 分（题单开始前的历史 AC）"));
    }
    @Test public void missingStartCannotInventElapsedTime() throws Exception {
        String details=TrainingScoreboardData.details(new JSONObject(),member,problem,new JSONObject("{\"state\":\"solved\",\"accepted_at\":1704069779}"));
        assertTrue(details.contains("首次已核验 AC：2024-01-01 08:42:59 北京时间"));
        assertTrue(details.contains("本题罚时：—（未提供题单开始时间）"));
    }
    @Test public void pendingCannotBecomeSolvedBecauseItContainsUnverifiedTimestamp() throws Exception {
        JSONObject pending=new JSONObject("{\"state\":\"pending\",\"accepted_at\":1704069779}");
        String details=TrainingScoreboardData.details(task,member,problem,pending);
        assertEquals("?",TrainingScoreboardData.cellLabel(pending));
        assertTrue(details.contains("状态：待核验"));
        assertTrue(details.contains("首次已核验 AC：暂无已核验时间"));
        assertTrue(details.contains("本题罚时：—"));
        assertFalse(details.contains("2024-01-01"));
    }
    @Test public void missingCellIsNoEvidenceAndRemainsClickableDescription() throws Exception {
        assertEquals("—",TrainingScoreboardData.cellLabel(null));
        assertEquals("Nick · 题目 A · 暂无通过证据 · 查看首次 AC 时间",TrainingScoreboardData.description(member,problem,null));
        assertTrue(TrainingScoreboardData.details(task,member,problem,null).contains("状态：暂无通过证据"));
    }
    @Test public void absentPenaltyAndRankAreDistinctFromRealZero() throws Exception {
        assertEquals("罚时 —",TrainingScoreboardData.penalty(new JSONObject()));
        assertEquals("罚时 —",TrainingScoreboardData.penalty(new JSONObject("{\"penalty_minutes\":null}")));
        assertEquals("罚时 0 分",TrainingScoreboardData.penalty(new JSONObject("{\"penalty_minutes\":0}")));
        assertEquals("—",TrainingScoreboardData.rank(new JSONObject("{\"rank\":null}")));
        assertEquals("2",TrainingScoreboardData.rank(new JSONObject("{\"rank\":2}")));
    }
    @Test public void missingOrBlankRealNameDoesNotPrintNull() throws Exception {
        for(String raw:new String[]{"{}","{\"real_name\":null}","{\"real_name\":\"  \"}"})
            assertEquals("未填写姓名",TrainingScoreboardData.realName(new JSONObject(raw)));
        assertEquals("Student",TrainingScoreboardData.realName(member));
    }
    @Test public void penaltyMayExceedOneDayWithoutWrapping() throws Exception {
        JSONObject solved=new JSONObject("{\"state\":\"solved\",\"accepted_at\":1704157260}");
        assertTrue(TrainingScoreboardData.details(task,member,problem,solved).contains("本题罚时：1501 分"));
    }
}
