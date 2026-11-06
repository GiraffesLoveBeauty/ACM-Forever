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
    private EditText searchField;private String draftQuery="";private boolean focusSearch;
    private String problemTag="",trackerTag="";
    @Override public void onCreate(Bundle state){super.onCreate(state);prefs=AppAppearance.prefs(this);mode=state==null?getIntent().getStringExtra("mode"):state.getString("mode");if(mode==null)mode="search";
        query=state==null?getIntent().getStringExtra("query"):state.getString("query","");if(query==null)query="";if(state!=null){ArrayList<String> back=state.getStringArrayList("history");if(back!=null)history.addAll(back);}createPage("全局搜索");account=api.sessionGeneration();
        if(state!=null&&state.getLong("tag_owner",-1)==account){problemTag=ProblemTags.restore(state.getString("problem_tag",""));trackerTag=ProblemTags.restore(state.getString("tracker_tag",""));}
        draftQuery=state==null?query:state.getString("draft_query",query);focusSearch="search".equals(mode)&&(state==null?query.isEmpty():state.getBoolean("focus_search",false));
        // A fresh home-page search is a submission; restoring a page must not rewrite history.
        if(state==null&&"search".equals(mode)&&!query.trim().isEmpty())submit(query);else render();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("mode",mode);out.putString("query",query);out.putString("draft_query",draftQuery);out.putBoolean("focus_search","search".equals(mode)&&searchField!=null&&searchField.hasFocus());out.putStringArrayList("history",new ArrayList<>(history));out.putLong("tag_owner",account);out.putString("problem_tag",problemTag);out.putString("tracker_tag",trackerTag);}
    @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(focused)focusInput();}
    private void focusInput(){if(focusSearch&&"search".equals(mode)&&searchField!=null&&searchField.hasWindowFocus()){KeyboardInputs.show(this,searchField);focusSearch=false;}}
    @Override protected void onResume(){super.onResume();if(api!=null&&account!=api.sessionGeneration()){ModalDialogs.close(this);problemTag="";trackerTag="";account=api.sessionGeneration();render();}}
    @Override public void onBackPressed(){if(writing)return;if(history.isEmpty()){super.onBackPressed();return;}PageMotion.change(this,false,()->{mode=history.pop();render();});}
    private void nav(String next){if(mode.equals(next))return;focusSearch=false;hideKeyboard();PageMotion.change(this,true,()->{history.push(mode);mode=next;render();});}
    private void saveModules(){prefs.edit().putString(SearchModules.KEY,SearchModules.encode(modules)).apply();}
    private void render(){modules=SearchModules.decode(prefs.contains(SearchModules.KEY)?prefs.getString(SearchModules.KEY,null):null);resetPage("settings".equals(mode)?"搜索设置":"history".equals(mode)?"历史记录":"add".equals(mode)?"添加模块":"全局搜索");
        header.removeAllViews();ImageButton back=new ImageButton(this);MobileStyle.flat(back);back.setBackgroundColor(Color.TRANSPARENT);back.setImageDrawable(AppIcons.get(this,"back",MobileStyle.TEXT));back.setContentDescription("返回");back.setPadding(dp(12),dp(12),dp(12),dp(12));back.setOnClickListener(v->onBackPressed());header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));
        if(!"search".equals(mode)){header.addView(title,new LinearLayout.LayoutParams(0,dp(48),1));searchField=null;}
        switch(mode){case "settings":settings();break;case "add":addModules();break;case "history":records();break;default:search();}AppAppearance.paintFields(root);}
    private JSONArray terms(){try{return new JSONArray(prefs.getString("search_history","[]"));}catch(Exception e){return new JSONArray();}}
    private void submit(String term){term=term.trim();if(term.isEmpty())return;query=term.codePointCount(0,term.length())>100?term.substring(0,term.offsetByCodePoints(0,100)):term;
        if(prefs.getBoolean("record_search",true)){JSONArray next=new JSONArray(),old=terms();next.put(query);for(int i=0;i<old.length()&&next.length()<10;i++)if(!query.equals(old.optString(i)))next.put(old.optString(i));prefs.edit().putString("search_history",next.toString()).apply();}
        draftQuery=query;focusSearch=false;hideKeyboard();PageMotion.change(this,true,()->{mode="search";render();});}
    private void hideKeyboard(){if(searchField!=null)searchField.clearFocus();root.setFocusableInTouchMode(true);root.requestFocus();android.view.inputmethod.InputMethodManager ime=(android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);if(ime!=null)ime.hideSoftInputFromWindow(root.getWindowToken(),0);}
    private void search(){
        EditText field=new EditText(this);searchField=field;field.setSingleLine(true);field.setHint("搜索用户、论坛、Wiki、题目…");field.setContentDescription("全局搜索关键词");field.setText(draftQuery);field.setSelection(field.length());field.setShowSoftInputOnFocus(true);field.setPadding(dp(12),dp(4),dp(12),dp(4));field.setBackground(MobileStyle.panel(this,MobileStyle.SEARCH,100,0));field.setBackgroundTintList(null);field.setTag("appearance_field_surface");LinearLayout.LayoutParams fieldSize=new LinearLayout.LayoutParams(0,dp(48),1);fieldSize.setMargins(dp(4),0,dp(8),0);header.addView(field,fieldSize);field.setImeOptions(EditorInfo.IME_ACTION_SEARCH);field.setOnEditorActionListener((v,a,e)->{if(a==EditorInfo.IME_ACTION_SEARCH){submit(field.getText().toString());return true;}return false;});
        field.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){draftQuery=s.toString();}public void afterTextChanged(android.text.Editable e){}});
        Button go=iconButton("搜索","search",()->submit(field.getText().toString()),false);header.addView(go,new LinearLayout.LayoutParams(dp(48),dp(48)));
        if(focusSearch){field.requestFocus();field.post(this::focusInput);}else{root.setFocusableInTouchMode(true);root.requestFocus();}
        if(query.isEmpty()){hotPosts();recent(body);searchSettings();return;}
        body.addView(text("搜索结果 · "+query,21));body.addView(text("按搜索设置的优先级，从上到下展示。",12));
        searchSettings();if(modules.isEmpty()){card(body).addView(text("尚未启用搜索模块，请在搜索设置中添加。",15));return;}tagFilters();
        for(String id:modules)loadModule(id,1,card(body));
    }
    private void searchSettings(){LinearLayout box=card(body);box.addView(button("搜索设置",()->nav("settings")),new LinearLayout.LayoutParams(-1,dp(48)));}
    private void tagFilters(){
        if(!api.isLoggedIn()||!modules.contains("problems")&&!modules.contains("tracker"))return;
        LinearLayout tools=card(body);tools.addView(text("题目标签筛选",16));tools.addView(text("与当前关键词共同生效；只影响对应结果区块。",12));
        for(String id:Arrays.asList("problems","tracker"))if(modules.contains(id)){
            String selected="problems".equals(id)?problemTag:trackerTag;
            Button tags=button(SearchModules.NAMES.get(id)+"标签："+(selected.isEmpty()?"全部标签":selected),()->{
                int token=serial;long owner=api.sessionGeneration();
                ProblemTagPicker.show(this,api,io,"",selected,()->token==serial&&owner==api.sessionGeneration()&&"search".equals(mode),tag->{if("problems".equals(id))problemTag=tag;else trackerTag=tag;focusSearch=false;render();});
            });tags.setContentDescription("筛选"+SearchModules.NAMES.get(id)+"搜索标签");tools.addView(tags,new LinearLayout.LayoutParams(-1,dp(48)));
        }
    }
    private void hotPosts(){LinearLayout slot=card(body);slot.setContentDescription("热搜模块");slot.addView(text("热搜",18));slot.addView(text("正在读取热门话题…",12));read(()->api.get(api.publicPostsPath("")+"?sort=hot&page=1&page_size=30"),slot,true,value->{slot.addView(text("热搜",18));slot.addView(text("热门话题中阅读量较高的4条",12));List<JSONObject> posts=SearchHotPosts.select((JSONObject)value);if(posts.isEmpty())slot.addView(text("暂无热门话题",14));for(int i=0;i<posts.size();i++){JSONObject post=posts.get(i);Button open=button((i+1)+"  "+post.optString("title"),()->openResult("forum",post));open.setMaxLines(2);open.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);slot.addView(open,new LinearLayout.LayoutParams(-1,-2));}});}
    private TextView historyChip(String term,Runnable action){TextView chip=text(term,14);chip.setPadding(dp(10),dp(8),dp(10),dp(8));chip.setBackground(MobileStyle.panel(this,MobileStyle.controlFill(MobileStyle.PANEL),10,MobileStyle.LINE));chip.setFocusable(true);chip.setContentDescription("搜索历史 "+term);chip.setOnClickListener(v->action.run());return chip;}
    private void recent(LinearLayout parent){LinearLayout box=card(parent);box.addView(text("最近 10 条搜索",18));JSONArray items=terms();if(items.length()==0)box.addView(text("暂无历史搜索",14));WrapLayout words=new WrapLayout(this);words.setContentDescription("搜索历史词条");for(int i=0;i<items.length();i++){String term=items.optString(i);words.addView(historyChip(term,()->submit(term)));}box.addView(words,new LinearLayout.LayoutParams(-1,-2));box.addView(button("历史记录",()->nav("history")),new LinearLayout.LayoutParams(-1,-2));}
    private Button iconButton(String label,String icon,Runnable action,boolean red){Button b=button("",action);b.setContentDescription(label);b.setMinWidth(0);b.setMinimumWidth(0);b.setPadding(dp(10),dp(10),dp(10),dp(10));b.setBackground(MobileStyle.panel(this,red?0x80d93838:MobileStyle.controlFill(MobileStyle.ACCENT),100,0));b.setForeground(new android.graphics.drawable.InsetDrawable(AppIcons.get(this,icon,red?MobileStyle.TEXT:MobileStyle.ON_ACCENT),dp(12)));return b;}
    private void settings(){equalButtons(body,button("历史记录",()->nav("history")),button("添加模块",()->nav("add")));body.addView(text("越靠上越优先 · 长按模块任意位置，上下拖动排序",13));if(modules.isEmpty())card(body).addView(text("所有模块已移除，可以重新添加。",15));
        ModuleOrderView order=new ModuleOrderView(this,scroll,ids->{modules=new ArrayList<>(ids);saveModules();});order.setContentDescription("搜索模块排序列表");body.addView(order,new LinearLayout.LayoutParams(-1,-2));
        for(String id:modules){LinearLayout box=column();box.setPadding(dp(14),dp(14),dp(14),dp(14));box.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0));box.setContentDescription("拖动排序 "+SearchModules.NAMES.get(id));LinearLayout line=row();box.addView(line);line.addView(text(SearchModules.NAMES.get(id),18),new LinearLayout.LayoutParams(0,-2,1));
            Button remove=iconButton("移除 "+SearchModules.NAMES.get(id),"close",()->{modules.remove(id);saveModules();render();},true);line.addView(remove,new LinearLayout.LayoutParams(dp(48),dp(48)));box.addView(text(SearchModules.description(id),12));order.addModule(box,id);
        }}
    private void addModules(){int count=0;for(Map.Entry<String,String> entry:SearchModules.NAMES.entrySet()){if(modules.contains(entry.getKey()))continue;count++;LinearLayout box=card(body),line=row();box.addView(line);line.addView(text(entry.getValue(),18),new LinearLayout.LayoutParams(0,-2,1));Button add=iconButton("添加 "+entry.getValue(),"add",()->{modules.add(entry.getKey());saveModules();render();},false);line.addView(add,new LinearLayout.LayoutParams(dp(52),dp(52)));box.addView(text(SearchModules.description(entry.getKey()),12));}if(count==0)card(body).addView(text("所有模块均已添加。",15));}
    private void records(){LinearLayout settings=card(body);CheckBox enabled=new CheckBox(this);enabled.setText("记录搜索历史（仅本机，最多 10 条）");enabled.setChecked(prefs.getBoolean("record_search",true));enabled.setOnCheckedChangeListener((b,v)->prefs.edit().putBoolean("record_search",v).apply());settings.addView(enabled);EditText filter=input(settings,"查询历史记录","");LinearLayout list=column();body.addView(list);
        Runnable show=()->{list.removeAllViews();JSONArray values=terms();WrapLayout words=new WrapLayout(this);list.addView(words,new LinearLayout.LayoutParams(-1,-2));for(int i=0;i<values.length();i++){String term=values.optString(i);if(!term.toLowerCase(Locale.ROOT).contains(filter.getText().toString().toLowerCase(Locale.ROOT)))continue;TextView chip=historyChip(term,()->submit(term));chip.setOnLongClickListener(v->{new ModalDialogs.Builder(this).setTitle("删除这条搜索记录？").setMessage(term).setNegativeButton("返回",null).setPositiveButton("删除",(d,w)->{JSONArray next=new JSONArray(),old=terms();for(int k=0;k<old.length();k++)if(!term.equals(old.optString(k)))next.put(old.optString(k));prefs.edit().putString("search_history",next.toString()).apply();render();}).show();return true;});words.addView(chip);}if(words.getChildCount()==0)list.addView(text("暂无匹配记录",14));else list.addView(text("点击搜索 · 长按删除单条",12));};
        filter.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){show.run();}public void afterTextChanged(android.text.Editable e){}});settings.addView(button("清空历史记录",()->new ModalDialogs.Builder(this).setTitle("清空本机搜索记录？").setNegativeButton("返回",null).setPositiveButton("确认清空",(d,w)->{prefs.edit().remove("search_history").apply();render();}).show()));show.run();}
    private void loadModule(String id,int page,LinearLayout slot){slot.removeAllViews();slot.addView(text(SearchModules.NAMES.get(id),18));slot.addView(text("正在搜索…",12));
        if(!SearchModules.available(id)){error(slot,new ApiClient.UnavailableEndpointException(SearchModules.NAMES.get(id)+"搜索"));slot.addView(text(SearchModules.NAMES.get(id),16));return;}
        if(SearchModules.privateModule(id)&&!api.isLoggedIn()){error(slot,new ApiClient.ApiException(401,"请先登录",false));slot.addView(text(SearchModules.NAMES.get(id),16));return;}
        final String term=query,exactTag="problems".equals(id)?problemTag:"tracker".equals(id)?trackerTag:"";slot.setContentDescription(SearchModules.NAMES.get(id)+"搜索");
        read(()->{String path=SearchModules.path(id,term,page,exactTag);if("users".equals(id))path=api.leaderboardPath("")+path.substring(path.indexOf('?'));else if("forum".equals(id))path=api.publicPostsPath("")+path.substring(path.indexOf('?'));return api.get(path);},slot,true,value->showModule(id,page,slot,value));
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
            case "tracker":next=new Intent(this,WebFeaturesActivity.class).putExtra("feature","tracker").putExtra("initial_query",item.optString("contest_id")).putExtra("initial_platform",item.optString("platform")).putExtra("initial_problem_tag",trackerTag);break;
            default:next=new Intent(this,MainActivity.class).putExtra("web_problem_platform",item.optString("platform")).putExtra("web_problem_id",item.optString("problem_id"));}
        opening=true;startActivity(next);
    }
}
