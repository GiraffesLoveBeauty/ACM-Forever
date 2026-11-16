package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import java.time.*;
import static org.junit.Assert.*;

public class UpdateCheckDayTest {
    private static final ZoneId SH=ZoneId.of("Asia/Shanghai");
    private static long at(String local,ZoneId zone){return LocalDateTime.parse(local).atZone(zone).toInstant().toEpochMilli();}
    @Test public void exactFourChangesDay(){long before=at("2026-11-15T03:59:59",SH),after=at("2026-11-15T04:00:00",SH);assertTrue(UpdateCheckDay.due(after,before,SH));assertFalse(UpdateCheckDay.due(before,before-1000,SH));}
    @Test public void midnightDoesNotReset(){assertFalse(UpdateCheckDay.due(at("2026-11-15T03:59:59",SH),at("2026-11-14T04:00:00",SH),SH));}
    @Test public void lateCheckSuppressesUntilTomorrowFour(){long success=at("2026-11-15T23:59:59",SH);assertFalse(UpdateCheckDay.due(at("2026-11-16T03:59:59",SH),success,SH));assertTrue(UpdateCheckDay.due(at("2026-11-16T04:00:00",SH),success,SH));}
    @Test public void absentOrFutureTimestampDoesNotBlockForever(){long now=at("2026-11-15T14:00:00",SH);assertTrue(UpdateCheckDay.due(now,0,SH));assertTrue(UpdateCheckDay.due(now,now+1,SH));}
    @Test public void usesPhoneZone(){long now=Instant.parse("2026-11-15T04:30:00Z").toEpochMilli(),success=Instant.parse("2026-11-15T03:30:00Z").toEpochMilli();assertFalse(UpdateCheckDay.due(now,success,SH));assertTrue(UpdateCheckDay.due(now,success,ZoneId.of("UTC")));}
    @Test public void dstDayIsCalendarBased(){ZoneId ny=ZoneId.of("America/New_York");assertFalse(UpdateCheckDay.due(at("2026-11-01T03:59:59",ny),at("2026-10-31T04:00:00",ny),ny));assertTrue(UpdateCheckDay.due(at("2026-11-01T04:00:00",ny),at("2026-10-31T04:00:00",ny),ny));}
}
