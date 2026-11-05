package com.giraffeslovebeauty.acmforever;

import org.json.*;
import java.util.*;

/** Existing PATCH contract: bind all edits to the exact account epoch/profile snapshot. */
final class AdminMemberEdits {
    static final String[] FIELDS={"name","real_name","school","status","cf_handle","atcoder_handle","luogu_id","nowcoder_id"};
    static final String[] LABELS={"用户名（昵称）","真实姓名","学校","身份","Codeforces","AtCoder","洛谷 UID","牛客 UID"};
    static final Map<String,String> BINDINGS=new LinkedHashMap<>();
    static {BINDINGS.put("cf_handle","codeforces");BINDINGS.put("atcoder_handle","atcoder");BINDINGS.put("luogu_id","luogu");BINDINGS.put("nowcoder_id","nowcoder");}
    static JSONObject payload(JSONObject snapshot,Map<String,String> values)throws JSONException {
        long epoch=snapshot.getLong("account_epoch");String revision=snapshot.getString("profile_revision");
        if(epoch<1||!revision.matches("[a-f0-9]{64}"))throw new IllegalArgumentException("资料版本不完整，请刷新后再修改");
        JSONObject data=new JSONObject().put("expected_account_epoch",epoch).put("profile_revision",revision),expected=new JSONObject(),versions=new JSONObject();boolean binding=false;
        for(String field:FIELDS){if(!values.containsKey(field))continue;String value=values.get(field).trim(),old=snapshot.optString(field,"");int limit="status".equals(field)||BINDINGS.containsKey(field)?64:128;
            if(value.codePointCount(0,value.length())>limit)throw new IllegalArgumentException("资料字段过长，最多 "+limit+" 字符");
            if("name".equals(field)&&value.isEmpty())throw new IllegalArgumentException("用户名不能为空");
            if(BINDINGS.containsKey(field)){
                if(value.equalsIgnoreCase(old))continue;
                if(!value.isEmpty()&&!value.matches(field.endsWith("_id")?"[1-9][0-9]{0,19}":"[A-Za-z0-9_.-]{1,64}"))throw new IllegalArgumentException("OJ 绑定请填写账号标识，不要填写网址");
                String platform=BINDINGS.get(field);expected.put(field,old);versions.put(platform,snapshot.getJSONObject("binding_versions").getLong(platform));binding=true;
            }else if(value.equals(old))continue;
            data.put(field,value);
        }
        if(data.length()==2)throw new IllegalArgumentException("没有修改内容");
        if(binding)data.put("confirm_bindings",true).put("expected_bindings",expected).put("binding_versions",versions);
        return data;
    }
    static boolean canManageAccount(boolean root,String role){return root||"member".equals(role);}
    static boolean active(JSONObject snapshot){return snapshot.optBoolean("is_active",false)||snapshot.optInt("is_active",0)==1;}
}
