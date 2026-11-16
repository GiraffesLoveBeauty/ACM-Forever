package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.Assert.*;

public class ReadRequestsTest {
    @Test public void sameRequestIsSharedButAnotherAccountIsNot()throws Exception{
        ReadRequests reads=new ReadRequests();ExecutorService workers=Executors.newFixedThreadPool(3);
        CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1);AtomicInteger count=new AtomicInteger();
        try{
            Callable<String> work=()->{count.incrementAndGet();started.countDown();assertTrue(release.await(3,TimeUnit.SECONDS));return "body";};
            Future<String> a=workers.submit(()->reads.run("server/account1/path",new ReadRequests.Scope(),work));assertTrue(started.await(2,TimeUnit.SECONDS));
            Future<String> b=workers.submit(()->reads.run("server/account1/path",new ReadRequests.Scope(),work));
            Future<String> c=workers.submit(()->reads.run("server/account2/path",new ReadRequests.Scope(),()->"separate"));
            assertEquals("separate",c.get(2,TimeUnit.SECONDS));Thread.sleep(100);release.countDown();assertEquals("body",a.get());assertEquals("body",b.get());assertEquals(1,count.get());
        }finally{release.countDown();workers.shutdownNow();}
    }
    @Test public void cancellingOnePageKeepsOtherReaderAndTwoSlotsAreEnforced()throws Exception{
        ReadRequests reads=new ReadRequests();ExecutorService workers=Executors.newFixedThreadPool(4);ReadRequests.Scope a=new ReadRequests.Scope(),b=new ReadRequests.Scope();
        CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1);AtomicBoolean disconnected=new AtomicBoolean();
        try{
            Future<String> one=workers.submit(()->reads.run("same",a,()->{reads.connection(()->disconnected.set(true));started.countDown();release.await(3,TimeUnit.SECONDS);return "ok";}));assertTrue(started.await(2,TimeUnit.SECONDS));
            Future<String> two=workers.submit(()->reads.run("same",b,()->{fail("duplicate");return "bad";}));Thread.sleep(100);a.cancel();assertFalse(disconnected.get());release.countDown();assertEquals("ok",two.get());assertThrows(ExecutionException.class,one::get);
            AtomicInteger live=new AtomicInteger(),max=new AtomicInteger();List<Future<String>> all=new ArrayList<>();
            for(int i=0;i<4;i++){String key="path"+i;all.add(workers.submit(()->reads.run(key,new ReadRequests.Scope(),()->{int n=live.incrementAndGet();max.accumulateAndGet(n,Math::max);Thread.sleep(50);live.decrementAndGet();return key;})));}
            for(Future<String> f:all)f.get();assertEquals(2,max.get());
        }finally{release.countDown();workers.shutdownNow();}
    }
    @Test public void obsoleteQueuedPageNeverStartsAndErrorsAreNotReplayed()throws Exception{
        ReadRequests reads=new ReadRequests();ReadRequests.Scope cancelled=new ReadRequests.Scope();cancelled.cancel();AtomicInteger count=new AtomicInteger();
        assertThrows(java.io.InterruptedIOException.class,()->reads.run("path",cancelled,()->{count.incrementAndGet();return "bad";}));assertEquals(0,count.get());
        assertThrows(java.io.IOException.class,()->reads.run("path",new ReadRequests.Scope(),()->{throw new java.io.IOException("offline");}));
        assertEquals("restored",reads.run("path",new ReadRequests.Scope(),()->"restored"));
    }
    @Test public void targetedWritesPreserveUnrelatedReadsAndBackoffIsBounded(){
        assertFalse(Arrays.asList(ReadInvalidation.paths("/api/forum/posts/7/like")).contains("/api/"));
        assertFalse(Arrays.asList(ReadInvalidation.paths("/api/forum/drafts/7")).contains("/api/me/problems"));
        assertEquals(10000,RetryDelay.millis(0,.5));assertEquals(20000,RetryDelay.millis(1,.5));assertEquals(40000,RetryDelay.millis(2,.5));assertEquals(60000,RetryDelay.millis(12,.5));
    }
}
