package com.giraffeslovebeauty.acmforever;

import java.util.*;
import org.json.*;

/** A cached page and its live replacement occupy one slot, never two appended copies. */
final class ForumFeed {
    static final int PAGE_SIZE=2;
    private final TreeMap<Integer,JSONObject> pages=new TreeMap<>();
    private int total,serverSize=PAGE_SIZE;
    void replace(int page,JSONObject response)throws JSONException {
        JSONArray rows=response.getJSONArray("rows");
        int size=Math.max(PAGE_SIZE,response.optInt("page_size",Math.max(PAGE_SIZE,rows.length())));
        if(size!=serverSize)pages.clear();serverSize=size;
        pages.put(page,response);total=Math.max(0,response.optInt("total"));
        int last=Math.max(1,(total+serverSize-1)/serverSize);pages.tailMap(last+1).clear();
    }
    JSONArray rows(){
        JSONArray result=new JSONArray();Set<Long> seen=new HashSet<>();
        for(JSONObject page:pages.values()){
            JSONArray rows=page.optJSONArray("rows");
            for(int i=0;rows!=null&&i<rows.length();i++){
                JSONObject row=rows.optJSONObject(i);if(row==null)continue;
                long id=row.optLong("id",0);if(id>0&&seen.add(id))result.put(row);
            }
        }
        return result;
    }
    int total(){return total;}
    int lastPage(){return pages.isEmpty()?0:pages.lastKey();}
    boolean more(){return (long)lastPage()*serverSize<total;}
    boolean more(int visible){return visible<rows().length()||more();}
    JSONArray visibleRows(int limit){JSONArray result=new JSONArray(),all=rows();for(int i=0;i<Math.min(limit,all.length());i++)result.put(all.optJSONObject(i));return result;}
}
