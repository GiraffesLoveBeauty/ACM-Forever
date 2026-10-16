package com.giraffeslovebeauty.acmforever;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;

/** UTF-8 form encoding using the overload available on every supported Android version. */
final class UrlEncoding {
    private UrlEncoding() { }

    static String form(String value) {
        try { return URLEncoder.encode(value, "UTF-8"); }
        catch (UnsupportedEncodingException impossible) { throw new AssertionError(impossible); }
    }
}
