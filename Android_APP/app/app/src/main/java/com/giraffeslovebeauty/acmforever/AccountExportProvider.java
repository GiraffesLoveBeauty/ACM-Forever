package com.giraffeslovebeauty.acmforever;

import android.content.*;
import android.database.*;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import java.io.*;
import java.util.*;

/** Short-lived, read-only credential exports. No files, preferences, logs or backups. */
public final class AccountExportProvider extends ContentProvider {
    static final String MIME="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final Map<String,Export> exports=new HashMap<>();
    private static final class Export{final byte[] bytes;final long owner,until;Export(byte[] b,long o){bytes=b;owner=o;until=SystemClock.elapsedRealtime()+600000;}}
    static synchronized Intent prepare(Context c,byte[] bytes){clear(c);String id=UUID.randomUUID().toString();exports.put(id,new Export(bytes,((AcmApplication)c.getApplicationContext()).api().sessionGeneration()));Uri uri=new Uri.Builder().scheme("content").authority(c.getPackageName()+".accounts").appendPath(id).appendPath("ACMforever-临时密码.xlsx").build();Intent send=new Intent(Intent.ACTION_SEND).setType(MIME).putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);send.setClipData(ClipData.newUri(c.getContentResolver(),"临时密码",uri));return send;}
    static synchronized void clear(Context c){for(Export value:exports.values())Arrays.fill(value.bytes,(byte)0);exports.clear();}
    private synchronized Export resolve(Uri uri)throws FileNotFoundException{Context c=getContext();if(c==null||!"content".equals(uri.getScheme())||!(c.getPackageName()+".accounts").equals(uri.getAuthority())||uri.getPathSegments().size()!=2||uri.getQuery()!=null||uri.getFragment()!=null)throw new FileNotFoundException("无效导出");Export e; synchronized(AccountExportProvider.class){e=exports.get(uri.getPathSegments().get(0));}ApiClient api=((AcmApplication)c.getApplicationContext()).api();if(e==null||e.until<SystemClock.elapsedRealtime()||e.owner!=api.sessionGeneration()||!api.isAdministrator())throw new FileNotFoundException("导出已失效，请重新分享");return e;}
    @Override public boolean onCreate(){return true;}
    @Override public String getType(Uri uri){return MIME;}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort){try{Export e=resolve(uri);String[] names=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;MatrixCursor c=new MatrixCursor(names,1);Object[] row=new Object[names.length];for(int i=0;i<names.length;i++)row[i]=OpenableColumns.DISPLAY_NAME.equals(names[i])?uri.getLastPathSegment():OpenableColumns.SIZE.equals(names[i])?e.bytes.length:null;c.addRow(row);return c;}catch(IOException e){throw new IllegalArgumentException(e);}}
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException{if(!"r".equals(mode))throw new FileNotFoundException("只读导出");Export e=resolve(uri);try{ParcelFileDescriptor[] pipe=ParcelFileDescriptor.createPipe();byte[] bytes=e.bytes.clone();new Thread(()->{try(OutputStream out=new ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])){out.write(bytes);}catch(IOException ignored){}finally{Arrays.fill(bytes,(byte)0);}},"account-export").start();return pipe[0];}catch(IOException ex){throw new FileNotFoundException("无法打开导出");}}
    @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException();}@Override public int update(Uri uri,ContentValues values,String where,String[] args){throw new UnsupportedOperationException();}@Override public int delete(Uri uri,String where,String[] args){throw new UnsupportedOperationException();}
}
