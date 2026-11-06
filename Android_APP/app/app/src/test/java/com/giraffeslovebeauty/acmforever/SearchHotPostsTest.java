package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class SearchHotPostsTest {
    private JSONObject post(long id,long views)throws Exception{return new JSONObject().put("id",id).put("title","Post "+id).put("views_count",views);}
    @Test public void picksFourByActualViewsWithoutChangingCachedResponse()throws Exception{
        JSONArray items=new JSONArray();for(int i=1;i<=6;i++)items.put(post(i,i*100));
        List<JSONObject> posts=SearchHotPosts.select(new JSONObject().put("items",items));
        assertEquals(4,posts.size());assertEquals(6,posts.get(0).getLong("id"));assertEquals(3,posts.get(3).getLong("id"));
        assertEquals(1,items.getJSONObject(0).getLong("id"));
    }
    @Test public void acceptsOldEndpointRowsAndDeduplicatesWithoutInventingViews()throws Exception{
        JSONArray rows=new JSONArray().put(post(1,0)).put(post(1,0)).put(new JSONObject().put("id",2).put("title","No count")).put(post(3,-1)).put(post(0,9));
        List<JSONObject> posts=SearchHotPosts.select(new JSONObject().put("rows",rows));
        assertEquals(1,posts.size());assertEquals(1,posts.get(0).getInt("id"));
    }
    @Test public void handlesEmptyResultsAndBreaksTiesDeterministically()throws Exception{
        assertTrue(SearchHotPosts.select(new JSONObject().put("items",new JSONArray())).isEmpty());
        List<JSONObject> posts=SearchHotPosts.select(new JSONObject().put("items",new JSONArray().put(post(2,100)).put(post(5,100))));
        assertEquals(5,posts.get(0).getLong("id"));
    }
}
