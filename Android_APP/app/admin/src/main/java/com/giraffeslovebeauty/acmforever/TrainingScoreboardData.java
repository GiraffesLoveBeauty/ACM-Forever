package com.giraffeslovebeauty.acmforever;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import org.json.JSONObject;

/** Read-only presentation of server evidence; missing data is never a zero or a date. */
final class TrainingScoreboardData {
    private TrainingScoreboardData() {}

    private static String value(JSONObject object,String key,String fallback) {
        String text=object==null||object.isNull(key)?"":object.optString(key,"").trim();
        return text.isEmpty()?fallback:text;
    }
    static String name(JSONObject row) { return value(row,"name","未命名"); }
    static String realName(JSONObject row) { return value(row,"real_name","未填写姓名"); }
    static String rank(JSONObject row) { return number(row,"rank")>0?String.valueOf(number(row,"rank")):"—"; }
    private static long number(JSONObject object,String key) {
        return object==null||object.isNull(key)?-1:object.optLong(key,-1);
    }
    static String penalty(JSONObject row) {
        long minutes=number(row,"penalty_minutes");
        return minutes<0?"罚时 —":"罚时 "+minutes+" 分";
    }
    static String state(JSONObject cell) {
        return value(cell,"state","empty");
    }
    static String status(JSONObject cell) {
        return "solved".equals(state(cell))?"已通过":"pending".equals(state(cell))?"待核验":"暂无通过证据";
    }
    static String cellLabel(JSONObject cell) {
        return "solved".equals(state(cell))?"+1":"pending".equals(state(cell))?"?":"—";
    }
    static String description(JSONObject row,JSONObject column,JSONObject cell) {
        return name(row)+" · 题目 "+value(column,"label","—")+" · "+status(cell)+" · 查看首次 AC 时间";
    }
    static String details(JSONObject task,JSONObject row,JSONObject column,JSONObject cell) {
        StringBuilder text=new StringBuilder(name(row)).append("\n姓名：").append(realName(row));
        text.append("\n\n题目 ").append(value(column,"label","—")).append(" · ")
            .append(value(column,"problem_name",value(column,"problem_id","未提供题目")));
        text.append("\n平台：").append(value(column,"platform","未提供"))
            .append("\n题号：").append(value(column,"problem_id","未提供"))
            .append("\n状态：").append(status(cell));
        long accepted=number(cell,"accepted_at"),starts=number(task,"starts_at");
        if(!"solved".equals(state(cell))) {
            text.append("\n首次已核验 AC：暂无已核验时间\n本题罚时：—");
        } else if(accepted<=0||accepted>Long.MAX_VALUE/1000) {
            text.append("\n首次已核验 AC：接口未提供时间\n本题罚时：0 分（无时间的历史 AC 不计罚时）");
        } else {
            SimpleDateFormat format=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.CHINA);
            format.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
            text.append("\n首次已核验 AC：").append(format.format(new Date(accepted*1000))).append(" 北京时间");
            if(starts<=0)text.append("\n本题罚时：—（未提供题单开始时间）");
            else if(accepted<starts)text.append("\n本题罚时：0 分（题单开始前的历史 AC）");
            else text.append("\n本题罚时：").append((accepted-starts)/60).append(" 分（从题单开始计，向下取整）");
        }
        return text.append("\n\n累计").append(penalty(row))
            .append("\n时间来自本题单采用的首次已核验 AC 证据，不代表平台全部历史中的最早提交。")
            .append("\n当前接口未提供错误提交次数，罚时不含错误提交加罚。").toString();
    }
}
