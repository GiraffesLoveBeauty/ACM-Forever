package com.giraffeslovebeauty.acmforever;

import java.util.*;

/** The same weighted undirected graph as latest Web GraphArt.vue. No business API. */
final class GraphRoutes {
    static final String[] NAMES={"s","u","a","b","c","t","v","d","e","f","g","h"};
    static final float[][] POINTS={{50,151},{114,83},{177,47},{248,63},{323,96},{348,174},{198,130},{256,167},{285,232},{155,215},{84,227},{312,32}};
    static final int[][] EDGES={{0,1,7},{0,6,3},{0,10,10},{1,2,4},{1,6,6},{2,3,8},{2,11,13},{3,4,7},{3,6,9},{4,5,8},{4,11,3},{6,7,2},{6,9,6},{7,5,4},{7,8,7},{9,8,8},{9,10,4},{10,8,16},{8,5,9},{3,7,9},{11,5,16}};
    final int[] distances=new int[NAMES.length];
    private final int[] previous=new int[NAMES.length];
    GraphRoutes(){
        Arrays.fill(distances,Integer.MAX_VALUE);Arrays.fill(previous,-1);distances[0]=0;boolean[] visited=new boolean[NAMES.length];
        for(int step=0;step<NAMES.length;step++){
            int current=-1;for(int i=0;i<NAMES.length;i++)if(!visited[i]&&(current<0||distances[i]<distances[current]))current=i;
            if(current<0||distances[current]==Integer.MAX_VALUE)break;visited[current]=true;
            for(int[] edge:EDGES){int next=edge[0]==current?edge[1]:edge[1]==current?edge[0]:-1;if(next>=0&&distances[current]+edge[2]<distances[next]){distances[next]=distances[current]+edge[2];previous[next]=current;}}
        }
    }
    int[] route(int target){
        if(target<0||target>=NAMES.length)throw new IllegalArgumentException("Unknown node");
        ArrayList<Integer> nodes=new ArrayList<>();for(int at=target;at>=0;at=previous[at])nodes.add(at);
        Collections.reverse(nodes);return nodes.stream().mapToInt(Integer::intValue).toArray();
    }
    String description(int target){StringBuilder text=new StringBuilder();for(int node:route(target)){if(text.length()>0)text.append(" → ");text.append(NAMES[node]);}return text+" · 权重 "+distances[target];}
}
