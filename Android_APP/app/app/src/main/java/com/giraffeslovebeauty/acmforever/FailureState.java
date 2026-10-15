package com.giraffeslovebeauty.acmforever;

/** Visible failure reasons. Successful empty responses are handled by the page. */
final class FailureState {
    private FailureState() { }

    static String title(Throwable failure) {
        if (failure == null) return "无API接口";
        if (failure instanceof ApiClient.NoNetworkException) return "无网络";
        if (failure instanceof ApiClient.UnconfiguredException) return "未配置服务器";
        if (failure instanceof ApiClient.UnavailableEndpointException) return "无API接口";
        if (failure instanceof ApiClient.ApiException) {
            ApiClient.ApiException api = (ApiClient.ApiException) failure;
            if (api.status == 401) return api.getMessage().contains("密码") ? api.getMessage() : "未登录或登录已失效";
            if (api.status == 403) return "无访问权限";
            if (api.status == 428) return "请修改初始密码";
            if (api.status == 429) return "请求过于频繁";
            if (api.status == 400 || api.status == 409 || api.status == 422) return api.getMessage();
            if (api.status == 410) return "功能已下线";
            if (api.missingContent) return "内容不存在";
            if (api.status == 404 || api.status == 405) return "无API接口";
            if (api.status >= 500) return "服务器异常";
            return "请求失败";
        }
        if (failure instanceof java.net.SocketTimeoutException) return "请求超时";
        if (failure instanceof javax.net.ssl.SSLException) return "安全连接失败";
        if (failure instanceof java.io.IOException) return "无法连接服务器";
        if (failure instanceof org.json.JSONException || failure instanceof ClassCastException) return "数据格式异常";
        return "请求失败";
    }
}
