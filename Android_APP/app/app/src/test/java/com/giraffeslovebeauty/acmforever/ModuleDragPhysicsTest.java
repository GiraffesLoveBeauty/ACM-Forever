package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class ModuleDragPhysicsTest {
    @Test public void neighbourMovesBeforeVisualBordersOverlap() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{100,100,100,100},0,14,8);
        motion.step(5,.016f);
        assertTrue(5+95 < 114+5); // The selected and next 90% borders have not met.
        assertTrue(motion.position(1)>114);
        assertEquals(Arrays.asList(0,1,2,3),motion.order());
    }
    @Test public void contactPropagatesRowByRowInsteadOfMovingEveryRowAtOnce() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{100,100,100,100},0,14,8);
        motion.step(15,.016f);
        assertTrue(motion.position(1)>114);
        assertEquals(228,motion.position(2),.001f);
        assertEquals(342,motion.position(3),.001f);
        for(int i=0;i<15;i++)motion.step(15,.016f);
        assertTrue(motion.position(2)>228);
        assertTrue(motion.position(1)-114>motion.position(3)-342);
    }
    @Test public void vacancyFillsWhenDraggedRowMovesIntoNextSlot() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{100,100,100,100},0,14,8);
        for(int i=0;i<12;i++)motion.step(i*13,.016f);
        assertEquals(Arrays.asList(1,0,2,3),motion.order());
        for(int i=0;i<120;i++)motion.step(143,.016f);
        assertEquals(0,motion.position(1),.1f);
    }
    @Test public void upwardContactAlsoStartsBeforeOverlapAndUsesActualRowHeights() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{80,120,90,100},2,14,8);
        motion.step(223,.016f);
        assertTrue(94+114 < 223+4.5f);
        assertTrue(motion.position(1)<94);
        assertEquals(0,motion.position(0),0);
        assertEquals(Arrays.asList(0,1,2,3),motion.order());
    }
    @Test public void upwardPressureCannotPushFirstRowIntoHeader() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{80,120,90},1,14,8);
        for(int i=0;i<120;i++)motion.step(89,.016f);
        assertEquals(0,motion.position(0),0);
    }
    @Test public void clampedTallerRowCanStillTakeEitherEndSlot() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{80,140,90},1,14,8);
        for(int i=0;i<120;i++)motion.step(-100,.016f);
        assertEquals(Arrays.asList(1,0,2),motion.order());
        assertEquals(0,motion.position(1),0);
        assertTrue(motion.position(0)>=140);
        for(int i=0;i<120;i++)motion.step(10000,.016f);
        assertEquals(Arrays.asList(0,2,1),motion.order());
        assertEquals(198,motion.position(1),0);
        assertTrue(motion.position(2)+90<=motion.position(1));
    }
    @Test public void downwardPressureCannotPushLastRowOutsideList() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{80,120,90},1,14,8);
        for(int i=0;i<120;i++)motion.step(99,.016f);
        assertEquals(228,motion.position(2),0);
    }
    @Test public void rapidReversalsAndSettlingKeepEveryRowWithinListBounds() {
        float[] heights={80,120,90,140};float total=472;
        for(int selected=0;selected<heights.length;selected++){
            ModuleDragPhysics motion=new ModuleDragPhysics(heights,selected,14,8);
            for(int frame=0;frame<320;frame++){
                motion.step(frame%80<40?frame%40*16:total-frame%40*16,.016f);
                for(int id=0;id<heights.length;id++){
                    assertTrue(motion.position(id)>=0);
                    assertTrue(motion.position(id)+heights[id]<=total);
                }
                assertEquals(heights.length,new HashSet<>(motion.order()).size());
            }
        }
    }
    @Test public void fastMovesStayBoundedAndCanReverseWithoutLosingRows() {
        ModuleDragPhysics motion=new ModuleDragPhysics(new float[]{100,140,80,120},0,14,8);
        motion.step(10000,.5f);
        assertEquals(Arrays.asList(1,2,3,0),motion.order());
        assertTrue(Float.isFinite(motion.position(0)));
        motion.step(-10000,.5f);
        assertEquals(Arrays.asList(0,1,2,3),motion.order());
        assertEquals(0,motion.position(0),0);
    }
}
