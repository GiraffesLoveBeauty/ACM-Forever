package com.giraffeslovebeauty.acmforever;

import org.json.JSONTokener;
import java.util.LinkedHashMap;
import java.util.Map;

/** Bounded process cache. Store JSON text so renderers never mutate another page's snapshot. */
final class ResponseCache {
    private final LinkedHashMap<String,String> values=new LinkedHashMap<>(16,.75f,true);
    private int characters;
    private final int limit;
    ResponseCache(){this(4*1024*1024);}
    ResponseCache(int limit){this.limit=limit;}
    synchronized Object get(String key) throws Exception {
        String value=values.get(key);return value==null?null:new JSONTokener(value).nextValue();
    }
    synchronized void put(String key,Object value){
        String text=value.toString();String old=values.remove(key);if(old!=null)characters-=old.length();
        if(text.length()>limit)return;values.put(key,text);characters+=text.length();
        while(characters>limit||values.size()>160){Map.Entry<String,String> first=values.entrySet().iterator().next();characters-=first.getValue().length();values.remove(first.getKey());}
    }
    synchronized void clear(){values.clear();characters=0;}
    synchronized long byteSize(){long bytes=0;for(String text:values.values())bytes+=text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;return bytes;}
    synchronized void remove(String key){String old=values.remove(key);if(old!=null)characters-=old.length();}
    synchronized void removeContaining(String path){values.entrySet().removeIf(entry->{if(!entry.getKey().contains(path))return false;characters-=entry.getValue().length();return true;});}
}
