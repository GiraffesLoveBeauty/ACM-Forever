package com.giraffeslovebeauty.acmforever;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/** Calls the existing Web session API. No /internal/v1 token is used by the app. */
final class ApiClient {
    private final CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private volatile String baseUrl = "";
    private volatile String csrfToken = "";
    private volatile boolean mustChangePassword;
    private volatile String role = "";
    private volatile String memberAccount = "";
    private volatile String currentAvatar = "";
    String currentAvatarUrl(){return currentAvatar;}
    private volatile long sessionGeneration;
    private volatile JSONObject mobileFeatures;
    private volatile long mobileCheckedAt;
    private final ResponseCache responses=new ResponseCache();
    private final ResponseCache readFailures=new ResponseCache(64*1024);
    private final Map<String,android.graphics.Bitmap> avatarCache=java.util.Collections.synchronizedMap(new java.util.LinkedHashMap<String,android.graphics.Bitmap>(32,.75f,true){
        @Override protected boolean removeEldestEntry(Map.Entry<String,android.graphics.Bitmap> entry){return size()>64;}
    });
    private static final class Replay {int hits;boolean missed;}
    private final ThreadLocal<Replay> replay=new ThreadLocal<>();
    private final ThreadLocal<Exception> readIssue=new ThreadLocal<>();
    void beginReadCycle(){readIssue.remove();}
    Exception readIssue(){return readIssue.get();}
    static final class CacheMissException extends IllegalStateException {CacheMissException(){super("No cached response");}}
    void beginReplay(){replay.set(new Replay());}
    void endReplay(){replay.remove();}
    boolean isReplay(){return replay.get()!=null;}
    boolean replayReady(){Replay state=replay.get();return state!=null&&state.hits>0&&!state.missed;}
    private String cacheKey(String path){return baseUrl+"\n"+sessionGeneration+"\n"+path;}
    private Runnable sessionChanged = () -> {};
    private Runnable loggedOut = () -> {};
    private final java.util.IdentityHashMap<java.net.HttpCookie, Long> cookieExpiry = new java.util.IdentityHashMap<>();
    void setSessionChanged(Runnable listener) { sessionChanged = listener; }
    void setLoggedOut(Runnable listener) { loggedOut = listener; }

    synchronized String exportSession() throws Exception {
        if (!isLoggedIn()) return "";
        JSONArray items = new JSONArray();
        long now = System.currentTimeMillis();
        for (java.net.HttpCookie cookie : cookies.getCookieStore().getCookies()) {
            if (cookie.hasExpired()) continue;
            long seconds = cookie.getMaxAge();
            if (seconds <= 0) continue; // Persist only server-issued persistent cookies.
            long expires = cookieExpiry.computeIfAbsent(cookie, c -> now + Math.min(seconds, 30L * 86400) * 1000);
            if (expires <= now) continue;
            items.put(new JSONObject().put("name", cookie.getName()).put("value", cookie.getValue())
                    .put("path", cookie.getPath() == null ? "/" : cookie.getPath())
                    .put("expires", expires));
        }
        return items.length() == 0 ? "" : new JSONObject().put("origin", baseUrl).put("cookies", items).toString();
    }

    boolean restoreSession(String value) throws Exception {
        if (value.isEmpty()) return false;
        JSONObject saved = new JSONObject(value);
        if (!baseUrl.equals(saved.getString("origin"))) return false;
        JSONArray items = saved.getJSONArray("cookies");
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.getJSONObject(i);
            long seconds = (item.getLong("expires") - System.currentTimeMillis()) / 1000;
            if (seconds <= 0) continue;
            java.net.HttpCookie cookie = new java.net.HttpCookie(item.getString("name"), item.getString("value"));
            cookie.setDomain(URI.create(baseUrl).getHost());
            cookie.setVersion(0); cookie.setPath(item.getString("path")); cookie.setSecure(true); cookie.setHttpOnly(true); cookie.setMaxAge(seconds);
            cookies.getCookieStore().add(URI.create(baseUrl), cookie);
        }
        return !cookies.getCookieStore().getCookies().isEmpty();
    }
    private java.util.function.BooleanSupplier networkAvailable = () -> true;

    void setNetworkAvailable(java.util.function.BooleanSupplier check) { networkAvailable = check; }

    static final class NoNetworkException extends java.io.IOException {
        NoNetworkException() { super("无网络"); }
    }

    static final class UnconfiguredException extends IllegalStateException {
        UnconfiguredException() { super("未配置服务器"); }
    }

    static final class ApiException extends IllegalStateException {
        final int status;
        final boolean missingContent;
        JSONObject details;
        ApiException(int status, String message, boolean missingContent) {
            super(message); this.status = status; this.missingContent = missingContent;
        }
    }

    static final class UnavailableEndpointException extends IllegalStateException {
        UnavailableEndpointException(String feature) { super("无API接口：" + feature); }
    }

    static String checkedBaseUrl(String value) {
        String raw = value == null ? "" : value.trim();
        if (raw.isEmpty()) return "";
        try {
            URI uri = new URI(raw);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null
                    || !(uri.getPath().isEmpty() || "/".equals(uri.getPath()))) {
                throw new IllegalArgumentException("请输入 HTTPS 服务根地址，不附加 /api 或查询参数。");
            }
            return raw.replaceAll("/+$", "");
        } catch (java.net.URISyntaxException e) {
            throw new IllegalArgumentException("服务地址格式无效。", e);
        }
    }

    synchronized void setBaseUrl(String value) {
        String checked = checkedBaseUrl(value);
        if (!checked.equals(baseUrl)) {
            ++sessionGeneration;
            cookies.getCookieStore().removeAll();
            csrfToken = "";
            mustChangePassword = false;
            role = "";
            memberAccount = "";
            mobileFeatures = null;
            mobileCheckedAt = 0;
            baseUrl = checked;
            responses.clear();
            readFailures.clear();
            avatarCache.clear();
            media.clear();
            sessionChanged.run();
        }
    }

    boolean isUnconfigured() {
        return baseUrl.isEmpty();
    }

    boolean isLoggedIn() {
        return !csrfToken.isEmpty();
    }

    long sessionGeneration() { return sessionGeneration; }
    String accountKey() { return memberAccount; }

    boolean requiresPasswordChange() { return mustChangePassword; }

    boolean isAdministrator() { return isLoggedIn() && ("admin".equals(role) || "root".equals(role)); }

    synchronized JSONObject refreshSession() throws Exception {
        if(isReplay())return new JSONObject();
        JSONObject result = getObject("/api/auth/me");
        if (!result.optBoolean("authenticated")) {
            clearSession();
            throw new ApiException(401, "登录已失效，请重新登录。", false);
        }
        csrfToken = result.optString("csrf_token", "");
        role = result.optString("role", "");
        memberAccount = result.optString("qq_id", memberAccount);
        mustChangePassword = result.optBoolean("must_change_password");
        sessionChanged.run();
        if (mustChangePassword) throw new IllegalStateException("请先修改初始密码。");
        return result;
    }

    String getBaseUrl() {
        return baseUrl;
    }

    boolean supportsMobile(String feature) throws Exception {
        if(!isReplay())checkConnection();
        if (mobileFeatures == null || System.currentTimeMillis() - mobileCheckedAt >= 60000) {
            try {
                JSONObject result = getObject("/api/mobile/v1/capabilities");
                JSONObject features = result.optJSONObject("features");
                if (result.optInt("api_version") != 1 || features == null)
                    throw new IllegalStateException("移动端 API 能力响应格式或版本不支持。");
                mobileFeatures = features;
            } catch (ApiException e) {
                if (e.status != 404 && e.status != 405) throw e;
                mobileFeatures = new JSONObject();
            }
            mobileCheckedAt = System.currentTimeMillis();
        }
        return mobileFeatures.optBoolean(feature);
    }

    String publicPostsPath(String suffix) throws Exception {
        return (supportsMobile("public_member_ids") ? "/api/mobile/v1/forum/posts" : "/api/forum/posts") + suffix;
    }

    String leaderboardPath(String suffix) throws Exception {
        return (supportsMobile("public_member_ids") ? "/api/mobile/v1/leaderboard" : "/api/community/leaderboard") + suffix;
    }

    JSONObject leaderboard(String range, String sort, String platforms, String search, int page, int size) throws Exception {
        JSONObject result=getObject(RankOptions.path(range,sort,platforms,search,page,size));
        if(result.optBoolean("positive_only"))return result;
        // Older servers include zero-AC rows: gather their pages before filtering and paging.
        JSONArray all=new JSONArray();
        int total=result.getInt("total");
        for(int offset=1;offset<=Math.max(1,(total+99)/100);offset++){
            JSONObject chunk=getObject(RankOptions.path(range,sort,platforms,search,offset,100));
            JSONArray data=chunk.getJSONArray("rows");
            for(int i=0;i<data.length();i++)if(data.getJSONObject(i).getInt("total_count")>0)all.put(data.getJSONObject(i));
        }
        int pages=Math.max(1,(all.length()+size-1)/size), current=page>=1&&page<=pages?page:1;
        JSONArray selected=new JSONArray();
        for(int i=(current-1)*size;i<Math.min(all.length(),current*size);i++)selected.put(all.getJSONObject(i));
        return new JSONObject().put("rows",selected).put("total",all.length()).put("page",current).put("page_size",size).put("positive_only",true);
    }

    JSONObject ownPublicProfile() throws Exception {
        requireMobile("own_public_profile", "本人公开主页");
        return getObject("/api/mobile/v1/me/public-profile");
    }

    JSONObject memberProfile(String publicId) throws Exception {
        requireMobile("member_profiles", "成员公开资料");
        return getObject("/api/mobile/v1/members/" + checkedPublicId(publicId));
    }

    JSONObject memberPosts(String publicId, int page) throws Exception {
        requireMobile("member_posts", "成员已发布话题");
        return getObject("/api/mobile/v1/members/" + checkedPublicId(publicId) + "/posts?page=" + page + "&page_size=12");
    }

    private void requireMobile(String feature, String name) throws Exception {
        if (!supportsMobile(feature)) throw new UnavailableEndpointException(name);
    }

    private String checkedPublicId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{32}")) throw new IllegalArgumentException("公开成员 ID 格式无效。");
        return value;
    }

    Object get(String path) throws Exception {
        String key=cacheKey(path);Replay state=replay.get();
        boolean cacheable=!path.startsWith("/api/auth/");
        if(state!=null){
            Object cached=cacheable?responses.get(key):null;
            if(cached!=null){state.hits++;return cached;}
            JSONObject failure=cacheable?(JSONObject)readFailures.get(key):null;
            if(failure!=null){state.hits++;throw new ApiException(failure.getInt("status"),failure.getString("message"),failure.getBoolean("missing"));}
            state.missed=true;throw new CacheMissException();
        }
        try{
            Object result=request("GET",path,null);
            if(key.equals(cacheKey(path))&&cacheable){responses.put(key,result);readFailures.remove(key);}
            return result;
        }catch(ApiException e){
            if(e.status>=500)readIssue.set(e);
            if(cacheable&&key.equals(cacheKey(path))&&(e.status==403||e.status==404||e.status==405||e.status==410))
                readFailures.put(key,new JSONObject().put("status",e.status).put("message",e.getMessage()).put("missing",e.missingContent));
            throw e;
        }catch(Exception e){
            if(PageRefresh.isConnectionFailure(FailureState.title(e)))readIssue.set(e);
            throw e;
        }
    }

    JSONObject getObject(String path) throws Exception {
        Object result = get(path);
        if (!(result instanceof JSONObject)) throw new org.json.JSONException("API应返回对象");
        return (JSONObject) result;
    }

    JSONArray getArray(String path) throws Exception {
        Object result = get(path);
        if (!(result instanceof JSONArray)) throw new org.json.JSONException("API应返回列表");
        return (JSONArray) result;
    }

    synchronized JSONObject login(String identifier, String password) throws Exception {
        clearSession();
        JSONObject body = new JSONObject().put("username", identifier).put("password", password);
        if (identifier.matches("[0-9]{4,12}")) body.put("qq_id", identifier);
        try {
            request("POST", "/api/auth/login", body);
            JSONObject session = getObject("/api/auth/me");
            if (!session.optBoolean("authenticated") || session.optString("csrf_token", "").isEmpty())
                throw new org.json.JSONException("服务器未确认登录会话");
            csrfToken = session.getString("csrf_token");
            ++sessionGeneration;
            mustChangePassword = session.optBoolean("must_change_password");
            role = session.optString("role", "");
            memberAccount = session.optString("qq_id", identifier);
            sessionChanged.run();
            return session;
        } catch (Exception e) { clearSession(); throw e; }
    }

    private void clearSession() {
        ++sessionGeneration;
        media.clear();
        avatarCache.clear();currentAvatar="";
        responses.clear();
        readFailures.clear();
        csrfToken = ""; mustChangePassword = false; role = ""; memberAccount = "";
        cookies.getCookieStore().removeAll();
        cookieExpiry.clear();
        sessionChanged.run();
    }

    synchronized void logout() throws Exception {
        try {
            if (!csrfToken.isEmpty()) request("POST", "/api/auth/logout", new JSONObject());
        } finally {
            try { clearSession(); }
            finally { loggedOut.run(); }
        }
    }

    JSONObject createPost(int categoryId, String title, String body) throws Exception {
        if (csrfToken.isEmpty()) throw new IllegalStateException("请先登录再发布帖子。");
        JSONObject payload = new JSONObject();
        payload.put("category_id", categoryId);
        payload.put("title", title);
        payload.put("body", body);
        return (JSONObject) request("POST", "/api/forum/posts", payload);
    }

    JSONObject updateName(String name) throws Exception {
        return (JSONObject) request("PUT", "/api/me/profile", new JSONObject().put("name", name));
    }

    JSONObject postAction(int postId, String action, String text, int parentId) throws Exception {
        if (!java.util.Arrays.asList("like", "bookmark", "report", "comments").contains(action))
            throw new IllegalArgumentException("无效的话题操作");
        JSONObject body = new JSONObject();
        if ("report".equals(action)) body.put("reason", text);
        if ("comments".equals(action)) body.put("body", text).put("parent_id", parentId);
        return writeObject("POST", "/api/forum/posts/" + postId + "/" + action, body);
    }

    JSONObject saveDraft(int draftId, int categoryId, String title, String body) throws Exception {
        return saveDraft(draftId,categoryId,title,body,0);
    }
    JSONObject saveDraft(int draftId, int categoryId, String title, String body,int version) throws Exception {
        JSONObject payload = new JSONObject().put("category_id", categoryId > 0 ? categoryId : JSONObject.NULL)
                .put("title", title).put("body", body);
        if(version>0)payload.put("edit_version",version);
        return writeObject(draftId > 0 ? "PUT" : "POST", "/api/forum/drafts" + (draftId > 0 ? "/" + draftId : ""), payload);
    }

    synchronized JSONObject saveDraftBound(long expected, int id, int category, String title, String body,int version) throws Exception {
        if(expected!=sessionGeneration || !isLoggedIn())throw new IllegalStateException("登录账号已切换，草稿保存已取消");
        return saveDraft(id,category,title,body,version);
    }

    synchronized void downloadPdf(String platform,String problemId,java.io.File file) throws Exception {
        checkConnection();
        URI uri=URI.create(baseUrl+problemPath(platform,problemId)+"/statement.pdf");
        HttpURLConnection connection=(HttpURLConnection)uri.toURL().openConnection();
        connection.setConnectTimeout(10000);connection.setReadTimeout(30000);connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept","application/pdf");
        for(Map.Entry<String,List<String>> header:cookies.get(uri,Collections.emptyMap()).entrySet())
            if(header.getKey()!=null)connection.setRequestProperty(header.getKey(),String.join("; ",header.getValue()));
        try {
            int code=connection.getResponseCode();
            if(code!=200){readResult(connection,uri);throw new java.io.IOException("PDF 接口响应异常");}
            if(connection.getContentLengthLong()>32L*1024*1024)throw new java.io.IOException("PDF 超过32 MB，请使用网页阅读");
            try(InputStream input=connection.getInputStream();java.io.FileOutputStream output=new java.io.FileOutputStream(file)){
                byte[] buffer=new byte[8192];int count,total=0;
                byte[] signature=new byte[5];int n=0;while(n<5){int read=input.read(signature,n,5-n);if(read<0)break;n+=read;}
                if(n!=5||!new String(signature,StandardCharsets.US_ASCII).equals("%PDF-"))throw new java.io.IOException("服务器未返回有效PDF");
                output.write(signature);
                while((count=input.read(buffer))!=-1){total+=count;if(total>32*1024*1024)throw new java.io.IOException("PDF 超过32 MB");output.write(buffer,0,count);}
            }
        }finally{connection.disconnect();}
    }

    synchronized JSONObject submitDraft(long expected,int draftId,int version) throws Exception {
        if(expected!=sessionGeneration||!isLoggedIn())throw new IllegalStateException("登录账号已切换，提交已取消");
        JSONObject payload=new JSONObject();if(version>0)payload.put("edit_version",version);
        return writeObject("POST", "/api/forum/drafts/" + draftId + "/submit",payload);
    }

    JSONObject deleteDraft(int draftId) throws Exception {
        return writeObject("DELETE", "/api/forum/drafts/" + draftId, new JSONObject());
    }

    JSONObject favoriteProblem(String platform, String problemId, boolean favorite) throws Exception {
        return writeObject("PUT", problemPath(platform, problemId) + "/state", new JSONObject().put("is_favorite", favorite));
    }

    static String problemPath(String platform, String problemId) {
        return "/api/me/problems/" + segment(platform) + "/" + segment(problemId);
    }

    private static String segment(String value) {
        return UrlEncoding.form(value).replace("+", "%20");
    }

    JSONObject writeObject(String method, String path, JSONObject body) throws Exception {
        Object value = request(method, path, body);
        if (!(value instanceof JSONObject)) throw new org.json.JSONException("API应返回对象");
        return (JSONObject) value;
    }

    Object adminRequest(String method, String path, JSONObject body) throws Exception {
        AdminApiPolicy.check(method, path);
        if (!isAdministrator() || requiresPasswordChange()) throw new ApiException(403, "无访问权限", false);
        if (path.equals("/api/auth/me")) return refreshSession();
        if (path.equals("/api/auth/logout")) { logout(); return new JSONObject().put("success", true); }
        return request(method, path, "GET".equals(method) ? null : body == null ? new JSONObject() : body);
    }

    JSONObject changePassword(String oldPassword, String newPassword) throws Exception {
        JSONObject body = new JSONObject().put("old_password", oldPassword).put("new_password", newPassword);
        JSONObject result = (JSONObject) request("POST", "/api/auth/change-password", body);
        mustChangePassword = false;
        return result;
    }

    JSONObject resetAvatar() throws Exception {
        return (JSONObject) request("DELETE", "/api/me/avatar", new JSONObject());
    }

    android.graphics.Bitmap cachedAvatarBitmap(String path){return avatarCache.get(baseUrl+"/"+path);}

    android.graphics.Bitmap avatarBitmap(String path) throws Exception {
        String base = baseUrl;
        String key=base+"/"+path;android.graphics.Bitmap cached=avatarCache.get(key);if(cached!=null)return cached;
        if (base.isEmpty() || path == null || !(path.startsWith("/uploads/avatars/") || path.equals("/assets/default-avatar.png"))) return null;
        URI address = URI.create(base).resolve(path);
        if (!address.getHost().equals(URI.create(base).getHost()) || !"https".equals(address.getScheme())) return null;
        HttpURLConnection connection = (HttpURLConnection) address.toURL().openConnection();
        connection.setConnectTimeout(10000); connection.setReadTimeout(10000);
        connection.setInstanceFollowRedirects(false);
        try {
            if (connection.getResponseCode() != 200) return null;
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int size;
                while ((size = input.read(buffer)) != -1) {
                    if (output.size() + size > 2 * 1024 * 1024) return null;
                    output.write(buffer, 0, size);
                }
                byte[] bytes = output.toByteArray();
                android.graphics.BitmapFactory.Options options = new android.graphics.BitmapFactory.Options();
                options.inJustDecodeBounds = true;
                android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
                if (options.outWidth <= 0 || options.outHeight <= 0) return null;
                options.inSampleSize = 1;
                while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > 256) options.inSampleSize *= 2;
                options.inJustDecodeBounds = false;
                android.graphics.Bitmap image=android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);if(image!=null&&base.equals(baseUrl))avatarCache.put(key,image);return image;
            }
        } finally { connection.disconnect(); }
    }

    synchronized JSONObject uploadForumImage(long expected,byte[] image)throws Exception{
        if(expected!=sessionGeneration||!isLoggedIn())throw new IllegalStateException("登录账号已切换，上传已取消");checkConnection();
        if(image.length==0||image.length>5*1024*1024)throw new IllegalArgumentException("上传图片不能超过 5 MB");
        String boundary="acmforum"+java.util.UUID.randomUUID().toString().replace("-","");URI uri=URI.create(baseUrl+"/api/forum/images");HttpURLConnection connection=(HttpURLConnection)uri.toURL().openConnection();
        connection.setRequestMethod("POST");connection.setConnectTimeout(10000);connection.setReadTimeout(60000);connection.setInstanceFollowRedirects(false);connection.setDoOutput(true);connection.setRequestProperty("X-CSRF-Token",csrfToken);connection.setRequestProperty("Content-Type","multipart/form-data; boundary="+boundary);
        for(Map.Entry<String,List<String>> header:cookies.get(uri,Collections.emptyMap()).entrySet())if(header.getKey()!=null)connection.setRequestProperty(header.getKey(),String.join("; ",header.getValue()));
        try{try(OutputStream out=connection.getOutputStream()){out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"image\"; filename=\"image.webp\"\r\nContent-Type: image/webp\r\n\r\n").getBytes(StandardCharsets.UTF_8));out.write(image);out.write(("\r\n--"+boundary+"--\r\n").getBytes(StandardCharsets.UTF_8));}JSONObject result=(JSONObject)readResult(connection,uri);ForumImages.markdown(result.getString("url"));return result;}finally{connection.disconnect();}
    }
    JSONObject uploadAvatar(byte[] image, String mimeType) throws Exception {
        checkConnection();
        if (csrfToken.isEmpty()) throw new IllegalStateException("请先登录再上传头像。");
        if (image.length == 0 || image.length > 2 * 1024 * 1024)
            throw new IllegalArgumentException("头像图片不能超过 2 MB。");
        if (!"image/png".equals(mimeType) && !"image/jpeg".equals(mimeType)
                && !"image/webp".equals(mimeType))
            throw new IllegalArgumentException("请选择 PNG、JPEG 或 WebP 图片。");
        String boundary = "acmforever" + System.currentTimeMillis();
        URL url = new URL(baseUrl + "/api/me/avatar");
        URI uri = url.toURI();
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setInstanceFollowRedirects(false);
        connection.setDoOutput(true);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("X-CSRF-Token", csrfToken);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        for (Map.Entry<String, List<String>> header : cookies.get(uri, Collections.emptyMap()).entrySet())
            if (header.getKey() != null) connection.setRequestProperty(header.getKey(), String.join("; ", header.getValue()));
        String extension = "image/png".equals(mimeType) ? "png" : "image/webp".equals(mimeType) ? "webp" : "jpg";
        try {
            try (OutputStream out = connection.getOutputStream()) {
                out.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"avatar\"; filename=\"avatar." + extension
                        + "\"\r\nContent-Type: " + mimeType + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
                out.write(image);
                out.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            }
            return (JSONObject) readResult(connection, uri);
        } finally { connection.disconnect(); }
    }

    private synchronized Object request(String method, String path, JSONObject body) throws Exception {
        if(isReplay())throw new CacheMissException(); // Preview work can never perform a write or network request.
        checkConnection();
        if (!path.startsWith("/api/")) throw new IllegalArgumentException("只能调用现有 /api/* 接口。");
        URL url = new URL(baseUrl + path);
        URI uri = url.toURI();
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept", "application/json");
        for (Map.Entry<String, List<String>> header : cookies.get(uri, Collections.emptyMap()).entrySet()) {
            if (header.getKey() != null) connection.setRequestProperty(header.getKey(), String.join("; ", header.getValue()));
        }
        try {
        if (body != null) {
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            if (!csrfToken.isEmpty() && !path.equals("/api/auth/login")) connection.setRequestProperty("X-CSRF-Token", csrfToken);
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream out = connection.getOutputStream()) { out.write(bytes); }
        }
            Object result=readResult(connection,uri);
            if(!"GET".equals(method)){
                if(path.startsWith("/api/forum/drafts")){responses.removeContaining("/api/forum/drafts");readFailures.removeContaining("/api/forum/drafts");}
                else {responses.clear();readFailures.clear();}
            }
            return result;
        } finally {
            connection.disconnect();
        }
    }

    static final class Media {final byte[] bytes;final String mime;Media(byte[] bytes,String mime){this.bytes=bytes;this.mime=mime;}}
    private final java.util.LinkedHashMap<String,Media> media=new java.util.LinkedHashMap<>(8,.75f,true);
    String communityImageUrl(String address){try{String resolved=new URI(baseUrl+"/").resolve(address).toString();return isCommunityMedia(resolved)?resolved:"";}catch(Exception ignored){return "";}}
    boolean isCommunityMedia(String address){try{URI uri=new URI(address),base=new URI(baseUrl);String path=uri.getRawPath(),query=uri.getRawQuery();return "https".equals(uri.getScheme())&&java.util.Objects.equals(uri.getHost(),base.getHost())&&(uri.getPort()<0?443:uri.getPort())==(base.getPort()<0?443:base.getPort())&&uri.getUserInfo()==null&&uri.getFragment()==null&&path!=null&&path.matches("/api/forum/images/[a-f0-9]{32}")&&(query==null||"variant=thumb".equals(query));}catch(Exception ignored){return false;}}
    synchronized Media communityMedia(String address)throws Exception{
        if(!isCommunityMedia(address))throw new IllegalArgumentException("图片地址不属于当前社区");String key=baseUrl+"/"+sessionGeneration+"/"+address;
        Media cached=media.get(key);if(cached!=null)return cached;checkConnection();URL url=new URL(address);HttpURLConnection connection=(HttpURLConnection)url.openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(10000);
        for(Map.Entry<String,List<String>> header:cookies.get(url.toURI(),Collections.emptyMap()).entrySet())if(header.getKey()!=null)connection.setRequestProperty(header.getKey(),String.join("; ",header.getValue()));
        try{int status=connection.getResponseCode();if(status!=200)throw new ApiException(status,"图片读取失败",status==404);String mime=connection.getContentType();if(mime==null)throw new java.io.IOException("图片缺少格式");mime=mime.split(";",2)[0].trim().toLowerCase(java.util.Locale.ROOT);if(!java.util.Arrays.asList("image/png","image/jpeg","image/webp","image/gif").contains(mime))throw new java.io.IOException("不支持的图片格式");
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();try(InputStream in=connection.getInputStream()){byte[] buffer=new byte[8192];int count;while((count=in.read(buffer))!=-1){if(bytes.size()+count>8*1024*1024)throw new java.io.IOException("图片超过 8 MB");bytes.write(buffer,0,count);}}
            Media result=new Media(bytes.toByteArray(),mime);media.put(key,result);int total=0;for(Media item:media.values())total+=item.bytes.length;java.util.Iterator<Media> oldest=media.values().iterator();while((total>16*1024*1024||media.size()>8)&&oldest.hasNext()){Media item=oldest.next();total-=item.bytes.length;oldest.remove();}return result;
        }finally{connection.disconnect();}
    }

    private Object readResult(HttpURLConnection connection, URI uri) throws Exception {
            int status = connection.getResponseCode();
            cookies.put(uri, connection.getHeaderFields());
            if (isLoggedIn() && connection.getHeaderFields().keySet().stream().anyMatch(k -> "Set-Cookie".equalsIgnoreCase(k))) sessionChanged.run();
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            StringBuilder text = new StringBuilder();
            if (stream != null) {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) text.append(line);
                }
            }
            if (status < 200 || status >= 300) {
                String message = "接口返回 HTTP " + status;
                JSONObject details = null;
                try { details = new JSONObject(text.toString()); message = details.optString("message", message); } catch (Exception ignored) { }
                if (status == 401) clearSession();
                if(status==403||status==404||status==410)responses.removeContaining(uri.getPath());
                if (status == 428) mustChangePassword = true;
                boolean missingContent = status == 404 && uri.getPath().matches(".*/(?:members/[A-Za-z0-9_-]{32}(?:/posts)?|posts/[0-9]+)");
                ApiException failure = new ApiException(status, message, missingContent); failure.details = details; throw failure;
            }
            Object result=new JSONTokener(text.toString()).nextValue();
            if(result instanceof JSONObject){JSONObject object=(JSONObject)result;String path=uri.getPath();
                if(("/api/auth/me".equals(path)||"/api/me/avatar".equals(path))&&object.has("avatar_url"))currentAvatar=object.isNull("avatar_url")?"":object.optString("avatar_url");
                else if("/api/me/profile".equals(path)&&object.optJSONObject("user")!=null&&object.getJSONObject("user").has("avatar_url"))currentAvatar=object.getJSONObject("user").isNull("avatar_url")?"":object.getJSONObject("user").optString("avatar_url");
            }
            return result;
    }

    private void checkConnection() throws Exception {
        if (!networkAvailable.getAsBoolean()) throw new NoNetworkException();
        if (baseUrl.isEmpty()) throw new UnconfiguredException();
    }
}
