package com.giraffeslovebeauty.acmforever;

import java.net.URI;
import java.util.Arrays;

/** Narrow API boundary for the packaged administrator interface. */
final class AdminApiPolicy {
    static void check(String method, String value) throws Exception {
        if (!Arrays.asList("GET", "POST", "PUT", "PATCH", "DELETE").contains(method)) throw new IllegalArgumentException("不支持的管理操作");
        URI uri = new URI(value);
        if (uri.isAbsolute() || uri.getRawAuthority() != null || uri.getFragment() != null || value.indexOf('\\') >= 0)
            throw new IllegalArgumentException("管理请求地址无效");
        String path = uri.getPath();
        if (path == null || !path.matches("/api/[A-Za-z0-9_/-]+") || path.contains("//")) throw new IllegalArgumentException("管理请求地址无效");
        boolean allowed = path.matches("/api/admin/[A-Za-z0-9_/-]+")
                || path.matches("/api/forum/posts/[0-9]+") && method.equals("GET")
                || path.matches("/api/member/[0-9]{4,12}")
                || path.matches("/api/tasks(?:/[A-Za-z0-9_-]+/cancel)?")
                || path.matches("/api/problems(?:/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/state)?")
                || path.matches("/api/challenge/(?:list|start|rating)")
                || path.matches("/api/forum/moderation/(?:posts|reports)(?:/[0-9]+)?")
                || Arrays.asList("/api/user", "/api/stats", "/api/training/weak-tags", "/api/training/summary",
                    "/api/contest/reviews", "/api/settings/contest-report", "/api/admins", "/api/ui/preferences").contains(path)
                || path.equals("/api/auth/me") && method.equals("GET")
                || path.equals("/api/auth/logout") && method.equals("POST");
        if (!allowed) throw new IllegalArgumentException("该接口不属于管理界面");
    }
}
