package com.giraffeslovebeauty.acmforever;

/** Write-to-read dependencies; keep unrelated screens warm. Auth changes clear everything. */
final class ReadInvalidation {
    static String[] paths(String path){
        if(path.startsWith("/api/auth/")||path.contains("account-closure"))return new String[]{"/api/"};
        if(path.startsWith("/api/forum/drafts"))return new String[]{"/api/forum/drafts","/api/forum/mine",path.endsWith("/submit")?"/forum/posts":"/api/forum/drafts"};
        if(path.startsWith("/api/forum/posts"))return new String[]{"/forum/posts","/api/forum/mine","/api/me/notifications","/posts?"};
        if(path.startsWith("/api/me/notifications"))return new String[]{"/api/me/notifications"};
        if(path.startsWith("/api/me/problems"))return new String[]{"/api/me/problems","/api/me/problem"};
        if(path.startsWith("/api/me/bindings")||path.equals("/api/me/profile")||path.contains("avatar"))return new String[]{"/api/me/profile","/api/me/avatar","/members/","/public-profile","/leaderboard"};
        if(path.contains("training-tasks"))return new String[]{"/training-tasks"};
        if(path.startsWith("/api/admin/"))return new String[]{"/api/admin/", "/api/me/profile", "/members/", "/leaderboard"};
        return new String[]{path.split("\\?",2)[0]};
    }
}
