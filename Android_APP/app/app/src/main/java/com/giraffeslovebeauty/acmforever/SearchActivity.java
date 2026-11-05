package com.giraffeslovebeauty.acmforever;

import android.content.*;
import android.graphics.Color;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import org.json.*;
import java.util.*;

/** One global search surface, with device-local ordering and removable search modules. */
public final class SearchActivity extends MobilePageActivity {
    private android.content.SharedPreferences prefs;private String mode="search",query="";
    private final ArrayDeque<String> history=new ArrayDeque<>();private List<String> modules;private long account;
    @Override public void onCreate(Bundle state){super.onCreate(state);prefs=AppAppearance.prefs(this);mode=state==null?getIntent().getStringExtra("mode"):state.getString("mode");if(mode==null)mode="search";
        query=state==null?getIntent().getStringExtra("query"):state.getString("query","");if(query==null)query="";if(state!=null){ArrayList<String> back=state.getStringArrayList("history");if(back!=null)history.addAll(back);}createPage("全局搜索");account=api.sessionGeneration();render();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("mode",mode);out.putString("query",query);out.putStringArrayList("history",new ArrayList<>(history));}
    @Override protected void onResume(){super.onResume();if(api!=null&&account!=api.sessionGeneration()){account=api.sessionGeneration();render();}}
    @Override public void onBackPressed(){if(writing)return;if(history.isEmpty()){super.onBackPressed();return;}mode=history.pop();render();}
    private void nav(String next){history.push(mode);mode=next;render();}
    private void saveModules(){prefs.edit().putString(SearchModules.KEY,SearchModules.encode(modules)).apply();}
    private void render(){modules=SearchModules.decode(prefs.contains(SearchModules.KEY)?prefs.getString(SearchModules.KEY,null):null);resetPage("settings".equals(mode)?"搜索设置":"history".equals(mode)?"历史记录":"add".equals(mode)?"添加模块":"全局搜索");
        switch(mode){case "settings":settings();break;case "add":addModules();break;case "history":records();break;default:search();}AppAppearance.paintFields(root);scroll.setOnDragListener((v,e)->{
            if(e.getAction()==DragEvent.ACTION_DRAG_STARTED)return e.getLocalState() instanceof String;
            if(e.getAction()==DragEvent.ACTION_DRAG_LOCATION){if(e.getY()<dp(72))scroll.smoothScrollBy(0,-dp(35));else if(e.getY()>scroll.getHeight()-dp(72))scroll.smoothScrollBy(0,dp(35));}
            return true;
        });}
    private JSONArray terms(){try{return new JSONArray(prefs.getString("search_history","[]"));}catch(Exception e){return new JSONArray();}}
    private void submit(String term){term=term.trim();if(term.isEmpty())return;query=term.codePointCount(0,term.length())>100?term.substring(0,term.offsetByCodePoints(0,100)):term;
        if(prefs.getBoolean("record_search",true)){JSONArray next=new JSONArray(),old=terms();next.put(query);for(int i=0;i<old.length()&&next.length()<10;i++)if(!query.equals(old.optString(i)))next.put(old.optString(i));prefs.edit().putString("search_history",next.toString()).apply();}
        mode="search";root.requestFocus();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(),0);render();}
    private void search(){
        LinearLayout tools=card(body);EditText field=input(tools,"搜索用户、论坛、Wiki、题目…",query);field.setImeOptions(EditorInfo.IME_ACTION_SEARCH);field.setOnEditorActionListener((v,a,e)->{if(a==EditorInfo.IME_ACTION_SEARCH){submit(field.getText().toString());return true;}return false;});
        equalButtons(tools,button("搜索",()->submit(field.getText().toString())),button("搜索设置",()->nav("settings")));
        if(query.isEmpty()){recent(body);return;}
        body.addView(text("搜索结果 · "+query,21));body.addView(text("按搜索设置排序，从左到右、从上到下展示。",12));
        if(modules.isEmpty()){card(body).addView(text("尚未启用搜索模块，请在搜索设置中添加。",15));return;}
        for(int i=0;i<modules.size();i+=2){LinearLayout line=row();line.setGravity(Gravity.TOP);body.addView(line,new LinearLayout.LayoutParams(-1,-2));for(int n=i;n<Math.min(i+2,modules.size());n++){
            String id=modules.get(n);LinearLayout frame=column();line.addView(frame,new LinearLayout.LayoutParams(0,-2,1));LinearLayout slot=card(frame);loadModule(id,1,slot);}}
    }
    private void recent(LinearLayout parent){LinearLayout box=card(parent);box.addView(text("最近 10 条搜索",18));JSONArray items=terms();if(items.length()==0)box.addView(text("暂无历史搜索",14));for(int i=0;i<items.length();i++){String term=items.optString(i);box.addView(button(term,()->submit(term)));}equalButtons(box,button("历史记录",()->nav("history")),button("搜索设置",()->nav("settings")));}
    private void settings(){equalButtons(body,button("历史记录",()->nav("history")),button("添加模块",()->nav("add")));body.addView(text("越靠上越优先 · 按住三条杠拖动排序",13));if(modules.isEmpty())card(body).addView(text("所有模块已移除，可以重新添加。",15));
        for(String id:modules){LinearLayout box=card(body),line=row();box.addView(line);TextView name=text(SearchModules.NAMES.get(id),18);line.addView(name,new LinearLayout.LayoutParams(0,-2,1));
            Button drag=button("☰",()->{});drag.setContentDescription("拖动排序 "+SearchModules.NAMES.get(id));drag.setOnLongClickListener(v->{v.startDragAndDrop(ClipData.newPlainText("search-module",id),new View.DragShadowBuilder(box),id,0);return true;});line.addView(drag,new LinearLayout.LayoutParams(dp(48),dp(48)));
            Button remove=button("×",()->{modules.remove(id);saveModules();render();});remove.setContentDescription("移除 "+SearchModules.NAMES.get(id));remove.setBackground(MobileStyle.panel(this,0x80d93838,12,0));remove.setTextColor(MobileStyle.TEXT);line.addView(remove,new LinearLayout.LayoutParams(dp(48),dp(48)));
            box.addView(text(SearchModules.description(id),12));box.setOnDragListener((v,event)->{if(event.getAction()==DragEvent.ACTION_DRAG_STARTED)return event.getLocalState() instanceof String;if(event.getAction()==DragEvent.ACTION_DROP){String from=String.valueOf(event.getLocalState());modules=SearchModules.move(modules,from,id);saveModules();render();return true;}return true;});
        }}
    private void addModules(){int count=0;for(Map.Entry<String,String> entry:SearchModules.NAMES.entrySet()){if(modules.contains(entry.getKey()))continue;count++;LinearLayout box=card(body),line=row();box.addView(line);line.addView(text(entry.getValue(),18),new LinearLayout.LayoutParams(0,-2,1));Button add=button("+",()->{modules.add(entry.getKey());saveModules();render();});add.setContentDescription("添加 "+entry.getValue());line.addView(add,new LinearLayout.LayoutParams(dp(48),dp(48)));box.addView(text(SearchModules.description(entry.getKey()),12));}if(count==0)card(body).addView(text("所有模块均已添加。",15));}
    private void records(){LinearLayout settings=card(body);CheckBox enabled=new CheckBox(this);enabled.setText("记录搜索历史（仅本机，最多 10 条）");enabled.setChecked(prefs.getBoolean("record_search",true));enabled.setOnCheckedChangeListener((b,v)->prefs.edit().putBoolean("record_search",v).apply());settings.addView(enabled);EditText filter=input(settings,"查询历史记录","");LinearLayout list=column();body.addView(list);
        Runnable show=()->{list.removeAllViews();JSONArray values=terms();for(int i=0;i<values.length();i++){String term=values.optString(i);if(!term.toLowerCase(Locale.ROOT).contains(filter.getText().toString().toLowerCase(Locale.ROOT)))continue;LinearLayout line=row();line.addView(button(term,()->submit(term)),new LinearLayout.LayoutParams(0,-2,1));line.addView(button("删除",()->{JSONArray next=new JSONArray(),old=terms();for(int k=0;k<old.length();k++)if(!term.equals(old.optString(k)))next.put(old.optString(k));prefs.edit().putString("search_history",next.toString()).apply();render();}));list.addView(line);}if(list.getChildCount()==0)list.addView(text("暂无匹配记录",14));};
        filter.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){show.run();}public void afterTextChanged(android.text.Editable e){}});settings.addView(button("清空历史记录",()->new ModalDialogs.Builder(this).setTitle("清空本机搜索记录？").setNegativeButton("返回",null).setPositiveButton("确认清空",(d,w)->{prefs.edit().remove("search_history").apply();render();}).show()));show.run();}
    private void loadModule(String id,int page,LinearLayout slot){slot.removeAllViews();slot.addView(text(SearchModules.NAMES.get(id),18));slot.addView(text("正在搜索…",12));
        if(!SearchModules.available(id)){error(slot,new ApiClient.UnavailableEndpointException(SearchModules.NAMES.get(id)+"搜索"));slot.addView(text(SearchModules.NAMES.get(id),16));return;}
        if(SearchModules.privateModule(id)&&!api.isLoggedIn()){error(slot,new ApiClient.ApiException(401,"请先登录",false));slot.addView(text(SearchModules.NAMES.get(id),16));return;}
        final String term=query;slot.setContentDescription(SearchModules.NAMES.get(id)+"搜索");
        read(()->{String path=SearchModules.path(id,term,page);if("users".equals(id))path=api.leaderboardPath("")+path.substring(path.indexOf('?'));else if("forum".equals(id))path=api.publicPostsPath("")+path.substring(path.indexOf('?'));return api.get(path);},slot,true,value->showModule(id,page,slot,value));
    }
    private void showModule(String id,int page,LinearLayout slot,Object value)throws Exception{
        slot.addView(text(SearchModules.NAMES.get(id),18));slot.addView(text(SearchModules.description(id),11));JSONArray items;int total;
        if(value instanceof JSONArray){JSONArray all=(JSONArray)value;items=new JSONArray();for(int i=0;i<all.length();i++){JSONObject item=all.optJSONObject(i);if(item!=null&&(item.optString("title")+" "+item.optString("body")+" "+item.optString("excerpt")).toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT)))items.put(item);}total=items.length();}
        else{JSONObject object=(JSONObject)value;items=object.optJSONArray("rows");if(items==null)items=object.optJSONArray("items");if(items==null)throw new JSONException("搜索结果格式不正确");total=object.optInt("total",items.length());}
        slot.addView(text("共 "+total+" 条",12));if(items.length()==0)slot.addView(text("暂无内容",14));
        int start=value instanceof JSONArray?(page-1)*6:0,end=value instanceof JSONArray?Math.min(items.length(),start+6):items.length();
        for(int i=start;i<end;i++){JSONObject item=items.getJSONObject(i);String label="users".equals(id)?item.optString("name"):"problems".equals(id)?item.optString("problem_name",item.optString("problem_id")):"tracker".equals(id)?item.optString("contest_name",item.optString("contest_id")):item.optString("title");
            Button open=button(label.isEmpty()?"未命名":label,()->openResult(id,item));open.setMaxLines(3);slot.addView(open,new LinearLayout.LayoutParams(-1,-2));if("users".equals(id)&&item.optString("public_member_id").isEmpty()){open.setEnabled(false);slot.addView(text("无API接口：成员主页标识",11));}}
        if(total>6){slot.addView(text("第 "+page+" / "+((total+5)/6)+" 页",12));equalButtons(slot,button("上一页",()->{if(page>1)loadModule(id,page-1,slot);}),button("下一页",()->{if(page*6<total)loadModule(id,page+1,slot);}));}
    }
    private void openResult(String id,JSONObject item){Intent next;
        switch(id){case "users":next=new Intent(this,MainActivity.class).putExtra("search_public_member",item.toString());break;
            case "forum":case "bookmarks":next=new Intent(this,MainActivity.class).putExtra("club_post_id",item.optInt("id"));break;
            case "posts":next=new Intent(this,WebFeaturesActivity.class).putExtra("feature","progress").putExtra("post_id",item.optInt("id"));break;
            case "drafts":next=new Intent(this,MainActivity.class).putExtra("cloud_draft_id",item.optInt("id"));break;
            case "wiki":next=new Intent(this,WebFeaturesActivity.class).putExtra("feature","wiki-article").putExtra("wiki_slug",item.optString("slug"));break;
            case "tracker":next=new Intent(this,WebFeaturesActivity.class).putExtra("feature","tracker").putExtra("initial_query",item.optString("contest_id")).putExtra("initial_platform",item.optString("platform"));break;
            default:next=new Intent(this,MainActivity.class).putExtra("web_problem_platform",item.optString("platform")).putExtra("web_problem_id",item.optString("problem_id"));}
        opening=true;startActivity(next);
    }
}
