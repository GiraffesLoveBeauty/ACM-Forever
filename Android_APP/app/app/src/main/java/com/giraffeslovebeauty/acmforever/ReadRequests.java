package com.giraffeslovebeauty.acmforever;

import java.io.InterruptedIOException;
import java.util.*;
import java.util.concurrent.*;

/** Coalesces identical reads. Cancellation belongs to subscribers, never to writes. */
final class ReadRequests {
    private static final ExecutorService disconnects=Executors.newFixedThreadPool(2,r->{Thread t=new Thread(r,"read-cancel");t.setDaemon(true);return t;});
    static final class Scope {
        private boolean cancelled;
        private final Set<Runnable> listeners = new HashSet<>();
        synchronized void check() throws InterruptedIOException { if(cancelled)throw new InterruptedIOException("页面读取已取消"); }
        void listen(Runnable listener) { boolean run; synchronized(this){run=cancelled;if(!run)listeners.add(listener);}if(run)listener.run(); }
        synchronized void remove(Runnable listener){listeners.remove(listener);}
        synchronized boolean cancelled(){return cancelled;}
        void cancel(){List<Runnable> copy; synchronized(this){if(cancelled)return;cancelled=true;copy=new ArrayList<>(listeners);listeners.clear();}for(Runnable r:copy)r.run();}
    }
    private static final class Flight {
        final CompletableFuture<String> result=new CompletableFuture<>();
        final Set<Scope> readers=Collections.newSetFromMap(new IdentityHashMap<>());
        Runnable disconnect;boolean stopping;
        synchronized boolean abandoned(){return readers.isEmpty()||readers.stream().allMatch(Scope::cancelled);}
        void cancel(){Runnable stop; synchronized(this){stop=abandoned()&&!stopping?disconnect:null;if(stop!=null)stopping=true;}if(stop!=null)disconnects.execute(stop);}
        void connection(Runnable stop){synchronized(this){disconnect=stop;}cancel();}
    }
    private final Map<String,Flight> flights=new HashMap<>();
    private final Semaphore slots=new Semaphore(2,true);
    private final ThreadLocal<Flight> current=new ThreadLocal<>();
    String run(String key,Scope scope,Callable<String> work)throws Exception{
        scope.check();Flight flight;boolean leader;
        synchronized(flights){flight=flights.get(key);leader=flight==null||flight.abandoned();if(leader){flight=new Flight();flights.put(key,flight);}synchronized(flight){flight.readers.add(scope);}}
        final Flight shared=flight;Runnable cancel=shared::cancel;scope.listen(cancel);
        try{
            if(leader){boolean acquired=false;try{
                while(!(acquired=slots.tryAcquire(100,TimeUnit.MILLISECONDS)))if(shared.abandoned())throw new InterruptedIOException("页面读取已取消");
                if(shared.abandoned())throw new InterruptedIOException("页面读取已取消");
                current.set(shared);shared.result.complete(work.call());
            }catch(Exception e){shared.result.completeExceptionally(e);}finally{current.remove();if(acquired)slots.release();synchronized(flights){flights.remove(key,shared);}}}
            while(true){scope.check();try{return shared.result.get(100,TimeUnit.MILLISECONDS);}catch(TimeoutException ignored){}catch(ExecutionException e){Throwable cause=e.getCause();if(cause instanceof Exception)throw (Exception)cause;throw new IllegalStateException(cause);}}
        }finally{scope.remove(cancel);synchronized(shared){shared.readers.remove(scope);}shared.cancel();}
    }
    void connection(Runnable disconnect){Flight f=current.get();if(f!=null)f.connection(disconnect);}
}
