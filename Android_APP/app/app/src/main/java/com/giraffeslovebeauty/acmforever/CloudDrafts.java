package com.giraffeslovebeauty.acmforever;

import org.json.JSONObject;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/** Process-owned, serialized autosave. No Activity is retained by pending network work. */
final class CloudDrafts {
    interface Backend { JSONObject save(long session, int id, int category, String title, String body, int version) throws Exception; }
    interface Completion { void done(Exception error); }
    static final class State {
        final int id, category, editVersion, sourcePostId; final String title, body, status; final boolean dirty, saving;
        State(int id,int category,String title,String body,String status,boolean dirty,boolean saving,int editVersion,int sourcePostId) {
            this.id=id;this.category=category;this.title=title;this.body=body;this.status=status;this.dirty=dirty;this.saving=saving;this.editVersion=editVersion;this.sourcePostId=sourcePostId;
        }
    }
    private final ScheduledExecutorService queue=Executors.newSingleThreadScheduledExecutor();
    private final Backend backend;
    private String owner="", title="", body="", status="尚未编辑";
    private long session=-1, epoch, revision, saved;
    private int id, category, editVersion, sourcePostId;
    private boolean saving;
    private ScheduledFuture<?> timer;
    CloudDrafts(Backend backend){this.backend=backend;}
    synchronized void bind(String owner,long session) {
        if(!this.owner.equals(owner)||this.session!=session){this.owner=owner;this.session=session;reset();}
    }
    synchronized void reset(){epoch++;if(timer!=null)timer.cancel(false);id=0;category=0;editVersion=0;sourcePostId=0;title="";body="";revision=0;saved=0;saving=false;status="尚未编辑";}
    synchronized State state(){return new State(id,category,title,body,status,revision!=saved,saving,editVersion,sourcePostId);}
    synchronized long generation(){return epoch;}
    synchronized void load(JSONObject draft){reset();id=draft.optInt("id");category=draft.optInt("category_id");editVersion=draft.optInt("edit_version");sourcePostId=draft.optInt("source_post_id");title=draft.optString("title");body=draft.optString("body");status="云端草稿已加载";}
    synchronized void update(int category,String title,String body){
        if(this.category==category&&this.title.equals(title)&&this.body.equals(body))return;
        this.category=category;this.title=title;this.body=body;revision++;status="等待自动保存…";
        if(timer!=null)timer.cancel(false);
        long expected=epoch; timer=queue.schedule(()->save(expected,null),900,TimeUnit.MILLISECONDS);
    }
    void flush(Completion completion){long expected;synchronized(this){expected=epoch;if(timer!=null)timer.cancel(false);}queue.execute(()->save(expected,completion));}
    void close(){queue.shutdownNow();}
    private void save(long expected,Completion completion){
        Exception failure=null;
        try {
            while(true){
                final int draft,cat,version;final String t,b;final long rev,bound;
                synchronized(this){
                    if(epoch!=expected)throw new IllegalStateException("账号或草稿已切换，操作已取消");
                    if(owner.isEmpty())throw new IllegalStateException("请先登录后保存云端草稿");
                    if(revision==saved)break;
                    draft=id;cat=category;version=editVersion;t=title;b=body;rev=revision;bound=session;saving=true;status="正在保存到账号…";
                    if(sourcePostId>0&&version<=0)throw new IllegalStateException("修改草稿缺少版本号，请重新加载；输入已保留");
                }
                JSONObject result=backend.save(bound,draft,cat,t,b,version);
                synchronized(this){
                    if(epoch!=expected)throw new IllegalStateException("账号或草稿已切换，操作已取消");
                    id=result.getInt("id");editVersion=result.optInt("edit_version",editVersion);sourcePostId=result.optInt("source_post_id",sourcePostId);saved=rev;saving=false;status="云端草稿已保存";
                    // A change made during the POST must update its returned ID, never create a second draft.
                    if(revision==saved)break;
                }
            }
        }catch(Exception e){failure=e;synchronized(this){if(epoch==expected){saving=false;status="保存失败，编辑内容仍保留："+FailureState.title(e);}}}
        if(completion!=null)completion.done(failure);
    }
}
