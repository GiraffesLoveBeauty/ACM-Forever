package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ImageButton;
import android.widget.PopupMenu;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.ArrayAdapter;
import android.widget.Spinner;
import android.widget.AdapterView;
import android.widget.TextView;
import android.widget.ProgressBar;
import android.widget.CheckBox;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.URLEncoder;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Small native API client sample. All business data remains on the existing backend. */
public final class MainActivity extends Activity {
    private static final int PICK_AVATAR = 41;
    private static final int BACKGROUND = Color.rgb(237, 243, 239);
    private static final int PANEL = Color.rgb(251, 253, 249);
    private static final int TEXT = Color.rgb(22, 52, 50);
    private static final int MUTED = Color.rgb(93, 116, 113);
    private static final int BRAND = Color.rgb(22, 118, 106);
    private static final int ACCENT = Color.rgb(214, 234, 114);
    private static final int LINE = Color.rgb(208, 222, 215);

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ExecutorService avatarIo = Executors.newFixedThreadPool(2);
    private final ApiClient api = new ApiClient();
    private LinearLayout root;
    private LinearLayout content;
    private EditText search;
    private LinearLayout nav;
    private ImageButton headerAvatar;
    private SharedPreferences preferences;
    private UpdateManager updates;
    private String screen = "forum";
    private String query = "";
    private String category = "";
    private String sort = "latest";
    private String days = "7";
    private String platform = "";
    private int page = 1;
    private int rankPageSize = 20;
    private boolean popupLoading;
    private int postId = 0;
    private JSONObject memberPreview;
    private String memberReturnScreen = "forum";
    private volatile int requestSerial = 0;
    private LinearLayout loadingRegion;
    private Exception publicFailure;
    private Exception publishedFailure;
    private Exception mottoFailure;
    private String composeTitle = "";
    private String composeBody = "";
    private int composeCategoryId = 0;
    private int composeDraftId = 0;
    private boolean composeBusy;
    private long composeRevision;
    private long composeSavedRevision;
    private boolean leaveComposeOnce;
    private TextView composeStatus;
    private boolean loginBusy;
    private SessionVault sessionVault;
    private volatile boolean sessionSaveFailed;
    private volatile boolean passwordSaveFailed;
    private boolean returnFromAdmin;
    private String searchScope = "forum";
    private String searchReturn = "forum";
    private boolean filterLoading;
    private AlertDialog forumFilterDialog;
    private String loginIdentifier = "";
    private String loginDestination = "account";
    private String problemState = "";
    private JSONObject selectedProblem;
    private String rankSort = "total_count";
    private boolean actionBusy;
    private int commentPostId;
    private String commentBody = "";
    private int commentParent;
    private final java.util.LinkedHashSet<String> rankPlatforms = new java.util.LinkedHashSet<>(
            java.util.Arrays.asList("codeforces", "luogu", "atcoder", "nowcoder", "cjlu"));

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        preferences = getSharedPreferences("acmforever_settings", MODE_PRIVATE);
        String defaultBase = getString(R.string.default_api_base_url);
        try {
            String savedBase = ApiClient.checkedBaseUrl(preferences.getString("api_base_url", ""));
            api.setBaseUrl(savedBase.isEmpty() ? defaultBase : savedBase);
        } catch (IllegalArgumentException ignored) {
            preferences.edit().remove("api_base_url").apply();
            api.setBaseUrl(defaultBase);
        }
        updates = new UpdateManager(this, io);
        api.setNetworkAvailable(this::networkAvailable);
        buildShell();
        sessionVault = new SessionVault(preferences);
        loginIdentifier = preferences.getString("remembered_account", "");
        api.setSessionChanged(() -> {
            try { if (!sessionVault.save(api.getBaseUrl(), api.exportSession())) sessionSaveFailed = true; }
            catch (Exception e) { sessionVault.clear(); sessionSaveFailed = true; }
        });
        if (preferences.getBoolean("auto_login", false)) {
            loginDestination = "forum";
            showLoginWaiting();
            io.execute(() -> {
                Exception failure = null;
                try {
                    if (!api.restoreSession(sessionVault.read(api.getBaseUrl()))) {
                        sessionVault.clear(); throw new ApiClient.ApiException(401, "请重新登录", false);
                    }
                    api.refreshSession();
                } catch (Exception e) { failure = e; }
                Exception result = failure;
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    finishLoginWaiting(); show(api.isLoggedIn() ? api.requiresPasswordChange() ? "account" : "forum" : "account");
                    if (result != null && !api.requiresPasswordChange()) failureBox(card(), FailureState.title(result), 120, null);
                });
            });
        } else loadScreen();
    }

    @Override protected void onResume() {
        super.onResume();
        if (updates != null) updates.resumePendingInstall();
        if (returnFromAdmin) { returnFromAdmin = false; loadScreen(); }
    }

    @Override protected void onDestroy() {
        ModalDialogs.close(this);
        if (updates != null) updates.close();
        io.shutdownNow();
        avatarIo.shutdownNow();
        super.onDestroy();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_AVATAR || resultCode != RESULT_OK || data == null || data.getData() == null) return;
        android.net.Uri uri = data.getData();
        String mime = getContentResolver().getType(uri);
        if (!"image/png".equals(mime) && !"image/jpeg".equals(mime) && !"image/webp".equals(mime)) {
            message("请选择 PNG、JPEG 或 WebP 图片。"); return;
        }
        io.execute(() -> {
            try (InputStream input = getContentResolver().openInputStream(uri);
                 ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                if (input == null) throw new IllegalStateException("无法读取所选图片。");
                byte[] buffer = new byte[8192]; int count;
                while ((count = input.read(buffer)) != -1) {
                    if (bytes.size() + count > 2 * 1024 * 1024) throw new IllegalArgumentException("头像图片不能超过 2 MB。");
                    bytes.write(buffer, 0, count);
                }
                api.uploadAvatar(bytes.toByteArray(), mime);
                runOnUiThread(() -> { message("头像已更新。"); loadScreen(); });
            } catch (Exception e) { runOnUiThread(() -> failureDialog(e)); }
        });
    }

    @Override public void onBackPressed() {
        if (loginBusy || composeBusy) { message("正在处理，请稍候…"); return; }
        if ("search".equals(screen)) { show(searchReturn); return; }
        if ("problem_detail".equals(screen)) { show("problems"); return; }
        if ("training".equals(screen) || "contests".equals(screen)) { show("account"); return; }
        if ("detail".equals(screen)) { show("forum"); return; }
        if ("account".equals(screen)) { show("mine"); return; }
        if ("member".equals(screen)) { show(memberReturnScreen); return; }
        if (!"forum".equals(screen)) { show("forum"); return; }
        super.onBackPressed();
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private GradientDrawable shape(int fill, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(radius));
        if (stroke != 0) drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private TextView label(String value, int sp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setLineSpacing(dp(2), 1f);
        if (bold) view.setTypeface(null, android.graphics.Typeface.BOLD);
        return view;
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    private void space(LinearLayout parent, int height) {
        View view = new View(this);
        parent.addView(view, new LinearLayout.LayoutParams(1, dp(height)));
    }

    private LinearLayout card() {
        LinearLayout box = column();
        box.setPadding(dp(16), dp(15), dp(16), dp(15));
        box.setBackground(shape(PANEL, 11, LINE));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(10);
        content.addView(box, params);
        return box;
    }

    private Button action(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextSize(13);
        button.setAllCaps(false);
        button.setTextColor(primary ? Color.WHITE : TEXT);
        button.setBackground(shape(primary ? TEXT : PANEL, 8, primary ? 0 : LINE));
        button.setMinHeight(dp(44));
        return button;
    }

    private void buildShell() {
        root = column();
        root.setFocusableInTouchMode(true);
        root.requestFocus();
        root.setBackgroundColor(BACKGROUND);
        if (Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                view.setPadding(0, bars.top, 0, bars.bottom);
                return insets;
            });
        } else {
            root.setFitsSystemWindows(true);
        }
        setContentView(root);

        LinearLayout header = row();
        header.setPadding(dp(14), dp(10), dp(14), dp(10));
        header.setBackgroundColor(PANEL);
        root.addView(header, new LinearLayout.LayoutParams(-1, dp(64)));

        headerAvatar = avatarButton(44);
        headerAvatar.setContentDescription("进入账号设置");
        headerAvatar.setOnClickListener(view -> show("account"));
        header.addView(headerAvatar, new LinearLayout.LayoutParams(dp(44), dp(44)));

        search = new EditText(this);
        search.setSingleLine(true);
        search.setTextSize(13);
        search.setHint("搜索论坛话题");
        search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        search.setBackground(shape(BACKGROUND, 9, LINE));
        search.setPadding(dp(13), 0, dp(13), 0);
        search.setOnFocusChangeListener((v, focused) -> { if (focused) openSearch(); });
        search.setOnClickListener(v -> openSearch());
        search.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                submitSearch(search.getText().toString());
                return true;
            }
            return false;
        });
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(0, dp(44), 1);
        searchParams.leftMargin = dp(9);
        searchParams.rightMargin = dp(9);
        header.addView(search, searchParams);

        ImageButton tools = new ImageButton(this);
        tools.setImageResource(R.drawable.ic_add);
        tools.setScaleType(ImageButton.ScaleType.CENTER_INSIDE);
        tools.setPadding(dp(8), dp(8), dp(8), dp(8));
        tools.setBackground(shape(PANEL, 9, LINE));
        tools.setContentDescription("打开常用工具");
        tools.setOnClickListener(this::showTools);
        header.addView(tools, new LinearLayout.LayoutParams(dp(40), dp(40)));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content = column();
        content.setPadding(dp(14), dp(16), dp(14), dp(24));
        scroll.addView(content);

        nav = row();
        nav.setBackgroundColor(PANEL);
        nav.setPadding(dp(3), dp(5), dp(3), dp(5));
        root.addView(nav, new LinearLayout.LayoutParams(-1, dp(65)));
        refreshNav();
    }

    private void refreshNav() {
        nav.removeAllViews();
        String[] ids = {"forum", "rank", "compose", "problems", "mine"};
        String[] names = {"▦\n主页", "♛\n排名", "＋", "⌘\n题库", "◉\n个人中心"};
        for (int i = 0; i < ids.length; i++) {
            String id = ids[i];
            boolean compose = "compose".equals(id);
            TextView item = label(names[i], compose ? 26 : 12,
                    compose ? Color.WHITE : id.equals(screen) ? BRAND : MUTED, id.equals(screen));
            item.setGravity(Gravity.CENTER);
            item.setOnClickListener(view -> show(id));
            if (compose) {
                item.setContentDescription("发布话题");
                item.setBackground(shape("compose".equals(screen) ? TEXT : BRAND, 24, 0));
                LinearLayout holder = column();
                holder.setGravity(Gravity.CENTER);
                holder.setOnClickListener(view -> show("compose"));
                holder.addView(item, new LinearLayout.LayoutParams(dp(46), dp(46)));
                nav.addView(holder, new LinearLayout.LayoutParams(0, -1, 1));
            } else nav.addView(item, new LinearLayout.LayoutParams(0, -1, 1));
        }
    }

    private JSONArray searchHistory() {
        try { return new JSONArray(preferences.getString("search_history", "[]")); }
        catch (Exception e) { return new JSONArray(); }
    }

    private void openSearch() {
        if (loginBusy || !java.util.Arrays.asList("forum", "rank", "problems").contains(screen)) return;
        searchScope = screen; searchReturn = screen;
        screen = "search"; ++requestSerial; refreshNav();
        content.removeAllViews(); renderSearch();
    }

    private void submitSearch(String value) {
        String term = value.trim();
        if (term.isEmpty()) { message("请输入搜索内容"); return; }
        if (!"search".equals(screen)) searchScope = screen;
        if (!java.util.Arrays.asList("forum", "rank", "problems").contains(searchScope)) return;
        if (preferences.getBoolean("record_search", true)) {
            JSONArray history = searchHistory(), next = new JSONArray(); next.put(term);
            for (int i = 0; i < history.length() && next.length() < 10; i++)
                if (!term.equals(history.optString(i))) next.put(history.optString(i));
            preferences.edit().putString("search_history", next.toString()).apply();
        }
        query = term; page = 1; screen = searchScope; search.setText(term);
        root.requestFocus();
        ((android.view.inputmethod.InputMethodManager) getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(search.getWindowToken(), 0);
        refreshNav(); loadScreen();
    }

    private void renderSearch() {
        content.removeAllViews();
        heading("SEARCH", "搜索" + ("rank".equals(searchScope) ? "排名" : "problems".equals(searchScope) ? "题库" : "话题"), "输入关键词后点击搜索，或点选历史搜索。");
        Button go = action("搜索", true); go.setOnClickListener(v -> submitSearch(search.getText().toString())); content.addView(go);
        LinearLayout history = card(); history.addView(label("最近 10 条搜索", 17, TEXT, true));
        JSONArray terms = searchHistory();
        if (terms.length() == 0) history.addView(label("暂无历史搜索", 13, MUTED, false));
        for (int i = 0; i < terms.length(); i += 2) {
            LinearLayout line = row(); history.addView(line);
            for (int j = i; j < Math.min(i + 2, terms.length()); j++) {
                String term = terms.optString(j); Button chip = action(term, false);
                chip.setOnClickListener(v -> submitSearch(term));
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1); params.setMargins(dp(3), dp(4), dp(3), dp(4)); line.addView(chip, params);
            }
        }
        Button records = action("历史记录", false); records.setOnClickListener(v -> showSearchRecords()); content.addView(records);
        Button settings = action("历史记录设置", false); settings.setOnClickListener(v -> {
            CheckBox record = new CheckBox(this); record.setText("记录搜索历史（仅保存在此设备，最多 10 条）"); record.setChecked(preferences.getBoolean("record_search", true));
            new ModalDialogs.Builder(this).setTitle("历史记录设置").setView(record)
                    .setNeutralButton("清空记录", (d, w) -> { preferences.edit().remove("search_history").apply(); renderSearch(); })
                    .setNegativeButton("取消", null).setPositiveButton("保存", (d, w) -> preferences.edit().putBoolean("record_search", record.isChecked()).apply()).show();
        }); content.addView(settings);
        Button cancel = action("取消搜索", false); cancel.setOnClickListener(v -> { root.requestFocus(); show(searchReturn); }); content.addView(cancel);
    }

    private void showSearchRecords() {
        JSONArray history = searchHistory(); String[] labels = new String[history.length()];
        for (int i = 0; i < history.length(); i++) labels[i] = history.optString(i);
        AlertDialog.Builder dialog = new ModalDialogs.Builder(this).setTitle("历史记录 · 点击删除单条").setNegativeButton("关闭", null);
        if (labels.length == 0) dialog.setMessage("暂无历史搜索");
        else dialog.setItems(labels, (d, which) -> {
            JSONArray next = new JSONArray(); for (int i = 0; i < history.length(); i++) if (i != which) next.put(history.optString(i));
            preferences.edit().putString("search_history", next.toString()).apply(); renderSearch();
        });
        dialog.show();
    }

    private void show(String next) {
        if (loginBusy || composeBusy) return;
        if ("compose".equals(screen) && !"compose".equals(next) && !leaveComposeOnce
                && composeRevision != composeSavedRevision && api.isLoggedIn()) {
            new ModalDialogs.Builder(this).setTitle("草稿尚未保存")
                    .setMessage("保存到账号后可在其他设备继续编辑。")
                    .setNegativeButton("继续编辑", null)
                    .setNeutralButton("暂不保存", (d, w) -> { leaveComposeOnce = true; show(next); })
                    .setPositiveButton("保存并离开", (d, w) -> saveComposer(() -> show(next))).show();
            return;
        }
        leaveComposeOnce = false;
        if (forumFilterDialog != null) forumFilterDialog.dismiss();
        screen = next;
        query = "";
        page = 1;
        search.setText("");
        search.setEnabled(java.util.Arrays.asList("forum", "rank", "problems").contains(next));
        String hint = "搜索论坛话题";
        if ("rank".equals(next)) hint = "搜索公开昵称";
        if ("problems".equals(next)) hint = "搜索题名或标签";
        if ("mine".equals(next)) hint = "个人中心";
        if ("account".equals(next)) hint = "账号设置";
        if ("member".equals(next)) hint = "成员主页";
        if ("compose".equals(next)) hint = "发帖编辑";
        search.setHint(hint);
        refreshNav();
        loadScreen();
    }

    private void loadScreen() {
        if (loginBusy) return;
        int serial = ++requestSerial;
        if (!api.isLoggedIn()) headerAvatar.setImageResource(android.R.drawable.ic_menu_myplaces);
        content.removeAllViews();
        loadingRegion = null;
        publicFailure = null;
        publishedFailure = null;
        mottoFailure = null;
        if ("search".equals(screen)) renderSearch();
        else if ("forum".equals(screen)) renderForum(serial);
        else if ("rank".equals(screen)) renderRank(serial);
        else if ("problems".equals(screen)) renderProblems(serial);
        else if ("compose".equals(screen)) renderCompose(serial);
        else if ("detail".equals(screen)) renderDetail(serial);
        else if ("account".equals(screen)) renderAccount(serial);
        else if ("member".equals(screen)) renderMember(serial);
        else if ("problem_detail".equals(screen)) renderProblemDetail(serial);
        else if ("training".equals(screen)) renderTraining(serial);
        else if ("contests".equals(screen)) renderContests();
        else renderMine(serial);
    }

    private void heading(String eyebrow, String title, String subtitle) {
        if (!query.isEmpty() && java.util.Arrays.asList("forum", "rank", "problems").contains(screen)) {
            subtitle = "关键词：" + query + "\n" + subtitle;
            title = "搜索结果 · " + title;
        }
        LinearLayout box = card();
        box.setBackground(shape(Color.rgb(220, 235, 220), 9, 0));
        box.addView(label(eyebrow, 11, BRAND, true));
        space(box, 4);
        box.addView(label(title, 23, TEXT, true));
        space(box, 4);
        box.addView(label(subtitle, 12, MUTED, false));
    }

    private void status(String message) {
        LinearLayout box = card();
        box.addView(label(message, 13, MUTED, false));
    }

    private boolean networkAvailable() {
        android.net.ConnectivityManager manager = (android.net.ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        android.net.NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    private Exception connectionFailure() {
        return !networkAvailable() ? new ApiClient.NoNetworkException() : new ApiClient.UnconfiguredException();
    }

    private void loading(String text) {
        loadingRegion = card();
        loadingRegion.setMinimumHeight(dp("compose".equals(screen) ? 600 : 320));
        loadingRegion.setGravity(Gravity.CENTER);
        loadingRegion.addView(label(text, 13, MUTED, false));
    }

    private void failureBox(LinearLayout box, String reason, int height, Runnable retry) {
        int retainedHeight = Math.max(dp(height), box.getHeight());
        box.removeAllViews();
        box.setMinimumHeight(retainedHeight);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(16), dp(16), dp(16), dp(16));
        box.setBackground(shape(Color.rgb(255, 244, 244), 10, Color.rgb(204, 57, 57)));
        TextView title = label(reason, 15, Color.rgb(183, 35, 35), true);
        title.setGravity(Gravity.CENTER);
        title.setContentDescription(reason);
        box.addView(title);
        if (retry != null) {
            space(box, 12);
            Button button = action("重试", false);
            button.setOnClickListener(v -> retry.run());
            box.addView(button, new LinearLayout.LayoutParams(dp(100), dp(44)));
        }
    }

    private void error(Exception failure) {
        if (loadingRegion == null || loadingRegion.getParent() != content) loadingRegion = card();
        failureBox(loadingRegion, FailureState.title(failure), "compose".equals(screen) ? 600 : 320, this::loadScreen);
    }

    private void failureDialog(Exception failure) {
        LinearLayout box = column();
        failureBox(box, FailureState.title(failure), 180, null);
        new ModalDialogs.Builder(this).setView(box).setPositiveButton("关闭", null).show();
    }

    private void chips(String[] labels, String[] values, String selected, java.util.function.Consumer<String> onChoose) {
        HorizontalScrollView scrolling = new HorizontalScrollView(this);
        scrolling.setHorizontalScrollBarEnabled(false);
        LinearLayout line = row();
        for (int i = 0; i < labels.length; i++) {
            String value = values[i];
            TextView chip = label(labels[i], 12, selected.equals(value) ? TEXT : MUTED, selected.equals(value));
            chip.setGravity(Gravity.CENTER);
            chip.setPadding(dp(13), 0, dp(13), 0);
            chip.setBackground(shape(selected.equals(value) ? Color.rgb(231, 240, 196) : PANEL, 20, LINE));
            chip.setOnClickListener(view -> onChoose.accept(value));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(36));
            params.rightMargin = dp(8);
            line.addView(chip, params);
        }
        scrolling.addView(line);
        content.addView(scrolling);
        space(content, 12);
    }

    private void renderForum(int serial) {
        forumHeader(null);
        loading("正在加载社区话题…");
        io.execute(() -> {
            try {
                String suffix = "?page=" + page + "&page_size=12&sort=" + sort
                        + "&q=" + encode(query) + "&category=" + encode(category);
                JSONObject result = api.getObject(api.publicPostsPath(suffix));
                result.getJSONArray("rows");
                runOnUiThread(() -> { if (serial == requestSerial) showForum(null, result); });
            } catch (Exception e) {
                runOnUiThread(() -> { if (serial == requestSerial) error(e); });
            }
        });
    }

    private void showForum(JSONArray categories, JSONObject result) {
        content.removeAllViews();
        forumHeader(categories);

        JSONArray rows = result.optJSONArray("rows");
        if (rows == null || rows.length() == 0) status("这里还没有话题，试试其他分类或关键词。");
        else for (int i = 0; i < rows.length(); i++) addPost(rows.optJSONObject(i));
        int total = result.optInt("total", 0);
        if (total > 0) addPager(total, 12);
    }

    private void forumHeader(JSONArray categories) {
        heading("ACMforever · 打一辈子爱臭美", "今天想聊点什么？", "提问、分享题解，记录每一步进步。");
        LinearLayout titleRow = row();
        titleRow.addView(label("社区话题", 18, TEXT, true), new LinearLayout.LayoutParams(0, -2, 1));
        ImageButton filter = new ImageButton(this);
        filter.setImageResource(R.drawable.ic_filter);
        filter.setScaleType(ImageButton.ScaleType.CENTER_INSIDE);
        filter.setPadding(dp(10), dp(10), dp(10), dp(10));
        filter.setBackground(shape(!category.isEmpty() || !"latest".equals(sort)
                ? Color.rgb(231, 240, 196) : PANEL, 9, LINE));
        filter.setContentDescription("筛选社区话题");
        filter.setOnClickListener(view -> {
            if (filterLoading || forumFilterDialog != null && forumFilterDialog.isShowing()) return;
            if (categories != null) { showForumFilters(categories); return; }
            filterLoading = true;
            int serial = requestSerial;
            io.execute(() -> {
                try {
                    JSONArray options = api.getArray("/api/forum/categories");
                    runOnUiThread(() -> { filterLoading = false; if (serial == requestSerial && "forum".equals(screen)) showForumFilters(options); });
                } catch (Exception e) { runOnUiThread(() -> { filterLoading = false; if (serial == requestSerial) failureDialog(e); }); }
            });
        });
        titleRow.addView(filter, new LinearLayout.LayoutParams(dp(44), dp(44)));
        content.addView(titleRow);
        space(content, 10);
    }

    private void showForumFilters(JSONArray categories) {
        if (forumFilterDialog != null && forumFilterDialog.isShowing()) return;
        LinearLayout form = column();
        form.setPadding(dp(22), dp(4), dp(22), 0);
        form.addView(label("话题分类", 14, TEXT, true));
        RadioGroup categoryGroup = new RadioGroup(this);
        String[] categoryValues = new String[categories.length() + 1];
        categoryValues[0] = "";
        RadioButton[] categoryButtons = new RadioButton[categoryValues.length];
        categoryButtons[0] = filterChoice("全部", category.isEmpty());
        categoryGroup.addView(categoryButtons[0]);
        for (int i = 0; i < categories.length(); i++) {
            JSONObject item = categories.optJSONObject(i);
            String name = item == null ? "分类" : item.optString("name", "分类");
            String slug = item == null ? "" : item.optString("slug", "");
            categoryValues[i + 1] = slug;
            categoryButtons[i + 1] = filterChoice(name, category.equals(slug));
            categoryGroup.addView(categoryButtons[i + 1]);
        }
        form.addView(categoryGroup);
        space(form, 10);
        form.addView(label("排序方式", 14, TEXT, true));
        String[] sortValues = {"latest", "hot", "unanswered"};
        String[] sortNames = {"最新", "热门", "待回答"};
        RadioGroup sortGroup = new RadioGroup(this);
        RadioButton[] sortButtons = new RadioButton[sortValues.length];
        for (int i = 0; i < sortValues.length; i++) {
            sortButtons[i] = filterChoice(sortNames[i], sort.equals(sortValues[i]));
            sortGroup.addView(sortButtons[i]);
        }
        form.addView(sortGroup);
        ScrollView scrolling = new ScrollView(this);
        scrolling.addView(form);
        forumFilterDialog = new ModalDialogs.Builder(this).setTitle("筛选社区话题").setView(scrolling)
                .setNegativeButton("取消", null)
                .setPositiveButton("应用筛选", (dialog, which) -> {
                    for (int i = 0; i < categoryButtons.length; i++)
                        if (categoryButtons[i].isChecked()) category = categoryValues[i];
                    for (int i = 0; i < sortButtons.length; i++)
                        if (sortButtons[i].isChecked()) sort = sortValues[i];
                    page = 1;
                    loadScreen();
                }).create();
        forumFilterDialog.setOnDismissListener(d -> forumFilterDialog = null);
        ModalDialogs.show(forumFilterDialog);
    }

    private RadioButton filterChoice(String name, boolean selected) {
        RadioButton option = new RadioButton(this);
        option.setId(View.generateViewId());
        option.setText(name);
        option.setTextColor(TEXT);
        option.setTextSize(14);
        option.setMinHeight(dp(44));
        option.setChecked(selected);
        return option;
    }

    private void addPost(JSONObject post) {
        if (post == null) return;
        LinearLayout box = card();
        box.addView(label(post.optString("category_name", "话题"), 11, BRAND, true));
        space(box, 7);
        box.addView(label(post.optString("title"), 16, TEXT, true));
        space(box, 6);
        box.addView(label(post.optString("excerpt"), 12, MUTED, false));
        space(box, 10);
        LinearLayout authorRow = row();
        ImageButton avatar = avatarButton(32);
        avatar.setContentDescription("查看" + value(post, "author_name", "ACM 成员") + "的公开主页");
        avatar.setOnClickListener(view -> openMember(post, "forum"));
        loadAvatar(avatar, value(post, "author_avatar_url", ""));
        authorRow.addView(avatar, new LinearLayout.LayoutParams(dp(32), dp(32)));
        TextView author = label("  " + post.optString("author_name", "ACM 成员") + "  ·  查看公开主页", 11, BRAND, true);
        author.setMinHeight(dp(40)); author.setGravity(Gravity.CENTER_VERTICAL);
        author.setOnClickListener(view -> openMember(post, "forum"));
        authorRow.addView(author, new LinearLayout.LayoutParams(0, -2, 1));
        box.addView(authorRow);
        box.addView(label(post.optInt("comments_count") + " 评论  ·  " + post.optInt("likes_count") + " 赞", 11, MUTED, false));
        int id = post.optInt("id");
        box.setOnClickListener(view -> { postId = id; screen = "detail"; loadScreen(); });
    }

    private void renderDetail(int serial) {
        loading("正在加载话题详情…");
        io.execute(() -> {
            try {
                JSONObject result = api.getObject(api.publicPostsPath("/" + postId));
                runOnUiThread(() -> { if (serial == requestSerial) showDetail(result); });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showDetail(JSONObject post) {
        content.removeAllViews();
        Button back = action("← 返回论坛", false);
        back.setOnClickListener(view -> show("forum"));
        content.addView(back);
        space(content, 10);
        LinearLayout box = card();
        box.addView(label(post.optString("category_name", "话题"), 11, BRAND, true));
        space(box, 8);
        box.addView(label(post.optString("title"), 22, TEXT, true));
        space(box, 8);
        TextView author = label(post.optString("author_name", "ACM 成员") + " · " + date(post.optLong("created_at")), 12, BRAND, true);
        author.setOnClickListener(v -> openMember(post, "forum")); box.addView(author);
        space(box, 16);
        box.addView(new ContentView(this, post.optString("body"), false, this::openBrowser));
        box.addView(label(post.optInt("views_count") + " 阅读", 12, MUTED, false));
        LinearLayout actions = row();
        Button like = action((post.optBoolean("viewer_liked") ? "♥ " : "♡ ") + post.optInt("likes_count") + " 赞", false);
        Button bookmark = action(post.optBoolean("viewer_bookmarked") ? "★ 已收藏" : "☆ 收藏", false);
        Button report = action("举报", false);
        like.setOnClickListener(v -> forumAction(like, "like", "", 0));
        bookmark.setOnClickListener(v -> forumAction(bookmark, "bookmark", "", 0));
        report.setOnClickListener(v -> {
            if (!requireLogin("detail")) return;
            EditText reason = new EditText(this); reason.setHint("请说明举报原因（3–500 字）");
            new ModalDialogs.Builder(this).setTitle("举报话题").setView(reason).setNegativeButton("取消", null)
                    .setPositiveButton("提交", (d, w) -> {
                        String text = reason.getText().toString().trim();
                        if (text.codePointCount(0, text.length()) < 3 || text.codePointCount(0, text.length()) > 500) { message("举报原因需要 3–500 字。"); return; }
                        forumAction(report, "report", text, 0);
                    }).show();
        });
        actions.addView(like, new LinearLayout.LayoutParams(0, dp(44), 1));
        actions.addView(bookmark, new LinearLayout.LayoutParams(0, dp(44), 1));
        actions.addView(report, new LinearLayout.LayoutParams(0, dp(44), 1));
        box.addView(actions);
        if (commentPostId != postId) { commentPostId = postId; commentBody = ""; commentParent = 0; }
        space(content, 9);
        content.addView(label("讨论区", 18, TEXT, true));
        LinearLayout editor = card();
        EditText input = new EditText(this); input.setMinLines(3); input.setGravity(Gravity.TOP);
        input.setHint("写下你的问题、想法或补充（2–5000 字）");
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(5000)});
        input.setText(commentBody); input.addTextChangedListener(watch(value -> commentBody = value));
        editor.addView(input);
        TextView replyTo = label(commentParent > 0 ? "正在回复评论 #" + commentParent + " · 点击取消回复" : "发布新的评论", 12, BRAND, true);
        replyTo.setOnClickListener(v -> { commentParent = 0; replyTo.setText("发布新的评论"); }); editor.addView(replyTo);
        Button send = action("发布评论", true);
        send.setOnClickListener(v -> {
            String text = input.getText().toString().trim();
            if (text.codePointCount(0, text.length()) < 2 || text.codePointCount(0, text.length()) > 5000) { message("评论需要 2–5000 字。"); return; }
            forumAction(send, "comments", text, commentParent);
        }); editor.addView(send);
        JSONArray comments = post.optJSONArray("comments");
        if (comments == null || comments.length() == 0) status("暂无已发布评论。");
        else for (int i = 0; i < comments.length(); i++) {
            JSONObject comment = comments.optJSONObject(i);
            if (comment == null) continue;
            LinearLayout item = card();
            item.addView(label(comment.optString("author_name", "ACM 成员") + " · " + date(comment.optLong("created_at")), 12, BRAND, true));
            if (comment.optInt("parent_id") > 0) item.addView(label("↳ 回复评论 #" + comment.optInt("parent_id"), 11, MUTED, false));
            item.addView(label(comment.optString("body"), 13, TEXT, false));
            if (comment.optInt("parent_id") == 0) {
                Button reply = action("回复", false);
                reply.setOnClickListener(v -> {
                    if (!requireLogin("detail")) return;
                    commentParent = comment.optInt("id"); replyTo.setText("正在回复 " + comment.optString("author_name") + " · 点击取消回复");
                    input.requestFocus();
                    ((ScrollView) content.getParent()).smoothScrollTo(0, editor.getTop());
                    ((android.view.inputmethod.InputMethodManager) getSystemService(INPUT_METHOD_SERVICE)).showSoftInput(input, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);
                }); item.addView(reply);
            }
        }
    }

    private String date(long seconds) {
        return seconds > 0 ? new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.CHINA).format(new java.util.Date(seconds * 1000L)) : "";
    }

    private boolean requireLogin(String destination) {
        if (api.isLoggedIn()) return true;
        loginDestination = destination;
        new ModalDialogs.Builder(this).setMessage("请先登录后继续操作。")
                .setNegativeButton("取消", null).setPositiveButton("前往登录", (d, w) -> show("account")).show();
        return false;
    }

    @FunctionalInterface private interface ApiWork { void run() throws Exception; }

    private void mutate(Button button, ApiWork work, Runnable success) {
        if (actionBusy) return;
        actionBusy = true; int serial = requestSerial;
        CharSequence title = button.getText(); button.setEnabled(false); button.setText("处理中…");
        io.execute(() -> {
            Exception failure = null;
            try { work.run(); } catch (Exception e) { failure = e; }
            Exception error = failure;
            runOnUiThread(() -> {
                actionBusy = false;
                if (isFinishing() || isDestroyed()) return;
                button.setEnabled(true); button.setText(title);
                if (serial != requestSerial) return;
                if (error == null) success.run(); else failureDialog(error);
            });
        });
    }

    private void forumAction(Button button, String kind, String text, int parent) {
        if (!requireLogin("detail")) return;
        int target = postId;
        mutate(button, () -> api.postAction(target, kind, text, parent), () -> {
            if ("report".equals(kind)) message("举报已提交，等待管理员核查。");
            else {
                if ("comments".equals(kind)) { commentBody = ""; commentParent = 0; }
                loadScreen();
            }
        });
    }

    private void renderRank(int serial) {
        rankHeader();
        loading("正在加载排名…");
        final String range=days, ordering=rankSort, selectedPlatforms=String.join(",",rankPlatforms), searchText=query;
        final int requestedPage=page, size=rankPageSize;
        io.execute(() -> {
            try {
                JSONObject result = api.leaderboard(range, ordering, selectedPlatforms, searchText, requestedPage, size);
                result.getJSONArray("rows");
                runOnUiThread(() -> { if (serial == requestSerial) showRank(result); });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void rankHeader(){
        heading("KEEP CLIMBING", "社区排名", "today".equals(days)?"北京时间当日 00:00 起 · 不含 0 AC 成员":"公开昵称与各平台去重 AC 题数 · 不含 0 AC 成员");
        chips(new String[]{"当日", "近 7 日", "近 30 日", "近 90 日", "近 1 年", "生涯"}, new String[]{"today", "7", "30", "90", "365", "all"}, days,
                value -> { if(days.equals(value))return;days = value; page = 1; loadScreen(); });
        Button filter = action("平台与排序筛选", false); filter.setOnClickListener(v -> showRankFilter()); content.addView(filter);
    }

    private void showRank(JSONObject result) {
        content.removeAllViews();
        page=result.optInt("page",1);
        rankHeader();

        JSONArray rows = result.optJSONArray("rows");
        if (rows == null || rows.length() == 0) status("暂无符合条件的成员。");
        else for (int i = 0; i < rows.length(); i++) {
            JSONObject user = rows.optJSONObject(i);
            if (user == null || user.optInt("total_count")<=0) continue;
            LinearLayout box = card();
            LinearLayout identity = row();
            ImageButton avatar = avatarButton(36);
            avatar.setContentDescription("查看" + value(user, "name", "ACM 成员") + "的公开主页");
            avatar.setOnClickListener(view -> openMember(user, "rank"));
            loadAvatar(avatar, value(user, "avatar_url", ""));
            identity.addView(avatar, new LinearLayout.LayoutParams(dp(36), dp(36)));
            identity.addView(label("  #" + ((page - 1) * rankPageSize + i + 1) + " " + user.optString("name", "ACM 成员"), 16, TEXT, true));
            box.addView(identity);
            space(box, 5);
            box.addView(label(user.optString("status", "") + "  ·  CF " + user.optInt("cf_count")
                    + "  ·  洛谷 " + user.optInt("luogu_count"), 12, MUTED, false));
            box.addView(label("AtCoder " + user.optInt("atcoder_count") + " · 牛客 " + user.optInt("nowcoder_count") + " · 校 OJ " + user.optInt("cjlu_count"), 12, MUTED, false));
            space(box, 4);
            box.addView(label("总 AC  " + user.optInt("total_count"), 17, BRAND, true));
            box.setOnClickListener(view -> openMember(user, "rank"));
        }
        addRankPager(result.optInt("total"));
    }

    private void renderProblems(int serial) {
        heading("PROBLEM BANK", "题库", "找一道适合今天的题，继续向 AC 前进。");
        if (api.isUnconfigured()) { error(connectionFailure()); return; }
        if (!api.isLoggedIn()) {
            failureBox(card(), "未登录", 320, null);
            Button login = action("进入账号设置登录", true);
            login.setOnClickListener(view -> { loginDestination = "problems"; show("account"); });
            content.addView(login);
            return;
        }
        loading("正在加载题库…");
        io.execute(() -> {
            try {
                String path = "/api/me/problems?page=" + page + "&page_size=20&platform="
                        + encode(platform) + "&tag=" + encode(query) + "&state=" + problemState;
                JSONObject result = api.getObject(path);
                result.getJSONArray("items");
                runOnUiThread(() -> { if (serial == requestSerial) showProblems(result); });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showProblems(JSONObject result) {
        content.removeAllViews();
        heading("PROBLEM BANK", "题库", "找一道适合今天的题，继续向 AC 前进。");
        chips(new String[]{"全部", "Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"},
                new String[]{"", "codeforces", "luogu", "atcoder", "nowcoder", "cjlu"}, platform,
                value -> { platform = value; page = 1; loadScreen(); });
        chips(new String[]{"全部题目", "已收藏"}, new String[]{"", "favorite"}, problemState, value -> { problemState = value; page = 1; loadScreen(); });
        content.addView(label("共 " + result.optInt("total") + " 道题目", 12, MUTED, false));

        JSONArray items = result.optJSONArray("items");
        if (items == null || items.length() == 0) status("没有符合条件的题目。");
        else for (int i = 0; i < items.length(); i++) {
            JSONObject problem = items.optJSONObject(i);
            if (problem == null) continue;
            LinearLayout box = card();
            box.addView(label(problem.optString("problem_name", problem.optString("problem_id", "题目")), 16, TEXT, true));
            space(box, 5);
            box.addView(label(problem.optString("platform") + "  ·  " + problem.optString("problem_rating", "难度未知"), 12, BRAND, true));
            box.addView(label(problem.optString("tags", ""), 12, MUTED, false));
            Button detail = action("查看题面与样例", true);
            detail.setOnClickListener(v -> { selectedProblem = problem; screen = "problem_detail"; loadScreen(); }); box.addView(detail);
            Button favorite = action(problem.optBoolean("is_favorite") ? "★ 已收藏 · 取消" : "☆ 收藏", false);
            favorite.setOnClickListener(v -> mutate(favorite, () -> api.favoriteProblem(problem.getString("platform"), problem.getString("problem_id"), !problem.optBoolean("is_favorite")), this::loadScreen));
            box.addView(favorite);
        }
        addPager(result.optInt("total"), 20);
    }

    private void showRankFilter() {
        if(popupLoading||ModalDialogs.isShowing(this))return;
        LinearLayout form = column(); form.setPadding(dp(20), 0, dp(20), 0);
        form.addView(label("统计平台（至少选择一个）", 14, TEXT, true));
        String[] values = {"codeforces", "luogu", "atcoder", "nowcoder", "cjlu"};
        String[] names = {"Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"};
        android.widget.CheckBox[] checks = new android.widget.CheckBox[values.length];
        for (int i = 0; i < values.length; i++) {
            checks[i] = new android.widget.CheckBox(this); checks[i].setText(names[i]);
            checks[i].setChecked(rankPlatforms.contains(values[i])); form.addView(checks[i]);
        }
        form.addView(label("排序方式", 14, TEXT, true));
        String[] sorts = {"total_count", "cf_count", "luogu_count", "atcoder_count", "nowcoder_count", "cjlu_count"};
        Spinner ordering = spinner(new String[]{"总 AC 数", "Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"});
        ordering.setSelection(java.util.Arrays.asList(sorts).indexOf(rankSort)); form.addView(ordering);
        AlertDialog dialog = new ModalDialogs.Builder(this).setTitle("排名筛选").setView(form).setNegativeButton("取消", null).setPositiveButton("应用", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            java.util.LinkedHashSet<String> selected = new java.util.LinkedHashSet<>();
            for (int i = 0; i < values.length; i++) if (checks[i].isChecked()) selected.add(values[i]);
            if (selected.isEmpty()) { message("至少选择一个平台。"); return; }
            rankPlatforms.clear(); rankPlatforms.addAll(selected); rankSort = sorts[ordering.getSelectedItemPosition()];
            dialog.dismiss(); page = 1; loadScreen();
        })); ModalDialogs.show(dialog);
    }

    private Spinner spinner(String[] names) {
        Spinner result = new Spinner(this);
        ArrayAdapter<String> options = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, names);
        options.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item); result.setAdapter(options);
        result.setMinimumHeight(dp(48)); return result;
    }

    private void renderProblemDetail(int serial) {
        if (selectedProblem == null) { show("problems"); return; }
        loading("正在加载题面与样例…");
        JSONObject selected = selectedProblem;
        io.execute(() -> {
            try {
                JSONObject problem = api.getObject(ApiClient.problemPath(selected.getString("platform"), selected.getString("problem_id")));
                runOnUiThread(() -> { if (serial == requestSerial) showProblemDetail(problem, selected); });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showProblemDetail(JSONObject problem, JSONObject selected) {
        content.removeAllViews();
        Button back = action("← 返回题库", false); back.setOnClickListener(v -> show("problems")); content.addView(back);
        heading("PROBLEM", value(problem, "problem_name", problem.optString("problem_id")), problem.optString("platform") + " · " + value(problem, "problem_rating", "难度未知"));
        LinearLayout box = card();
        if (problem.optBoolean("content_available")) {
            String html = value(problem, "statement_html", "");
            String source = html.isEmpty() ? value(problem, "statement_text", "") : html;
            box.addView(new ContentView(this, source, !html.isEmpty(), this::openBrowser));
        } else box.addView(label("题库已有目录，题面与样例尚未采集；可先打开原题。", 14, MUTED, false));
        JSONArray samples = problem.optJSONArray("samples");
        if (samples != null) for (int i = 0; i < samples.length(); i++) {
            JSONObject sample = samples.optJSONObject(i); if (sample == null) continue;
            LinearLayout sampleBox = card(); sampleBox.addView(label("样例 " + (i + 1), 16, TEXT, true));
            sampleValue(sampleBox, "输入", sample.optString("input")); sampleValue(sampleBox, "输出", sample.optString("output"));
        }
        LinearLayout actions = card();
        Button favorite = action(selected.optBoolean("is_favorite") ? "★ 已收藏 · 取消" : "☆ 收藏题目", false);
        favorite.setOnClickListener(v -> {
            boolean next = !selected.optBoolean("is_favorite");
            mutate(favorite, () -> api.favoriteProblem(problem.getString("platform"), problem.getString("problem_id"), next), () -> {
                try { selected.put("is_favorite", next); } catch (org.json.JSONException ignored) { }
                favorite.setText(next ? "★ 已收藏 · 取消" : "☆ 收藏题目");
            });
        }); actions.addView(favorite);
        String url = value(problem, "problem_url", "");
        if (!url.isEmpty()) { Button original = action("在 App 内打开原题", true); original.setOnClickListener(v -> openBrowser(url)); actions.addView(original); }
    }

    private void sampleValue(LinearLayout box, String title, String text) {
        box.addView(label(title, 12, BRAND, true));
        TextView value = label(text, 13, TEXT, false); value.setTypeface(android.graphics.Typeface.MONOSPACE); value.setTextIsSelectable(true); box.addView(value);
        Button copy = action("复制" + title, false);
        copy.setOnClickListener(v -> {
            ((android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(android.content.ClipData.newPlainText(title, text));
            android.widget.Toast.makeText(this, "已复制" + title, android.widget.Toast.LENGTH_SHORT).show();
        }); box.addView(copy);
    }

    private void renderTraining(int serial) {
        heading("MY TRAINING", "今日训练", "只访问本人训练记录；按相邻难度生成三个训练区。");
        if (!requireLogin("training")) return;
        LinearLayout summary = card(); summary.addView(label("正在读取训练统计…",13,MUTED,false));
        io.execute(() -> {
            try {
                JSONObject data = api.getObject("/api/me/training/summary");
                int streak = data.getInt("streak_days"), active = data.getInt("active_days");
                runOnUiThread(() -> { if (serial == requestSerial) { summary.removeAllViews(); summary.addView(label("连续 " + streak + " 天 · 近一年活跃 " + active + " 天",16,BRAND,true)); } });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) failureBox(summary,FailureState.title(e),100,null); }); }
        });
        LinearLayout form = card();
        String[] platforms = {"", "codeforces", "luogu", "atcoder", "nowcoder"};
        Spinner platformChoice = spinner(new String[]{"全部平台", "Codeforces", "洛谷", "AtCoder", "牛客"}); form.addView(platformChoice);
        EditText tag = new EditText(this); tag.setHint("算法标签、题名或题号（可选）"); form.addView(tag);
        android.widget.CheckBox weak = new android.widget.CheckBox(this); weak.setText("按我的弱项训练"); form.addView(weak);
        Spinner difficulty = spinner(new String[]{"不限难度"}); form.addView(difficulty);
        platformChoice.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                java.util.List<String> values = trainingDifficulties(platforms[position]);
                ArrayAdapter<String> adapter = new ArrayAdapter<>(MainActivity.this, android.R.layout.simple_spinner_dropdown_item, values);
                difficulty.setAdapter(adapter);
                difficulty.setSelection("codeforces".equals(platforms[position]) ? 2 : "atcoder".equals(platforms[position]) ? 8 : "luogu".equals(platforms[position]) ? 2 : "nowcoder".equals(platforms[position]) ? 1 : 0);
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        Button generate = action("生成今日训练", true); form.addView(generate);
        LinearLayout zones = column(); content.addView(zones);
        LinearLayout history = card(); history.addView(label("挑战历史", 17, TEXT, true));
        generate.setOnClickListener(v -> {
            if (actionBusy) return;
            String selected = platforms[platformChoice.getSelectedItemPosition()];
            java.util.List<String> levels = trainingDifficulties(selected);
            int index = difficulty.getSelectedItemPosition(); String tagText = tag.getText().toString().trim(); boolean byWeak = weak.isChecked();
            actionBusy = true; generate.setEnabled(false); zones.removeAllViews();
            String[] names = {"稳定基础", "主训练", "突破上限"};
            LinearLayout[] slots = new LinearLayout[3];
            for (int i = 0; i < 3; i++) { slots[i] = column(); slots[i].setPadding(dp(16),dp(16),dp(16),dp(16)); slots[i].setBackground(shape(PANEL,10,LINE)); slots[i].setMinimumHeight(dp(180)); slots[i].addView(label(names[i] + " · 正在生成…", 15, BRAND, true)); zones.addView(slots[i]); }
            io.execute(() -> {
                for (int i = 0; i < 3; i++) {
                    int slot = i; JSONObject result = null; Exception failure = null;
                    try {
                        Object target = JSONObject.NULL;
                        if ("codeforces".equals(selected) || "atcoder".equals(selected)) {
                            int base = Integer.parseInt(levels.get(index)); int max = "codeforces".equals(selected) ? 3500 : 4000; int min = "codeforces".equals(selected) ? 800 : 0;
                            target = Math.max(min, Math.min(max, base + (i - 1) * 150));
                        } else if (!selected.isEmpty()) target = levels.get(Math.max(0, Math.min(levels.size()-1, index + i - 1)));
                        result = api.writeObject("POST", "/api/me/challenge/start", new JSONObject().put("platform",selected).put("tag",tagText).put("weak_tag",byWeak).put("difficulty", target));
                    } catch (Exception e) { failure = e; }
                    JSONObject value = result; Exception error = failure;
                    runOnUiThread(() -> {
                        if (serial != requestSerial) return;
                        slots[slot].removeAllViews();
                        if (error != null) failureBox(slots[slot], FailureState.title(error),180,null);
                        else {
                            slots[slot].addView(label(names[slot], 15, BRAND, true));
                            slots[slot].addView(label(value(value,"problem_name",value.optString("problem_id")), 16,TEXT,true));
                            slots[slot].addView(label(value.optString("platform") + " · " + value(value,"problem_rating","难度未知"),12,MUTED,false));
                            slots[slot].addView(label(value.optString("recommendation_reason"),12,MUTED,false));
                            if (!value.optString("problem_url").isEmpty()) { Button open = action("打开题目",false); open.setOnClickListener(button -> openBrowser(value.optString("problem_url"))); slots[slot].addView(open); }
                        }
                    });
                }
                runOnUiThread(() -> { actionBusy = false; if (serial == requestSerial) { generate.setEnabled(true); loadTrainingHistory(history, serial); } });
            });
        });
        loadTrainingHistory(history, serial);
    }

    private java.util.List<String> trainingDifficulties(String platform) {
        if ("luogu".equals(platform)) return java.util.Arrays.asList("未评定","入门","普及-","普及/提高-","普及+/提高","提高+/省选-","省选/NOI-","NOI/NOI+/CTSC");
        if ("nowcoder".equals(platform)) return java.util.Arrays.asList("1星","2星","3星","4星","5星");
        java.util.List<String> values = new java.util.ArrayList<>();
        if (platform.isEmpty()) { values.add("不限难度"); return values; }
        for (int n = "codeforces".equals(platform) ? 800 : 0; n <= ("codeforces".equals(platform) ? 3500 : 4000); n += 100) values.add(String.valueOf(n));
        return values;
    }

    private void loadTrainingHistory(LinearLayout box, int serial) {
        box.removeAllViews(); box.addView(label("正在读取挑战历史…", 14, MUTED, false));
        io.execute(() -> {
            try {
                JSONArray rows = api.getArray("/api/me/training/challenges");
                runOnUiThread(() -> {
                    if (serial != requestSerial) return;
                    box.removeAllViews(); box.addView(label("挑战历史 · 仅自己可见", 17, TEXT, true));
                    if (rows.length() == 0) box.addView(label("暂无挑战记录。", 13, MUTED, false));
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.optJSONObject(i); if (row == null) continue;
                        space(box, 12); box.addView(label(value(row,"problem_name",row.optString("problem_id")),15,TEXT,true));
                        box.addView(label(row.optString("platform") + " · " + row.optString("status") + " · " + date(row.optLong("created_at")),12,MUTED,false));
                    }
                });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) failureBox(box,FailureState.title(e),250,()->loadTrainingHistory(box,serial)); }); }
        });
    }

    private void renderContests() {
        heading("CONTEST REVIEW", "赛事复盘", "查询自己的比赛题目，并保存逐题补题状态。");
        if (!requireLogin("contests")) return;
        LinearLayout form = card(); EditText contest = new EditText(this); contest.setHint("比赛 ID"); contest.setSingleLine(true); form.addView(contest);
        Button load = action("查询比赛题目", true); form.addView(load);
        LinearLayout results = card(); results.addView(label("请输入比赛 ID 查询；无记录时请先同步数据。",13,MUTED,false));
        load.setOnClickListener(v -> {
            String id = contest.getText().toString().trim(); if (id.isEmpty()) { message("请输入比赛 ID。"); return; }
            int serial = requestSerial;
            mutate(load, () -> {
                JSONArray rows = api.getArray("/api/me/contest/reviews?contest_id=" + encode(id));
                runOnUiThread(() -> { if (serial == requestSerial) showContestRows(results,id,rows); });
            }, () -> { });
        });
    }

    private void showContestRows(LinearLayout box, String contest, JSONArray rows) {
        box.removeAllViews();
        if (rows.length() == 0) box.addView(label("暂无这场比赛的题目记录，请先同步数据。",14,MUTED,false));
        String[] keys = {"todo","unsolved","queued","solved","reviewed","ignored"};
        String[] labels = {"待处理","未通过","待补题","已解决","已复盘","忽略"};
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i); if (row == null) continue;
            space(box, 14); box.addView(label(row.optString("problem_id"),16,TEXT,true));
            box.addView(label(value(row,"verdict","未记录结果") + " · " + value(row,"rating","难度未知"),12,MUTED,false));
            Spinner status = spinner(labels); int selected = java.util.Arrays.asList(keys).indexOf(row.optString("status")); status.setSelection(Math.max(0,selected)); box.addView(status);
            Button save = action("保存本题状态",false);
            save.setOnClickListener(v -> {
                String next = keys[status.getSelectedItemPosition()];
                mutate(save, () -> api.writeObject("PUT","/api/me/contest/reviews",new JSONObject().put("contest_id",contest).put("problem_id",row.getString("problem_id")).put("status",next)), () -> android.widget.Toast.makeText(this,"本题状态已保存",android.widget.Toast.LENGTH_SHORT).show());
            }); box.addView(save);
        }
    }

    private void addPager(int total, int size) {
        if (api.isUnconfigured() || total <= size) return;
        LinearLayout pager = row();
        Button previous = action("上一页", false), next = action("下一页", false);
        previous.setEnabled(page > 1);
        next.setEnabled((long) page * size < total);
        previous.setOnClickListener(view -> { page--; loadScreen(); });
        next.setOnClickListener(view -> { page++; loadScreen(); });
        pager.addView(previous, new LinearLayout.LayoutParams(0, dp(44), 1));
        pager.addView(label("  第 " + page + " 页  ", 12, MUTED, false));
        pager.addView(next, new LinearLayout.LayoutParams(0, dp(44), 1));
        content.addView(pager);
    }

    private void addRankPager(int total){
        final int pages=Math.max(1,(total+rankPageSize-1)/rankPageSize);
        LinearLayout pager=row();pager.setPadding(0,dp(12),0,dp(12));
        Button previous=action("上一页",false),next=action("下一页",false);
        previous.setTextSize(11);next.setTextSize(11);previous.setMinWidth(0);next.setMinWidth(0);
        previous.setPadding(dp(4),0,dp(4),0);next.setPadding(dp(4),0,dp(4),0);
        previous.setEnabled(page>1);next.setEnabled(page<pages);
        previous.setOnClickListener(v->{page--;loadScreen();});next.setOnClickListener(v->{page++;loadScreen();});
        pager.addView(previous,new LinearLayout.LayoutParams(0,dp(46),1));
        LinearLayout position=column(),number=row();number.setGravity(Gravity.CENTER);
        EditText input=new EditText(this);input.setSingleLine(true);input.setInputType(InputType.TYPE_CLASS_NUMBER);input.setText(String.valueOf(page));input.setTextSize(12);input.setGravity(Gravity.CENTER);input.setPadding(0,0,0,0);input.setSelectAllOnFocus(true);input.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_GO);input.setContentDescription("输入排行榜页码");
        number.addView(label("第",11,MUTED,false));number.addView(input,new LinearLayout.LayoutParams(dp(36),dp(42)));number.addView(label("页",11,MUTED,false));
        position.addView(number);TextView count=label("（共"+pages+"页）",10,MUTED,false);count.setGravity(Gravity.CENTER);position.addView(count);
        pager.addView(position,new LinearLayout.LayoutParams(0,-2,1.3f));
        Runnable jump=()->{int target;try{String raw=input.getText().toString().trim();target=raw.matches("[0-9]+")?Integer.parseInt(raw):1;}catch(Exception e){target=1;}if(target<1||target>pages)target=1;input.setText(String.valueOf(target));if(target!=page){page=target;loadScreen();}};
        input.setOnEditorActionListener((v,id,event)->{if(id==android.view.inputmethod.EditorInfo.IME_ACTION_GO||(event!=null&&event.getKeyCode()==android.view.KeyEvent.KEYCODE_ENTER&&event.getAction()==android.view.KeyEvent.ACTION_UP)){jump.run();return true;}return false;});
        input.setOnFocusChangeListener((v,focus)->{if(!focus&&v.isAttachedToWindow())jump.run();});
        LinearLayout quantity=row();quantity.setGravity(Gravity.CENTER);quantity.addView(label("一页",11,MUTED,false));Spinner sizes=spinner(new String[]{"5","10","20","100"});int[] options={5,10,20,100};sizes.setSelection(rankPageSize==5?0:rankPageSize==10?1:rankPageSize==100?3:2);
        sizes.setContentDescription("排行榜每页数量");sizes.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> parent){}public void onItemSelected(android.widget.AdapterView<?> parent,View view,int index,long id){if(options[index]!=rankPageSize){rankPageSize=options[index];page=1;loadScreen();}}});
        quantity.addView(sizes,new LinearLayout.LayoutParams(0,dp(48),1));quantity.addView(label("项",11,MUTED,false));pager.addView(quantity,new LinearLayout.LayoutParams(0,dp(48),1.8f));pager.addView(next,new LinearLayout.LayoutParams(0,dp(46),1));content.addView(pager);
    }

    private void renderCompose(int serial) {
        heading("CREATE A POST", "发布话题", "写下问题或经验，选择分类后提交审核。");
        loading("正在加载论坛分类…");
        io.execute(() -> {
            try {
                JSONArray categories = api.getArray("/api/forum/categories");
                runOnUiThread(() -> { if (serial == requestSerial) showCompose(categories); });
            } catch (Exception e) {
                runOnUiThread(() -> { if (serial == requestSerial) error(e); });
            }
        });
    }

    private void showCompose(JSONArray categories) {
        content.removeAllViews();
        heading("CREATE A POST", "发布话题", "写下问题或经验，选择分类后提交审核。");
        if (!api.isLoggedIn()) status("可先编辑内容；提交前需要登录成员账号。");
        if (categories.length() == 0) { status("暂无可用分类，请稍后重试。"); return; }

        String[] names = new String[categories.length()];
        int[] ids = new int[categories.length()];
        int selected = 0;
        for (int i = 0; i < categories.length(); i++) {
            JSONObject category = categories.optJSONObject(i);
            names[i] = category == null ? "分类" : category.optString("name", "分类");
            ids[i] = category == null ? 0 : category.optInt("id");
            if (ids[i] == composeCategoryId) selected = i;
        }
        composeCategoryId = ids[selected];

        LinearLayout box = card();
        box.addView(label("话题分类", 13, TEXT, true));
        Spinner category = new Spinner(this);
        ArrayAdapter<String> options = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, names);
        options.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        category.setAdapter(options);
        category.setSelection(selected);
        category.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (composeCategoryId != ids[position]) { composeCategoryId = ids[position]; composerChanged(); }
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { composeCategoryId = 0; }
        });
        box.addView(category, new LinearLayout.LayoutParams(-1, dp(48)));
        space(box, 12);
        box.addView(label("标题（4–120 字）", 13, TEXT, true));
        EditText title = new EditText(this);
        title.setSingleLine(true);
        title.setHint("例如：二分答案的边界怎么判断？");
        title.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(120)});
        title.setText(composeTitle);
        title.addTextChangedListener(watch(value -> { composeTitle = value; composerChanged(); }));
        box.addView(title);
        space(box, 12);
        box.addView(label("正文（5–20000 字）", 13, TEXT, true));
        EditText body = new EditText(this);
        body.setHint("描述问题、已经尝试的方法，或分享解题思路…");
        body.setGravity(Gravity.TOP);
        body.setMinLines(8);
        body.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        body.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(20000)});
        body.setText(composeBody);
        body.addTextChangedListener(watch(value -> { composeBody = value; composerChanged(); }));
        box.addView(body, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout format = row();
        Button bold = action("加粗", false), code = action("代码块", false), quote = action("引用", false);
        bold.setOnClickListener(v -> insertFormat(body, "**", "**"));
        code.setOnClickListener(v -> insertFormat(body, "\n```\n", "\n```\n"));
        quote.setOnClickListener(v -> insertFormat(body, "> ", ""));
        format.addView(bold, new LinearLayout.LayoutParams(0, dp(44), 1)); format.addView(code, new LinearLayout.LayoutParams(0, dp(44), 1)); format.addView(quote, new LinearLayout.LayoutParams(0, dp(44), 1)); box.addView(format);
        Button preview = action("预览正文", false);
        preview.setOnClickListener(v -> { LinearLayout article = column(); article.addView(new ContentView(this, composeBody, false, this::openBrowser)); detailsDialog("正文预览", article); }); box.addView(preview);
        composeStatus = label(composeRevision == composeSavedRevision && composeDraftId > 0 ? "草稿已保存" : "编辑内容尚未保存到账号", 12, MUTED, false);
        box.addView(composeStatus);
        Button save = action("保存草稿", false);
        save.setOnClickListener(v -> { if (requireLogin("compose")) saveComposer(null); }); box.addView(save);
        if (composeDraftId > 0) {
            Button remove = action("删除当前草稿", false);
            remove.setOnClickListener(v -> new ModalDialogs.Builder(this).setTitle("删除草稿？").setMessage("删除后无法恢复。")
                    .setNegativeButton("取消", null).setPositiveButton("删除", (d, w) -> mutate(remove, () -> api.deleteDraft(composeDraftId), () -> { clearComposer(); loadScreen(); })).show());
            box.addView(remove);
        }
        space(box, 10);
        box.addView(label("提交后进入人工审核；通过后才会出现在主页。", 12, MUTED, false));

        Button submit = action("提交审核", true);
        submit.setOnClickListener(view -> {
            String postTitle = title.getText().toString().trim();
            String postBody = body.getText().toString().trim();
            if (postTitle.codePointCount(0, postTitle.length()) < 4 || postTitle.codePointCount(0, postTitle.length()) > 120) { message("标题需要 4–120 字。"); return; }
            if (postBody.codePointCount(0, postBody.length()) < 5 || postBody.codePointCount(0, postBody.length()) > 20000) { message("正文需要 5–20000 字。"); return; }
            if (composeCategoryId <= 0) { message("请选择有效的话题分类。"); return; }
            if (!api.isLoggedIn()) {
                new ModalDialogs.Builder(this).setMessage("请先登录成员账号，再提交帖子。编辑内容会保留在本次 App 运行期间。")
                        .setNegativeButton("继续编辑", null)
                         .setPositiveButton("前往登录", (dialog, which) -> { loginDestination = "compose"; show("account"); }).show();
                return;
            }
            saveComposer(() -> {
                submit.setEnabled(false);
                composeBusy = true;
                int draftId = composeDraftId;
                io.execute(() -> {
                    try {
                        JSONObject result = api.submitDraft(draftId);
                        runOnUiThread(() -> {
                            composeBusy = false; clearComposer(); show("forum");
                            message(result.optString("message", "已提交审核。"));
                        });
                    } catch (Exception e) { runOnUiThread(() -> { composeBusy = false; submit.setEnabled(true); failureDialog(e); }); }
                });
            });
        });
        content.addView(submit);
    }

    private void insertFormat(EditText input, String before, String after) {
        int start = Math.max(0, input.getSelectionStart()), end = Math.max(start, input.getSelectionEnd());
        String selected = input.getText().toString().substring(start, end);
        input.getText().replace(start, end, before + selected + after);
        input.setSelection(start + before.length(), start + before.length() + selected.length()); input.requestFocus();
    }

    private void composerChanged() {
        composeRevision++;
        if (composeStatus != null) composeStatus.setText("有未保存的修改");
    }

    private void clearComposer() {
        composeTitle = ""; composeBody = ""; composeCategoryId = 0; composeDraftId = 0;
        composeRevision = 0; composeSavedRevision = 0; composeStatus = null;
    }

    private void saveComposer(Runnable afterSave) {
        if (composeBusy || actionBusy || !requireLogin("compose")) return;
        composeBusy = true;
        int draft = composeDraftId, categoryId = composeCategoryId;
        String title = composeTitle, body = composeBody;
        long revision = composeRevision;
        if (composeStatus != null) composeStatus.setText("正在保存草稿…");
        io.execute(() -> {
            try {
                JSONObject saved = api.saveDraft(draft, categoryId, title, body);
                int savedId = saved.getInt("id");
                runOnUiThread(() -> {
                    composeBusy = false; composeDraftId = savedId; composeSavedRevision = revision;
                    if (isFinishing() || isDestroyed()) return;
                    if (composeStatus != null) composeStatus.setText(composeRevision == revision ? "草稿已保存" : "已保存上一版，仍有新修改未保存");
                    if (afterSave != null) {
                        if (composeRevision != revision) saveComposer(afterSave); else afterSave.run();
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    composeBusy = false;
                    if (isFinishing() || isDestroyed()) return;
                    if (composeStatus != null) composeStatus.setText("保存失败，编辑内容仍保留");
                    failureDialog(e);
                });
            }
        });
    }

    private void openDraft(int id) {
        if (composeBusy || loginBusy) return;
        if (composeRevision != composeSavedRevision && (!composeTitle.isEmpty() || !composeBody.isEmpty())) {
            new ModalDialogs.Builder(this).setTitle("先处理当前编辑内容")
                    .setMessage("读取另一份草稿前，请先保存或放弃当前修改。")
                    .setNegativeButton("取消", null).setNeutralButton("放弃当前修改", (d,w) -> { clearComposer(); openDraft(id); })
                    .setPositiveButton("保存当前草稿", (d,w) -> saveComposer(() -> openDraft(id))).show(); return;
        }
        int serial = requestSerial;
        io.execute(() -> {
            try {
                JSONObject draft = api.getObject("/api/forum/drafts/" + id);
                runOnUiThread(() -> {
                    if (serial != requestSerial || isFinishing() || isDestroyed()) return;
                    composeTitle = draft.optString("title"); composeBody = draft.optString("body");
                    composeCategoryId = draft.optInt("category_id"); composeDraftId = id;
                    composeRevision = 0; composeSavedRevision = 0; show("compose");
                });
            } catch (Exception e) { runOnUiThread(() -> { if (serial == requestSerial) failureDialog(e); }); }
        });
    }

    private TextWatcher watch(java.util.function.Consumer<String> onChange) {
        return new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence text, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence text, int start, int before, int count) {
                onChange.accept(text.toString());
            }
            @Override public void afterTextChanged(Editable text) { }
        };
    }

    private void renderMine(int serial) {
        heading("PUBLIC PROFILE", "个人中心", "公开资料、各平台通过题数与已发布话题。");
        if (api.isUnconfigured() || !api.isLoggedIn()) {
            publicFailure = api.isUnconfigured() ? connectionFailure() : new ApiClient.ApiException(401, "未登录", false);
            publishedFailure = publicFailure;
            showPublicMember(null, true, null);
            return;
        }
        loading("正在加载公开主页…");
        io.execute(() -> {
            JSONObject user = null, posts = null;
            Exception profileError = null, postsError = null;
            try {
                JSONObject result = api.getObject("/api/me/profile");
                JSONObject account = result.getJSONObject("user");
                user = new JSONObject().put("name", account.getString("name")).put("status", account.optString("status"))
                        .put("avatar_url", account.optString("avatar_url", "")).put("platform_counts", result.getJSONObject("platform_counts"))
                        .put("total_count", result.getInt("total_count"));
                String[] platforms = {"codeforces", "luogu", "atcoder", "nowcoder", "cjlu"};
                String[] keys = {"cf_count", "luogu_count", "atcoder_count", "nowcoder_count", "cjlu_count"};
                for (int i = 0; i < keys.length; i++) user.put(keys[i], user.getJSONObject("platform_counts").optInt(platforms[i], 0));
            } catch (Exception e) { profileError = e; }
            try {
                JSONArray all = api.getArray("/api/forum/mine/posts"), published = new JSONArray();
                int total = 0;
                for (int i = 0; i < all.length(); i++) {
                    JSONObject post = all.getJSONObject(i); if (!"published".equals(post.optString("status"))) continue;
                    if (total >= (page - 1) * 12 && total < page * 12) published.put(post); total++;
                }
                posts = new JSONObject().put("rows", published).put("total", total);
            } catch (Exception e) { postsError = e; }
            // Motto is optional; its absence must not hide existing profile or posts APIs.
            Exception mottoError = null;
            if (user != null) {
                try { user.put("motto", api.ownPublicProfile().getString("motto")); }
                catch (Exception e) { mottoError = e; }
            }
            JSONObject profile = user, published = posts;
            Exception profileFailure = profileError, postsFailure = postsError, mottoResult = mottoError;
            runOnUiThread(() -> {
                if (serial != requestSerial) return;
                publicFailure = profileFailure; publishedFailure = postsFailure;
                mottoFailure = mottoResult;
                showPublicMember(profile, true, published);
            });
        });
    }

    private void showPublicProfile(JSONObject profile) {
        showPublicMember(profile == null ? null : profile.optJSONObject("user"), true);
    }

    private void openMember(JSONObject row, String from) {
        memberPreview = row;
        memberReturnScreen = from;
        show("member");
    }

    private void renderMember(int serial) {
        String publicId = value(memberPreview, "public_member_id", value(memberPreview, "author_public_member_id", ""));
        if (api.isUnconfigured() || publicId.isEmpty()) {
            publicFailure = api.isUnconfigured() ? connectionFailure() : new ApiClient.UnavailableEndpointException("成员公开主页");
            publishedFailure = publicFailure;
            showPublicMember(memberPreview, false, null); return;
        }
        loading("正在加载成员公开主页…");
        io.execute(() -> {
            JSONObject profile = null, posts = null;
            Exception profileError = null, postsError = null;
            try {
                profile = api.memberProfile(publicId);
                profile.getString("public_member_id"); profile.getString("name"); profile.getJSONObject("platform_counts"); profile.getString("motto");
            } catch (Exception e) { profileError = e; profile = null; }
            try { posts = api.memberPosts(publicId, page); posts.getJSONArray("rows"); } catch (Exception e) { postsError = e; posts = null; }
            JSONObject user = profile == null ? memberPreview : profile, published = posts;
            Exception profileFailure = profileError, postsFailure = postsError;
            runOnUiThread(() -> {
                if (serial != requestSerial) return;
                publicFailure = profileFailure; publishedFailure = postsFailure;
                showPublicMember(user, false, published);
            });
        });
    }

    private String count(JSONObject row, String key) {
        return row != null && row.has(key) && !row.isNull(key) ? String.valueOf(row.optInt(key)) : "—";
    }

    private ImageButton avatarButton(int size) {
        ImageButton avatar = new ImageButton(this);
        avatar.setImageResource(android.R.drawable.ic_menu_myplaces);
        avatar.setScaleType(android.widget.ImageView.ScaleType.CENTER_CROP);
        avatar.setBackground(shape(ACCENT, size / 2, 0));
        avatar.setClipToOutline(true);
        avatar.setPadding(0, 0, 0, 0);
        return avatar;
    }

    private void loadAvatar(ImageButton view, String path) {
        if (api.isUnconfigured() || path.isEmpty()) return;
        int serial = requestSerial;
        avatarIo.execute(() -> {
            if (serial != requestSerial) return;
            try {
                android.graphics.Bitmap image = api.avatarBitmap(path);
                if (image != null) runOnUiThread(() -> { if (serial == requestSerial) view.setImageBitmap(image); });
            } catch (Exception ignored) { /* Keep the local default avatar if the image is unavailable. */ }
        });
    }

    private void publicStat(LinearLayout parent, String title, String number) {
        LinearLayout item = column();
        item.setPadding(dp(10), dp(10), dp(10), dp(10));
        item.setBackground(shape(BACKGROUND, 8, 0));
        item.addView(label(number, 23, BRAND, true));
        item.addView(label(title, 11, MUTED, false));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1);
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        parent.addView(item, params);
    }

    private void showPublicMember(JSONObject user, boolean own) {
        showPublicMember(user, own, null);
    }

    private void showPublicMember(JSONObject user, boolean own, JSONObject publishedPosts) {
        boolean publicData = publicFailure == null && user != null && user.has("platform_counts");
        content.removeAllViews();
        if (!own) {
            Button back = action("← 返回" + ("rank".equals(memberReturnScreen) ? "排名" : "论坛"), false);
            back.setOnClickListener(v -> show(memberReturnScreen));
            content.addView(back);
        }
        String name = user == null ? "资料不可用" : user.optString("name", user.optString("author_name", "ACM 成员"));
        LinearLayout hero = card();
        hero.setBackground(shape(Color.rgb(220, 235, 220), 12, 0));
        hero.addView(label("PUBLIC PROFILE · " + (own ? "我的主页" : "成员主页"), 11, BRAND, true));
        space(hero, 12);
        LinearLayout identity = row();
        ImageButton avatar = avatarButton(58);
        identity.addView(avatar, new LinearLayout.LayoutParams(dp(58), dp(58)));
        String avatarPath = value(user, "avatar_url", value(user, "author_avatar_url", ""));
        loadAvatar(avatar, avatarPath);
        if (own) {
            avatar.setContentDescription("进入账号设置");
            avatar.setOnClickListener(v -> show("account"));
            if (avatarPath.isEmpty()) headerAvatar.setImageResource(android.R.drawable.ic_menu_myplaces);
            else loadAvatar(headerAvatar, avatarPath);
        } else avatar.setContentDescription(name + "的头像");
        LinearLayout copy = column(); copy.setPadding(dp(12), 0, 0, 0);
        copy.addView(label(name, 22, TEXT, true));
        if (user != null && user.has("status")) copy.addView(label(value(user, "status", ""), 12, MUTED, false));
        identity.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        hero.addView(identity);
        space(hero, 12);
        if (publicData && user.has("motto")) hero.addView(label("座右铭 · " + value(user, "motto", "暂无座右铭"), 12, MUTED, false));
        else {
            LinearLayout motto = column(); hero.addView(motto, new LinearLayout.LayoutParams(-1, dp(64)));
            failureBox(motto, FailureState.title(publicFailure == null ? mottoFailure : publicFailure), 64, null);
        }
        LinearLayout achievements = card();
        achievements.addView(label("各平台通过题数", 17, TEXT, true));
        space(achievements, 7);
        if (!publicData) {
            LinearLayout region = column(); achievements.addView(region);
            failureBox(region, FailureState.title(publicFailure), 264, this::loadScreen);
        } else {
            String[] names = {"Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ", "合计"};
            String[] keys = {"cf_count", "luogu_count", "atcoder_count", "nowcoder_count", "cjlu_count", "total_count"};
            for (int i = 0; i < names.length; i += 2) {
                LinearLayout stats = row();
                publicStat(stats, names[i], count(user, keys[i]));
                publicStat(stats, names[i + 1], count(user, keys[i + 1]));
                achievements.addView(stats);
            }
            achievements.addView(label("生涯各平台通过题数 · 逐题记录仅自己可见", 12, MUTED, false));
        }
        LinearLayout community = card();
        community.addView(label("发布的论坛话题", 17, TEXT, true));
        space(community, 7);
        if (publishedPosts == null) {
            LinearLayout region = column(); community.addView(region);
            failureBox(region, FailureState.title(publishedFailure), 180, this::loadScreen);
        }
        else {
            JSONArray rows = publishedPosts.optJSONArray("rows");
            if (rows == null || rows.length() == 0) community.addView(label("暂无已发布话题。", 12, MUTED, false));
            else for (int i = 0; i < rows.length(); i++) {
                JSONObject post = rows.optJSONObject(i); if (post == null) continue;
                menuRow(community, post.optString("title"), post.optString("category_name", "话题"), () -> { postId = post.optInt("id"); show("detail"); });
            }
            addPager(publishedPosts.optInt("total"), 12);
        }
        if (own) {
            Button account = action(user == null ? "登录并查看账号设置" : "打开账号设置与我的记录", true);
            account.setOnClickListener(v -> show("account"));
            content.addView(account);
        }
    }

    private void renderAccount(int serial) {
        heading("MY ACCOUNT", "账号设置", "登录、资料、安全和仅自己可见的记录。");
        if (!api.isLoggedIn()) {
            showLogin();
            Button connection = action("检查更新", false);
            connection.setOnClickListener(v -> checkForUpdates()); content.addView(connection);
            return;
        }
        if (api.requiresPasswordChange()) {
            failureBox(card(), "请修改初始密码", 180, null);
            Button change = action("修改初始密码", true);
            change.setOnClickListener(v -> showChangePassword()); content.addView(change); return;
        }
        loading("正在加载账号资料…");
        io.execute(() -> {
            try { api.refreshSession(); }
            catch (Exception e) {
                runOnUiThread(() -> {
                    if (serial != requestSerial) return;
                    if (api.requiresPasswordChange()) { loadScreen(); return; }
                    error(e);
                    Button connection = action("检查更新", false);
                    connection.setOnClickListener(v -> checkForUpdates()); content.addView(connection);
                    if (!api.isLoggedIn()) showLogin();
                }); return;
            }
            JSONObject profile = null;
            JSONArray posts = null, bookmarks = null, drafts = null;
            Exception[] failures = new Exception[4];
            try { profile = api.getObject("/api/me/profile"); profile.getJSONObject("user"); } catch (Exception e) { failures[0] = e; profile = null; }
            try { posts = api.getArray("/api/forum/mine/posts"); } catch (Exception e) { failures[1] = e; }
            try { bookmarks = api.getArray("/api/forum/mine/bookmarks"); } catch (Exception e) { failures[2] = e; }
            try { drafts = api.getArray("/api/forum/drafts"); } catch (Exception e) { failures[3] = e; }
            JSONObject account = profile;
            JSONArray mine = posts, saved = bookmarks, editing = drafts;
            runOnUiThread(() -> { if (serial == requestSerial) showAccountProfile(account, mine, saved, editing, failures); });
        });
    }

    private void showLogin() {
        LinearLayout box = card();
        box.addView(label("账号登录", 18, TEXT, true));
        space(box, 8);
        box.addView(label("使用管理员发放的账号。", 12, MUTED, false));
        if (api.isUnconfigured()) {
            LinearLayout region = column(); box.addView(region);
            failureBox(region, FailureState.title(connectionFailure()), 180, null);
            return;
        }
        EditText qq = new EditText(this);
        qq.setHint("用户名 / QQ"); qq.setSingleLine(true);
        qq.setInputType(InputType.TYPE_CLASS_TEXT); qq.setText(loginIdentifier);
        box.addView(qq);
        EditText password = new EditText(this);
        password.setHint("密码"); password.setSingleLine(true);
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setText(sessionVault.readPassword(api.getBaseUrl(), loginIdentifier));
        box.addView(password);
        CheckBox remember = new CheckBox(this); remember.setText("记住我（记住账号）");
        remember.setChecked(preferences.getBoolean("remember_account", false)); box.addView(remember);
        CheckBox savePassword = new CheckBox(this); savePassword.setText("保存密码（在此设备加密保存）");
        savePassword.setChecked(preferences.getBoolean("save_password", false)); box.addView(savePassword);
        savePassword.setOnCheckedChangeListener((button, checked) -> { if (checked) remember.setChecked(true); else sessionVault.clearPassword(); });
        CheckBox auto = new CheckBox(this); auto.setText("自动登录（会话失效后需重新登录）");
        auto.setChecked(preferences.getBoolean("auto_login", false)); box.addView(auto);
        auto.setOnCheckedChangeListener((button, checked) -> { if (checked) remember.setChecked(true); else { preferences.edit().putBoolean("auto_login", false).apply(); sessionVault.clear(); } });
        remember.setOnCheckedChangeListener((button, checked) -> { if (!checked) { auto.setChecked(false); savePassword.setChecked(false); preferences.edit().remove("remembered_account").putBoolean("remember_account", false).apply(); } });
        qq.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            public void onTextChanged(CharSequence s, int start, int before, int count) { password.setText(""); }
            public void afterTextChanged(Editable s) { }
        });
        Button submit = action("登录", true);
        submit.setOnClickListener(view -> {
            if (loginBusy) return;
            String user = qq.getText().toString().trim();
            String secret = password.getText().toString();
            password.setText("");
            if (user.isEmpty() || secret.isEmpty()) { message("请输入用户名 / QQ 和密码。"); return; }
            submit.setEnabled(false);
            loginIdentifier = user;
            boolean shouldSavePassword = savePassword.isChecked();
            preferences.edit().putBoolean("remember_account", remember.isChecked()).putBoolean("auto_login", auto.isChecked())
                    .putString("remembered_account", remember.isChecked() ? user : "").apply();
            showLoginWaiting();
            io.execute(() -> {
                try {
                    JSONObject result = api.login(user, secret);
                    if (shouldSavePassword) passwordSaveFailed = !sessionVault.savePassword(api.getBaseUrl(), user, secret);
                    else sessionVault.clearPassword();
                    runOnUiThread(() -> {
                        if (isFinishing() || isDestroyed()) return;
                        finishLoginWaiting();
                        if (sessionSaveFailed) { sessionSaveFailed = false; message("登录成功，但无法安全保存会话；下次请重新登录。"); }
                        if (passwordSaveFailed) { passwordSaveFailed = false; message("登录成功，但设备无法安全保存密码；下次请手动输入。"); }
                        if (result.optBoolean("must_change_password")) {
                            show("account");
                            showChangePassword();
                        } else show(loginDestination);
                    });
                } catch (Exception e) {
                    if (e instanceof ApiClient.ApiException && ((ApiClient.ApiException) e).status == 401) sessionVault.clearPassword();
                    runOnUiThread(() -> {
                        if (isFinishing() || isDestroyed()) return;
                        finishLoginWaiting();
                        show("account");
                        LinearLayout failure = card();
                        failureBox(failure, FailureState.title(e), 160, null);
                    });
                }
            });
        });
        box.addView(submit);
    }

    private void showLoginWaiting() {
        loginBusy = true;
        ++requestSerial;
        screen = "login_wait";
        ((android.view.inputmethod.InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                .hideSoftInputFromWindow(root.getWindowToken(), 0);
        root.getChildAt(0).setVisibility(View.GONE);
        nav.setVisibility(View.GONE);
        content.removeAllViews();
        LinearLayout wait = card();
        wait.setMinimumHeight(dp(520)); wait.setGravity(Gravity.CENTER);
        ProgressBar spinner = new ProgressBar(this);
        spinner.setContentDescription("正在登录，请稍候");
        wait.addView(spinner, new LinearLayout.LayoutParams(dp(48), dp(48)));
        space(wait, 26);
        wait.addView(label("正在登录…", 23, TEXT, true));
        space(wait, 10);
        TextView detail = label("正在验证账号与会话，成功后自动跳转。", 13, MUTED, false);
        detail.setGravity(Gravity.CENTER); wait.addView(detail);
        wait.postDelayed(() -> {
            if (loginBusy) detail.setText("网络响应较慢，请稍候；超时后可返回重试。\n请确认手机已接入 Tailscale 网络。");
        }, 12000);
    }

    private void finishLoginWaiting() {
        loginBusy = false;
        root.getChildAt(0).setVisibility(View.VISIBLE);
        nav.setVisibility(View.VISIBLE);
        screen = "account";
    }

    private void showAccountProfile(JSONObject result, JSONArray posts, JSONArray bookmarks, JSONArray drafts, Exception[] failures) {
        content.removeAllViews();
        JSONObject user = result == null ? null : result.optJSONObject("user");
        heading("MY ACCOUNT", "账号设置", "仅自己可见的资料与账号操作。");

        String avatarPath = value(user, "avatar_url", "");
        if (avatarPath.isEmpty()) headerAvatar.setImageResource(android.R.drawable.ic_menu_myplaces);
        else loadAvatar(headerAvatar, avatarPath);
        addAdministratorSection();
        if (user != null) {
        LinearLayout identity = card();
        identity.addView(label("个人资料", 13, BRAND, true));
        menuRow(identity, "修改昵称", value(user, "name", "ACM 成员"), () -> showRename(value(user, "name", "")));
        menuRow(identity, "社区头像", "上传图片或恢复默认", this::showAvatarActions);
        menuRow(identity, "座右铭", api.mottoStatus(), this::showMottoEditor);
        menuRow(identity, "OJ 账号绑定", "仅自己可见 · 只读", () -> showBindings(user));
        LinearLayout training = card();
        training.addView(label("我的学习 · 仅自己可见", 13, BRAND, true));
        menuRow(training, "通过题数", "累计 " + result.optInt("total_count") + " 题", () -> showTraining(result));
        menuRow(training, "最近 AC", "题目、平台与通过时间", () -> showRecent(result.optJSONArray("recent_ac")));
        menuRow(training, "今日训练", "稳定基础、主训练、突破上限与挑战历史", () -> show("training"));
        menuRow(training, "赛事复盘", "按比赛查看题目并保存补题状态", () -> show("contests"));
        menuRow(training, "我的题目收藏", "查看自己收藏的题目", () -> { problemState = "favorite"; show("problems"); });
        } else failureBox(card(), FailureState.title(failures[0]), 300, this::loadScreen);
        LinearLayout community = card();
        community.addView(label("我的社区 · 仅自己可见", 13, BRAND, true));
        privateMenuRow(community, "我的话题", posts, failures[1]);
        privateMenuRow(community, "我的收藏", bookmarks, failures[2]);
        privateMenuRow(community, "草稿", drafts, failures[3]);
        LinearLayout settings = card();
        settings.addView(label("账号与应用", 13, BRAND, true));
        menuRow(settings, "修改密码", "保护账号安全", this::showChangePassword);
        menuRow(settings, "外观设置", "薄荷主题", () -> message("样品当前使用薄荷主题，深色模式待加入。"));
        menuRow(settings, "检查更新", "检查新版本并下载安装", this::checkForUpdates);
        menuRow(settings, "关于 ACMforever", "0.1.12 · 调试版", () -> message("打一辈子爱臭美 / ACMforever\n版本 0.1.12 · 调试版"));
        Button logout = action("退出登录", false);
        logout.setOnClickListener(view -> {
            io.execute(() -> {
                try { api.logout(); sessionVault.clearPassword(); preferences.edit().putBoolean("auto_login", false).apply(); runOnUiThread(() -> { clearComposer(); commentBody = ""; commentParent = 0; selectedProblem = null; memberPreview = null; loginDestination = "account"; loadScreen(); }); }
                catch (Exception e) { runOnUiThread(() -> failureDialog(e)); }
            });
        });
        content.addView(logout);
    }

    private boolean isAdministratorAccount() {
        return api.isAdministrator();
    }

    private void addAdministratorSection() {
        if (!isAdministratorAccount()) return;
        LinearLayout admin = card();
        admin.setBackground(shape(Color.rgb(231, 240, 196), 11, LINE));
        admin.addView(label("管理员栏", 15, BRAND, true));
        menuRow(admin, "管理后台", "成员、训练、社区与系统管理", this::showAdministratorMenu);
    }

    private void showAdministratorMenu() {
        if (!isAdministratorAccount()) { message("请使用管理员账号登录。"); return; }
        returnFromAdmin = true;
        AdminActivity.open(this, api);
    }

    private String value(JSONObject object, String key, String fallback) {
        if (object == null || object.isNull(key)) return fallback;
        String result = object.optString(key, "").trim();
        return result.isEmpty() ? fallback : result;
    }

    private void showMottoEditor() {
        if(popupLoading||ModalDialogs.isShowing(this))return;
        if (api.isUnconfigured()) { failureDialog(connectionFailure()); return; }
        popupLoading=true;
        int serial = requestSerial;
        io.execute(() -> {
            try {
                if (!api.supportsMobile("edit_motto")) throw new ApiClient.UnavailableEndpointException("座右铭编辑");
                JSONObject profile = api.ownPublicProfile();
                runOnUiThread(() -> {
                    popupLoading=false;
                    if (serial != requestSerial) return;
                    EditText input = new EditText(this);
                    input.setHint("最多 100 个字符；留空可清除"); input.setText(profile.optString("motto"));
                    AlertDialog dialog = new ModalDialogs.Builder(this).setTitle("修改座右铭")
                            .setMessage("座右铭会展示在公开主页。")
                            .setView(input).setNegativeButton("取消", null).setPositiveButton("保存", null).create();
                    dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                        String motto = input.getText().toString().trim();
                        if (motto.codePointCount(0, motto.length()) > 100) { input.setError("不能超过 100 个字符"); return; }
                        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
                        io.execute(() -> {
                            try {
                                api.updateMotto(motto);
                                runOnUiThread(() -> { dialog.dismiss(); message("座右铭已保存。"); });
                            } catch (Exception e) {
                                runOnUiThread(() -> { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true); failureDialog(e); });
                            }
                        });
                    }));
                    ModalDialogs.show(dialog);
                });
            } catch (Exception e) { runOnUiThread(() -> { popupLoading=false;if (serial == requestSerial) failureDialog(e); }); }
        });
    }

    private void menuRow(LinearLayout parent, String title, String subtitle, Runnable onClick) {
        LinearLayout line = row();
        line.setPadding(0, dp(12), 0, dp(12));
        line.setMinimumHeight(dp(56));
        LinearLayout copy = column();
        copy.addView(label(title, 15, TEXT, true));
        copy.addView(label(subtitle, 11, MUTED, false));
        line.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        line.addView(label("›", 23, MUTED, false));
        line.setOnClickListener(v -> {if(!popupLoading&&!ModalDialogs.isShowing(this))onClick.run();});
        parent.addView(line);
        View divider = new View(this); divider.setBackgroundColor(LINE);
        parent.addView(divider, new LinearLayout.LayoutParams(-1, dp(1)));
    }

    private void privateMenuRow(LinearLayout parent, String title, JSONArray rows, Exception failure) {
        if (rows != null) {
            menuRow(parent, title, rows.length() + " 条", () -> showPrivateList(title, rows));
        } else {
            parent.addView(label(title, 14, TEXT, true));
            LinearLayout slot = column(); parent.addView(slot);
            failureBox(slot, FailureState.title(failure), 64, this::loadScreen);
        }
    }

    private AlertDialog detailsDialog(String title, LinearLayout body) {
        body.setPadding(dp(20), dp(8), dp(20), dp(12));
        ScrollView scroll = new ScrollView(this); scroll.addView(body);
        return new ModalDialogs.Builder(this).setTitle(title).setView(scroll).setPositiveButton("关闭", null).show();
    }

    private void showBindings(JSONObject user) {
        LinearLayout body = column();
        body.addView(label("绑定由管理员维护，仅本人及管理员可见。", 12, MUTED, false));
        String[] fields = {"cf_handle", "luogu_id", "atcoder_handle", "nowcoder_id", "cjlu_username"};
        String[] names = {"Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"};
        for (int i = 0; i < fields.length; i++) {
            space(body, 12);
            body.addView(label(names[i] + " · " + value(user, fields[i], "未绑定"), 14, TEXT, false));
        }
        detailsDialog("OJ 账号绑定", body);
    }

    private void showTraining(JSONObject profile) {
        LinearLayout body = column();
        body.addView(label("累计通过 " + profile.optInt("total_count") + " 题", 20, BRAND, true));
        JSONObject counts = profile.optJSONObject("platform_counts");
        String[] platforms = {"codeforces", "luogu", "atcoder", "nowcoder", "cjlu"};
        String[] names = {"Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"};
        for (int i = 0; i < platforms.length; i++) {
            space(body, 10);
            body.addView(label(names[i] + " · " + (counts == null ? 0 : counts.optInt(platforms[i])) + " 题", 14, TEXT, false));
        }
        detailsDialog("我的学习统计", body);
    }

    private void showRecent(JSONArray rows) {
        LinearLayout body = column();
        body.addView(label("这些逐题记录仅自己可见。", 12, MUTED, false));
        if (rows == null || rows.length() == 0) body.addView(label("暂无 AC 记录。", 14, MUTED, false));
        else for (int i = 0; i < rows.length(); i++) {
            JSONObject item = rows.optJSONObject(i); if (item == null) continue;
            space(body, 14);
            TextView title = label(value(item, "problem_name", value(item, "problem_id", "题目")), 15, TEXT, true);
            String url = value(item, "problem_url", "");
            if (!url.isEmpty()) title.setOnClickListener(v -> openBrowser(url));
            body.addView(title);
            String date = item.optLong("submit_time") > 0 ? new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.CHINA)
                    .format(new java.util.Date(item.optLong("submit_time") * 1000L)) : "";
            body.addView(label(value(item, "platform", "") + " · " + date, 12, MUTED, false));
        }
        detailsDialog("最近 AC", body);
    }

    private void showPrivateList(String title, JSONArray rows) {
        LinearLayout box = column();
        final AlertDialog[] dialog = new AlertDialog[1];
        box.addView(label("仅自己可见", 12, MUTED, false));
        if (rows == null || rows.length() == 0) box.addView(label("暂无内容", 12, MUTED, false));
        else for (int i = 0; i < rows.length(); i++) {
            JSONObject item = rows.optJSONObject(i);
            if (item == null) continue;
            space(box, 14);
            box.addView(label(value(item, "title", "未命名草稿"), 15, TEXT, true));
            String state = value(item, "status", "");
            String status = "pending".equals(state) ? "待审核" : "published".equals(state) ? "已发布" : "rejected".equals(state) ? "未通过" : state;
            box.addView(label(value(item, "category_name", "") + " " + status, 12, MUTED, false));
            box.addView(label(date(item.optLong("updated_at",item.optLong("created_at"))),12,MUTED,false));
            if ("草稿".equals(title)) {
                Button edit = action("继续编辑草稿", true);
                edit.setOnClickListener(v -> { dialog[0].dismiss(); openDraft(item.optInt("id")); }); box.addView(edit);
            } else if ("published".equals(state) || "我的收藏".equals(title)) {
                Button open = action("查看话题与讨论", false);
                open.setOnClickListener(v -> { dialog[0].dismiss(); postId = item.optInt("id"); show("detail"); }); box.addView(open);
            }
            if ("我的话题".equals(title)) {
                Button remove = action("删除话题", false);
                remove.setOnClickListener(v -> new ModalDialogs.Builder(this).setTitle("删除此话题？").setMessage("删除后将不再展示。")
                        .setNegativeButton("取消",null).setPositiveButton("删除",(d,w) -> mutate(remove, () -> api.writeObject("DELETE","/api/forum/posts/" + item.getInt("id"),new JSONObject()), () -> { dialog[0].dismiss(); loadScreen(); })).show());
                box.addView(remove);
            }
        }
        dialog[0] = detailsDialog(title, box);
    }

    private void showAvatarActions() {
        new ModalDialogs.Builder(this).setTitle("社区头像").setItems(new String[]{"上传图片（PNG / JPEG / WebP，最多 2 MB）", "恢复默认头像"}, (dialog, index) -> {
            if (index == 1) { resetAvatar(); return; }
            if (api.isUnconfigured()) { failureDialog(connectionFailure()); return; }
            Intent picker = new Intent(Intent.ACTION_GET_CONTENT);
            picker.setType("image/*");
            startActivityForResult(Intent.createChooser(picker, "选择社区头像"), PICK_AVATAR);
        }).setNegativeButton("取消", null).show();
    }

    private void showRename(String current) {
        EditText input = new EditText(this);
        input.setSingleLine(true); input.setText(current); input.setMaxLines(1);
        new ModalDialogs.Builder(this).setTitle("修改昵称").setView(input).setNegativeButton("取消", null)
                .setPositiveButton("保存", (d, w) -> {
                    String name = input.getText().toString().trim();
                    if (name.isEmpty() || name.length() > 100) { message("昵称需要 1–100 字。"); return; }
                    if (api.isUnconfigured()) { failureDialog(connectionFailure()); return; }
                    io.execute(() -> { try { api.updateName(name); runOnUiThread(this::loadScreen); }
                    catch (Exception e) { runOnUiThread(() -> failureDialog(e)); } });
                }).show();
    }

    private void showChangePassword() {
        LinearLayout form = column(); form.setPadding(dp(20), 0, dp(20), 0);
        EditText oldPassword = new EditText(this), newPassword = new EditText(this), confirmation = new EditText(this);
        oldPassword.setHint("当前密码"); newPassword.setHint("新密码"); confirmation.setHint("确认新密码");
        oldPassword.setInputType(129); newPassword.setInputType(129); confirmation.setInputType(129);
        form.addView(oldPassword); form.addView(newPassword); form.addView(confirmation);
        AlertDialog dialog = new ModalDialogs.Builder(this).setTitle("修改密码").setMessage("新密码需 12–128 位、无空格，并包含至少三类字符。")
                .setView(form).setNegativeButton("取消", null).setPositiveButton("确认修改", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            String oldValue = oldPassword.getText().toString(), newValue = newPassword.getText().toString();
            if (oldValue.isEmpty() || newValue.length() < 12 || newValue.length() > 128) { message("请输入当前密码和 12–128 位的新密码。"); return; }
            if (!newValue.equals(confirmation.getText().toString())) { message("两次输入的新密码不一致。"); return; }
            mutate(dialog.getButton(AlertDialog.BUTTON_POSITIVE), () -> api.changePassword(oldValue, newValue), () -> {
                sessionVault.clearPassword();
                oldPassword.setText(""); newPassword.setText(""); confirmation.setText("");
                dialog.dismiss(); message("密码已更新。"); loadScreen();
            });
        })); ModalDialogs.show(dialog);
    }

    private void resetAvatar() {
        if (api.isUnconfigured()) { failureDialog(connectionFailure()); return; }
        new ModalDialogs.Builder(this).setMessage("恢复默认社区头像？").setNegativeButton("取消", null)
                .setPositiveButton("恢复", (d, w) -> io.execute(() -> {
                    try { api.resetAvatar(); runOnUiThread(this::loadScreen); }
                    catch (Exception e) { runOnUiThread(() -> failureDialog(e)); }
                })).show();
    }

    private String encode(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }

    private void message(String value) {
        new ModalDialogs.Builder(this).setMessage(value).setPositiveButton("知道了", null).show();
    }

    private void showTools(View anchor) {
        if (loginBusy || composeBusy || actionBusy || popupLoading || ModalDialogs.isShowing(this)) return;
        new ModalDialogs.Builder(this).setTitle("常用工具").setItems(new String[]{"扫一扫", "检查更新"}, (dialog, index) -> {
            if(index==0)showScanPreview();else checkForUpdates();
        }).setNegativeButton("关闭",null).show();
    }

    private void showScanPreview() {
        EditText address = new EditText(this);
        address.setSingleLine(true);
        address.setHint("粘贴 HTTPS 网页链接，演示扫码结果");
        new ModalDialogs.Builder(this).setTitle("扫一扫 · 链接预览")
                .setMessage("二维码格式和相机识别仍待确认。当前可粘贴 HTTPS 链接，确认后在 App 内打开。")
                .setView(address).setNegativeButton("取消", null)
                .setPositiveButton("预览链接", (dialog, which) -> openBrowser(address.getText().toString().trim()))
                .show();
    }

    private void openBrowser(String value) {
        try {
            String checked = BrowserActivity.checkedUrl(value);
            String domain = java.net.URI.create(checked).getHost();
            new ModalDialogs.Builder(this).setTitle("打开网页")
                    .setMessage("域名：" + domain + "\n完整链接：" + checked + "\n\n确认在应用内打开？")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("打开", (dialog, which) -> {
                        Intent intent = new Intent(this, BrowserActivity.class);
                        intent.putExtra("url", checked);
                        startActivity(intent);
                    }).show();
        } catch (Exception e) { failureDialog(e); }
    }



    private void checkForUpdates() {
        updates.check(preferences.getString("update_manifest_url", getString(R.string.default_update_manifest_url)));
    }
}
