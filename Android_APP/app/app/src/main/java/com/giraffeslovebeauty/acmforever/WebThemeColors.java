package com.giraffeslovebeauty.acmforever;

import java.util.*;

/** Colour solver equivalent to Web theme-colors.js; no Android or WebView dependency. */
final class WebThemeColors {
    private WebThemeColors(){}
    static int readable(int[] backgrounds,int preferred,double minimum){
        Solver solver=new Solver(backgrounds,preferred,minimum);
        if(solver.ratio(preferred)>=minimum)return preferred;
        List<double[]> intervals=new ArrayList<>();intervals.add(new double[]{0,1});
        for(int bg:backgrounds){double level=ThemePalette.luminance(bg),lower=(level+.05)/minimum-.05,upper=minimum*(level+.05)-.05;List<double[]> next=new ArrayList<>();
            for(double[] range:intervals){double lo=range[0],hi=range[1];if(lo<=Math.min(hi,lower))next.add(new double[]{lo,Math.min(hi,lower)});if(Math.max(lo,upper)<=hi)next.add(new double[]{Math.max(lo,upper),hi});}intervals=next;
        }
        for(double[] range:intervals){double lo=range[0],hi=range[1];solver.edge(0xff000000,preferred,hi,true);solver.edge(preferred,0xffffffff,lo,false);
            int left=0,right=256;while(left<right){int mid=(left+right)>>>1;if(ThemePalette.luminance(gray(mid))<lo)left=mid+1;else right=mid;}int low=left;
            left=0;right=256;while(left<right){int mid=(left+right)>>>1;if(ThemePalette.luminance(gray(mid))<=hi)left=mid+1;else right=mid;}int high=left-1;
            if(low<=high&&low<=255&&high>=0)solver.consider(gray(Math.max(low,Math.min(high,(int)Math.round((((preferred>>16)&255)+((preferred>>8)&255)+(preferred&255))/3.0)))));
        }
        if(solver.safe!=null)return solver.safe;
        // Keep the Web fallback's candidate order and ties, including incompatible surfaces.
        solver.best=0xff000000;solver.bestRatio=-1;LinkedHashSet<Integer> candidates=new LinkedHashSet<>();candidates.add(preferred);candidates.add(0xff000000);candidates.add(0xffffffff);
        for(int i=0;i<=50;i++){candidates.add(ThemePalette.mix(preferred,0xff000000,i/50.0));candidates.add(ThemePalette.mix(preferred,0xffffffff,i/50.0));}
        for(int i=0;i<=255;i++)candidates.add(gray(i));for(int candidate:candidates)solver.consider(candidate);return solver.safe!=null?solver.safe:solver.best;
    }
    private static int gray(int n){return 0xff000000|(n<<16)|(n<<8)|n;}
    private static final class Solver {
        final int[] backgrounds;final int preferred;final double minimum;Integer safe;int best;double distance=Double.POSITIVE_INFINITY,bestRatio=-1;
        Solver(int[] backgrounds,int preferred,double minimum){this.backgrounds=backgrounds;this.preferred=preferred;this.minimum=minimum;}
        double ratio(int color){double result=Double.POSITIVE_INFINITY;for(int background:backgrounds)result=Math.min(result,ThemePalette.contrast(color,background));return result;}
        void consider(int color){double contrast=ratio(color);if(contrast>bestRatio){best=color;bestRatio=contrast;}if(contrast>=minimum){double d=0;for(int shift:new int[]{16,8,0})d+=Math.pow(((color>>shift)&255)-((preferred>>shift)&255),2);if(d<distance){safe=color;distance=d;}}}
        void edge(int from,int to,double threshold,boolean lastBelow){double lo=0,hi=1;for(int i=0;i<18;i++){double mid=(lo+hi)/2,value=ThemePalette.luminance(ThemePalette.mix(from,to,mid));if(lastBelow?value<=threshold:value<threshold)lo=mid;else hi=mid;}consider(ThemePalette.mix(from,to,lastBelow?lo:hi));}
    }
}
