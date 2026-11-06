package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class WikiNavigationTest {
    private JSONObject category(int id,Integer parent,String name)throws Exception{return new JSONObject().put("id",id).put("parent_id",parent==null?JSONObject.NULL:parent).put("name",name);}
    private WikiCatalog catalog(JSONObject...rows)throws Exception{return new WikiCatalog(new JSONObject().put("categories",new JSONArray(rows)));}
    private JSONObject heading(String id,int level,double top)throws Exception{return new JSONObject().put("id",id).put("title",id).put("level",level).put("top",top);}
    private WikiOutline outline(JSONObject...rows)throws Exception{return new WikiOutline(new JSONObject().put("height",1000).put("headings",new JSONArray(rows)));}
    @Test public void publicHierarchyAndOrderComeFromServer()throws Exception{
        WikiCatalog catalog=catalog(category(2,1,"图论"),category(1,null,"算法"),category(3,null,"工具"));
        assertEquals("算法",catalog.children(0).get(0).getString("name"));assertEquals(2,catalog.children(0).size());assertEquals(2,catalog.children(1).get(0).getInt("id"));assertEquals(0,catalog.children(3).size());
    }
    @Test public void pathsAreOrderedFromRootToCurrentCategory()throws Exception{
        WikiCatalog catalog=catalog(category(1,null,"算法"),category(2,1,"图论"),category(3,2,"最短路"));
        assertEquals(3,catalog.path(3).size());assertEquals("算法",catalog.path(3).get(0).getString("name"));assertEquals("最短路",catalog.path(3).get(2).getString("name"));
    }
    @Test public void invalidParentsDuplicatesAndCyclesAreRejected()throws Exception{
        assertThrows(JSONException.class,()->catalog(category(1,2,"失效")));
        assertThrows(JSONException.class,()->catalog(category(1,2,"一"),category(2,1,"二")));
        assertThrows(JSONException.class,()->catalog(category(1,null,"一"),category(1,null,"重号")));
        assertThrows(JSONException.class,()->catalog(category(1,-1,"非法")));
    }
    @Test public void emptyCatalogRemainsEmpty()throws Exception{WikiCatalog catalog=catalog();assertTrue(catalog.categories.isEmpty());assertThrows(JSONException.class,()->catalog.path(99));}
    @Test public void absentCountsAreNotInvented()throws Exception{assertEquals("",WikiCatalog.count(category(1,null,"算法")));assertEquals("0 篇文章",WikiCatalog.count(category(1,null,"算法").put("published_count",0)));assertEquals("12 篇文章",WikiCatalog.count(category(1,null,"算法").put("published_count",12)));}
    @Test public void outlinePreservesRenderedHierarchyAndExactIds()throws Exception{WikiOutline toc=outline(heading("图论",1,0),heading("dijkstra",2,120.5),heading("dijkstra-2",2,450));assertEquals(3,toc.headings.size());assertEquals(2,toc.find("dijkstra-2").level);assertEquals(450,toc.find("dijkstra-2").top,0);assertNull(toc.find("missing"));}
    @Test public void currentChapterFollowsViewportAndSupportsUpwardScroll()throws Exception{WikiOutline toc=outline(heading("first",1,0),heading("second",2,200),heading("third",3,700));assertEquals("first",toc.active(-100).id);assertEquals("second",toc.active(200).id);assertEquals("third",toc.active(900).id);assertEquals("first",toc.active(10).id);}
    @Test public void noHeadingsIsValid()throws Exception{assertNull(outline().active(100));assertTrue(outline().headings.isEmpty());}
    @Test public void invalidOutlineCannotSupplyUnsafeScrollCoordinates()throws Exception{assertThrows(JSONException.class,()->outline(heading("a",2,-1)));assertThrows(JSONException.class,()->outline(heading("a",7,0)));assertThrows(JSONException.class,()->outline(heading("a",2,50),heading("b",2,20)));assertThrows(JSONException.class,()->outline(heading("same",2,0),heading("same",2,20)));}
}
