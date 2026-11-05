package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** Bundled historical notes, independent of the server's next-release manifest. */
final class ReleaseHistory {
    static final String ASSET="releases/history.json";
    final List<Entry> entries;
    private ReleaseHistory(List<Entry> entries){this.entries=Collections.unmodifiableList(entries);}
    static ReleaseHistory parse(String source,String installedVersion)throws JSONException{
        JSONObject root=new JSONObject(source);JSONArray items=root.getJSONArray("entries");
        if(root.getInt("schemaVersion")!=1||items.length()<1||items.length()>200)throw new JSONException("更新日志格式无效");
        ArrayList<Entry> entries=new ArrayList<>();HashSet<String> versions=new HashSet<>();Entry previous=null;
        for(int i=0;i<items.length();i++){
            Entry entry=new Entry(items.getJSONObject(i));
            if(!versions.add(entry.versionName)||previous!=null&&compare(previous.versionName,entry.versionName)<=0)throw new JSONException("更新日志版本顺序无效");
            entries.add(entry);previous=entry;
        }
        if(!entries.get(0).versionName.equals(installedVersion))throw new JSONException("更新日志与安装版本不一致");
        return new ReleaseHistory(entries);
    }
    private static int compare(String a,String b){String[] x=a.split("\\."),y=b.split("\\.");for(int i=0;i<3;i++){int order=Integer.compare(Integer.parseInt(x[i]),Integer.parseInt(y[i]));if(order!=0)return order;}return 0;}
    private static String required(JSONObject value,String key,int limit)throws JSONException{String text=value.getString(key).trim();if(text.isEmpty()||text.length()>limit)throw new JSONException("更新日志缺少有效内容");return text;}
    static final class Entry {
        final String versionName,date,summary;final List<String> changes,notes;
        private Entry(JSONObject item)throws JSONException{
            versionName=required(item,"versionName",24);if(!versionName.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}"))throw new JSONException("更新日志版本无效");
            date=item.optString("recordDate","");if(!date.isEmpty()&&!date.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}"))throw new JSONException("更新日志日期无效");
            summary=required(item,"summary",300);changes=lines(item.getJSONArray("changes"),true);notes=lines(item.optJSONArray("notes"),false);
        }
        private List<String> lines(JSONArray array,boolean required)throws JSONException{
            if(array==null){if(required)throw new JSONException("更新日志缺少变更");return Collections.emptyList();}
            if(array.length()>40||required&&array.length()==0)throw new JSONException("更新日志条目无效");
            ArrayList<String> out=new ArrayList<>();for(int i=0;i<array.length();i++){String text=array.getString(i).trim();if(text.isEmpty()||text.length()>2000)throw new JSONException("更新说明内容无效");out.add(text);}return Collections.unmodifiableList(out);
        }
        String details(){
            StringBuilder text=new StringBuilder();if(!date.isEmpty())text.append("记录日期：").append(date).append("\n\n");
            text.append(summary).append("\n\n更新日志\n");for(String change:changes)text.append("• ").append(change).append("\n\n");
            if(!notes.isEmpty()){text.append("更新说明\n");for(String note:notes)text.append("• ").append(note).append("\n\n");}
            text.append("以上为该版本的本地调试记录；当前行为以最新版本为准。版本日志不代表服务器已发布对应接口。");return text.toString();
        }
    }
}
