package com.giraffeslovebeauty.acmforever;

/** Same visible ranges, sorts and page sizes as the Vue leaderboard. */
final class RankOptions {
    static String path(String range,String sort,String platforms,String search,int page,int size){
        if(!java.util.Arrays.asList("7","30","90","365","all").contains(range))range="7";
        if(!java.util.Arrays.asList("total_count","cf_count","luogu_count","atcoder_count","nowcoder_count","cjlu_count").contains(sort))sort="total_count";
        if(size!=10&&size!=20&&size!=50&&size!=100)size=20;
        return "/api/community/leaderboard?days="+range+"&sort="+sort+"&platforms="+UrlEncoding.form(platforms)
            +"&search="+UrlEncoding.form(search)+"&page="+Math.max(1,page)+"&page_size="+size+"&positive_only=1";
    }
}
