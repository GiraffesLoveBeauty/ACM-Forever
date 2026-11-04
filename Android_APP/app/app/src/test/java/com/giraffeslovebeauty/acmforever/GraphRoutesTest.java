package com.giraffeslovebeauty.acmforever;
import org.junit.Test;
import static org.junit.Assert.*;
public class GraphRoutesTest {
    @Test public void defaultRouteMatchesWeb(){GraphRoutes graph=new GraphRoutes();assertArrayEquals(new int[]{0,6,7,5},graph.route(5));assertEquals(9,graph.distances[5]);assertEquals("s → v → d → t · 权重 9",graph.description(5));}
    @Test public void everyTargetHasAnOptimalConnectedRoute(){GraphRoutes graph=new GraphRoutes();for(int target=0;target<GraphRoutes.NAMES.length;target++){int sum=0;int[] route=graph.route(target);assertEquals(0,route[0]);assertEquals(target,route[route.length-1]);for(int i=1;i<route.length;i++){boolean found=false;for(int[] edge:GraphRoutes.EDGES)if((edge[0]==route[i-1]&&edge[1]==route[i])||(edge[1]==route[i-1]&&edge[0]==route[i])){sum+=edge[2];found=true;break;}assertTrue(found);}assertEquals(graph.distances[target],sum);}for(int[] edge:GraphRoutes.EDGES){assertTrue(graph.distances[edge[0]]<=graph.distances[edge[1]]+edge[2]);assertTrue(graph.distances[edge[1]]<=graph.distances[edge[0]]+edge[2]);}}
    @Test public void selectingSourceReturnsZeroCost(){GraphRoutes graph=new GraphRoutes();assertArrayEquals(new int[]{0},graph.route(0));assertEquals(0,graph.distances[0]);}
}
