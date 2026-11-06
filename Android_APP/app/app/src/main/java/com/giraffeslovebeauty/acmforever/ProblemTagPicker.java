package com.giraffeslovebeauty.acmforever;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.function.*;

/** One searchable picker; reads genuine API labels, preserves cache, discards stale owners. */
final class ProblemTagPicker {
    static void show(Activity activity, ApiClient api, ExecutorService io, String platform, String selected, BooleanSupplier current, Consumer<String> choose) {
        if (activity.isFinishing() || activity.isDestroyed() || ModalDialogs.isShowing(activity) || !current.getAsBoolean()) return;
        new ProblemTagPicker(activity, api, io, platform, selected, current, choose).open();
    }
    private final Activity activity; private final ApiClient api; private final ExecutorService io;
    private final String platform, selected; private final BooleanSupplier current; private final Consumer<String> choose; private final long owner;
    private final LinearLayout root, status; private final EditText search; private final ListView list; private final PageRefresh refresh;
    private final List<String> tags = new ArrayList<>(), visible = new ArrayList<>();
    private final ArrayAdapter<String> adapter; private AlertDialog dialog; private boolean closed, loading, cached;
    private Exception lastFailure;
    private int dp(float n) { return MobileStyle.dp(activity, n); }
    private TextView text(String value) { TextView view = new TextView(activity); view.setText(value); view.setTextColor(MobileStyle.MUTED); view.setTextSize(13); view.setPadding(0, dp(6), 0, dp(6)); return view; }
    private Button button(String label) { Button button = new Button(activity); button.setText(label); MobileStyle.button(button, false); return button; }
    private ProblemTagPicker(Activity activity, ApiClient api, ExecutorService io, String platform, String selected, BooleanSupplier current, Consumer<String> choose) {
        this.activity = activity; this.api = api; this.io = io; this.platform = platform; this.selected = selected; this.current = current; this.choose = choose; owner = api.sessionGeneration();
        root = new SpacedLayout(activity); root.setOrientation(LinearLayout.VERTICAL);
        root.addView(text("按完整标签筛选，可与题名、题号关键词一起使用。"));
        refresh = new PageRefresh(activity, root, 1); refresh.reset(1); refresh.userAction();
        search = new EditText(activity); search.setSingleLine(true); search.setHint("搜索标签"); search.setContentDescription("搜索题目标签"); root.addView(search, new LinearLayout.LayoutParams(-1, dp(48)));
        TextView active = text("当前：" + (selected.isEmpty() ? "全部标签" : selected)); root.addView(active);
        Button all = button("全部标签"); MobileStyle.control(all, false, selected.isEmpty(), 12); all.setOnClickListener(v -> select("")); root.addView(all, new LinearLayout.LayoutParams(-1, dp(48)));
        status = new SpacedLayout(activity); status.setOrientation(LinearLayout.VERTICAL); root.addView(status);
        list = new ListView(activity) {
            @Override public boolean dispatchTouchEvent(MotionEvent event) {
                if(event.getActionMasked()==MotionEvent.ACTION_DOWN)getParent().requestDisallowInterceptTouchEvent(true);
                boolean handled=super.dispatchTouchEvent(event); // Keep native item clicks and accessibility.
                if(event.getActionMasked()==MotionEvent.ACTION_UP||event.getActionMasked()==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);
                return handled;
            }
        }; list.setDivider(null); list.setContentDescription("题目标签候选列表"); root.addView(list, new LinearLayout.LayoutParams(-1, dp(220)));
        adapter = new ArrayAdapter<String>(activity, android.R.layout.simple_list_item_1, visible) {
            @Override public View getView(int position, View old, ViewGroup parent) {
                TextView item = (TextView) super.getView(position, old, parent); String tag = getItem(position); boolean chosen = selected.equalsIgnoreCase(tag);
                item.setText(tag); item.setContentDescription("选择题目标签 " + tag); item.setTextSize(15); item.setMinHeight(dp(48)); item.setPadding(dp(12), dp(10), dp(12), dp(10));
                item.setTextColor(chosen ? MobileStyle.ON_ACCENT : MobileStyle.TEXT); item.setBackground(MobileStyle.panel(activity, MobileStyle.controlFill(chosen ? MobileStyle.ACCENT : MobileStyle.PANEL), 10, 0)); return item;
            }
        };
        list.setAdapter(adapter); list.setOnItemClickListener((parent, view, index, id) -> select(visible.get(index)));
        search.addTextChangedListener(new android.text.TextWatcher() { public void beforeTextChanged(CharSequence s, int a, int c, int f) {} public void onTextChanged(CharSequence s, int a, int b, int c) { matches(); } public void afterTextChanged(android.text.Editable e) {} });
    }
    private void open() {
        status.addView(text("正在读取标签…")); dialog = new ModalDialogs.Builder(activity).setTitle("题目标签").setView(root).show();
        dialog.setOnDismissListener(d -> { closed = true; refresh.close(); }); refresh.register(1, this::load);
        io.execute(() -> {
            List<String> saved = null; api.beginReplay(); try { saved = ProblemTags.options(api.getObject(ProblemTags.path(platform))); } catch (Exception ignored) {} finally { api.endReplay(); }
            List<String> result = saved; activity.runOnUiThread(() -> { if (!valid()) return; if (result != null) { cached = true; refresh.cached(1); tags.addAll(result); matches(); } load(); });
        });
    }
    private boolean valid() { return !closed && !activity.isFinishing() && !activity.isDestroyed() && owner == api.sessionGeneration() && current.getAsBoolean(); }
    private void select(String tag) { if (!valid()) { if (dialog != null) dialog.dismiss(); return; } dialog.dismiss(); choose.accept(tag); }
    private void matches() {
        visible.clear(); visible.addAll(ProblemTags.search(tags, search.getText().toString())); adapter.notifyDataSetChanged();
        status.removeAllViews(); status.setBackgroundColor(Color.TRANSPARENT);
        if(lastFailure!=null){
            ErrorModule.style(status);TextView error=text(FailureState.title(lastFailure));error.setTextColor(ErrorModule.ink());status.addView(error);
            if(cached)status.addView(text("保留已缓存标签，可继续选择。"));
            Button retry=button("重新读取标签");retry.setOnClickListener(v->refresh.refreshNow());status.addView(retry);return;
        }
        status.addView(text(tags.isEmpty() ? "当前平台暂无标签。" : visible.isEmpty() ? "没有匹配的标签。" : "共 " + visible.size() + " 个标签"));
    }
    private void load() {
        if (!valid() || loading) return; loading = true; refresh.start(1);
        io.execute(() -> {
            List<String> result = null; Exception failure = null;
            try { if (owner != api.sessionGeneration()) throw new IllegalStateException("登录账号已切换"); result = ProblemTags.options(api.getObject(ProblemTags.path(platform))); } catch (Exception e) { failure = e; }
            List<String> value = result; Exception issue = failure;
            activity.runOnUiThread(() -> {
                loading = false; if (!valid()) { refresh.close(); return; }
                if (issue == null) { lastFailure=null;cached=true;refresh.cached(1);tags.clear(); tags.addAll(value); matches(); }
                else {
                    lastFailure=issue;refresh.failure(FailureState.title(issue));matches();
                }
                refresh.finish(1);
            });
        });
    }
}
