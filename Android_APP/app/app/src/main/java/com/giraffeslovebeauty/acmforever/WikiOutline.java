package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** Positions come from sanitized, typeset DOM headings, never Markdown line guesses. */
final class WikiOutline {
    static final class Heading {
        final String id,title;final int level;final float top;
        Heading(String id,String title,int level,float top){this.id=id;this.title=title;this.level=level;this.top=top;}
    }
    final List<Heading> headings=new ArrayList<>();final float height;
    WikiOutline(JSONObject metrics)throws JSONException {
        height=(float)metrics.getDouble("height");if(!Float.isFinite(height)||height<0)throw new JSONException("Wiki正文尺寸异常");
        JSONArray rows=metrics.getJSONArray("headings");Set<String> ids=new HashSet<>();float previous=-1;
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);String id=row.getString("id"),title=row.getString("title");int level=row.getInt("level");float top=(float)row.getDouble("top");
            if(id.isEmpty()||!ids.add(id)||level<1||level>6||!Float.isFinite(top)||top<0||top<previous)throw new JSONException("Wiki章节目录格式异常");
            headings.add(new Heading(id,title,level,top));previous=top;
        }
    }
    Heading find(String id){for(Heading heading:headings)if(heading.id.equals(id))return heading;return null;}
    Heading active(float viewportTop){if(headings.isEmpty())return null;Heading selected=headings.get(0);for(Heading heading:headings){if(heading.top>viewportTop)break;selected=heading;}return selected;}
}
