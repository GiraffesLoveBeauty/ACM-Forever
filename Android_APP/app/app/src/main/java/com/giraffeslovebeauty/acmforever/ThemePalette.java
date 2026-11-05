package com.giraffeslovebeauty.acmforever;

/** Pure colour calculations shared by native pages and local theme previews. */
final class ThemePalette {
    final int primary,background,surface,accent,text,muted,line,brand,hero,onHero,onAccent,onSelected,selected,cat;
    final boolean dark;
    ThemePalette(int primary,int background,int surface,int accent,boolean dark,boolean industrial){
        this(primary,background,surface,accent,dark,industrial,false);
    }
    ThemePalette(int primary,int background,int surface,int accent,boolean dark,boolean industrial,int[] overrides){this(primary,background,surface,accent,dark,industrial,false,overrides);}
    private ThemePalette(int primary,int background,int surface,int accent,boolean dark,boolean industrial,boolean acm){
        this(primary,background,surface,accent,dark,industrial,acm,new int[6]);
    }
    private ThemePalette(int primary,int background,int surface,int accent,boolean dark,boolean industrial,boolean acm,int[] overrides){
        this.primary=primary;this.background=background;this.surface=surface;this.accent=accent;this.dark=dark;
        text=overrides[0]!=0?overrides[0]:industrial?(dark?0xfff5f6eb:0xff292c29):solve(acm,new int[]{background,surface},dark?0xffedf5eb:acm?0xff1e211c:0xff163432,4.5);
        muted=overrides[1]!=0?overrides[1]:industrial?(dark?0xffb4bbac:0xff62685e):solve(acm,new int[]{background,surface},mix(text,surface,.3),4.5);
        line=overrides[2]!=0?overrides[2]:industrial?(dark?0xff454b41:0xffc7cabc):mix(surface,text,.22);
        brand=overrides[3]!=0?overrides[3]:solve(acm,new int[]{background,surface},primary,4.5);
        hero=overrides[5]!=0?overrides[5]:acm?accent:industrial?(dark?0xff151814:0xff20231f):mix(surface,primary,dark?.1:.15);
        onHero=solve(acm,new int[]{hero},acm?text:0xffffffff,4.5);onAccent=solve(acm,new int[]{accent},acm?text:0xff163432,4.5);
        selected=mix(surface,primary,acm?.12:.1);
        onSelected=acm?onAccent:overrides[4]!=0?overrides[4]:WebThemeColors.readable(new int[]{selected},primary,4.5);
        cat=readable(new int[]{surface,accent},primary,3);
    }
    private static int solve(boolean nativeTheme,int[] surfaces,int preferred,double minimum){return nativeTheme?readable(surfaces,preferred,minimum):WebThemeColors.readable(surfaces,preferred,minimum);}
    static ThemePalette acm(int primary){return acm(primary,0xffffffff);}
    static ThemePalette acm(int primary,int secondary){
        boolean dark=luminance(secondary)<.35;
        // White keeps the existing mist-grey search surface; other colours follow the secondary tone.
        int background=mix(secondary,dark?0xffffffff:0xff566883,.065);
        return new ThemePalette(primary,background,secondary,primary,dark,false,true);
    }
    static int module(int surface,int transparency){return (surface&0x00ffffff)|(Math.round(255*(1-Math.max(0,Math.min(5,transparency))/5f))<<24);}
    static int mix(int a,int b,double amount){int out=0xff000000;for(int shift:new int[]{16,8,0})out|=((int)Math.round(((a>>shift)&255)*(1-amount)+((b>>shift)&255)*amount))<<shift;return out;}
    static double luminance(int color){double result=0;double[] weights={.2126,.7152,.0722};int[] shifts={16,8,0};for(int i=0;i<3;i++){double c=((color>>shifts[i])&255)/255.0;result+=weights[i]*(c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4));}return result;}
    static double contrast(int a,int b){double x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
    static int readable(int[] surfaces,int preferred,double minimum){
        int best=preferred;double bestRatio=0,bestDistance=Double.MAX_VALUE;
        for(int target:new int[]{0xff000000,0xffffffff})for(int step=0;step<=100;step++){
            int candidate=mix(preferred,target,step/100.0);double ratio=Double.MAX_VALUE;for(int bg:surfaces)ratio=Math.min(ratio,contrast(bg,candidate));
            double distance=0;for(int shift:new int[]{16,8,0})distance+=Math.pow(((candidate>>shift)&255)-((preferred>>shift)&255),2);
            if(ratio>=minimum&&distance<bestDistance){best=candidate;bestDistance=distance;}
            if(bestDistance==Double.MAX_VALUE&&ratio>bestRatio){best=candidate;bestRatio=ratio;}
        }
        return best;
    }
}
