package com.giraffeslovebeauty.acmforever;

import java.util.concurrent.*;

/** A new page never queues behind work belonging to the old page. */
final class PageReads {
    private final ApiClient api;
    private final ExecutorService pool=Executors.newFixedThreadPool(2);
    private final ExecutorService previews=Executors.newSingleThreadExecutor();
    private ReadRequests.Scope scope=new ReadRequests.Scope();
    PageReads(ApiClient api){this.api=api;}
    // Workers are shared per Activity; obsolete queued tasks test their scope before running.
    void cancel(){scope.cancel();scope=new ReadRequests.Scope();}
    private void execute(ExecutorService executor,Runnable work){ReadRequests.Scope selected=scope;try{executor.execute(()->{try{selected.check();api.readIn(selected,work);}catch(java.io.InterruptedIOException ignored){}});}catch(RejectedExecutionException ignored){}}
    void network(Runnable work){execute(pool,work);}
    void preview(Runnable work){execute(previews,work);}
    void close(){scope.cancel();pool.shutdown();previews.shutdown();}
}
