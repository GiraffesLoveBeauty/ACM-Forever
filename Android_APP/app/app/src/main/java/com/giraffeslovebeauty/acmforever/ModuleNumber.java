package com.giraffeslovebeauty.acmforever;

/** Human-readable catalog number. Content hashes, signatures and native compatibility remain separate. */
final class ModuleNumber {
    static String pinyin(String id){switch(id){
        case "official-themes":return "guan_1_fang_1_zhu_3_ti_2_ku_4";
        case "advanced":return "gao_1_ji_2_ge_4_xing_4_hua_4";
        case "admin":return "shou_3_ji_1_bian_4_jie_2_guan_3_li_3";
        case "cat-art":return "fen_1_ceng_2_mao_1_niang_2_su_4_cai_2";
        default:throw new IllegalArgumentException("未知模块");
    }}
    static String create(String id,String version,String build){
        if(!version.matches("[0-9]+\\.[0-9]+\\.[0-9]+")||build.isEmpty()||!build.matches("M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})"))throw new IllegalArgumentException("模块编号无效");
        return pinyin(id)+"-"+version+"-"+build;
    }
    static String validate(String id,String version,String number){
        int separator=number.lastIndexOf('-');
        if(separator<0||!number.equals(create(id,version,number.substring(separator+1))))throw new IllegalArgumentException("模块编号与模块或App版本不匹配");
        return number;
    }
    private ModuleNumber(){}
}
