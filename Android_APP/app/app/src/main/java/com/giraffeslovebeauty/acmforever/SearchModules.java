package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import java.util.*;

/** Stable IDs, ordering and API boundaries shared by global search and its settings. */
final class SearchModules {
    static final String KEY="global_search_modules";
    static final List<String> DEFAULT=Collections.unmodifiableList(Arrays.asList("users","forum","wiki","problems"));
    static final Map<String,String> NAMES;
    static {
        LinkedHashMap<String,String> names=new LinkedHashMap<>();
        names.put("users","用户");names.put("forum","论坛");names.put("wiki","Wiki");names.put("problems","题目");
        names.put("tracker","比赛进度");names.put("posts","我的话题");names.put("bookmarks","话题收藏");names.put("drafts","云端草稿");
        names.put("sheets","社团题单");names.put("discussions","按题讨论");names.put("mistakes","错题本");
        NAMES=Collections.unmodifiableMap(names);
    }
    static List<String> decode(String saved){
        if(saved==null)return new ArrayList<>(DEFAULT);
        try{JSONArray values=new JSONArray(saved);List<String> result=new ArrayList<>();for(int i=0;i<values.length();i++){String id=values.optString(i);if(NAMES.containsKey(id)&&!result.contains(id))result.add(id);}return result;}
        catch(Exception e){return new ArrayList<>(DEFAULT);}
    }
    static String encode(List<String> values){return new JSONArray(values).toString();}
    static List<String> move(List<String> values,String id,String before){
        List<String> next=new ArrayList<>(values);int from=next.indexOf(id),to=next.indexOf(before);
        if(from<0||to<0||from==to)return next;next.remove(from);next.add(to,id);return next;
    }
    static boolean available(String id){return NAMES.containsKey(id)&&!Arrays.asList("sheets","discussions","mistakes").contains(id);}
    static boolean privateModule(String id){return Arrays.asList("problems","tracker","posts","bookmarks","drafts").contains(id);}
    static String description(String id){
        switch(id){case "users":return "检索公开排行榜中的昵称和身份，包含零 AC 成员";
            case "forum":return "公开话题标题与正文";case "wiki":return "公开文章、标签与正文";
            case "problems":return "题名、题号或标签 · 需要登录";case "tracker":return "本人比赛进度 · 需要登录";
            case "posts":case "bookmarks":case "drafts":return "仅本人可见，在接口返回范围内筛选（最多最近 100 条）";
            default:return "无API接口：该模块尚无全局搜索接口";}
    }
    static String path(String id,String term,int page){
        String q=UrlEncoding.form(term);int p=Math.max(1,page);
        switch(id){case "forum":return "/api/forum/posts?q="+q+"&page="+p+"&page_size=6&sort=latest";
            case "wiki":return "/api/wiki/search?q="+q+"&page="+p+"&page_size=6";
            case "problems":return "/api/me/problems?tag="+q+"&page="+p+"&page_size=6&scope=all";
            case "tracker":return "/api/me/problems/tracker?tag="+q+"&scope=all&page="+p+"&page_size=6";
            case "posts":return "/api/forum/mine/posts";case "bookmarks":return "/api/forum/mine/bookmarks";case "drafts":return "/api/forum/drafts";
            case "users":return "/api/community/leaderboard?days=all&search="+q+"&page="+p+"&page_size=6&positive_only=0";
            default:throw new IllegalArgumentException("无API接口");}
    }
    static String path(String id,String term,int page,String exactTag){
        return path(id,term,page)+(Arrays.asList("problems","tracker").contains(id)?ProblemTags.parameter(exactTag):"");
    }
}
