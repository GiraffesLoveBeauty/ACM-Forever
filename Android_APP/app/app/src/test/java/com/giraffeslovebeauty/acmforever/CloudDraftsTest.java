package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CloudDraftsTest {
    private void flush(CloudDrafts drafts) throws Exception {
        CountDownLatch done=new CountDownLatch(1);AtomicReference<Exception> error=new AtomicReference<>();
        drafts.flush(e->{error.set(e);done.countDown();});assertTrue(done.await(5,TimeUnit.SECONDS));
        if(error.get()!=null)throw error.get();
    }
    @Test public void editingDuringCreateUpdatesReturnedIdWithoutDuplicatingDraft() throws Exception {
        CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1),done=new CountDownLatch(1);
        List<Integer> ids=new ArrayList<>();List<String> bodies=new ArrayList<>();
        CloudDrafts drafts=new CloudDrafts((session,id,category,title,body,version)->{
            ids.add(id);bodies.add(body);if(ids.size()==1){started.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));}
            return new JSONObject().put("id",42);
        });
        try {
            drafts.bind("one",7);drafts.update(1,"First","old body");drafts.flush(e->done.countDown());
            assertTrue(started.await(5,TimeUnit.SECONDS));drafts.update(1,"First","new body");release.countDown();
            assertTrue(done.await(5,TimeUnit.SECONDS));assertEquals(java.util.Arrays.asList(0,42),ids);
            assertEquals(java.util.Arrays.asList("old body","new body"),bodies);assertEquals(42,drafts.state().id);assertFalse(drafts.state().dirty);
        } finally {release.countDown();drafts.close();}
    }
    @Test public void lateSaveCannotReplaceNextAccountsDraft() throws Exception {
        CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1),done=new CountDownLatch(1);
        CloudDrafts drafts=new CloudDrafts((session,id,category,title,body,version)->{started.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));return new JSONObject().put("id",99);});
        try {
            drafts.bind("one",1);drafts.update(1,"Private","Secret");drafts.flush(e->done.countDown());
            assertTrue(started.await(5,TimeUnit.SECONDS));drafts.bind("two",2);release.countDown();assertTrue(done.await(5,TimeUnit.SECONDS));
            assertEquals(0,drafts.state().id);assertEquals("",drafts.state().body);assertFalse(drafts.state().dirty);
        } finally {release.countDown();drafts.close();}
    }
    @Test public void failedSaveRetainsDirtyTextAndCanRetry() throws Exception {
        java.util.concurrent.atomic.AtomicBoolean fail=new java.util.concurrent.atomic.AtomicBoolean(true);
        CloudDrafts drafts=new CloudDrafts((session,id,category,title,body,version)->{if(fail.get())throw new java.io.IOException("offline");return new JSONObject().put("id",13);});
        try {
            drafts.bind("one",1);drafts.update(1,"Topic","keep this");
            try {flush(drafts);fail("Expected failed save");}catch(java.io.IOException expected){}
            assertTrue(drafts.state().dirty);assertEquals("keep this",drafts.state().body);
            fail.set(false);flush(drafts);assertEquals(13,drafts.state().id);assertFalse(drafts.state().dirty);
        } finally {drafts.close();}
    }
    @Test public void rotationWithSameOwnerKeepsLoadedDraftAndOtherOwnerClearsIt() throws Exception {
        CloudDrafts drafts=new CloudDrafts((session,id,category,title,body,version)->new JSONObject().put("id",id));
        try {
            drafts.bind("one",1);drafts.load(new JSONObject().put("id",12).put("category_id",2).put("title","Title").put("body","Text"));
            drafts.bind("one",1);assertEquals(12,drafts.state().id);assertEquals("Text",drafts.state().body);
            drafts.bind("two",2);assertEquals("",drafts.state().body);
        } finally {drafts.close();}
    }
    @Test public void revisedDraftUsesLatestVersionAndConflictKeepsInput() throws Exception {
        List<Integer> versions=new ArrayList<>();java.util.concurrent.atomic.AtomicBoolean conflict=new java.util.concurrent.atomic.AtomicBoolean();
        CloudDrafts drafts=new CloudDrafts((session,id,category,title,body,version)->{versions.add(version);if(conflict.get())throw new ApiClient.ApiException(409,"草稿已由其他设备修改",false);return new JSONObject().put("id",id).put("edit_version",version+1).put("source_post_id",8);});
        try{drafts.bind("one",1);drafts.load(new JSONObject().put("id",12).put("category_id",1).put("edit_version",4).put("source_post_id",8).put("title","Original").put("body","Original body"));
            drafts.update(1,"Changed","Keep my text");flush(drafts);assertEquals(java.util.Arrays.asList(4),versions);assertEquals(5,drafts.state().editVersion);assertEquals(8,drafts.state().sourcePostId);
            conflict.set(true);drafts.update(1,"Changed again","Preserve conflicting edit");try{flush(drafts);fail("409 expected");}catch(ApiClient.ApiException expected){assertEquals(409,expected.status);}
            assertTrue(drafts.state().dirty);assertEquals(5,drafts.state().editVersion);assertEquals("Preserve conflicting edit",drafts.state().body);
        }finally{drafts.close();}
    }
    @Test public void rankMatchesWebRangesSortsPageSizesAndEscapesSearch() {
        String path=RankOptions.path("365","cf_count","codeforces,atcoder","a&中文",2,50);
        assertTrue(path.contains("days=365"));assertTrue(path.contains("sort=cf_count"));assertTrue(path.contains("page_size=50"));
        assertTrue(path.contains("platforms=codeforces%2Catcoder"));assertTrue(path.contains("search=a%26%E4%B8%AD%E6%96%87"));assertTrue(path.contains("positive_only=1"));
        String fallback=RankOptions.path("bad","bad","codeforces","",-10,5);
        assertTrue(fallback.contains("days=7"));assertTrue(fallback.contains("page=1&"));assertTrue(fallback.contains("page_size=20"));
    }
}
