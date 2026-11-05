package com.giraffeslovebeauty.acmforever;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

/** Bounded page history, newest first. Only UI snapshots belong here. */
final class NavigationStack<T> {
    private static final int LIMIT=32;
    private final ArrayDeque<T> entries=new ArrayDeque<>();
    void push(T entry){if(entry==null)return;entries.push(entry);while(entries.size()>LIMIT)entries.removeLast();}
    T pop(){return entries.pollFirst();}
    boolean isEmpty(){return entries.isEmpty();}
    void clear(){entries.clear();}
    ArrayList<T> snapshot(){return new ArrayList<>(entries);}
    void restore(List<T> saved){entries.clear();if(saved==null)return;for(T entry:saved){if(entry!=null)entries.addLast(entry);if(entries.size()==LIMIT)break;}}
}
