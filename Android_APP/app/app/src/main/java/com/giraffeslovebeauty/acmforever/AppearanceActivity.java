package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.*;
import android.content.res.ColorStateList;
import android.database.Cursor;
import android.graphics.*;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.function.BooleanSupplier;
import java.util.function.IntSupplier;

/** Local personalization. Colour changes repaint existing views without navigation. */
public final class AppearanceActivity extends Activity {
    private static final int PICK_IMAGE=71,PICK_THEME=72,CROP_IMAGE=73,IMPORT_LOCAL=74;
    private static final int[] COLORS={0xffc8eb21,0xff82c7aa,0xff83b8e5,0xffbaa4df,0xffebafc5,0xffe9c786,0xffffffff,0xfff4f5f7,0xff292c29};
    private static final String[] NAMES={"黄绿","薄荷","天蓝","薰衣草","樱粉","暖杏","纯白","雾灰","墨色"};
    private String page="menu",pickerTarget="background";
    private String category="all";
    private final ArrayDeque<String> history=new ArrayDeque<>();
    private final ArrayList<Runnable> paints=new ArrayList<>();
    private SharedPreferences prefs;
    private String themeId;
    @Override public SharedPreferences getSharedPreferences(String name,int mode){return "acmforever_settings".equals(name)&&LocalThemes.valid(themeId)?super.getSharedPreferences("local_theme_"+themeId,mode):super.getSharedPreferences(name,mode);}
    private LinearLayout root,body;
    private final java.util.concurrent.ExecutorService files=java.util.concurrent.Executors.newSingleThreadExecutor();
    private boolean saving,choosing,navigating;
    private int dp(float value){return MobileStyle.dp(this,value);}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);themeId=getIntent().getStringExtra(LocalThemes.EXTRA);
        if(themeId!=null&&(!LocalThemes.valid(themeId)||!LocalThemes.exists(getApplicationContext(),themeId))){finish();return;}
        prefs=AppAppearance.prefs(this);
        if(state==null)page=getIntent().getStringExtra("page")==null?"menu":getIntent().getStringExtra("page");
        if(state!=null){page=state.getString("page","menu");category=state.getString("category","all");pickerTarget=state.getString("picker_target","background");choosing=state.getBoolean("choosing",false);ArrayList<String> saved=state.getStringArrayList("history");if(saved!=null)history.addAll(saved);}
        render();
    }
    @Override protected void onResume(){super.onResume();navigating=false;if(prefs!=null)render();}
    @Override protected void onPause(){if(themeId!=null)AppAppearance.load(getApplicationContext());super.onPause();}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("page",page);state.putString("category",category);state.putString("picker_target",pickerTarget);state.putBoolean("choosing",choosing);state.putStringArrayList("history",new ArrayList<>(history));}
    @Override protected void onDestroy(){files.shutdown();ModalDialogs.close(this);super.onDestroy();}
    @Override public void onBackPressed(){if(saving)return;if(history.isEmpty()){finish();return;}PageMotion.change(this,false,()->{page=history.pop();render();});}
    private void go(String next){if(page.equals(next)||saving)return;PageMotion.change(this,true,()->{history.push(page);page=next;render();});}
    private String title(){switch(page){case "saved":return "我的主题";case "background":return "背景选择";case "theme":return "主题选择";case "controls":return "控件背景透明度";case "library":return "主题库";case "picker":return "theme".equals(pickerTarget)?"ACMForever主色":"secondary".equals(pickerTarget)?"ACMForever辅色":"调色盘";default:return themeId==null?"个性化设置":LocalThemes.name(getApplicationContext(),themeId);}}
    private LinearLayout column(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.VERTICAL);return b;}
    private LinearLayout row(){LinearLayout b=new SpacedLayout(this);b.setOrientation(LinearLayout.HORIZONTAL);b.setGravity(Gravity.CENTER_VERTICAL);return b;}
    private void bind(Runnable paint){paints.add(paint);paint.run();}
    private TextView text(String value,int size,boolean bold){
        TextView t=new TextView(this);t.setText(value);t.setTextSize(size);if(bold)t.setTypeface(null,Typeface.BOLD);bind(()->t.setTextColor(MobileStyle.TEXT));return t;
    }
    private void gap(LinearLayout parent,int amount){parent.addView(new View(this),new LinearLayout.LayoutParams(1,dp(amount)));}
    private LinearLayout card(){
        LinearLayout b=column();b.setPadding(dp(16),dp(16),dp(16),dp(16));bind(()->b.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0)));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(12);body.addView(b,lp);return b;
    }
    private Button button(String title,BooleanSupplier selected,Runnable action){
        Button b=new Button(this);b.setText(title);MobileStyle.button(b,false);
        bind(()->{MobileStyle.control(b,false,selected.getAsBoolean(),12);MobileStyle.symbol(b);});
        b.setOnClickListener(v->{if(!saving&&!navigating&&!ModalDialogs.isShowing(this))action.run();});return b;
    }
    private Button button(String title,Runnable action){return button(title,()->false,action);}
    private void visible(View view,BooleanSupplier show){bind(()->view.setVisibility(show.getAsBoolean()?View.VISIBLE:View.GONE));}
    private void save(SharedPreferences.Editor edit){AppAppearance.changed(this,edit);repaint();}
    private void repaint(){
        root.setBackground(ProfileCover.drawable(this));AppAppearance.window(this);
        for(Runnable paint:paints)paint.run();AppAppearance.paintFields(root);
    }
    /** Only navigation builds a page. Selecting colours and opacity never calls render(). */
    private void render(){
        AppAppearance.load(this);paints.clear();root=column();root.setContentDescription("个性化页面");AppAppearance.content(this,root);
        LinearLayout header=row();header.setPadding(dp(12),dp(8),dp(12),dp(8));bind(()->header.setBackgroundColor(MobileStyle.CHROME));
        ImageButton back=new ImageButton(this);MobileStyle.flat(back);back.setBackgroundColor(Color.TRANSPARENT);back.setPadding(dp(12),dp(12),dp(12),dp(12));
        bind(()->back.setImageDrawable(AppIcons.get(this,"back",MobileStyle.TEXT)));back.setContentDescription("返回");back.setOnClickListener(v->onBackPressed());
        header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));TextView title=text(title(),21,true);title.setGravity(Gravity.CENTER);title.setSingleLine(true);title.setEllipsize(android.text.TextUtils.TruncateAt.END);header.addView(title,new LinearLayout.LayoutParams(0,dp(48),1));header.addView(new View(this),new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(header);
        ScrollView scroll=new ScrollView(this);scroll.setContentDescription("个性化滚动区域");scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=column();body.setPadding(dp(16),dp(16),dp(16),dp(24));scroll.addView(body);
        switch(page){case "background":background();break;case "theme":theme();break;case "controls":controls();break;case "library":library();break;case "picker":picker();break;default:menu();}
        repaint();
    }
    private Intent advanced(String page){return OptionalModules.target(this,"advanced").putExtra("page",page).putExtra(LocalThemes.EXTRA,themeId);}
    private void menu(){
        LinearLayout box=card();
        box.addView(button("背景选择",()->go("background")),new LinearLayout.LayoutParams(-1,dp(64)));
        box.addView(button("主题选择",()->go("theme")),new LinearLayout.LayoutParams(-1,dp(64)));
        box.addView(button("高级个性化",()->OptionalModules.open(this,"advanced",advanced("menu"))),new LinearLayout.LayoutParams(-1,dp(64)));
        LinearLayout character=card();character.addView(text("分层猫娘素材",18,true));
        character.addView(text("按需下载彩色头像、敲代码插画及分层换色素材。基础小图标与加载提示无需下载。",13,false));
        character.addView(button(ModuleStore.available(this,"cat-art")?"查看猫娘素材":"下载分层猫娘素材",()->OptionalModules.open(this,"cat-art",new Intent(this,AppearanceActivity.class).putExtra("page","theme"))));
    }
    private boolean imageMode(){return "image".equals(prefs.getString("bg_mode","solid"));}
    private boolean followTheme(){return "theme".equals(prefs.getString("bg_source","custom"));}
    private boolean acmTheme(){return !"web".equals(prefs.getString("theme_source","acm"));}
    private void background(){
        LinearLayout modes=card();
        modes.addView(button("选择本机图片",this::imageMode,this::pickImage));
        modes.addView(button("使用纯色背景",()->"solid".equals(prefs.getString("bg_mode","solid")),()->save(prefs.edit().putString("bg_mode","solid"))));
        modes.addView(button("使用渐变背景",()->"gradient".equals(prefs.getString("bg_mode","solid")),()->save(prefs.edit().putString("bg_mode","gradient"))));
        LinearLayout imageOptions=card();visible(imageOptions,this::imageMode);imageOptions.addView(text("透明度",15,true));
        SeekBar opacity=slider(5,prefs.getInt("bg_transparency",2));opacity.setContentDescription("背景透明度");
        change(opacity,value->save(prefs.edit().putInt("bg_transparency",value)));imageOptions.addView(opacity,new LinearLayout.LayoutParams(-1,dp(48)));
        LinearLayout options=card();visible(options,()->!imageMode());
        LinearLayout segmented=new SpacedLayout(this){
            float start;boolean swiping;
            @Override public boolean onInterceptTouchEvent(MotionEvent e){
                if(e.getAction()==MotionEvent.ACTION_DOWN){start=e.getX();swiping=false;}
                if(e.getAction()==MotionEvent.ACTION_MOVE&&Math.abs(e.getX()-start)>dp(24)){swiping=true;return true;}return false;
            }
            @Override public boolean onTouchEvent(MotionEvent e){
                if(e.getAction()==MotionEvent.ACTION_UP&&swiping){save(prefs.edit().putString("bg_source",e.getX()<start?"custom":"theme"));return true;}return true;
            }
        };segmented.setOrientation(LinearLayout.HORIZONTAL);
        segmented.addView(button("与主题同色",this::followTheme,()->save(prefs.edit().putString("bg_source","theme"))),new LinearLayout.LayoutParams(0,-2,1));
        segmented.addView(button("自定义",()->!followTheme(),()->save(prefs.edit().putString("bg_source","custom"))),new LinearLayout.LayoutParams(0,-2,1));
        options.addView(segmented);LinearLayout custom=column();visible(custom,()->!followTheme());gap(custom,12);
        swatches(custom,()->prefs.getInt("bg_color",0xffffffff),color->save(prefs.edit().putInt("bg_color",color)),"background");options.addView(custom);
    }
    private void theme(){
        LinearLayout options=card();
        options.addView(button("ACMForever",this::acmTheme,()->save(prefs.edit().putString("theme_source","acm"))));
        options.addView(button("主题库",()->!acmTheme(),()->OptionalModules.open(this,"official-themes",new Intent(this,AppearanceActivity.class).putExtra("page","library").putExtra(LocalThemes.EXTRA,themeId))));
        options.addView(button("本地导入",()->OptionalModules.open(this,"advanced",advanced("theme"))));
        LinearLayout colors=card();visible(colors,this::acmTheme);colors.setContentDescription("ACMForever主色");colors.addView(text("ACMForever主色",16,true));gap(colors,12);
        swatches(colors,()->prefs.getInt("theme_primary",0xffc8eb21),color->save(prefs.edit().putInt("theme_primary",color).putString("theme_source","acm")),"theme");
        LinearLayout secondary=card();visible(secondary,this::acmTheme);secondary.setContentDescription("ACMForever辅色");secondary.addView(text("ACMForever辅色",16,true));gap(secondary,12);
        swatches(secondary,()->prefs.getInt("theme_secondary",0xffffffff),color->save(prefs.edit().putInt("theme_secondary",color).putString("theme_source","acm")),"secondary");
        LinearLayout modules=card();modules.setContentDescription("模块背景预览");modules.addView(text("模块背景透明度",15,true));
        SeekBar transparency=slider(5,prefs.getInt("module_transparency",0));transparency.setContentDescription("模块背景透明度");
        change(transparency,value->save(prefs.edit().putInt("module_transparency",value)));modules.addView(transparency,new LinearLayout.LayoutParams(-1,dp(48)));
        modules.addView(button("搜索栏与下方菜单背景透明度",()->go("controls")));
        LinearLayout character=card();character.addView(text("猫娘配色",16,true));gap(character,10);
        ImageView image=new ImageView(this);image.setScaleType(ImageView.ScaleType.FIT_CENTER);final int[] tone={0};
        bind(()->{if(tone[0]!=MobileStyle.ACCENT||image.getDrawable()==null){image.setImageBitmap(CharacterArt.bitmap(this,CharacterArt.LOADING));tone[0]=MobileStyle.ACCENT;}});
        character.addView(image,new LinearLayout.LayoutParams(-1,dp(200)));
        TextView hint=text("发色与眼睛、服装、蝴蝶结与装饰随主题配色。",12,false);bind(()->hint.setTextColor(MobileStyle.MUTED));character.addView(hint);
    }
    private void controls(){
        LinearLayout box=card();box.addView(text("调整按键、搜索栏与底部菜单的背景透明度",15,true));
        SeekBar transparency=slider(5,prefs.getInt("control_transparency",0));transparency.setContentDescription("按键搜索栏与下方菜单背景透明度");change(transparency,value->save(prefs.edit().putInt("control_transparency",value)));box.addView(transparency,new LinearLayout.LayoutParams(-1,dp(48)));
        LinearLayout preview=card();preview.addView(text("效果预览",17,true));TextView search=text("ACMForever",14,false);search.setGravity(Gravity.CENTER_VERTICAL);search.setPadding(dp(14),0,dp(14),0);bind(()->search.setBackground(MobileStyle.panel(this,MobileStyle.SEARCH,20,0)));preview.addView(search,new LinearLayout.LayoutParams(-1,dp(48)));
        preview.addView(button("ACMForever",()->{}));LinearLayout menu=row();menu.setPadding(dp(12),dp(12),dp(12),dp(12));bind(()->menu.setBackgroundColor(MobileStyle.CHROME));for(String title:new String[]{"主页","排名","题库","个人中心"}){TextView label=text(title,12,true);label.setGravity(Gravity.CENTER);menu.addView(label,new LinearLayout.LayoutParams(0,dp(44),1));}preview.addView(menu);
    }
    private void library(){
        LinearLayout intro=card();intro.addView(text("网页主题",18,true));intro.addView(text("直接读取官方原始主题资源，主题配色保存在本机。导入与分享位于高级个性化。",13,false));
        intro.addView(button("导入网页主题 JSON",()->OptionalModules.open(this,"advanced",advanced("library"))));
        WrapLayout categories=new WrapLayout(this);String[] keys={"all","default","arknights","minecraft","genshin","zenless","colors","imported"},names={"全部","默认","明日方舟","我的世界","原神","绝区零","基础配色","本机导入"};
        for(int i=0;i<keys.length;i++){String key=keys[i];Button choice=button(names[i],()->key.equals(category),()->{category=key;repaint();});categories.addView(choice,new ViewGroup.LayoutParams(-2,-2));}
        intro.addView(categories,new LinearLayout.LayoutParams(-1,-2));LinearLayout list=column();body.addView(list);libraryItems(list);
    }
    private void libraryItems(LinearLayout list){
        try{
            JSONArray items=AppAppearance.presets(this);
            for(int i=0;i<items.length();i++){
                JSONObject preset=items.getJSONObject(i);String id=preset.getString("id"),name=preset.getString("name");
                String group=preset.optString("category","colors");
                LinearLayout tile=column();tile.setPadding(dp(16),dp(16),dp(16),dp(16));bind(()->tile.setBackground(MobileStyle.panel(this,MobileStyle.MODULE,16,0)));
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(12);list.addView(tile,lp);tile.addView(text(name,18,true));gap(tile,8);
                visible(tile,()->"all".equals(category)||group.equals(category));
                if(preset.has("description"))tile.addView(text(preset.getString("description"),12,false));
                JSONObject sample=WebThemes.profile(preset,false).getJSONObject("colors");LinearLayout marks=row();
                for(String key:new String[]{"primary","background","surface","accent"}){View swatch=new Swatch(Color.parseColor(sample.getString(key)),false,()->false);marks.addView(swatch,new LinearLayout.LayoutParams(0,dp(48),1));}tile.addView(marks);
                LinearLayout actions=row();
                for(boolean dark:new boolean[]{false,true}){
                    Button use=button(dark?"深色":"浅色",()->!acmTheme()&&id.equals(prefs.getString("theme_preset",""))&&prefs.getBoolean("theme_dark",false)==dark,
                            ()->save(prefs.edit().putString("theme_source","web").putString("theme_preset",id).putBoolean("theme_dark",dark)
                                    .putString("bg_mode","solid").putString("bg_source","theme")));
                    use.setContentDescription(name+(dark?"深色":"浅色"));actions.addView(use,new LinearLayout.LayoutParams(0,-2,1));
                }tile.addView(actions);
            }
            TextView empty=text("此分类暂无模板",16,true);list.addView(empty);visible(empty,()->{if("all".equals(category))return false;for(int i=0;i<items.length();i++)if(category.equals(items.optJSONObject(i).optString("category")))return false;return true;});
        }catch(Exception e){list.addView(text("主题库读取失败："+e.getMessage(),16,true));}
    }
    private SeekBar slider(int max,int progress){
        SeekBar seek=new SeekBar(this);seek.setMax(max);seek.setProgress(Math.max(0,Math.min(max,progress)));seek.setSplitTrack(false);
        bind(()->{seek.setProgressTintList(ColorStateList.valueOf(MobileStyle.BRAND));seek.setThumbTintList(ColorStateList.valueOf(MobileStyle.BRAND));
            if(max==5){android.graphics.drawable.GradientDrawable tick=MobileStyle.panel(this,MobileStyle.MUTED,3,0);tick.setSize(dp(4),dp(4));seek.setTickMark(tick);}});return seek;
    }
    private void change(SeekBar seek,java.util.function.IntConsumer choose){seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar b,int value,boolean user){if(user&&!saving)choose.accept(value);}public void onStartTrackingTouch(SeekBar b){}public void onStopTrackingTouch(SeekBar b){}});}
    private void swatches(LinearLayout parent,IntSupplier selected,java.util.function.IntConsumer choose,String target){
        LinearLayout line=null;
        for(int i=0;i<=COLORS.length;i++){
            if(i%4==0){line=row();LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(56));lp.topMargin=dp(6);parent.addView(line,lp);}
            boolean rainbow=i==COLORS.length;int color=rainbow?0:COLORS[i];
            BooleanSupplier checked=()->rainbow?customColor(target,selected.getAsInt()):!customColor(target,selected.getAsInt())&&color==selected.getAsInt();
            Swatch swatch=new Swatch(color,rainbow,checked);if(rainbow)swatch.colorSource=selected;swatch.setContentDescription(("secondary".equals(target)?"ACMForever辅色：":"")+(rainbow?"打开调色盘":NAMES[i]));
            bind(()->{swatch.setSelected(checked.getAsBoolean());swatch.invalidate();});
            swatch.setOnClickListener(v->{if(saving)return;if(rainbow){pickerTarget=target;go("picker");}else{prefs.edit().putBoolean(target+"_custom_color",false).apply();choose.accept(color);}});line.addView(swatch,new LinearLayout.LayoutParams(0,-1,1));
            if(rainbow)for(int n=i%4+1;n<4;n++)line.addView(new View(this),new LinearLayout.LayoutParams(0,-1,1));
        }
    }
    private boolean customColor(String target,int color){if(prefs.contains(target+"_custom_color"))return prefs.getBoolean(target+"_custom_color",false);for(int preset:COLORS)if(preset==color)return false;return true;}
    private String pickerKey(){return "theme".equals(pickerTarget)?"theme_primary":"secondary".equals(pickerTarget)?"theme_secondary":"bg_color";}
    private int pickerDefault(){return "secondary".equals(pickerTarget)?Color.WHITE:"theme".equals(pickerTarget)?0xffc8eb21:Color.WHITE;}
    private void picker(){
        LinearLayout box=card();int current=prefs.getInt(pickerKey(),pickerDefault());
        ColorWheel wheel=new ColorWheel(this,current);box.addView(wheel,new LinearLayout.LayoutParams(-1,dp(260)));
        TextView preview=text("已选颜色",15,true);preview.setMinHeight(dp(48));preview.setGravity(Gravity.CENTER);box.addView(preview,new LinearLayout.LayoutParams(-1,dp(48)));
        java.util.function.IntConsumer update=color->{preview.setBackground(MobileStyle.panel(this,color,12,MobileStyle.LINE));preview.setTextColor(ThemePalette.readable(new int[]{color},MobileStyle.TEXT,4.5));};update.accept(current);wheel.onColor(update);
        box.addView(text("明度",14,true));float[] hsv=new float[3];Color.colorToHSV(current,hsv);SeekBar brightness=slider(100,Math.round(hsv[2]*100));brightness.setContentDescription("颜色明度");change(brightness,value->wheel.brightness(value/100f));box.addView(brightness);
        box.addView(button("应用颜色",()->{SharedPreferences.Editor edit=prefs.edit().putInt(pickerKey(),wheel.color()).putBoolean(pickerTarget+"_custom_color",true);if(!"background".equals(pickerTarget))edit.putString("theme_source","acm");save(edit);onBackPressed();}));
    }
    private void pickImage(){OptionalModules.open(this,"advanced",advanced("background"));}
    private final class Swatch extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private final int color;private final boolean rainbow;private final BooleanSupplier checked;
        private IntSupplier colorSource;
        Swatch(int color,boolean rainbow,BooleanSupplier checked){super(AppearanceActivity.this);this.color=color;this.rainbow=rainbow;this.checked=checked;setMinimumHeight(dp(48));setFocusable(true);}
        @Override protected void onDraw(Canvas c){
            boolean selected=checked.getAsBoolean();int fill=rainbow&&selected&&colorSource!=null?colorSource.getAsInt():color;float x=getWidth()/2f,y=getHeight()/2f,r=Math.min(dp(21),Math.min(x,y)-dp(5));paint.setStyle(Paint.Style.FILL);paint.setColor(fill|0xff000000);paint.setAlpha(255);
            if(rainbow&&!selected)paint.setShader(new SweepGradient(x,y,new int[]{Color.RED,Color.YELLOW,Color.GREEN,Color.CYAN,Color.BLUE,Color.MAGENTA,Color.RED},null));c.drawCircle(x,y,r,paint);paint.setShader(null);
            paint.setStyle(Paint.Style.STROKE);paint.setColor(selected?MobileStyle.BRAND:MobileStyle.LINE);paint.setStrokeWidth(dp(selected?3:1));c.drawCircle(x,y,r+dp(3),paint);
            if(selected){paint.setColor(ThemePalette.readable(new int[]{fill},MobileStyle.TEXT,4.5));paint.setStrokeWidth(dp(3));paint.setStrokeCap(Paint.Cap.ROUND);Path p=new Path();p.moveTo(x-dp(7),y);p.lineTo(x-dp(2),y+dp(5));p.lineTo(x+dp(8),y-dp(6));c.drawPath(p,paint);}paint.setStyle(Paint.Style.FILL);
        }
    }
}
