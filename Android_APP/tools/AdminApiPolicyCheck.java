package com.giraffeslovebeauty.acmforever;

/** Run with the JDK; no Android runtime or real server required. */
public class AdminApiPolicyCheck {
    public static void main(String[] args) throws Exception {
        String[] allowed={"/api/auth/me", "/api/admin/web-account-candidates?page=1", "/api/member/90000001",
            "/api/problems/codeforces/1843A/state", "/api/tasks/12/cancel", "/api/forum/moderation/posts/1",
            "/api/admin/cf/sync", "/api/forum/posts/1"};
        for(String path:allowed) AdminApiPolicy.check("GET",path);
        String[] rejected={"https://evil.invalid/api/admin/members", "//evil.invalid/api/admin/members",
            "/api/admin/../auth/login", "/api/admin/%2e%2e/auth/login", "/api/admin/%252e%252e/auth/login",
            "/api/admin/members#fragment", "/api/admin//members", "/api/admin/members\\other",
            "/api/auth/login", "/api/internal/token", "/api/me/profile", "/api/admin/members%0a"};
        for(String path:rejected){boolean denied=false;try{AdminApiPolicy.check("GET",path);}catch(Exception e){denied=true;}if(!denied)throw new AssertionError(path);}
        boolean denied=false;try{AdminApiPolicy.check("TRACE","/api/admin/members");}catch(Exception e){denied=true;}
        if(!denied)throw new AssertionError("TRACE allowed");
        System.out.println("Admin API policy passed: allowed management paths and rejected foreign/traversal/unsupported requests.");
    }
}
