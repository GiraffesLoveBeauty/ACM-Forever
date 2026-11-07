package com.giraffeslovebeauty.acmforever;

import android.os.Bundle;
import android.widget.LinearLayout;

/** Local help and a factual summary of existing data/permission use. */
public final class HelpActivity extends MobilePageActivity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); createPage("帮助与说明");
        LinearLayout help = card(body); help.addView(text("统一帮助、问题反馈", 19));
        help.addView(text("统一帮助与问题反馈在QQ群里直接提", 16));
        LinearLayout data = card(body); data.addView(text("数据与权限说明", 19));
        data.addView(text("账号与登录", 17));
        data.addView(text("记住账号、记住密码和自动登录由登录页控制。选择保存的密码和登录会话通过设备加密后留在本机；联网验证会话后才能使用 App。退出登录会清除本机保存的密码和自动登录会话。", 14));
        data.addView(text("本机数据", 17));
        data.addView(text("搜索历史、搜索设置、主题、背景原图与裁剪位置只保存在本机；主题文件仅在你主动分享时交给系统分享目标。清理临时文件不会删除账号密码、主题背景或草稿。卸载 App 或在系统中清除应用数据会移除本机数据。", 14));
        data.addView(text("服务器数据", 17));
        data.addView(text("帖子、评论、收藏、云端草稿和 OJ 绑定通过已登录会话访问服务器。确认上传的头像和发帖图片会发送到服务器，自定义背景图只保存在本机。清理本机缓存不会删除服务器数据。账户注销的开关、范围和结果以注销页面的服务器说明与回执为准。", 14));
        data.addView(text("权限与外部页面", 17));
        data.addView(text("网络用于登录、读取内容和更新。通知用于你勾选的训练提醒，可在系统设置关闭。开机广播用于恢复已经启用的本地提醒。图片由系统相册或文件选择器授权读取；安装新版仍需你允许本 App 安装并由系统确认。外链会交给系统浏览器，更新文件来自设置页显示的发布地址。", 14));
        AppAppearance.paintFields(root);
    }
}
