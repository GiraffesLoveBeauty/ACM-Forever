package com.giraffeslovebeauty.acmforever;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/** Temporary, read-only installer grants for verified APKs in private cache. */
public final class UpdateFileProvider extends ContentProvider {
    @Override public boolean onCreate(){return true;}
    private File resolve(Uri uri) throws FileNotFoundException {
        String name=uri.getLastPathSegment();
        if(!"content".equals(uri.getScheme()) || !getContext().getPackageName().concat(".updates").equals(uri.getAuthority())
                || uri.getPathSegments().size()!=1 || name==null || !name.matches("verified-[A-Za-z0-9_-]+\\.apk")
                || uri.getQuery()!=null || uri.getFragment()!=null)throw new FileNotFoundException();
        File file=new File(new File(getContext().getCacheDir(),"updates"),name);
        if(!file.isFile())throw new FileNotFoundException();return file;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if(!"r".equals(mode))throw new FileNotFoundException("Read only");
        return ParcelFileDescriptor.open(resolve(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public String getType(Uri uri){return "application/vnd.android.package-archive";}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order){
        try{
            File file=resolve(uri);String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor cursor=new MatrixCursor(columns);Object[] values=new Object[columns.length];
            for(int i=0;i<columns.length;i++)values[i]=OpenableColumns.DISPLAY_NAME.equals(columns[i])?file.getName():OpenableColumns.SIZE.equals(columns[i])?file.length():null;
            cursor.addRow(values);return cursor;
        }catch(FileNotFoundException e){return null;}
    }
    @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException();}
    @Override public int update(Uri uri,ContentValues values,String where,String[] args){throw new UnsupportedOperationException();}
    @Override public int delete(Uri uri,String where,String[] args){throw new UnsupportedOperationException();}
}
