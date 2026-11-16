package com.giraffeslovebeauty.acmforever;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.zip.*;
import org.json.*;

/** Minimal XLSX with inline text cells. Untrusted names are never interpreted as formulas. */
final class AccountWorkbook {
    static byte[] create(JSONArray rows)throws Exception{
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(ZipOutputStream out=new ZipOutputStream(bytes)){
            entry(out,"[Content_Types].xml","<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/></Types>");
            entry(out,"_rels/.rels","<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>");
            entry(out,"xl/workbook.xml","<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets><sheet name=\"临时密码\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>");
            entry(out,"xl/_rels/workbook.xml.rels","<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/></Relationships>");
            StringBuilder sheet=new StringBuilder("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>");row(sheet,new String[]{"账号","真实姓名","临时密码","到期时间（北京时间）"});int successes=0;for(int i=0;i<rows.length();i++){JSONObject r=rows.getJSONObject(i);if(!r.has("temporary_password"))continue;successes++;row(sheet,new String[]{r.optString("username",r.optString("qq_id")),r.optString("real_name"),r.getString("temporary_password"),TrainingUi.date(r.optLong("expires_at"))});}if(successes==0)throw new IllegalArgumentException("本次没有可导出的成功临时密码结果");sheet.append("</sheetData></worksheet>");entry(out,"xl/worksheets/sheet1.xml",sheet.toString());
        }return bytes.toByteArray();
    }
    private static void row(StringBuilder out,String[] cells){out.append("<row>");for(String c:cells)out.append("<c t=\"inlineStr\"><is><t xml:space=\"preserve\">").append(xml(c)).append("</t></is></c>");out.append("</row>");}
    private static String xml(String text){return text.replaceAll("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]", "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;");}
    private static void entry(ZipOutputStream out,String name,String value)throws IOException{out.putNextEntry(new ZipEntry(name));out.write(("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"+value).getBytes(StandardCharsets.UTF_8));out.closeEntry();}
}
