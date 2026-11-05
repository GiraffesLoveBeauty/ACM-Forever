package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import java.util.*;
import java.io.*;
import org.json.*;

/** Composites supplied real layers; fixed skin/ears/collar/cuffs/laptop are never tinted. */
final class CharacterArt {
    private static final LinkedHashMap<String,Bitmap> cache=new LinkedHashMap<>();
    private static final Map<Integer,Parts> sources=new HashMap<>();
    private static final class Layer {Bitmap bitmap;String group,name;}
    private static final class Parts {int width,height;final List<Layer> layers=new ArrayList<>();}
    private static Parts parts(Context context,int resource){
        Parts ready=sources.get(resource);if(ready!=null)return ready;
        try(InputStream in=context.getAssets().open("character/catalog.json");ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] bytes=new byte[4096];int count;while((count=in.read(bytes))!=-1)out.write(bytes,0,count);
            JSONObject item=new JSONObject(out.toString("UTF-8")).getJSONObject("assets").getJSONObject(resource==R.drawable.avatar_catgirl?"avatar":"loading");Parts result=new Parts();result.width=item.getInt("width");result.height=item.getInt("height");JSONArray entries=item.getJSONArray("layers");
            for(int i=0;i<entries.length();i++){JSONObject entry=entries.getJSONObject(i);Layer layer=new Layer();layer.group=entry.getString("group");layer.name=entry.getString("name");try(InputStream image=context.getAssets().open("character/"+entry.getString("file"))){layer.bitmap=BitmapFactory.decodeStream(image);}if(layer.bitmap==null||layer.bitmap.getWidth()!=result.width||layer.bitmap.getHeight()!=result.height)throw new IOException("角色图层尺寸不一致");result.layers.add(layer);}
            sources.put(resource,result);return result;
        }catch(Exception error){throw new IllegalStateException("无法读取本机角色图层",error);}
    }
    static synchronized Bitmap bitmap(Context context,int resource){
        int primary=AppAppearance.palette().primary;String key=resource+":"+primary;Bitmap ready=cache.get(key);if(ready!=null)return ready;
        Parts parts=parts(context,resource);Bitmap result=Bitmap.createBitmap(parts.width,parts.height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(result);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);float[] tone=new float[3];Color.colorToHSV(primary,tone);
        for(Layer layer:parts.layers){
            if("fixed".equals(layer.group)){canvas.drawBitmap(layer.bitmap,0,0,paint);continue;}
            int[] pixels=new int[parts.width*parts.height];layer.bitmap.getPixels(pixels,0,parts.width,0,0,parts.width,parts.height);float[] color=new float[3];
            for(int i=0;i<pixels.length;i++){int alpha=Color.alpha(pixels[i]);if(alpha==0)continue;float light=Color.red(pixels[i])/255f;color[0]=tone[0];
                if("eyes".equals(layer.name)){color[1]=tone[1]*.2f;color[2]=.07f+.1f*light;}
                else if("hair_eyes".equals(layer.group)){color[1]=tone[1]<.05f?0:.16f+.75f*tone[1];color[2]=Math.min(1,(.17f+1.08f*light)*(.65f+.35f*tone[2]));}
                else if("clothes".equals(layer.group)){color[1]=tone[1]<.05f?0:.12f+.6f*tone[1];color[2]=.42f+.56f*light;}
                else{color[0]=(tone[0]+35)%360;color[1]=tone[1]<.05f?0:.22f+.6f*tone[1];color[2]=.32f+.66f*light;}
                pixels[i]=Color.HSVToColor(alpha,color);
            }
            Bitmap tinted=Bitmap.createBitmap(pixels,parts.width,parts.height,Bitmap.Config.ARGB_8888);canvas.drawBitmap(tinted,0,0,paint);tinted.recycle();
        }
        // Downsampling separate layers can round shared antialiased edges differently
        // from a reference PNG. Restore pixels with no visible tint-layer contribution;
        // this mask is derived from actual layer alpha/occlusion, never colour guessing.
        Bitmap original=BitmapFactory.decodeResource(context.getResources(),resource),visibility=BitmapFactory.decodeResource(context.getResources(),resource==R.drawable.avatar_catgirl?R.drawable.avatar_color_mask:R.drawable.loading_color_mask);
        int[] before=new int[parts.width*parts.height],mask=new int[before.length],after=new int[before.length];original.getPixels(before,0,parts.width,0,0,parts.width,parts.height);visibility.getPixels(mask,0,parts.width,0,0,parts.width,parts.height);result.getPixels(after,0,parts.width,0,0,parts.width,parts.height);
        for(int i=0;i<after.length;i++)after[i]=(mask[i]&0xffffff)==0?before[i]:(before[i]&0xff000000)|(after[i]&0xffffff);
        result.setPixels(after,0,parts.width,0,0,parts.width,parts.height);original.recycle();visibility.recycle();
        cache.put(key,result);while(cache.size()>6)cache.remove(cache.keySet().iterator().next());return result;
    }
}
