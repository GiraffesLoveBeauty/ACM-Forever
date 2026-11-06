package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class PageMotionTest {
    @Test public void bottomDestinationsArePeersButDetailAndAccountAreNot(){
        for(String from:new String[]{"forum","rank","compose","problems","mine"})
            for(String to:new String[]{"forum","rank","compose","problems","mine"})assertTrue(PageMotion.parallel(from,to));
        assertFalse(PageMotion.parallel("forum","detail"));assertFalse(PageMotion.parallel("account","mine"));
        assertFalse(PageMotion.parallel("problem_detail","problems"));assertFalse(PageMotion.parallel("member","detail"));
    }
}
