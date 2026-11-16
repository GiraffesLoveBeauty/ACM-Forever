package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class ForumFeedTest {
    private JSONObject page(int total,int... ids)throws Exception{
        JSONArray rows=new JSONArray();for(int id:ids)rows.put(new JSONObject().put("id",id).put("title","Post "+id));
        return new JSONObject().put("rows",rows).put("total",total);
    }
    @Test public void cacheThenLiveReplaceOnePageAndDeduplicateAcrossPages()throws Exception{
        ForumFeed feed=new ForumFeed();feed.replace(1,page(6,6,5));feed.replace(1,page(7,7,6));feed.replace(2,page(7,6,5));
        assertEquals(3,feed.rows().length());assertEquals(7,feed.rows().getJSONObject(0).getInt("id"));assertEquals(2,feed.lastPage());assertTrue(feed.more());
    }
    @Test public void completedWindowAndShrinkingTotalDoNotKeepDeletedTail()throws Exception{
        ForumFeed feed=new ForumFeed();feed.replace(1,page(4,4,3));feed.replace(2,page(4,2,1));assertFalse(feed.more());
        feed.replace(1,page(1,4));assertEquals(1,feed.rows().length());assertEquals(1,feed.lastPage());assertFalse(feed.more());
    }
    @Test public void outOfOrderReadRetriesKeepServerPageOrder()throws Exception{
        ForumFeed feed=new ForumFeed();feed.replace(2,page(6,4,3));feed.replace(1,page(6,6,5));
        assertEquals(6,feed.rows().getJSONObject(0).getInt("id"));assertEquals(3,feed.rows().getJSONObject(3).getInt("id"));
    }
    @Test public void malformedPageDoesNotReplaceUsableCache()throws Exception{
        ForumFeed feed=new ForumFeed();feed.replace(1,page(4,4,3));
        assertThrows(JSONException.class,()->feed.replace(1,new JSONObject().put("total",4)));
        assertEquals(2,feed.rows().length());
    }
    @Test public void serverMinimumFiveCanBeDisplayedInTwosWithoutSkippingItems()throws Exception{
        ForumFeed feed=new ForumFeed();feed.replace(1,page(8,1,2,3,4,5).put("page_size",5));
        assertEquals(2,feed.visibleRows(2).length());assertEquals(4,feed.visibleRows(4).length());assertTrue(feed.more(4));
        feed.replace(2,page(8,6,7,8).put("page_size",5));assertEquals(7,feed.visibleRows(7).length());assertFalse(feed.more(8));
        for(int i=0;i<8;i++)assertEquals(i+1,feed.visibleRows(8).getJSONObject(i).getInt("id"));
    }
}
