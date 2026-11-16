package com.giraffeslovebeauty.acmforever;

final class RetryDelay {
    static long millis(int failure,double random){long base=10000L<<Math.min(3,Math.max(0,failure));base=Math.min(60000,base);return Math.min(60000,Math.round(base*(.95+.1*Math.max(0,Math.min(1,random)))));}
}
