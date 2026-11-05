package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class SearchModulesTest {
    @Test public void defaultsAndSavedEmptyAreDistinct(){assertEquals(Arrays.asList("users","forum","wiki","problems"),SearchModules.decode(null));assertTrue(SearchModules.decode("[]").isEmpty());assertEquals(SearchModules.DEFAULT,SearchModules.decode("broken"));}
    @Test public void deduplicatesAndDropsRetiredModules(){assertEquals(Arrays.asList("wiki","forum"),SearchModules.decode("[\"wiki\",\"unknown\",\"forum\",\"wiki\"]"));}
    @Test public void movingBothDirectionsPreservesEveryModule(){List<String> start=SearchModules.decode(null);List<String> next=SearchModules.move(start,"users","problems");assertEquals(Arrays.asList("forum","wiki","problems","users"),next);assertEquals(SearchModules.DEFAULT,start);assertEquals(start,SearchModules.move(next,"users","forum"));assertEquals(next,SearchModules.move(next,"missing","users"));}
    @Test public void roundTripAndMissingApis(){List<String> all=new ArrayList<>(SearchModules.NAMES.keySet());assertEquals(all,SearchModules.decode(SearchModules.encode(all)));for(String id:Arrays.asList("sheets","discussions","mistakes")){assertFalse(SearchModules.available(id));assertThrows(IllegalArgumentException.class,()->SearchModules.path(id,"x",1));}assertTrue(SearchModules.privateModule("drafts"));assertFalse(SearchModules.privateModule("users"));}
    @Test public void queryIsEncodedAndUsersIncludeZeroAc(){String path=SearchModules.path("users","A&B 中文",2);assertTrue(path.contains("positive_only=0"));assertTrue(path.contains("search=A%26B+%E4%B8%AD%E6%96%87"));assertTrue(path.contains("page=2"));assertTrue(SearchModules.path("wiki","a?b",0).contains("page=1"));}
}
