package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** The public navigation response is the only source of category names and counts. */
final class WikiCatalog {
    final List<JSONObject> categories=new ArrayList<>();
    WikiCatalog(JSONObject response)throws JSONException {
        JSONArray rows=response.getJSONArray("categories");Set<Integer> ids=new HashSet<>();
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);int id=row.getInt("id");
            if(id<=0||!ids.add(id)||row.getString("name").trim().isEmpty())throw new JSONException("Wiki目录格式异常");
            if(!row.isNull("parent_id")&&row.getInt("parent_id")<=0)throw new JSONException("Wiki父分类格式异常");
            categories.add(row);
        }
        for(JSONObject row:categories)path(row.getInt("id")); // Reject missing parents/cycles.
    }
    JSONObject find(int id){for(JSONObject row:categories)if(row.optInt("id")==id)return row;return null;}
    List<JSONObject> children(int parent){List<JSONObject> result=new ArrayList<>();for(JSONObject row:categories)if(parent==0?row.isNull("parent_id"):row.optInt("parent_id")==parent)result.add(row);return result;}
    List<JSONObject> path(int id)throws JSONException {
        LinkedList<JSONObject> result=new LinkedList<>();Set<Integer> seen=new HashSet<>();
        while(id>0){JSONObject row=find(id);if(row==null||!seen.add(id))throw new JSONException("Wiki分类路径已失效");result.addFirst(row);id=row.isNull("parent_id")?0:row.getInt("parent_id");}
        return result;
    }
    static String count(JSONObject category){return category.has("published_count")&&!category.isNull("published_count")?Math.max(0,category.optInt("published_count"))+" 篇文章":"";}
}
