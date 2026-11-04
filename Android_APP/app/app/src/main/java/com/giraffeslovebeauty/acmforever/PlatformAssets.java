package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.drawable.Drawable;

/** Original platform branding, fetched from each platform's publicly served official site. */
final class PlatformAssets {
    private PlatformAssets(){}
    static String name(String key){switch(key){case "all":return "ALL";case "codeforces":return "Codeforces";case "luogu":return "洛谷";case "atcoder":return "AtCoder";case "nowcoder":return "牛客";default:return "校 OJ";}}
    static Drawable logo(Context context,String key){
        if("all".equals(key))return AppIcons.get(context,"compose",MobileStyle.CAT);
        int resource;switch(key){case "codeforces":resource=R.drawable.platform_codeforces;break;case "luogu":resource=R.drawable.platform_luogu;break;
            case "atcoder":resource=R.drawable.platform_atcoder;break;case "nowcoder":resource=R.drawable.platform_nowcoder;break;default:resource=R.drawable.platform_cjlu;}
        return context.getDrawable(resource).mutate();
    }
}
