package com.giraffeslovebeauty.acmforever;

import android.app.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.*;
import java.util.function.*;

/** Native chapter navigation around the isolated local Markdown reader. */
final class WikiReaderNavigation implements ContentView.OutlineListener {
    private final Activity activity;private final ScrollView scroll;private final LinearLayout bar;
    private final JSONObject route;private final BooleanSupplier valid;private final TextView current;
    private ContentView content;private WikiOutline outline;private String active="";
    private boolean closed,restored;private AlertDialog dialog;private ArrayAdapter<WikiOutline.Heading> adapter;
    private int dp(float value){return MobileStyle.dp(activity,value);}
    WikiReaderNavigation(Activity activity,ScrollView scroll,LinearLayout bar,JSONObject route,BooleanSupplier valid){
        this.activity=activity;this.scroll=scroll;this.bar=bar;this.route=route;this.valid=valid;
        bar.removeAllViews();bar.setVisibility(View.VISIBLE);bar.setPadding(dp(14),dp(4),dp(14),dp(4));bar.setBackgroundColor(MobileStyle.CHROME);
        current=new TextView(activity);current.setText("正在生成章节目录…");current.setTextColor(MobileStyle.TEXT);current.setTextSize(13);current.setMaxLines(2);current.setContentDescription("Wiki当前章节");bar.addView(current,new LinearLayout.LayoutParams(0,-2,1));
        Button open=new Button(activity);open.setText("文章目录");MobileStyle.button(open,false);open.setOnClickListener(v->show());bar.addView(open,new LinearLayout.LayoutParams(dp(116),dp(48)));
    }
    ContentView content(String source,Consumer<String> link){
        content=new ContentView(activity,source,false,link,this);content.setContentDescription("Wiki文章正文");
        content.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->restore());return content;
    }
    private boolean live(){return !closed&&!activity.isFinishing()&&!activity.isDestroyed()&&valid.getAsBoolean();}
    private float visibleTop(){int[] reader=new int[2],viewport=new int[2];content.getLocationInWindow(reader);scroll.getLocationInWindow(viewport);return (viewport[1]-reader[1])/activity.getResources().getDisplayMetrics().density;}
    // The native scroll position is integral pixels; allow one pixel at the heading boundary.
    private float chapterTop(){return visibleTop()+12+1/activity.getResources().getDisplayMetrics().density;}
    @Override public void changed(WikiOutline next){if(!live())return;outline=next;content.postOnAnimation(()->{if(live()){restore();update();}});}
    private void restore(){
        if(!live()||restored||outline==null||content==null||scroll.getHeight()==0||content.getHeight()<Math.max(dp(100),dp(outline.height))-2)return;
        restored=true;WikiOutline.Heading saved=outline.find(route.optString("wiki_anchor"));
        if(saved!=null)move(saved,(float)route.optDouble("wiki_anchor_offset",0));else scroll.scrollTo(0,Math.max(0,route.optInt("scroll_y",0)));
        update();
    }
    void update(){
        if(!live()||outline==null||!restored)return;
        WikiOutline.Heading selected=outline.active(chapterTop());
        if(selected==null){current.setText("本文暂无章节目录");active="";return;}
        if(!active.equals(selected.id)){active=selected.id;current.setText(activity.getString(R.string.wiki_current_chapter,selected.title));if(adapter!=null)adapter.notifyDataSetChanged();}
        capture();
    }
    void capture(){
        if(!live()||!restored||outline==null||content==null)return;
        float top=visibleTop();WikiOutline.Heading selected=outline.active(chapterTop());
        try{route.put("scroll_y",scroll.getScrollY());route.put("wiki_anchor",selected!=null&&top>=0?selected.id:"");route.put("wiki_anchor_offset",selected==null?0:top-selected.top);}catch(JSONException ignored){}
    }
    private void move(WikiOutline.Heading heading,float offset){
        if(!Float.isFinite(offset))offset=0;
        int target=scroll.getScrollY()+dp(heading.top+offset-visibleTop());scroll.scrollTo(0,Math.max(0,target));
    }
    @Override public void anchor(String id){if(!live()||outline==null)return;WikiOutline.Heading target=outline.find(id);if(target==null)return;move(target,-12);update();}
    private void show(){
        if(!live()||ModalDialogs.isShowing(activity))return;
        LinearLayout box=new SpacedLayout(activity);box.setOrientation(LinearLayout.VERTICAL);
        TextView help=new TextView(activity);help.setText(outline==null?"正在生成章节目录…":outline.headings.isEmpty()?"本文暂无章节目录":"点击章节跳转；主题色标记当前阅读章节。");help.setTextColor(MobileStyle.MUTED);help.setTextSize(13);help.setPadding(0,dp(8),0,dp(12));box.addView(help);
        if(outline!=null&&!outline.headings.isEmpty()){
            List<WikiOutline.Heading> headings=new ArrayList<>(outline.headings);int base=6;for(WikiOutline.Heading h:headings)base=Math.min(base,h.level);final int firstLevel=base;
            ListView list=new ListView(activity){@Override public boolean dispatchTouchEvent(MotionEvent event){if(event.getActionMasked()==MotionEvent.ACTION_DOWN)getParent().requestDisallowInterceptTouchEvent(true);boolean result=super.dispatchTouchEvent(event);if(event.getActionMasked()==MotionEvent.ACTION_UP||event.getActionMasked()==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);return result;}};
            list.setDivider(null);list.setContentDescription("Wiki章节目录列表");
            adapter=new ArrayAdapter<WikiOutline.Heading>(activity,android.R.layout.simple_list_item_1,headings){@Override public View getView(int position,View old,ViewGroup parent){
                TextView item=(TextView)super.getView(position,old,parent);WikiOutline.Heading h=getItem(position);boolean chosen=h.id.equals(active);
                item.setText(h.title);item.setContentDescription("跳转Wiki章节 "+h.title);item.setTextSize(15);item.setMinHeight(dp(48));item.setPadding(dp(12+Math.max(0,h.level-firstLevel)*14),dp(10),dp(12),dp(10));
                item.setTextColor(chosen?MobileStyle.ON_ACCENT:MobileStyle.TEXT);item.setBackground(MobileStyle.panel(activity,MobileStyle.controlFill(chosen?MobileStyle.ACCENT:MobileStyle.PANEL),10,0));item.setSelected(chosen);return item;
            }};
            list.setAdapter(adapter);list.setOnItemClickListener((parent,v,index,id)->{String target=headings.get(index).id;dialog.dismiss();anchor(target);});box.addView(list,new LinearLayout.LayoutParams(-1,dp(300)));
            for(int i=0;i<headings.size();i++)if(headings.get(i).id.equals(active)){list.setSelection(i);break;}
        }
        dialog=new ModalDialogs.Builder(activity).setTitle("文章目录").setView(box).show();dialog.setOnDismissListener(d->adapter=null);
    }
    void close(){capture();closed=true;if(dialog!=null&&dialog.isShowing())dialog.dismiss();bar.removeAllViews();bar.setVisibility(View.GONE);}
}
