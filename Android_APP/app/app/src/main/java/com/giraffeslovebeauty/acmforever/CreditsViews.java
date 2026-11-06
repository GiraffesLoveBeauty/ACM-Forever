package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.view.*;
import android.widget.*;
import java.io.InputStream;
import java.util.*;

/** Shared offline avatar/name rows for About and historical releases. */
final class CreditsViews {
    private final Activity activity;
    private final GithubCredits credits;
    private final Map<String, Bitmap> avatars = new HashMap<>();
    CreditsViews(Activity activity, GithubCredits credits) { this.activity = activity; this.credits = credits; }
    private int dp(int n) { return MobileStyle.dp(activity, n); }
    private TextView text(String value, int size) {
        TextView view = new TextView(activity); view.setText(value); view.setTextSize(size);
        view.setTextColor(size < 14 ? MobileStyle.MUTED : MobileStyle.TEXT);
        view.setPadding(0, dp(4), 0, dp(4)); return view;
    }
    void role(LinearLayout parent, String label, List<String> names, String empty) {
        parent.addView(text(label, 13));
        if (names.isEmpty()) parent.addView(text(empty, 13));
        for (String login : names) person(parent, credits.people.get(login), false);
    }
    void person(LinearLayout parent, GithubCredits.Person person, boolean description) {
        LinearLayout row = new SpacedLayout(activity); row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(4), dp(5), dp(4), dp(5)); row.setMinimumHeight(dp(54));
        ImageView avatar = new ImageView(activity); avatar.setScaleType(ImageView.ScaleType.CENTER_CROP);
        avatar.setBackground(MobileStyle.panel(activity, MobileStyle.MODULE, 100, 0)); avatar.setClipToOutline(true);
        Bitmap bitmap = avatars.get(person.avatar);
        if (bitmap == null) {
            try (InputStream in = activity.getAssets().open(person.avatar)) {
                bitmap = BitmapFactory.decodeStream(in);
                if (bitmap != null) avatars.put(person.avatar, bitmap);
            } catch (java.io.IOException ignored) { /* The username remains readable if an asset is damaged. */ }
        }
        if (bitmap == null) avatar.setImageDrawable(AppIcons.get(activity, "avatar", MobileStyle.TEXT));
        else avatar.setImageBitmap(bitmap);
        avatar.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        LinearLayout.LayoutParams imageBounds = new LinearLayout.LayoutParams(dp(40), dp(40)); imageBounds.rightMargin = dp(12); row.addView(avatar, imageBounds);
        LinearLayout copy = new LinearLayout(activity); copy.setOrientation(LinearLayout.VERTICAL);
        copy.addView(text("@" + person.login, 15));
        if (description) copy.addView(text(person.role, 12));
        else if (person.bot()) copy.addView(text("自动化账号", 12));
        row.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        row.setContentDescription("GitHub " + person.login + (person.bot() ? " · 自动化账号" : ""));
        row.setOnClickListener(v -> openProfile(person.profileUrl));
        parent.addView(row, new LinearLayout.LayoutParams(-1, -2));
    }
    void version(LinearLayout parent, String version) {
        GithubCredits.Version record = credits.versions.get(version);
        if (record == null) { parent.addView(text("未收录本版本人员记录", 13)); return; }
        role(parent, "上传 / 提交负责人", record.uploaders, "未收录");
        role(parent, "发起 Review", record.reviewRequesters, "尚未收录发起 Review 的记录");
        role(parent, "Review", record.reviewers, "尚未收录评审记录");
        if (!record.publishers.isEmpty()) role(parent, "安装包自动发布", record.publishers, "");
        parent.addView(text(record.publication(), 12));
        parent.addView(text(record.scope, 12));
    }
    private void openProfile(String url) {
        try { activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE)); }
        catch (ActivityNotFoundException e) { Toast.makeText(activity, "未找到可打开 GitHub 的浏览器", Toast.LENGTH_SHORT).show(); }
    }
}
