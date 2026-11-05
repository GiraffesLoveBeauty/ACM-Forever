package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.view.View;
import org.json.*;

/** Device-owned background and theme; never sent through ApiClient. */
final class AppAppearance {
    private static ThemePalette palette=ThemePalette.acm(0xffc8eb21);
    static SharedPreferences prefs(Context c){return c.getSharedPreferences("acmforever_settings",0);}
    static long revision(Context c){return prefs(c).getLong("appearance_revision",0);}
    static void changed(Context c,SharedPreferences.Editor edit){edit.putLong("appearance_revision",revision(c)+1).apply();load(c);}
    static void load(Context c){
        SharedPreferences p=prefs(c);
        MobileStyle.DESIGN="original";
        if(!p.contains("bg_mode"))p.edit().putString("bg_mode",ProfileCover.exists(c)?"image":p.getBoolean("profile_gradient",false)?"gradient":"solid")
                .putString("bg_source","custom").putInt("bg_color",0xffffffff).putInt("bg_transparency",2).apply();
        try{
            if("web".equals(p.getString("theme_source","acm"))){
                JSONObject preset=findPreset(c,p.getString("theme_preset","industrial"));boolean dark=p.getBoolean("theme_dark",false);JSONObject profile=WebThemes.profile(preset,dark),colors=profile.getJSONObject("colors");
                MobileStyle.DESIGN=preset.optString("design_template","original");
                palette=new ThemePalette(Color.parseColor(colors.getString("primary")),Color.parseColor(colors.getString("background")),Color.parseColor(colors.getString("surface")),Color.parseColor(colors.getString("accent")),dark,"industrial".equals(preset.getString("id")),WebThemes.overrides(profile));
            }else palette=ThemePalette.acm(p.getInt("theme_primary",0xffc8eb21),p.getInt("theme_secondary",0xffffffff));
        }catch(Exception e){palette=ThemePalette.acm(0xffc8eb21);MobileStyle.DESIGN="original";}
        MobileStyle.BACKGROUND=palette.background;MobileStyle.PANEL=palette.surface;MobileStyle.TEXT=palette.text;MobileStyle.MUTED=palette.muted;
        MobileStyle.ACCENT=palette.accent;MobileStyle.BRAND=palette.brand;MobileStyle.LINE=palette.line;MobileStyle.HERO=palette.hero;MobileStyle.ON_HERO=palette.onHero;MobileStyle.ON_ACCENT=palette.onAccent;MobileStyle.ON_SELECTED=palette.onSelected;MobileStyle.SELECTED=palette.selected;MobileStyle.CAT=palette.cat;
        MobileStyle.MODULE=ThemePalette.module(palette.surface,p.getInt("module_transparency",0));
        MobileStyle.CONTROL_TRANSPARENCY=Math.max(0,Math.min(5,p.getInt("control_transparency",0)));
        MobileStyle.CHROME=MobileStyle.controlFill(palette.surface);MobileStyle.SEARCH=MobileStyle.controlFill(palette.background);
    }
    static ThemePalette palette(){return palette;}
    static JSONArray imported(Context c){try{return new JSONArray(prefs(c).getString("web_imported_themes","[]"));}catch(JSONException e){return new JSONArray();}}
    static JSONObject catalogue(Context c,String file)throws Exception{try(java.io.InputStream in=c.getAssets().open("themes/"+file)){java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int count;while((count=in.read(buffer))!=-1)out.write(buffer,0,count);return new JSONObject(new String(out.toByteArray(),java.nio.charset.StandardCharsets.UTF_8));}}
    static JSONArray presets(Context c)throws Exception{JSONArray all=catalogue(c,"web-designs.json").getJSONArray("presets"),colors=catalogue(c,"web-presets.json").getJSONArray("presets"),local=imported(c);for(int i=0;i<colors.length();i++)all.put(colors.getJSONObject(i).put("category","colors"));for(int i=0;i<local.length();i++)all.put(local.getJSONObject(i).put("category","imported"));return all;}
    static JSONObject findPreset(Context c,String id)throws Exception{JSONArray items=presets(c);for(int i=0;i<items.length();i++)if(id.equals(items.getJSONObject(i).getString("id")))return items.getJSONObject(i);throw new IllegalArgumentException("未知主题");}
    static int backgroundColor(Context c){SharedPreferences p=prefs(c);return "theme".equals(p.getString("bg_source","custom"))?("web".equals(p.getString("theme_source","acm"))?palette.background:palette.primary):p.getInt("bg_color",0xffffffff);}
    static void window(Activity activity){
        window(activity.getWindow());
        View bars=activity.findViewById(android.R.id.content);if(bars!=null){View surface=bars.findViewWithTag("system_bar_surface");if(surface!=null)surface.setBackgroundColor(MobileStyle.PANEL);}
        if(bars!=null){View frame=bars.findViewWithTag("theme_content_frame");if(frame instanceof android.widget.FrameLayout)paintBackdrop((android.widget.FrameLayout)frame);}
    }
    static void window(android.view.Window window){
        window.setStatusBarColor(MobileStyle.PANEL);window.setNavigationBarColor(MobileStyle.PANEL);
        int flags=window.getDecorView().getSystemUiVisibility();
        boolean light=ThemePalette.contrast(MobileStyle.PANEL,Color.BLACK)>=ThemePalette.contrast(MobileStyle.PANEL,Color.WHITE);
        flags=light?flags|View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR:flags&~(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        window.getDecorView().setSystemUiVisibility(flags);
    }
    /** System bars have their own opaque surface; the custom background starts below them. */
    static void content(Activity activity,View body){
        android.widget.FrameLayout frame=contentFrame(activity,activity.getWindow(),body);
        activity.setContentView(frame);frame.requestApplyInsets();
    }
    static void content(android.app.Dialog dialog,View body){
        android.widget.FrameLayout frame=contentFrame(dialog.getContext(),dialog.getWindow(),body);
        dialog.setContentView(frame);frame.requestApplyInsets();
    }
    private static android.widget.FrameLayout contentFrame(Context context,android.view.Window window,View body){
        if(android.os.Build.VERSION.SDK_INT>=30)window.setDecorFitsSystemWindows(false);
        else window.getDecorView().setSystemUiVisibility(window.getDecorView().getSystemUiVisibility()|View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        android.widget.FrameLayout frame=new android.widget.FrameLayout(context);frame.setTag("system_bar_surface");frame.setBackgroundColor(MobileStyle.PANEL);body.setFitsSystemWindows(false);
        android.widget.FrameLayout layers=new android.widget.FrameLayout(context);layers.setTag("theme_content_frame");body.setTag(body.getTag()==null?"theme_body":body.getTag());layers.addView(body,new android.widget.FrameLayout.LayoutParams(-1,-1));frame.addView(layers,new android.widget.FrameLayout.LayoutParams(-1,-1));paintBackdrop(layers);
        frame.setOnApplyWindowInsetsListener((view,insets)->{
            int left,top,right,bottom;
            if(android.os.Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.systemBars()|android.view.WindowInsets.Type.displayCutout());left=bars.left;top=bars.top;right=bars.right;bottom=Math.max(bars.bottom,insets.getInsets(android.view.WindowInsets.Type.ime()).bottom);}
            else{left=insets.getSystemWindowInsetLeft();top=insets.getSystemWindowInsetTop();right=insets.getSystemWindowInsetRight();bottom=insets.getSystemWindowInsetBottom();}
            android.widget.FrameLayout.LayoutParams bounds=(android.widget.FrameLayout.LayoutParams)layers.getLayoutParams();
            if(bounds.leftMargin!=left||bounds.topMargin!=top||bounds.rightMargin!=right||bounds.bottomMargin!=bottom){bounds.setMargins(left,top,right,bottom);layers.setLayoutParams(bounds);}return insets;
        });
        return frame;
    }
    private static void paintBackdrop(android.widget.FrameLayout layers){
        View body=layers.getChildAt(layers.getChildCount()-1);OfficialThemeView backdrop=layers.getChildAt(0) instanceof OfficialThemeView?(OfficialThemeView)layers.getChildAt(0):null;
        if(OfficialThemeView.background(layers.getContext())){if(backdrop==null){backdrop=new OfficialThemeView(layers.getContext(),"background");layers.addView(backdrop,0,new android.widget.FrameLayout.LayoutParams(-1,-1));}backdrop.setVisibility(View.VISIBLE);backdrop.refresh();body.setBackgroundColor(Color.TRANSPARENT);}
        else if(backdrop!=null){backdrop.setVisibility(View.GONE);body.setBackground(ProfileCover.drawable(layers.getContext()));}
    }
    static void paintFields(View view){
        if(view instanceof android.widget.EditText){android.widget.EditText field=(android.widget.EditText)view;field.setTextColor(MobileStyle.TEXT);field.setHintTextColor(MobileStyle.MUTED);field.setBackgroundTintList("appearance_field_surface".equals(field.getTag())?null:android.content.res.ColorStateList.valueOf(MobileStyle.BRAND));}
        else if(view instanceof android.widget.CompoundButton){((android.widget.CompoundButton)view).setTextColor(MobileStyle.TEXT);((android.widget.CompoundButton)view).setButtonTintList(android.content.res.ColorStateList.valueOf(MobileStyle.BRAND));}
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++)paintFields(group.getChildAt(i));}
    }
}
