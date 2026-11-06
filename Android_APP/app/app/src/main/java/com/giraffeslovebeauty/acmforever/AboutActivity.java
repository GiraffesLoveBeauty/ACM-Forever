package com.giraffeslovebeauty.acmforever;

import android.os.Bundle;
import android.widget.LinearLayout;

/** Login-protected credits page; names and avatars are bundled for offline use. */
public final class AboutActivity extends MobilePageActivity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); createPage("关于 ACMForever");
        LinearLayout intro = card(body); intro.addView(text("ACMForever", 25));
        intro.addView(text("一起交流，一起 AC", 16));
        String version;
        try { version = getPackageManager().getPackageInfo(getPackageName(), 0).versionName; }
        catch (android.content.pm.PackageManager.NameNotFoundException e) { version = "版本信息不可用"; }
        intro.addView(text("版本 " + version, 14));
        try {
            GithubCredits credits = GithubCredits.load(this); CreditsViews views = new CreditsViews(this, credits);
            LinearLayout owner = card(body); owner.addView(text("App 维护", 19));
            for (String login : credits.maintainers) views.person(owner, credits.people.get(login), true);
            owner.addView(text(credits.historyOwnerNote, 12));
            LinearLayout thanks = card(body); thanks.addView(text("特别鸣谢", 21));
            thanks.addView(text("感谢代码贡献、评审协作和自动化支持。点击头像或用户名可打开 GitHub。", 13));
            for (String login : credits.thanks) {
                GithubCredits.Person person = credits.people.get(login);
                if (!person.bot()) views.person(thanks, person, true);
            }
            LinearLayout automation = card(body); automation.addView(text("自动化支持", 19));
            for (String login : credits.thanks) {
                GithubCredits.Person person = credits.people.get(login);
                if (person.bot()) views.person(automation, person, true);
            }
            automation.addView(text("机器人代码评审不等于人工批准。", 12));
            LinearLayout source = card(body); source.addView(text("记录来源", 17));
            source.addView(text("GitHub 仓库贡献者、App PR 的发起与评审记录、公开 Release；本机快照日期：" + credits.capturedOn + "。后续参与者会随版本补充，当前信息并非实时名单。", 12));
        } catch (Exception e) {
            LinearLayout unavailable = card(body); ErrorModule.style(unavailable);
            unavailable.addView(text("本地人员记录读取失败", 15));
        }
        AppAppearance.paintFields(root);
    }
}
