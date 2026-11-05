package com.giraffeslovebeauty.acmforever;

import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;
import java.util.UUID;

/** Read-only, temporary theme attachments. Never exposes app settings or update APKs. */
public final class ThemeShareProvider extends ContentProvider {
    private static final long RETAIN_MS=7L*24*60*60*1000;
    private static File directory(Context context){return new File(context.getCacheDir(),"theme-shares");}
    /** Call off the main thread. The chooser is launched only after the complete archive is closed. */
    static Intent prepare(Context context,ThemePackage pack)throws Exception{
        File folder=directory(context);if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("无法创建分享文件");
        File[] stale=folder.listFiles();long cutoff=System.currentTimeMillis()-RETAIN_MS;
        if(stale!=null)for(File file:stale)if(file.isFile()&&file.getName().matches("[a-f0-9]{32}\\.acmtheme")&&file.lastModified()<cutoff)file.delete();
        String id=UUID.randomUUID().toString().replace("-","");File file=new File(folder,id+ThemePackage.EXTENSION);
        if(!file.createNewFile())throw new IOException("无法创建分享文件");
        try(FileOutputStream out=new FileOutputStream(file)){pack.write(out);}catch(Exception failure){file.delete();throw failure;}
        String name="ACMforever-"+pack.name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]","_")+ThemePackage.EXTENSION;
        Uri uri=new Uri.Builder().scheme("content").authority(context.getPackageName()+".themes").appendPath(id).appendPath(name).build();
        Intent send=new Intent(Intent.ACTION_SEND).setType("application/zip").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        send.setClipData(ClipData.newUri(context.getContentResolver(),name,uri));return send;
    }
    @Override public boolean onCreate(){return true;}
    private File resolve(Uri uri)throws FileNotFoundException{
        if(getContext()==null||!"content".equals(uri.getScheme())||!(getContext().getPackageName()+".themes").equals(uri.getAuthority())
                ||uri.getQuery()!=null||uri.getFragment()!=null||uri.getPathSegments().size()!=2)throw new FileNotFoundException("无效的主题附件");
        String id=uri.getPathSegments().get(0),name=uri.getLastPathSegment();
        if(!id.matches("[a-f0-9]{32}")||name==null||!name.endsWith(ThemePackage.EXTENSION)||name.length()>120||name.matches(".*[\\\\/\\p{Cntrl}].*"))throw new FileNotFoundException("无效的主题附件");
        try{File folder=directory(getContext()).getCanonicalFile(),file=new File(folder,id+ThemePackage.EXTENSION).getCanonicalFile();
            if(!folder.equals(file.getParentFile())||!file.isFile())throw new FileNotFoundException("主题附件已失效，请重新分享");return file;
        }catch(IOException error){throw new FileNotFoundException(error.getMessage());}
    }
    @Override public String getType(Uri uri){try{resolve(uri);return "application/zip";}catch(FileNotFoundException error){throw new IllegalArgumentException(error.getMessage());}}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort){
        try{File file=resolve(uri);String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor cursor=new MatrixCursor(columns,1);Object[] values=new Object[columns.length];
            for(int i=0;i<columns.length;i++)if(OpenableColumns.DISPLAY_NAME.equals(columns[i]))values[i]=uri.getLastPathSegment();else if(OpenableColumns.SIZE.equals(columns[i]))values[i]=file.length();
            cursor.addRow(values);return cursor;
        }catch(FileNotFoundException error){throw new IllegalArgumentException(error.getMessage());}
    }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException{
        if(!"r".equals(mode))throw new FileNotFoundException("主题附件只允许读取");return ParcelFileDescriptor.open(resolve(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException("主题附件只允许读取");}
    @Override public int update(Uri uri,ContentValues values,String where,String[] args){throw new UnsupportedOperationException("主题附件只允许读取");}
    @Override public int delete(Uri uri,String where,String[] args){throw new UnsupportedOperationException("主题附件只允许读取");}
}
