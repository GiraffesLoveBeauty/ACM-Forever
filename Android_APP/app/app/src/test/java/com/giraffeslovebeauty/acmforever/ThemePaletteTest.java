package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class ThemePaletteTest {
    @Test public void oldThemesKeepWhiteSecondaryAndOriginalSearchSurface(){
        ThemePalette palette=ThemePalette.acm(0xff83b8e5);
        assertEquals(0xffffffff,palette.surface);
        assertEquals(0xfff4f5f7,palette.background);
        assertEquals(0xff83b8e5,palette.accent);
        assertFalse(palette.dark);
    }
    @Test public void primaryAndSecondaryAreIndependentAndTextStaysReadable(){
        for(int secondary:new int[]{0xffffffff,0xffebafc5,0xff82c7aa,0xff83b8e5,0xff292c29,0xff000000}){
            ThemePalette blue=ThemePalette.acm(0xff83b8e5,secondary),pink=ThemePalette.acm(0xffebafc5,secondary);
            assertEquals(secondary,blue.surface);
            assertEquals(blue.surface,pink.surface);
            assertEquals(blue.background,pink.background);
            assertEquals(0xff83b8e5,blue.accent);
            assertEquals(0xffebafc5,pink.accent);
            assertTrue(ThemePalette.contrast(secondary,blue.text)>=4.49);
            assertTrue(ThemePalette.contrast(blue.background,blue.text)>=4.49);
            assertTrue(ThemePalette.contrast(secondary,blue.brand)>=4.49);
        }
        assertTrue(ThemePalette.acm(0xff83b8e5,0xff292c29).dark);
    }
}
