package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class ModuleEdgeScrollTest {
    private int distance(float pointer,int hz,float density){ModuleEdgeScroll motion=new ModuleEdgeScroll(density);int pixels=0;for(int i=0;i<hz;i++)pixels+=motion.step(pointer,800,64,1f/hz);return pixels;}
    @Test public void equalTimeTravelsTheSameDistanceAt60And120Hz(){
        assertEquals(distance(800,60,2.75f),distance(800,120,2.75f),1);
        assertEquals(-distance(0,60,1),distance(800,60,1));
    }
    @Test public void approachingEdgeGraduallyIncreasesSpeedWithALowerCap(){
        int shallow=distance(744,60,1),middle=distance(768,60,1),edge=distance(800,60,1);
        assertTrue(shallow<middle&&middle<edge);
        assertTrue(edge>60&&edge<=96);
        assertEquals(0,distance(400,60,1));
    }
    @Test public void leavingBandStopsImmediatelyAndDropsFractionalCarry(){
        ModuleEdgeScroll motion=new ModuleEdgeScroll(1);
        for(int i=0;i<60;i++)motion.step(800,800,64,1f/60);
        for(int i=0;i<60;i++)assertEquals(0,motion.step(400,800,64,1f/60));
        assertEquals(0,motion.step(800,800,64,1f/120));
    }
    @Test public void reversingDirectionDoesNotKeepScrollingTheOldWay(){
        ModuleEdgeScroll motion=new ModuleEdgeScroll(2);int distance=0;
        for(int i=0;i<60;i++)motion.step(800,800,64,1f/60);
        for(int i=0;i<30;i++){int delta=motion.step(0,800,64,1f/60);assertTrue(delta<=0);distance+=delta;}
        assertTrue(distance<0);
    }
    @Test public void stalledFramesDoNotCauseLargeJumps(){
        ModuleEdgeScroll motion=new ModuleEdgeScroll(1);
        for(int i=0;i<60;i++)motion.step(800,800,64,1f/60);
        int delta=motion.step(800,800,64,2);
        assertTrue(delta>=0&&delta<=5);
    }
    @Test public void smallViewportsKeepANeutralZoneAndInvalidGeometryStops(){
        ModuleEdgeScroll motion=new ModuleEdgeScroll(1);
        assertEquals(0,motion.step(30,60,64,.016f));
        assertEquals(0,motion.step(0,0,64,.016f));
        assertEquals(0,motion.step(0,800,0,.016f));
    }
}
