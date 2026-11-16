package com.giraffeslovebeauty.acmforever;

import java.time.*;

/** A phone-local calendar day begins at 04:00, including on daylight-saving transitions. */
final class UpdateCheckDay {
    private UpdateCheckDay() {}
    static LocalDate day(long instant, ZoneId zone) {
        ZonedDateTime local=Instant.ofEpochMilli(instant).atZone(zone);
        return local.toLocalTime().isBefore(LocalTime.of(4,0))?local.toLocalDate().minusDays(1):local.toLocalDate();
    }
    static boolean due(long now,long lastSuccess,ZoneId zone) {
        return lastSuccess<=0||now<lastSuccess||!day(now,zone).equals(day(lastSuccess,zone));
    }
}
