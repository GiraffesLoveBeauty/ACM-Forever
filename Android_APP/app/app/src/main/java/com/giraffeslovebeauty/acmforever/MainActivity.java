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
import android.view.ViewGroup;
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

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Small native API client sample. All business data remains on the existing backend. */
public final class MainActivity extends Activity {
    private static final int PICK_AVATAR = 41;
    private static final int IMPORT_MARKDOWN = 42;
    private static final int PICK_COVER = 43;
    private static final int PICK_POST_IMAGE = 44;
    private boolean choosingPostImage,headerAvatarLoading;
    private long imageOwner,imageDraftGeneration,headerCheckedAt;
    private long headerAvatarOwner=-1,headerCheckOwner=-1;
    private android.net.Uri pendingPostImage;
    private EditText composeBodyInput;
    private CloudDrafts cloud;
    private final android.os.Handler ui = new android.os.Handler(android.os.Looper.getMainLooper());
    private boolean sessionRestoreAttempted;
    private Exception sessionRestoreFailure;
    private boolean openingPdf;
    private boolean openingUpdates;
    private String recoveryOffered="";
    private int BACKGROUND = Color.rgb(244, 245, 247);
    private int PANEL = Color.WHITE;
    private int TEXT = Color.rgb(30, 33, 28);
    private int MUTED = Color.rgb(112, 119, 107);
    private int BRAND = Color.rgb(49, 91, 54);
    private int ACCENT = Color.rgb(200, 235, 33);
    private int LINE = Color.rgb(229, 232, 224);

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ExecutorService previewIo=Executors.newSingleThreadExecutor();
    private final ThreadLocal<LoadContext> loadContext=new ThreadLocal<>();
    private PageRefresh pageRefresh;
    private ActionNotice actionNotice;
    private DetailUi detailUi;
    private String profilePlatform="all";
    private long appearanceSeen;
    private static final class DetailUi {
        int serial,id;JSONObject post;boolean interacted,sending;
        Button like,bookmark,send;EditText input;TextView replyTo,title,author,reads,category;
        LinearLayout editor,comments,body;
    }
    private boolean composeEditorShown;
    private boolean presentingRead;
    private static final class LoadContext {
        final int serial;final boolean preview;final java.util.concurrent.atomic.AtomicBoolean delivered;
        LoadContext(int serial,boolean preview,java.util.concurrent.atomic.AtomicBoolean delivered){this.serial=serial;this.preview=preview;this.delivered=delivered;}
    }
    private final ExecutorService avatarIo = Executors.newFixedThreadPool(2);
    private ApiClient api;
    private AcmApplication application;
    private LinearLayout root;
    private LinearLayout content;
    private ScrollView pageScroll;
    private final NavigationStack<Bundle> navigation=new NavigationStack<>();
    private int pendingScroll=-1;
    private long navigationOwner;
    private boolean externalRoot;
    private EditText search;
    private LinearLayout nav;
    private ImageButton headerAvatar;
    private SharedPreferences preferences;

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
    private String composeTitle = "";
    private String composeBody = "";
    private int composeCategoryId = 0;
    private int composeDraftId = 0;
    private boolean composeBusy;
    private long composeRevision;
    private long composeSavedRevision;
    private long composeGeneration=-1,markdownOwner=-1,markdownGeneration=-1;
    private boolean leaveComposeOnce;
    private TextView composeStatus;
    private boolean loginBusy;
    private SessionVault sessionVault;
    private volatile boolean passwordSaveFailed;
    private boolean returnFromAdmin;
    private String searchScope = "forum";
    private String searchReturn = "forum";
    private boolean filterLoading;
    private AlertDialog forumFilterDialog;
    private String loginIdentifier = "";
    private String loginDestination = "account";
    private String problemState = "";
    private String problemScope="all";
    private int notificationComment;
    private String contestIdentifier="";
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
        application = (AcmApplication) getApplication();
        cloud = application.drafts();
        api = application.api();
        preferences = getSharedPreferences("acmforever_settings", MODE_PRIVATE);
        // Application configures the shared client once. Recreating a screen must not
        // acquire its request monitor while an existing network operation is pending.

        navigationOwner=api.sessionGeneration();externalRoot=getIntent().getBooleanExtra("external_navigation",false)||getIntent().hasExtra("web_problem_id")||getIntent().hasExtra("club_post_id")||getIntent().hasExtra("cloud_draft_id");
        getIntent().putExtra("external_navigation",externalRoot);
        if (state != null && state.getLong("session_generation", -1) == api.sessionGeneration()) {
            restoreNavigation(state);navigation.restore(state.getParcelableArrayList("navigation_history"));
            markdownOwner=state.getLong("markdown_owner",-1);markdownGeneration=state.getLong("markdown_draft_generation",-1);
        }
        syncAppearance();buildShell();
        search.setText(query);
        updateSearchHeader();
        sessionVault = application.vault();
        loginIdentifier = preferences.getString("remembered_account", "");
        syncCloudEditor();
        int incomingPost=getIntent().getIntExtra("club_post_id",0);getIntent().removeExtra("club_post_id");if(incomingPost>0){postId=incomingPost;screen="detail";}
        String incomingPage=getIntent().getStringExtra("club_page");
        if("checkin".equals(incomingPage)||"reviews".equals(incomingPage)){if(api.isLoggedIn())screen=incomingPage;else{loginDestination=incomingPage;screen="account";}}
        updateSearchHeader();refreshNav();
        acceptWebIntent(getIntent());
        restoreWebSession();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);setIntent(intent);
        acceptWebIntent(intent);
        int id=intent.getIntExtra("club_post_id",0);
        intent.removeExtra("club_post_id");if(id>0){int comment=notificationComment;navigate("detail",()->{postId=id;notificationComment=comment;});}
        String target=intent.getStringExtra("club_page");
        if("checkin".equals(target)||"reviews".equals(target)){if(api.isLoggedIn())show(target);else{loginDestination=target;show("account");}}
    }

    @Override protected void onResume() {
        super.onResume();openingSpace=false;
        if(navigationOwner!=api.sessionGeneration()){navigation.clear();navigationOwner=api.sessionGeneration();refreshComposer();if(!"compose".equals(screen))loadScreen();}
        else{
            CloudDrafts.State draft=cloud.state();
            if(composeGeneration!=draft.generation||(draft.category>0&&composeCategoryId!=draft.category)||!composeTitle.equals(draft.title)||!composeBody.equals(draft.body))refreshComposer();
        }

        if(root!=null&&appearanceSeen!=AppAppearance.revision(this)){
            pendingScroll=pageScroll==null?0:pageScroll.getScrollY();syncAppearance();pageRefresh.close();ModalDialogs.close(this);buildShell();search.setText(query);updateSearchHeader();loadScreen();
        }
        if (returnFromAdmin) { returnFromAdmin = false; loadScreen(); }
        if(headerAvatar!=null)refreshHeaderAvatar(true);
        openingUpdates=false;application.updates().attach(this,null);
    }

    @Override protected void onPause(){if(application!=null)application.updates().detach(this);super.onPause();}

    private void acceptWebIntent(Intent intent){
        int draft=intent.getIntExtra("cloud_draft_id",0);if(intent.hasExtra("cloud_draft_id")&&draft>=0){intent.removeExtra("cloud_draft_id");if(externalRoot&&navigation.isEmpty()&&"forum".equals(screen)){screen="compose";updateSearchHeader();refreshNav();}ui.post(()->openDraft(draft));}
        if(intent.hasExtra("notification_comment_id")){notificationComment=Math.max(0,intent.getIntExtra("notification_comment_id",0));intent.removeExtra("notification_comment_id");}
        String source=intent.getStringExtra("web_problem_platform"),id=intent.getStringExtra("web_problem_id");
        if(source!=null&&id!=null&&!id.isEmpty()){try{JSONObject problem=new JSONObject().put("platform",source).put("problem_id",id);intent.removeExtra("web_problem_id");if(externalRoot&&navigation.isEmpty()){selectedProblem=problem;screen="problem_detail";}else openProblem(problem);}catch(org.json.JSONException ignored){}}
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putLong("session_generation",api.sessionGeneration());
        state.putLong("markdown_owner",markdownOwner);state.putLong("markdown_draft_generation",markdownGeneration);
        state.putParcelableArrayList("navigation_history",navigationOwner==api.sessionGeneration()?navigation.snapshot():new java.util.ArrayList<Bundle>());
        savePageState(state);
    }

    private void savePageState(Bundle state) {
        state.putBoolean("choosing_post_image",choosingPostImage);state.putLong("image_owner",imageOwner);state.putLong("image_draft_generation",imageDraftGeneration);
        if(pendingPostImage!=null)state.putString("pending_post_image",pendingPostImage.toString());
        // UI state only: cookies, CSRF and passwords stay out of saved instance state.
        state.putString("screen", "login_wait".equals(screen) ? "account" : screen);
        state.putInt("scroll_y",pendingScroll>=0?pendingScroll:pageScroll==null?0:pageScroll.getScrollY());
        state.putString("query", query); state.putString("category", category); state.putString("sort", sort);
        state.putString("days", days); state.putString("platform", platform); state.putInt("page", page);
        state.putInt("rank_page_size", rankPageSize); state.putString("rank_sort", rankSort);
        state.putStringArrayList("rank_platforms", new java.util.ArrayList<>(rankPlatforms));
        state.putString("profile_platform",profilePlatform);state.putInt("post_id", postId); state.putString("problem_state", problemState);
        state.putString("problem_scope",problemScope);state.putInt("notification_comment",notificationComment);
        state.putString("contest_identifier",contestIdentifier);
        state.putString("member_return", memberReturnScreen);
        state.putString("member_preview", memberPreview == null ? "" : memberPreview.toString());
        if (selectedProblem != null) {
            state.putString("problem_platform", selectedProblem.optString("platform"));
            state.putString("problem_id", selectedProblem.optString("problem_id"));
        }
        state.putString("search_scope", searchScope); state.putString("search_return", searchReturn);
        state.putString("compose_title", composeTitle); state.putString("compose_body", composeBody);
        state.putInt("compose_category", composeCategoryId); state.putInt("compose_draft", composeDraftId);
        state.putLong("compose_revision", composeRevision); state.putLong("compose_saved_revision", composeSavedRevision);
        state.putInt("comment_post", commentPostId); state.putString("comment_body", commentBody); state.putInt("comment_parent", commentParent);
    }

    private void restoreNavigation(Bundle state) {
        pendingScroll=Math.max(0,state.getInt("scroll_y",0));
        choosingPostImage=state.getBoolean("choosing_post_image",false);imageOwner=state.getLong("image_owner",-1);imageDraftGeneration=state.getLong("image_draft_generation",-1);
        String pending=state.getString("pending_post_image","");if(!pending.isEmpty())pendingPostImage=android.net.Uri.parse(pending);
        screen = state.getString("screen", "forum");
        query = state.getString("query", ""); category = state.getString("category", ""); sort = state.getString("sort", "latest");
        days = state.getString("days", "7");if(!java.util.Arrays.asList("7","30","90","365","all").contains(days))days="7"; platform = state.getString("platform", ""); page = state.getInt("page", 1);
        rankPageSize = state.getInt("rank_page_size",20); rankSort = state.getString("rank_sort", "total_count");
        java.util.ArrayList<String> platforms = state.getStringArrayList("rank_platforms");
        if (platforms != null && !platforms.isEmpty()) { rankPlatforms.clear(); rankPlatforms.addAll(platforms); }
        profilePlatform=state.getString("profile_platform","all");postId = state.getInt("post_id", 0); problemState = state.getString("problem_state", "");
        problemScope=state.getString("problem_scope","all");notificationComment=state.getInt("notification_comment",0);
        contestIdentifier=state.getString("contest_identifier","");
        memberReturnScreen = state.getString("member_return", "forum");
        try {
            String member = state.getString("member_preview", "");
            memberPreview = member.isEmpty() ? null : new JSONObject(member);
            selectedProblem=null;
            if (state.containsKey("problem_id")) selectedProblem = new JSONObject()
                    .put("platform", state.getString("problem_platform")).put("problem_id", state.getString("problem_id"));
        } catch (org.json.JSONException ignored) { memberPreview = null; selectedProblem = null; }
        searchScope = state.getString("search_scope", "forum"); searchReturn = state.getString("search_return", "forum");
        if(state.containsKey("compose_title")){
            composeTitle = state.getString("compose_title", ""); composeBody = state.getString("compose_body", "");
            composeCategoryId = state.getInt("compose_category", 0); composeDraftId = state.getInt("compose_draft", 0);
            composeRevision = state.getLong("compose_revision", 0); composeSavedRevision = state.getLong("compose_saved_revision", 0);
        }
        commentPostId = state.getInt("comment_post", 0); commentBody = state.getString("comment_body", ""); commentParent = state.getInt("comment_parent", 0);
    }

    @Override protected void onDestroy() {
        ++requestSerial;
        ui.removeCallbacksAndMessages(null);
        ModalDialogs.close(this);

        io.shutdownNow();
        previewIo.shutdownNow();if(pageRefresh!=null)pageRefresh.close();
        avatarIo.shutdownNow();
        super.onDestroy();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if(requestCode==PICK_POST_IMAGE){choosingPostImage=false;if(resultCode==RESULT_OK&&data!=null&&data.getData()!=null){pendingPostImage=data.getData();consumePostImage();}return;}
        if(requestCode==PICK_COVER&&resultCode==RESULT_OK&&data!=null&&data.getData()!=null){
            android.net.Uri selected=data.getData();
            io.execute(()->{try{ProfileCover.save(this,selected);present(()->{loadScreen();message("个人中心背景已保存到本机。");});}catch(Exception e){present(()->failureDialog(e));}});return;
        }
        if(requestCode==IMPORT_MARKDOWN && resultCode==RESULT_OK && data!=null && data.getData()!=null){
            android.net.Uri selected=data.getData();
            long owner=markdownOwner,generation=markdownGeneration;
            io.execute(()->{try(InputStream input=getContentResolver().openInputStream(selected);ByteArrayOutputStream out=new ByteArrayOutputStream()){
                if(input==null)throw new IllegalStateException("无法读取文件");byte[] buf=new byte[4096];int count;
                while((count=input.read(buf))!=-1){if(out.size()+count>100000)throw new IllegalArgumentException("Markdown 文件过大");out.write(buf,0,count);}
                String text=new String(out.toByteArray(),StandardCharsets.UTF_8);if(text.startsWith("\uFEFF"))text=text.substring(1);
                if(text.length()>20000)throw new IllegalArgumentException("正文最多20000字");final String markdown=text;
                present(()->{if(isFinishing()||isDestroyed())return;if(owner!=api.sessionGeneration()||generation!=cloud.generation()||!currentComposer(generation)){actionNotice.show("导入",new IllegalStateException("账号或草稿已切换，请重新导入"));return;}composeBody=markdown;composerChanged();loadScreen();});
            }catch(Exception e){present(()->failureDialog(e));}});return;
        }
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
                    if (bytes.size() + count > 20 * 1024 * 1024) throw new IllegalArgumentException("原始头像不能超过20 MB。");
                    bytes.write(buffer, 0, count);
                }
                api.uploadAvatar(AvatarTools.compress(bytes.toByteArray()), "image/jpeg");
                present(() -> { message("头像已更新。"); loadScreen(); });
            } catch (Exception e) { present(() -> failureDialog(e)); }
        });
    }

    @Override public void onBackPressed() {
        if (loginBusy || composeBusy) { message("正在处理，请稍候…"); return; }
        if(navigationOwner!=api.sessionGeneration()){navigation.clear();navigationOwner=api.sessionGeneration();}
        if(!allowLeavingEditor(this::onBackPressed))return;
        leaveComposeOnce=false;ModalDialogs.close(this);
        boolean returningFromDetail="detail".equals(screen)||"member".equals(screen);
        Bundle previous=navigation.pop();
        if(previous!=null){restoreNavigation(previous);if("forum".equals(screen)&&!returningFromDetail){query="";page=1;pendingScroll=0;}root.requestFocus();search.setText(query);updateSearchHeader();refreshNav();readFromAction=true;loadScreen();return;}
        if(externalRoot){finish();return;}
        if(!"forum".equals(screen)||!query.isEmpty()){screen="forum";query="";page=1;pendingScroll=0;root.requestFocus();search.setText("");updateSearchHeader();refreshNav();loadScreen();return;}
        super.onBackPressed();
    }

    private Bundle pageSnapshot(){
        Bundle state=new Bundle();savePageState(state);
        // The cloud draft owns editor text. Avoid copying it into every history entry.
        if(!"compose".equals(screen))for(String key:new String[]{"compose_title","compose_body","compose_category","compose_draft","compose_revision","compose_saved_revision"})state.remove(key);
        return state;
    }

    private void restoreScroll(){
        if(pageScroll==null)return;final int target=pendingScroll>=0?pendingScroll:pageScroll.getScrollY();final int serial=requestSerial;
        pageScroll.post(()->{if(serial!=requestSerial||isDestroyed())return;pageScroll.scrollTo(0,target);pendingScroll=-1;});
    }

    private boolean allowLeavingEditor(Runnable proceed){
        if(!"compose".equals(screen)||leaveComposeOnce||!cloud.state().dirty)return true;
        if(ModalDialogs.isShowing(this))return false;
        new ModalDialogs.Builder(this).setTitle("草稿尚未保存")
                .setMessage("离开前保存到账号，云端草稿与网页同步。保存失败时会保留当前编辑内容。")
                .setNegativeButton("继续编辑",null)
                .setNeutralButton("放弃未保存修改",(d,w)->{clearComposer();leaveComposeOnce=true;proceed.run();})
                .setPositiveButton("保存并离开",(d,w)->saveComposer(proceed)).show();return false;
    }

    private void syncAppearance(){
        AppAppearance.load(this);BACKGROUND=MobileStyle.BACKGROUND;PANEL=MobileStyle.PANEL;TEXT=MobileStyle.TEXT;MUTED=MobileStyle.MUTED;
        BRAND=MobileStyle.BRAND;ACCENT=MobileStyle.ACCENT;LINE=MobileStyle.LINE;appearanceSeen=AppAppearance.revision(this);AppAppearance.window(this);
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void loadPage(int serial,Runnable work){
        pageRefresh.register(serial,()->startRead(serial,work));
        pageRefresh.start(serial);java.util.concurrent.atomic.AtomicBoolean delivered=new java.util.concurrent.atomic.AtomicBoolean();
        previewIo.execute(()->{
            loadContext.set(new LoadContext(serial,true,delivered));api.beginReplay();
            try{work.run();}finally{
                api.endReplay();loadContext.remove();
                try{io.execute(()->{api.beginReadCycle();loadContext.set(new LoadContext(serial,false,delivered));try{work.run();}finally{loadContext.remove();}});}
                catch(java.util.concurrent.RejectedExecutionException ignored){/* Activity closed while the cache preview was finishing. */}
            }
        });
    }
    private void startRead(int serial,Runnable work){
        if(isDestroyed()||serial!=requestSerial)return;
        pageRefresh.start(serial);java.util.concurrent.atomic.AtomicBoolean delivered=new java.util.concurrent.atomic.AtomicBoolean();
        try{io.execute(()->{api.beginReadCycle();loadContext.set(new LoadContext(serial,false,delivered));try{work.run();}finally{loadContext.remove();}});}catch(java.util.concurrent.RejectedExecutionException ignored){}
    }
    private void present(Runnable action){
        LoadContext context=loadContext.get();
        Exception readIssue=context!=null&&!context.preview?api.readIssue():null;
        if(context!=null&&context.preview&&!api.replayReady())return;
        runOnUiThread(()->{
            if(isFinishing()||isDestroyed()||context!=null&&context.serial!=requestSerial)return;
            if(context!=null&&context.preview)pageRefresh.cached(context.serial);
            boolean previous=presentingRead;presentingRead=context!=null&&!context.preview;
            try{if(readIssue==null||!pageRefresh.failure(FailureState.title(readIssue)))action.run();}finally{
                AppAppearance.paintFields(root);presentingRead=previous;restoreScroll();
                if(context!=null&&!context.preview&&context.delivered.compareAndSet(false,true))pageRefresh.finish(context.serial);
            }
        });
    }

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
        LinearLayout layout = new SpacedLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new SpacedLayout(this);
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
        box.setPadding(dp(18), dp(18), dp(18), dp(18));
        box.setBackground(shape(MobileStyle.MODULE, 12, 0));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(10);
        content.addView(box, params);
        return box;
    }

    private Button action(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        MobileStyle.button(button,primary);
        return button;
    }

    private void buildShell() {
        root = column();
        root.setFocusableInTouchMode(true);
        root.requestFocus();
        root.setBackground(ProfileCover.drawable(this));
        AppAppearance.content(this,root);

        LinearLayout header = row();
        header.setPadding(dp(14), dp(10), dp(14), dp(10));
        header.setBackgroundColor(MobileStyle.CHROME);
        root.addView(header, new LinearLayout.LayoutParams(-1, dp(64)));
        pageRefresh=new PageRefresh(this,root,1);
        actionNotice=new ActionNotice(this,root,2);

        headerAvatar = avatarButton(44);
        headerAvatar.setContentDescription("进入账号设置");
        headerAvatar.setOnClickListener(view -> show("account"));
        header.addView(headerAvatar, new LinearLayout.LayoutParams(dp(44), dp(44)));

        search = new EditText(this);
        search.setTag("appearance_field_surface");
        search.setSingleLine(true);
        search.setTextSize(13);
        search.setHint("搜索论坛话题");
        search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        search.setBackground(shape(MobileStyle.SEARCH, 20, 0));
        android.graphics.drawable.Drawable magnifier=AppIcons.get(this,"search",MUTED);magnifier.setBounds(0,0,dp(18),dp(18));search.setCompoundDrawables(magnifier,null,null,null);search.setCompoundDrawablePadding(dp(8));
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
        ImageButton tools=new ImageButton(this);MobileStyle.flat(tools);android.graphics.drawable.Drawable plus=getDrawable(R.drawable.skland_add);plus.setTint(MobileStyle.ON_ACCENT);tools.setImageDrawable(plus);tools.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);tools.setBackground(MobileStyle.panel(this,MobileStyle.controlFill(ACCENT),12,0));tools.setPadding(dp(8),dp(8),dp(8),dp(8));tools.setContentDescription("常用工具");tools.setOnClickListener(v->showTools(tools));header.addView(tools,new LinearLayout.LayoutParams(dp(44),dp(44)));

        ScrollView scroll = new ScrollView(this);
        pageScroll=scroll;
        scroll.setFillViewport(true);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content = column();
        content.setPadding(dp(12), dp(12), dp(12), dp(24));
        scroll.addView(content);

        nav = row();
        nav.setBackgroundColor(MobileStyle.CHROME);
        nav.setPadding(dp(3), dp(5), dp(3), dp(5));
        root.addView(nav, new LinearLayout.LayoutParams(-1, dp(65)));
        refreshNav();
    }

    private void refreshNav() {
        nav.removeAllViews();
        String[] ids = {"forum", "rank", "compose", "problems", "mine"};
        String[] names = {"主页", "排名", "发帖", "题库", "个人中心"};
        for (int i = 0; i < ids.length; i++) {
            String id = ids[i];
            boolean compose = "compose".equals(id);
            boolean active=id.equals(screen);LinearLayout holder=column();holder.setGravity(Gravity.CENTER);holder.setContentDescription(names[i]);holder.setOnClickListener(v->show(id));
            android.widget.ImageView icon=new android.widget.ImageView(this);icon.setImageDrawable(AppIcons.get(this,id,compose?MobileStyle.ON_ACCENT:active?TEXT:MUTED));
            if(compose){icon.setPadding(dp(5),dp(5),dp(5),dp(5));icon.setBackground(shape(MobileStyle.controlFill(ACCENT),16,0));icon.setImageDrawable(AppIcons.get(this,id,MobileStyle.ON_ACCENT));}
            holder.addView(icon,new LinearLayout.LayoutParams(dp(compose?44:23),dp(compose?44:23)));
            if(!compose){TextView title=label(names[i],10,active?TEXT:MUTED,active);title.setGravity(Gravity.CENTER);holder.addView(title);View indicator=new View(this);indicator.setBackground(shape(active?ACCENT:Color.TRANSPARENT,2,0));LinearLayout.LayoutParams mark=new LinearLayout.LayoutParams(dp(16),dp(3));mark.topMargin=dp(3);holder.addView(indicator,mark);}
            nav.addView(holder,new LinearLayout.LayoutParams(0,-1,1));
        }
    }

    private JSONArray searchHistory() {
        try { return new JSONArray(preferences.getString("search_history", "[]")); }
        catch (Exception e) { return new JSONArray(); }
    }

    private void openSearch() {
        if (loginBusy || !java.util.Arrays.asList("forum", "rank", "problems").contains(screen)) return;
        searchScope = screen; searchReturn = screen;
        navigation.push(pageSnapshot());pendingScroll=0;
        screen = "search"; ++requestSerial; refreshNav();
        pageRefresh.reset(requestSerial);
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
        Button cancel = action("取消搜索", false); cancel.setOnClickListener(v -> onBackPressed()); content.addView(cancel);
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

    private boolean readFromAction;
    private void show(String next) {
        navigate(next,null);
    }

    private void navigate(String next,Runnable prepare) {
        if (loginBusy || composeBusy) return;
        if(!next.equals(screen)&&!allowLeavingEditor(()->navigate(next,prepare)))return;
        readFromAction=true;
        leaveComposeOnce = false;
        if (forumFilterDialog != null) forumFilterDialog.dismiss();
        if(java.util.Arrays.asList("club","sheets","discussions","mistakes","reviews","templates","checkin").contains(next)){openTrainingCenter(next);return;}
        if(!next.equals(screen)||prepare!=null){navigation.push(pageSnapshot());pendingScroll=0;}
        if(prepare!=null)prepare.run();
        screen = next;
        query = "";
        page = 1;
        search.setText("");
        updateSearchHeader();
        refreshNav();
        loadScreen();
    }

    private void openPost(int id){navigate("detail",()->{postId=id;notificationComment=0;});}
    private void openProblem(JSONObject problem){navigate("problem_detail",()->selectedProblem=problem);}

    private void updateSearchHeader() {
        search.setEnabled(java.util.Arrays.asList("forum", "rank", "problems").contains(screen));
        String hint = "搜索论坛话题";
        if ("rank".equals(screen)) hint = "搜索公开昵称";
        if ("problems".equals(screen)) hint = "搜索题名或标签";
        if ("mine".equals(screen)) hint = "个人中心";
        if ("account".equals(screen)) hint = "账号设置";
        if ("member".equals(screen)) hint = "成员主页";
        if ("compose".equals(screen)) hint = "发帖编辑";
        search.setHint(hint);
    }

    private void loadScreen() {
        if (loginBusy) return;
        if(navigationOwner!=api.sessionGeneration()){navigation.clear();navigationOwner=api.sessionGeneration();}
        if(api.isLoggedIn()&&api.requiresPasswordChange())screen="account";
        int serial = ++requestSerial;
        pageRefresh.reset(serial);if(readFromAction)pageRefresh.userAction();actionNotice.hide();detailUi=null;composeEditorShown=false;composeBodyInput=null;
        if (!api.isLoggedIn()) defaultAvatar(headerAvatar);
        else refreshHeaderAvatar(false);
        content.removeAllViews();
        loadingRegion = null;
        publicFailure = null;
        publishedFailure = null;
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
        else if (java.util.Arrays.asList("club","sheets","discussions","mistakes","reviews","templates","checkin").contains(screen)){String target=screen;screen="problems";updateSearchHeader();refreshNav();renderProblems(serial);openTrainingCenter(target);}
        else renderMine(serial);
        if(loadingRegion==null)restoreScroll();
    }

    private void heading(String eyebrow, String title, String subtitle) {
        if (!query.isEmpty() && java.util.Arrays.asList("forum", "rank", "problems").contains(screen)) {
            subtitle = "关键词：" + query + "\n" + subtitle;
            title = "搜索结果 · " + title;
        }
        LinearLayout box=HomeBanner.create(this,eyebrow,title,subtitle,"rank".equals(screen)||"account".equals(screen),this::exploreGraph);
        LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(-1,-2);size.bottomMargin=dp(10);content.addView(box,size);
    }

    private void exploreGraph(int initial){
        LinearLayout panel=column();panel.setPadding(dp(12),dp(12),dp(12),dp(16));panel.setBackground(shape(MobileStyle.HERO,12,0));
        GraphArtView graph=new GraphArtView(this,true);graph.setContentDescription("放大的最短路径图谱");panel.addView(graph,new LinearLayout.LayoutParams(-1,dp(236)));TextView status=label("",13,MobileStyle.ON_HERO,true);status.setContentDescription("图谱路径结果");panel.addView(status);
        Spinner nodes=new Spinner(this);nodes.setContentDescription("图谱终点选择");String[] names=new String[GraphRoutes.NAMES.length];for(int i=0;i<names.length;i++)names[i]="终点 "+GraphRoutes.NAMES[i];nodes.setAdapter(MobileStyle.options(this,names));panel.addView(nodes,new LinearLayout.LayoutParams(-1,dp(48)));graph.onTarget(i->{status.setText(graph.status());if(nodes.getSelectedItemPosition()!=i)nodes.setSelection(i);});
        nodes.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> parent,View view,int position,long id){if(graph.target()!=position)graph.select(position);}public void onNothingSelected(AdapterView<?> parent){}});graph.select(initial);nodes.setSelection(initial);
        TextView hint=label("点选节点探索；s 为起点，数字为边权。",11,MobileStyle.ON_HERO,false);panel.addView(hint);detailsDialog("最短路径图谱",panel);
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
        loadingRegion.addView(new CodingCatView(this),new LinearLayout.LayoutParams(dp(180),dp(120)));
        loadingRegion.addView(label(text, 13, MUTED, false));
    }

    private void failureBox(LinearLayout box, String reason, int height, Runnable retry) {
        if(pageRefresh!=null&&presentingRead&&pageRefresh.failure(reason))return;
        int retainedHeight = Math.max(dp(height), box.getHeight());
        box.removeAllViews();
        box.setMinimumHeight(retainedHeight);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(16), dp(16), dp(16), dp(16));
        ErrorModule.style(box);
        TextView title = label(reason, 15, ErrorModule.ink(), true);
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
        if(pageRefresh!=null&&presentingRead&&pageRefresh.failure(FailureState.title(failure)))return;
        if (loadingRegion == null || loadingRegion.getParent() != content) loadingRegion = card();
        failureBox(loadingRegion, FailureState.title(failure), "compose".equals(screen) ? 600 : 320, this::loadScreen);
    }

    private void failureDialog(Exception failure) {
        if(pageRefresh!=null&&PageRefresh.isConnectionFailure(FailureState.title(failure))){pageRefresh.actionFailure(FailureState.title(failure));return;}
        LinearLayout box = column();
        failureBox(box, FailureState.title(failure), 180, null);
        new ModalDialogs.Builder(this).setView(box).setPositiveButton("关闭", null).show();
    }

    private void chips(String[] labels, String[] values, String selected, java.util.function.Consumer<String> onChoose) {
        WrapLayout line = new WrapLayout(this);
        line.setContentDescription("筛选选项，自动换行");
        for (int i = 0; i < labels.length; i++) {
            String value = values[i];
            TextView chip = label(labels[i], 12, TEXT, selected.equals(value));
            MobileStyle.control(chip,false,selected.equals(value),20);
            chip.setGravity(Gravity.CENTER);
            chip.setPadding(dp(13), 0, dp(13), 0);
            chip.setOnClickListener(view -> onChoose.accept(value));
            line.addView(chip, new ViewGroup.LayoutParams(-2, dp(44)));
        }
        content.addView(line,new LinearLayout.LayoutParams(-1,-2));
        space(content, 12);
    }

    private void renderForum(int serial) {
        forumHeader(null);
        loading("正在加载社区话题…");
        loadPage(serial,() -> {
            try {
                String suffix = "?page=" + page + "&page_size=12&sort=" + sort
                        + "&q=" + encode(query) + "&category=" + encode(category);
                JSONObject result = api.getObject(api.publicPostsPath(suffix));
                result.getJSONArray("rows");
                present(() -> { if (serial == requestSerial) showForum(null, result); });
            } catch (Exception e) {
                present(() -> { if (serial == requestSerial) error(e); });
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
        heading("ACMFOREVER / COMMUNITY", "一起交流，一起 AC", "打一辈子爱臭美\n提问 · 题解 · 每一次进步");
        LinearLayout titleRow = row();
        titleRow.addView(label("社区话题", 18, TEXT, true), new LinearLayout.LayoutParams(0, -2, 1));
        ImageButton filter = new ImageButton(this);
        filter.setImageDrawable(AppIcons.get(this,"filter",TEXT));
        filter.setScaleType(ImageButton.ScaleType.CENTER_INSIDE);
        filter.setPadding(dp(10), dp(10), dp(10), dp(10));
        filter.setBackground(shape(MobileStyle.controlFill(!category.isEmpty() || !"latest".equals(sort)
                ? MobileStyle.SELECTED : PANEL), 9, MobileStyle.controlFill(LINE)));
        filter.setContentDescription("筛选社区话题");
        filter.setOnClickListener(view -> {
            if (filterLoading || forumFilterDialog != null && forumFilterDialog.isShowing()) return;
            if (categories != null) { showForumFilters(categories); return; }
            filterLoading = true;
            int serial = requestSerial;
            io.execute(() -> {
                try {
                    JSONArray options = api.getArray("/api/forum/categories");
                    present(() -> { filterLoading = false; if (serial == requestSerial && "forum".equals(screen)) showForumFilters(options); });
                } catch (Exception e) { present(() -> { filterLoading = false; if (serial == requestSerial) failureDialog(e); }); }
            });
        });
        titleRow.addView(filter, new LinearLayout.LayoutParams(dp(44), dp(44)));
        content.addView(titleRow);
        space(content, 10);
    }

    private void showForumFilters(JSONArray categories) {
        if (forumFilterDialog != null && forumFilterDialog.isShowing()) return;
        LinearLayout form=column();form.setPadding(0,dp(2),0,dp(4));
        TextView intro=label("分类与排序可分别选择。",12,MUTED,false);form.addView(intro);space(form,16);
        form.addView(filterSection("话题分类","forum"));
        String[] values=new String[categories.length()+1],names=new String[values.length];values[0]="";names[0]="全部";
        for(int i=0;i<categories.length();i++){JSONObject item=categories.optJSONObject(i);values[i+1]=value(item,"slug","");names[i+1]=value(item,"name","分类");}
        RadioButton[] categoryButtons=filterGrid(form,names,values,category,"forum");
        space(form,18);form.addView(filterSection("排序方式","filter"));
        String[] sortValues={"latest","hot","unanswered"};
        RadioButton[] sortButtons=filterGrid(form,new String[]{"最新发布","热门话题","等待回答"},sortValues,sort,"history");
        forumFilterDialog=new ModalDialogs.Builder(this).setTitle("筛选社区话题").setView(form).setNegativeButton("取消",null)
                .setPositiveButton("应用筛选",(dialog,which)->{
                    for(int i=0;i<values.length;i++)if(categoryButtons[i].isChecked())category=values[i];
                    for(int i=0;i<sortValues.length;i++)if(sortButtons[i].isChecked())sort=sortValues[i];
                    page=1;loadScreen();
                }).create();
        forumFilterDialog.setOnDismissListener(d->forumFilterDialog=null);ModalDialogs.show(forumFilterDialog);
    }
    private TextView filterSection(String title,String icon){TextView text=label(title,14,TEXT,true);AppIcons.on(text,icon,BRAND,21);return text;}
    private android.graphics.drawable.Drawable choiceBackground(){
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        states.addState(new int[]{android.R.attr.state_checked},shape(MobileStyle.controlFill(MobileStyle.SELECTED),12,MobileStyle.controlFill(BRAND)));
        states.addState(new int[]{},shape(MobileStyle.controlFill(BACKGROUND),12,0));return states;
    }
    private RadioButton[] filterGrid(LinearLayout form,String[] names,String[] values,String selected,String icon){
        android.widget.GridLayout grid=new android.widget.GridLayout(this);grid.setColumnCount(2);form.addView(grid,new LinearLayout.LayoutParams(-1,-2));
        RadioButton[] options=new RadioButton[names.length];
        for(int i=0;i<names.length;i++){
            RadioButton option=new RadioButton(this);options[i]=option;option.setId(View.generateViewId());option.setText(names[i]);
            option.setTextSize(13);option.setTextColor(TEXT);option.setButtonDrawable((android.graphics.drawable.Drawable)null);
            option.setBackground(choiceBackground());option.setPadding(dp(12),dp(9),dp(12),dp(9));option.setMinHeight(dp(50));
            AppIcons.on(option,icon,BRAND,20);option.setChecked(selected.equals(values[i]));MobileStyle.flat(option);
            android.widget.GridLayout.LayoutParams params=new android.widget.GridLayout.LayoutParams();params.width=0;params.height=-2;
            params.columnSpec=android.widget.GridLayout.spec(i%2,1f);params.rowSpec=android.widget.GridLayout.spec(i/2);
            params.setMargins(i%2==0?0:dp(4),dp(8),i%2==0?dp(4):0,0);grid.addView(option,params);
            option.setOnClickListener(v->{for(RadioButton other:options)if(other!=null)other.setChecked(other==option);});
        }
        return options;
    }

    private void addPost(JSONObject post) {
        if (post == null) return;
        LinearLayout box = card();
        LinearLayout authorRow = row();
        ImageButton avatar = avatarButton(32);
        avatar.setContentDescription("查看" + value(post, "author_name", "ACM 成员") + "的公开主页");
        avatar.setOnClickListener(view -> openMember(post, "forum"));
        loadAvatar(avatar, value(post, "author_avatar_url", ""));
        authorRow.addView(avatar, new LinearLayout.LayoutParams(dp(32), dp(32)));
        LinearLayout authorCopy=column();authorCopy.setPadding(dp(10),0,0,0);
        TextView author = label(post.optString("author_name", "ACM 成员"), 13, TEXT, true);
        author.setOnClickListener(view -> openMember(post, "forum"));
        authorCopy.addView(author);if(post.optLong("created_at")>0)authorCopy.addView(label(date(post.optLong("created_at")),10,MUTED,false));
        authorRow.addView(authorCopy, new LinearLayout.LayoutParams(0, -2, 1));
        box.addView(authorRow);
        space(box, 12);
        box.addView(label(post.optString("title"), 17, TEXT, true));
        if(!api.communityImageUrl(post.optString("cover_url")).isEmpty())box.addView(new CommunityCover(this,post.optString("cover_url"),true));
        space(box, 6);
        TextView excerpt=label(post.optString("excerpt"),13,MUTED,false);excerpt.setMaxLines(3);excerpt.setEllipsize(android.text.TextUtils.TruncateAt.END);box.addView(excerpt);
        space(box,10);TextView categoryTag=label("# "+post.optString("category_name", "话题"),11,MUTED,false);
        categoryTag.setPadding(dp(8),dp(4),dp(8),dp(4));categoryTag.setBackground(shape(BACKGROUND,10,0));box.addView(categoryTag,new LinearLayout.LayoutParams(-2,-2));
        space(box,14);LinearLayout interactions=row();interactions.addView(label(post.optInt("views_count")+" 阅读",10,MUTED,false),new LinearLayout.LayoutParams(0,-2,1));
        postMetric(interactions,"comment",post.optInt("comments_count"));postMetric(interactions,"like",post.optInt("likes_count"));box.addView(interactions);
        int id = post.optInt("id");
        box.setOnClickListener(view -> openPost(id));
    }

    private void renderDetail(int serial) {
        loading("正在加载话题详情…");
        loadPage(serial,() -> {
            try {
                JSONObject result = api.getObject(api.publicPostsPath("/"+postId+(notificationComment>0?"?comment_id="+notificationComment:"")));
                present(() -> { if (serial == requestSerial) showDetail(result); });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showDetail(JSONObject post) {
        if(detailUi!=null&&detailUi.serial==requestSerial&&detailUi.id==postId){
            DetailUi current=detailUi;
            // A read started before a write must not replace optimistic/confirmed local state.
            if(current.interacted)return;
            String oldBody=current.post.optString("body");
            try{java.util.Iterator<String> keys=post.keys();while(keys.hasNext()){String key=keys.next();current.post.put(key,post.get(key));}}catch(org.json.JSONException ignored){}
            current.title.setText(post.optString("title"));current.category.setText(post.optString("category_name","话题"));
            current.author.setText(post.optString("author_name","ACM 成员")+" · "+date(post.optLong("created_at")));
            current.reads.setText(post.optInt("views_count")+" 阅读");
            if(!oldBody.equals(post.optString("body"))){current.body.removeAllViews();current.body.addView(new ContentView(this,post.optString("body"),false,this::openBrowser));}
            reactionLabel(current.like,"like",current.post);reactionLabel(current.bookmark,"bookmark",current.post);renderComments(current,post.optJSONArray("comments"));return;
        }
        content.removeAllViews();
        DetailUi current=new DetailUi();current.serial=requestSerial;current.id=postId;current.post=post;detailUi=current;
        Button back=action("← 返回",false);back.setOnClickListener(v->onBackPressed());content.addView(back);space(content,10);
        LinearLayout box=card();current.category=label(post.optString("category_name","话题"),11,BRAND,true);box.addView(current.category);space(box,8);
        current.title=label(post.optString("title"),22,TEXT,true);box.addView(current.title);space(box,8);
        current.author=label(post.optString("author_name","ACM 成员")+" · "+date(post.optLong("created_at")),12,BRAND,true);
        current.author.setOnClickListener(v->openMember(post,"detail"));box.addView(current.author);space(box,16);
        if(!api.communityImageUrl(post.optString("cover_url")).isEmpty())box.addView(new CommunityCover(this,post.optString("cover_url"),false));
        current.body=column();current.body.addView(new ContentView(this,post.optString("body"),false,this::openBrowser));box.addView(current.body);
        current.reads=label(post.optInt("views_count")+" 阅读",12,MUTED,false);box.addView(current.reads);
        LinearLayout actions=row();current.like=action("",false);current.bookmark=action("",false);Button report=action("举报",false);
        reactionLabel(current.like,"like",post);reactionLabel(current.bookmark,"bookmark",post);
        current.like.setOnClickListener(v->toggleReaction(current.like,"like",post));current.bookmark.setOnClickListener(v->toggleReaction(current.bookmark,"bookmark",post));
        report.setOnClickListener(v->{
            if(!requireLogin("detail"))return;EditText reason=new EditText(this);reason.setHint("请说明举报原因（3–500 字）");
            new ModalDialogs.Builder(this).setTitle("举报话题").setView(reason).setNegativeButton("取消",null).setPositiveButton("提交",(d,w)->{
                String text=reason.getText().toString().trim();int length=text.codePointCount(0,text.length());
                if(length<3||length>500){message("举报原因需要 3–500 字。");return;}forumAction(report,"report",text,0);
            }).show();
        });
        for(Button b:new Button[]{current.like,current.bookmark,report}){b.setMinWidth(0);b.setPadding(dp(8),0,dp(8),0);actions.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));}box.addView(actions);
        if(post.optBoolean("viewer_is_author")){
            Button progress=action("投稿进度 / 修改帖子",false);progress.setOnClickListener(v->openWebFeature("progress",current.id));box.addView(progress);
            Button remove=action("删除帖子",false);box.addView(remove);
            remove.setOnClickListener(v->new ModalDialogs.Builder(this).setTitle("删除帖子？").setMessage("删除后无法恢复。")
                    .setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->mutate(remove,()->api.writeObject("DELETE","/api/forum/posts/"+current.id,new JSONObject()),()->show("forum"))).show());
        }
        if(commentPostId!=postId){commentPostId=postId;commentBody="";commentParent=0;}
        space(content,9);content.addView(label("讨论区",18,TEXT,true));current.editor=card();
        current.input=new EditText(this);current.input.setMinLines(3);current.input.setGravity(Gravity.TOP);
        current.input.setHint("支持 Markdown、代码和公式（2–5000 字）");current.input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(10000)});
        current.input.setText(commentBody);current.input.addTextChangedListener(watch(text->{commentBody=text;current.interacted=true;}));current.editor.addView(current.input);
        WrapLayout format=new WrapLayout(this);format.setContentDescription("评论Markdown工具");
        String[][] marks={{"加粗","**","**"},{"斜体","*","*"},{"代码","`","`"},{"代码块","\n```cpp\n","\n```\n"},{"公式","$","$"},{"引用","\n> ",""},{"链接","[","](https://)"}};
        for(String[] mark:marks){Button tool=action(mark[0],false);compactTool(tool);tool.setOnClickListener(v->insertFormat(current.input,mark[1],mark[2]));format.addView(tool);}
        Button preview=action("预览评论",false);preview.setContentDescription("预览评论");compactTool(preview);preview.setOnClickListener(v->{LinearLayout article=column();article.addView(new ContentView(this,current.input.getText().toString(),false,this::openBrowser));detailsDialog("评论预览",article);});format.addView(preview);current.editor.addView(format,new LinearLayout.LayoutParams(-1,-2));
        current.replyTo=label(commentParent>0?"正在回复评论 #"+commentParent+" · 点击取消回复":"发布新的评论",12,BRAND,true);
        current.replyTo.setPadding(0,dp(10),0,dp(10));current.replyTo.setMinHeight(dp(44));current.replyTo.setOnClickListener(v->{current.interacted=true;commentParent=0;current.replyTo.setText("发布新的评论");});current.editor.addView(current.replyTo);
        current.send=action("发布评论",true);current.send.setOnClickListener(v->sendComment(current));current.editor.addView(current.send);
        current.comments=column();content.addView(current.comments,new LinearLayout.LayoutParams(-1,-2));renderComments(current,post.optJSONArray("comments"));
        if(notificationComment>0){int target=notificationComment;current.comments.postDelayed(()->{View comment=current.comments.findViewWithTag("comment-"+target);if(comment!=null&&detailUi==current){comment.setBackground(shape(MobileStyle.SELECTED,12,BRAND));comment.requestRectangleOnScreen(new android.graphics.Rect(0,0,comment.getWidth(),comment.getHeight()),false);}},350);}
    }
    private void renderComments(DetailUi current,JSONArray comments){
        current.comments.removeAllViews();
        if(comments==null||comments.length()==0){TextView empty=label("暂无已发布评论。",13,MUTED,false);empty.setTag("empty");empty.setPadding(dp(16),dp(14),dp(16),dp(14));current.comments.addView(empty);return;}
        for(int i=0;i<comments.length();i++){JSONObject comment=comments.optJSONObject(i);if(comment==null)continue;
            LinearLayout item=commentCard();item.addView(label(comment.optString("author_name","ACM 成员")+" · "+date(comment.optLong("created_at")),12,BRAND,true));
            if(comment.optInt("parent_id")>0)item.addView(label("回复评论 #"+comment.optInt("parent_id"),11,MUTED,false));
            item.setTag("comment-"+comment.optInt("id"));item.addView(new ContentView(this,comment.optString("body"),false,this::openBrowser));if(comment.optInt("parent_id")==0)addReply(item,current,comment.optInt("id"),comment.optString("author_name"));current.comments.addView(item);
        }
    }
    private LinearLayout commentCard(){LinearLayout item=column();item.setPadding(dp(16),dp(14),dp(16),dp(14));item.setBackground(shape(MobileStyle.MODULE,12,0));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(10);item.setLayoutParams(params);return item;}
    private void addReply(LinearLayout item,DetailUi current,int id,String author){
        Button reply=action("回复",false);reply.setOnClickListener(v->{
            if(!requireLogin("detail"))return;current.interacted=true;commentParent=id;current.replyTo.setText("正在回复 "+author+" · 点击取消回复");current.input.requestFocus();
            ((ScrollView)content.getParent()).smoothScrollTo(0,current.editor.getTop());
            ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).showSoftInput(current.input,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);
        });item.addView(reply);
    }
    private void sendComment(DetailUi current){
        if(current.sending||!requireLogin("detail"))return;
        String text=current.input.getText().toString().trim();int length=text.codePointCount(0,text.length());
        if(length<2||length>5000){actionNotice.show("评论发送",new IllegalArgumentException("评论需要 2–5000 字"));return;}
        int parent=commentParent;long account=api.sessionGeneration();current.interacted=true;current.sending=true;current.send.setEnabled(false);current.send.setText("正在发送…");
        actionNotice.hide();View empty=current.comments.findViewWithTag("empty");if(empty!=null)current.comments.removeView(empty);
        LinearLayout pending=commentCard();TextView state=label("我 · 正在发送…",12,MUTED,true);pending.addView(state);
        if(parent>0)pending.addView(label("回复评论 #"+parent,11,MUTED,false));pending.addView(new ContentView(this,text,false,this::openBrowser));current.comments.addView(pending,0);
        io.execute(()->{
            int id=0;Exception failure=null;try{JSONObject response=api.postAction(current.id,"comments",text,parent);id=response.getInt("id");if(id<=0)throw new org.json.JSONException("缺少评论编号");}catch(Exception e){failure=e;}
            int confirmed=id;Exception error=failure;
            present(()->{
                current.sending=false;if(current!=detailUi||current.serial!=requestSerial||account!=api.sessionGeneration()&&!expiredWrite(error))return;
                current.send.setEnabled(true);current.send.setText("发布评论");
                if(error==null){
                    state.setText("我 · 评论 #"+confirmed);state.setTextColor(BRAND);
                    if(text.equals(current.input.getText().toString().trim()))current.input.setText("");
                    if(commentParent==parent){commentParent=0;current.replyTo.setText("发布新的评论");}
                    if(parent==0)addReply(pending,current,confirmed,"我");
                }else{state.setText("发送失败 · 正文保留在输入框");state.setTextColor(0xffaf2424);pending.setBackground(shape(0xfffff0ef,12,0xfff2c7c2));actionNotice.show("评论发送",error);}
            });
        });
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
            present(() -> {
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
        mutate(button, () -> api.postAction(target, kind, text, parent), () -> message("举报已提交，等待管理员核查。"));
    }

    private void reactionLabel(Button button,String kind,JSONObject post){
        boolean liked="like".equals(kind),active=post.optBoolean(liked?"viewer_liked":"viewer_bookmarked");
        button.setText(liked?(active?"已赞 ":"赞 ")+post.optInt("likes_count"):(active?"已收藏":"收藏"));
        AppIcons.on(button,liked?"like":"bookmark",active?BRAND:MUTED,18);
        button.setContentDescription(liked?"话题点赞":"收藏话题");
    }
    private void toggleReaction(Button button,String kind,JSONObject post){
        if(Boolean.TRUE.equals(button.getTag())||!requireLogin("detail"))return;
        String key="like".equals(kind)?"viewer_liked":"viewer_bookmarked";boolean old=post.optBoolean(key);int oldCount=post.optInt("likes_count");
        int serial=requestSerial,target=post.optInt("id",postId);long account=api.sessionGeneration();if(detailUi!=null)detailUi.interacted=true;
        button.setTag(Boolean.TRUE);button.setEnabled(false);button.setAlpha(.65f);actionNotice.hide();
        try{post.put(key,!old);if("like".equals(kind))post.put("likes_count",Math.max(0,oldCount+(old?-1:1)));}catch(org.json.JSONException ignored){}
        reactionLabel(button,kind,post);
        io.execute(()->{
            JSONObject response=null;Exception failure=null;try{response=api.postAction(target,kind,"",0);response.getBoolean("active");}catch(Exception e){failure=e;}
            JSONObject result=response;Exception error=failure;
            present(()->{
                if(serial!=requestSerial||account!=api.sessionGeneration()&&!expiredWrite(error))return;
                button.setTag(null);button.setEnabled(true);button.setAlpha(1f);
                boolean active=error==null?result.optBoolean("active"):old;
                try{post.put(key,active);if("like".equals(kind))post.put("likes_count",Math.max(0,oldCount+(old==active?0:active?1:-1)));}catch(org.json.JSONException ignored){}
                reactionLabel(button,kind,post);if(error!=null)actionNotice.show("like".equals(kind)?"点赞":"收藏",error);
            });
        });
    }

    private boolean expiredWrite(Exception failure){return failure instanceof ApiClient.ApiException&&((ApiClient.ApiException)failure).status==401&&!api.isLoggedIn();}

    private void renderRank(int serial) {
        rankHeader();
        loading("正在加载排名…");
        final String range=days, ordering=rankSort, selectedPlatforms=String.join(",",rankPlatforms), searchText=query;
        final int requestedPage=page, size=rankPageSize;
        loadPage(serial,() -> {
            try {
                JSONObject result = api.leaderboard(range,ordering,selectedPlatforms,searchText,requestedPage,size);
                result.getJSONArray("rows");
                present(() -> { if (serial == requestSerial) showRank(result); });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void rankHeader(){
        heading("ACMFOREVER / RANKING", "每一题，都算数", "社区排行榜\n仅展示所选平台合计通过数大于 0 的成员");
        chips(new String[]{"近7日","近30日","近90日","近1年","生涯"},new String[]{"7","30","90","365","all"},days,
            value->{if(days.equals(value))return;days=value;page=1;loadScreen();});
        Button filter=action("平台组合 · 排序 · 每页数量",false);filter.setOnClickListener(v->showRankFilter());content.addView(filter);
        String[] names={"Codeforces","洛谷","AtCoder","牛客","校 OJ"}, keys={"codeforces","luogu","atcoder","nowcoder","cjlu"};
        java.util.List<String> selected=new java.util.ArrayList<>();for(int i=0;i<keys.length;i++)if(rankPlatforms.contains(keys[i]))selected.add(names[i]);
        TextView summary=label(String.join(" / ",selected)+" · 每页"+rankPageSize+"人",12,MUTED,false);summary.setPadding(0,dp(10),0,dp(10));content.addView(summary);
    }

    private void showRank(JSONObject result) {
        content.removeAllViews();
        page=result.optInt("page",1);
        rankHeader();

        JSONArray rows = result.optJSONArray("rows");
        if (rows == null || rows.length() == 0) status("暂无符合条件的成员。");
        else for (int i = 0; i < rows.length(); i++) {
            JSONObject user = rows.optJSONObject(i);
            if (user == null||user.optInt("total_count")<=0) continue;
            LinearLayout box = card();
            LinearLayout identity = row();
            int position=(page-1)*rankPageSize+i+1;TextView number=label(String.format(java.util.Locale.ROOT,"%02d",position),20,position<=3?BRAND:MUTED,true);identity.addView(number,new LinearLayout.LayoutParams(dp(40),-2));
            ImageButton avatar = avatarButton(36);
            avatar.setContentDescription("查看" + value(user, "name", "ACM 成员") + "的公开主页");
            avatar.setOnClickListener(view -> openMember(user, "rank"));
            loadAvatar(avatar, value(user, "avatar_url", ""));
            identity.addView(avatar, new LinearLayout.LayoutParams(dp(36), dp(36)));
            LinearLayout person=column();person.setPadding(dp(10),0,dp(6),0);TextView nickname=label(user.optString("name", "ACM 成员"),15,TEXT,true);nickname.setMaxLines(1);nickname.setEllipsize(android.text.TextUtils.TruncateAt.END);person.addView(nickname);person.addView(label(user.optString("status",""),10,MUTED,false));identity.addView(person,new LinearLayout.LayoutParams(0,-2,1));
            LinearLayout total=column();TextView ac=label(String.valueOf(user.optInt("total_count")),25,TEXT,true);ac.setGravity(Gravity.RIGHT);total.addView(ac);total.addView(label("AC / 通过",9,BRAND,true));identity.addView(total);
            box.addView(identity);
            space(box, 5);
            box.addView(label("CF " + user.optInt("cf_count")
                    + "  ·  洛谷 " + user.optInt("luogu_count"), 12, MUTED, false));
            box.addView(label("AtCoder " + user.optInt("atcoder_count") + " · 牛客 " + user.optInt("nowcoder_count") + " · 校 OJ " + user.optInt("cjlu_count"), 12, MUTED, false));
            box.setOnClickListener(view -> openMember(user, "rank"));
        }
        addRankPager(result.optInt("total"));
    }

    private void renderProblems(int serial) {
        if(!java.util.Arrays.asList("codeforces","atcoder","luogu","nowcoder","cjlu").contains(platform))platform="codeforces";
        heading("PROBLEM BANK", "题库", "找一道适合今天的题，继续向 AC 前进。");
        addClubEntry();
        if (api.isUnconfigured()) { error(connectionFailure()); return; }
        if (!api.isLoggedIn()) {
            failureBox(card(), "未登录", 320, null);
            Button login = action("进入账号设置登录", true);
            login.setOnClickListener(view -> { loginDestination = "problems"; show("account"); });
            content.addView(login);
            return;
        }
        loading("正在加载题库…");
        loadPage(serial,() -> {
            try {
                String path = "/api/me/problems?page=" + page + "&page_size=20&platform="
                        + encode(platform) + "&tag=" + encode(query) + "&state=" + problemState+"&scope="+problemScope;
                JSONObject result = api.getObject(path);
                result.getJSONArray("items");
                present(() -> { if (serial == requestSerial) showProblems(result); });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showProblems(JSONObject result) {
        content.removeAllViews();
        heading("PROBLEM BANK", "题库", "找一道适合今天的题，继续向 AC 前进。");
        addClubEntry();
        chips(new String[]{"Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"},
                new String[]{"codeforces", "luogu", "atcoder", "nowcoder", "cjlu"}, platform,
                value -> { platform = value; page = 1; loadScreen(); });
        chips(new String[]{"全部题目","我已 AC"},new String[]{"all","solved"},problemScope,value->{problemScope=value;page=1;loadScreen();});
        chips(new String[]{"全部收藏状态", "已收藏"}, new String[]{"", "favorite"}, problemState, value -> { problemState = value; page = 1; loadScreen(); });
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
            detail.setOnClickListener(v -> openProblem(problem)); box.addView(detail);
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
            checks[i].setChecked(rankPlatforms.contains(values[i]));checks[i].setBackground(choiceBackground());checks[i].setTextColor(TEXT);checks[i].setPadding(dp(12),dp(8),dp(12),dp(8));checks[i].setMinHeight(dp(50));
            android.graphics.drawable.Drawable mark=PlatformAssets.logo(this,values[i]);mark.setBounds(0,0,dp(36),dp(28));checks[i].setCompoundDrawablesRelative(null,null,mark,null);form.addView(checks[i],new LinearLayout.LayoutParams(-1,-2));
        }
        form.addView(label("排序方式", 14, TEXT, true));
        String[] sorts = {"total_count", "cf_count", "luogu_count", "atcoder_count", "nowcoder_count", "cjlu_count"};
        Spinner ordering = spinner(new String[]{"总 AC 数", "Codeforces", "洛谷", "AtCoder", "牛客", "校 OJ"});
        ordering.setSelection(Math.max(0,java.util.Arrays.asList(sorts).indexOf(rankSort))); form.addView(ordering);
        form.addView(label("每页显示",14,TEXT,true));
        int[] sizes={10,20,50,100}; Spinner size=spinner(new String[]{"10人","20人","50人","100人"});
        for(int i=0;i<sizes.length;i++)if(sizes[i]==rankPageSize)size.setSelection(i);form.addView(size);
        AlertDialog dialog = new ModalDialogs.Builder(this).setTitle("排名筛选").setView(form).setNegativeButton("取消", null).setPositiveButton("应用", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            java.util.LinkedHashSet<String> selected = new java.util.LinkedHashSet<>();
            for (int i = 0; i < values.length; i++) if (checks[i].isChecked()) selected.add(values[i]);
            if (selected.isEmpty()) { android.widget.Toast.makeText(this,"至少选择一个平台",android.widget.Toast.LENGTH_SHORT).show(); return; }
            rankPlatforms.clear(); rankPlatforms.addAll(selected); rankSort = sorts[ordering.getSelectedItemPosition()];rankPageSize=sizes[size.getSelectedItemPosition()];
            dialog.dismiss(); page = 1; loadScreen();
        })); ModalDialogs.show(dialog);
    }

    private Spinner spinner(String[] names) {
        Spinner result = new Spinner(this);
        result.setAdapter(MobileStyle.options(this,names));
        result.setBackgroundTintList(android.content.res.ColorStateList.valueOf(BRAND));
        result.setMinimumHeight(dp(48)); return result;
    }

    private void renderProblemDetail(int serial) {
        if (selectedProblem == null) { onBackPressed(); return; }
        loading("正在加载题面与样例…");
        JSONObject selected = selectedProblem;
        loadPage(serial,() -> {
            try {
                JSONObject problem = api.getObject(ApiClient.problemPath(selected.getString("platform"), selected.getString("problem_id")));
                present(() -> { if (serial == requestSerial) showProblemDetail(problem, selected); });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) error(e); }); }
        });
    }

    private void showProblemDetail(JSONObject problem, JSONObject selected) {
        content.removeAllViews();
        Button back = action("← 返回", false); back.setOnClickListener(v -> onBackPressed()); content.addView(back);
        heading("PROBLEM", value(problem, "problem_name", problem.optString("problem_id")), problem.optString("platform") + " · " + value(problem, "problem_rating", "难度未知"));
        Button discussion=action("按题讨论 / 加入错题本",true);content.addView(discussion);
        discussion.setOnClickListener(v->{Intent intent=new Intent(this,ClubActivity.class);intent.putExtra("page","discussions");intent.putExtra("platform",selected.optString("platform"));intent.putExtra("problem_id",selected.optString("problem_id"));startActivity(intent);});

        LinearLayout box = card();
        if (problem.optBoolean("content_available") && "pdf".equals(problem.optString("statement_format"))) {
            box.addView(label("已采集 PDF 题面，含原始图示、公式与样例。",14,MUTED,false));
            Button pdf=action("阅读 PDF · 翻页 / 缩放 / 适应宽度",true);box.addView(pdf);
            pdf.setOnClickListener(v->{if(openingPdf)return;openingPdf=true;Intent intent=new Intent(this,PdfActivity.class);intent.putExtra("platform",selected.optString("platform"));intent.putExtra("problem_id",selected.optString("problem_id"));startActivity(intent);ui.postDelayed(()->openingPdf=false,800);});
        } else if (problem.optBoolean("content_available")) {
            String html = value(problem, "statement_html", "");
            String source = html.isEmpty() ? value(problem, "statement_text", "") : html;
            box.addView(new ContentView(this, source, !html.isEmpty(), this::openBrowser));
        } else {
            box.addView(label("failed".equals(problem.optString("last_fetch_status"))?"上次采集失败，请管理员重新拉取题面。":"已收录目录，题面尚未采集；可等待后重新检查。",14,MUTED,false));
            Button retry=action("重新检查",false);retry.setOnClickListener(v->loadScreen());box.addView(retry);
        }
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
                MobileStyle.symbol(favorite);
            });
        }); actions.addView(favorite);
        String url = value(problem, "problem_url", "");
        if (!url.isEmpty()) { Button original = action("查看原题 ↗", true); original.setOnClickListener(v -> openBrowser(url)); actions.addView(original); }
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
        Button due=action("查看今日到期补题 / 间隔复习",true);due.setOnClickListener(v->show("reviews"));content.addView(due);
        LinearLayout dueList=card();dueList.addView(label("正在读取今日到期补题…",13,MUTED,false));
        loadPage(serial,()->{
            try{
                JSONArray plans=api.getArray("/api/me/club/reviews");
                present(()->{if(serial!=requestSerial)return;TrainingReminder.scheduleReviews(this,plans);dueList.removeAllViews();dueList.addView(label("今日到期补题",17,BRAND,true));int count=0;
                    for(int i=0;i<plans.length();i++){JSONObject item=plans.optJSONObject(i);if(item==null||!item.optBoolean("due"))continue;count++;Button entry=action(item.optString("platform")+" · "+item.optString("problem_id"),false);entry.setOnClickListener(v->{Intent intent=new Intent(this,ClubActivity.class);intent.putExtra("page","discussions").putExtra("platform",item.optString("platform")).putExtra("problem_id",item.optString("problem_id"));startActivity(intent);});dueList.addView(entry);}
                    if(count==0)dueList.addView(label("暂无到期补题",13,MUTED,false));
                });
            }catch(Exception e){present(()->{if(serial==requestSerial)failureBox(dueList,FailureState.title(e),180,null);});}
        });
        LinearLayout summary = card(); summary.addView(label("正在读取训练统计…",13,MUTED,false));
        loadPage(serial,() -> {
            try {
                JSONObject data = api.getObject("/api/me/training/summary");
                int streak = data.getInt("streak_days"), active = data.getInt("active_days");
                present(() -> { if (serial == requestSerial) { summary.removeAllViews(); summary.addView(label("连续 " + streak + " 天 · 近一年活跃 " + active + " 天",16,BRAND,true)); } });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) failureBox(summary,FailureState.title(e),100,null); }); }
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
            for (int i = 0; i < 3; i++) { slots[i] = column(); slots[i].setPadding(dp(16),dp(16),dp(16),dp(16)); slots[i].setBackground(shape(MobileStyle.MODULE,10,LINE)); slots[i].setMinimumHeight(dp(180)); slots[i].addView(label(names[i] + " · 正在生成…", 15, BRAND, true)); zones.addView(slots[i]); }
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
                    present(() -> {
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
                present(() -> { actionBusy = false; if (serial == requestSerial) { generate.setEnabled(true); loadTrainingHistory(history, serial); } });
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
        loadPage(serial,() -> {
            try {
                JSONArray rows = api.getArray("/api/me/training/challenges");
                present(() -> {
                    if (serial != requestSerial) return;
                    box.removeAllViews(); box.addView(label("挑战历史 · 仅自己可见", 17, TEXT, true));
                    if (rows.length() == 0) box.addView(label("暂无挑战记录。", 13, MUTED, false));
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.optJSONObject(i); if (row == null) continue;
                        space(box, 12); box.addView(label(value(row,"problem_name",row.optString("problem_id")),15,TEXT,true));
                        box.addView(label(row.optString("platform") + " · " + row.optString("status") + " · " + date(row.optLong("created_at")),12,MUTED,false));
                    }
                });
            } catch (Exception e) { present(() -> { if (serial == requestSerial) failureBox(box,FailureState.title(e),250,()->loadTrainingHistory(box,serial)); }); }
        });
    }

    private void renderContests() {
        heading("CONTEST REVIEW", "赛事复盘", "查询自己的比赛题目，并保存逐题补题状态。");
        if (!requireLogin("contests")) return;
        LinearLayout form = card(); EditText contest = new EditText(this); contest.setHint("比赛 ID"); contest.setSingleLine(true);contest.setText(contestIdentifier);contest.addTextChangedListener(watch(value->contestIdentifier=value)); form.addView(contest);
        Button load = action("查询比赛题目", true); form.addView(load);
        LinearLayout results = card(); results.addView(label("请输入比赛 ID 查询；无记录时请先同步数据。",13,MUTED,false));
        Runnable lookup=() -> {
            String id = contest.getText().toString().trim(); if (id.isEmpty()) { message("请输入比赛 ID。"); return; }
            int serial = ++requestSerial;pageRefresh.reset(serial);if(readFromAction)pageRefresh.userAction();load.setEnabled(false);
            loadPage(serial,()->{try{JSONArray rows=api.getArray("/api/me/contest/reviews?contest_id="+encode(id));present(()->{showContestRows(results,id,rows);load.setEnabled(true);});}
                catch(Exception e){present(()->{failureBox(results,FailureState.title(e),180,null);load.setEnabled(true);});}});
        };
        load.setOnClickListener(v->lookup.run());if(!contestIdentifier.trim().isEmpty())lookup.run();
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
            String current=row.optString("status");
            Spinner status = spinner(labels); int selected = java.util.Arrays.asList(keys).indexOf(current); status.setSelection(Math.max(0,selected)); box.addView(status);
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

    private void addRankPager(int total) {
        int pages=Math.max(1,(total+rankPageSize-1)/rankPageSize);
        LinearLayout pager=row();Button previous=action("上一页",false),next=action("下一页",false);
        previous.setEnabled(page>1);next.setEnabled(page<pages);
        previous.setOnClickListener(v->{page--;loadScreen();});next.setOnClickListener(v->{page++;loadScreen();});
        pager.addView(previous,new LinearLayout.LayoutParams(0,dp(44),1));
        pager.addView(label(" 第"+page+" / "+pages+"页 ",12,MUTED,false));
        pager.addView(next,new LinearLayout.LayoutParams(0,dp(44),1));content.addView(pager);
        content.addView(label("共"+total+"名成员 · 每页"+rankPageSize+"人",12,MUTED,false));
    }

    private void renderCompose(int serial) {
        if(!api.isLoggedIn()){loginDestination="compose";screen="account";updateSearchHeader();refreshNav();renderAccount(serial);return;}
        syncCloudEditor();
        heading("WRITE / COMMUNITY", "发布话题", "草稿自动保存到账号，与网页版同步。");
        loading("正在加载论坛分类…");
        loadPage(serial,() -> {
            try {
                JSONArray categories = api.getArray("/api/forum/categories");
                present(() -> { if (serial == requestSerial) showCompose(categories); });
            } catch (Exception e) {
                present(() -> { if (serial == requestSerial) error(e); });
            }
        });
    }

    private void showCompose(JSONArray categories) {
        if(composeEditorShown)return;composeEditorShown=true;
        content.removeAllViews();
        syncCloudEditor();
        offerDraftRecovery();
        final long editorGeneration=composeGeneration;
        heading("WRITE / COMMUNITY", "发布话题", "草稿自动保存到账号，与网页版同步。");
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
                if (composeCategoryId != ids[position]&&currentComposer(editorGeneration)) { composeCategoryId = ids[position]; composerChanged(); }
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        box.addView(category, new LinearLayout.LayoutParams(-1, dp(48)));
        space(box, 12);
        box.addView(label("标题（4–120 字）", 13, TEXT, true));
        EditText title = new EditText(this);
        title.setSingleLine(true);
        title.setHint("例如：二分答案的边界怎么判断？");
        title.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(120)});
        title.setText(composeTitle);
        title.addTextChangedListener(watch(value -> { if(currentComposer(editorGeneration)){composeTitle = value; composerChanged();} }));
        box.addView(title);
        space(box, 12);
        box.addView(label("正文（5–20000 字）", 13, TEXT, true));
        EditText body = new EditText(this);
        composeBodyInput=body;
        body.setHint("描述问题、已经尝试的方法，或分享解题思路…");
        body.setGravity(Gravity.TOP);
        body.setMinLines(8);
        body.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        body.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(20000)});
        body.setText(composeBody);
        body.setContentDescription("发帖正文输入");
        body.addTextChangedListener(watch(value -> { if(currentComposer(editorGeneration)){composeBody = value; composerChanged();} }));
        box.addView(body, new LinearLayout.LayoutParams(-1, -2));
        space(box,12);
        WrapLayout format = new WrapLayout(this);format.setContentDescription("发帖格式工具");
        Button bold = action("加粗", false), code = action("代码块", false), quote = action("引用", false);
        bold.setOnClickListener(v -> insertFormat(body, "**", "**"));
        code.setOnClickListener(v -> insertFormat(body, "\n```\n", "\n```\n"));
        quote.setOnClickListener(v -> insertFormat(body, "> ", ""));
        compactTool(bold);compactTool(code);compactTool(quote);format.addView(bold);format.addView(code);format.addView(quote);
        String[] titles={"H1","H2","斜体","删除线","无序列表","有序列表","行内代码","链接"};
        String[] before={"# ","## ","*","~~","- ","1. ","`","["},after={"","","*","~~","","","`","](https://)"};
        for(int i=0;i<titles.length;i++){final int index=i;Button tool=action(titles[i],false);compactTool(tool);tool.setOnClickListener(v->insertFormat(body,before[index],after[index]));format.addView(tool);}
        box.addView(format,new LinearLayout.LayoutParams(-1,-2));space(box,14);
        WrapLayout tools=new WrapLayout(this);tools.setContentDescription("发帖草稿工具");box.addView(tools,new LinearLayout.LayoutParams(-1,-2));
        Button image=action("插入图片",false);compactTool(image);image.setContentDescription("插入发帖图片");image.setOnClickListener(v->choosePostImage());tools.addView(image);
        Button importMd=action("导入 .md",false);compactTool(importMd);importMd.setOnClickListener(v->{if(composeBusy||!currentComposer(editorGeneration))return;markdownOwner=api.sessionGeneration();markdownGeneration=editorGeneration;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("text/*");picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,IMPORT_MARKDOWN);});tools.addView(importMd);
        Button draftList=action("云端草稿",false);compactTool(draftList);draftList.setOnClickListener(v->showCloudDraftList());tools.addView(draftList);
        Button preview = action("预览正文", false);
        preview.setContentDescription("预览发帖正文");
        compactTool(preview);preview.setOnClickListener(v -> { LinearLayout article = column(); article.addView(new ContentView(this, composeBody, false, this::openBrowser)); detailsDialog("正文预览", article); });tools.addView(preview);
        composeStatus = label(cloud.state().status, 12, MUTED, false);
        box.addView(composeStatus);
        Button save = action("保存草稿", false);
        compactTool(save);save.setOnClickListener(v -> { if (currentComposer(editorGeneration)&&requireLogin("compose")) saveComposer(null); });tools.addView(save);
        if (composeDraftId > 0) {
            final int draftId=composeDraftId;
            Button remove = action("删除当前草稿", false);
            remove.setOnClickListener(v -> {if(!currentComposer(editorGeneration))return;new ModalDialogs.Builder(this).setTitle("删除草稿？").setMessage("删除后无法恢复。")
                    .setNegativeButton("取消", null).setPositiveButton("删除", (d, w) -> {if(currentComposer(editorGeneration))mutate(remove, () -> api.deleteDraft(draftId), () -> { if(editorGeneration==cloud.generation())clearComposer();else syncCloudEditor();loadScreen(); });}).show();});
            compactTool(remove);tools.addView(remove);
        }
        space(box, 10);
        box.addView(label("提交后进入人工审核；通过后才会出现在主页。", 12, MUTED, false));

        Button submit = action("提交审核", true);
        submit.setOnClickListener(view -> {
            if(!currentComposer(editorGeneration))return;
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
                setControlsEnabled(box,false);
                composeBusy = true;
                CloudDrafts.State snapshot=cloud.state();int draftId = composeDraftId;long owner=api.sessionGeneration(),generation=composeGeneration;
                io.execute(() -> {
                    try {
                        JSONObject result = api.submitDraft(owner,draftId,snapshot.editVersion);int submitted=result.getInt("id");
                        present(() -> {
                            composeBusy = false;if(generation!=cloud.generation()){refreshComposer();return;}clearComposer(); show("forum");openWebFeature("progress",submitted);
                        });
                    } catch (Exception e) { present(() -> { composeBusy = false; submit.setEnabled(true);setControlsEnabled(box,true);failureDialog(e); }); }
                });
            });
        });
        content.addView(submit);
        ui.post(this::consumePostImage);
    }

    private void insertFormat(EditText input, String before, String after) {
        int start = Math.max(0, input.getSelectionStart()), end = Math.max(start, input.getSelectionEnd());
        String selected = input.getText().toString().substring(start, end);
        input.getText().replace(start, end, before + selected + after);
        input.setSelection(start + before.length(), start + before.length() + selected.length()); input.requestFocus();
    }

    private void compactTool(Button tool){tool.setTextSize(12);tool.setMinWidth(0);tool.setMinimumWidth(0);tool.setMinHeight(dp(44));tool.setMinimumHeight(dp(44));tool.setPadding(dp(10),dp(6),dp(10),dp(6));}

    private void composerChanged() {
        if(!cloud.update(composeGeneration,composeCategoryId,composeTitle,composeBody)){refreshComposer();return;}
        composeRevision++;
        try {preferences.edit().putString(recoveryKey(),new JSONObject().put("id",composeDraftId).put("title",composeTitle).put("body",composeBody).put("category_id",composeCategoryId).toString()).apply();}catch(Exception ignored){}
        if(composeStatus!=null)composeStatus.setText("等待自动保存…");
    }
    private void syncCloudEditor(){
        cloud.bind(api.isLoggedIn()?api.getBaseUrl()+"/"+api.accountKey():"",api.sessionGeneration());
        CloudDrafts.State state=cloud.state();composeGeneration=state.generation;composeDraftId=state.id;composeCategoryId=state.category;composeTitle=state.title;composeBody=state.body;
        if(!state.dirty)composeSavedRevision=composeRevision;
    }
    private void refreshComposer(){
        if(isFinishing()||isDestroyed())return;
        syncCloudEditor();
        if("compose".equals(screen)){composeStatus=null;composeBodyInput=null;ModalDialogs.close(this);loadScreen();}
    }
    private boolean currentComposer(long generation){
        if(generation==composeGeneration&&generation==cloud.generation())return true;
        refreshComposer();return false;
    }
    private void clearComposer(){
        if(api.isLoggedIn())preferences.edit().remove(recoveryKey()).apply();
        cloud.reset();syncCloudEditor();composeRevision=0;composeSavedRevision=0;composeStatus=null;
    }
    private void saveComposer(Runnable afterSave){
        if(composeBusy||!requireLogin("compose"))return;
        long generation=composeGeneration;
        if(!cloud.update(generation,composeCategoryId,composeTitle,composeBody)){popupLoading=false;refreshComposer();return;}
        composeBusy=true;setControlsEnabled(content,false);
        cloud.flush(generation,error->present(()->{
            composeBusy=false;if(isFinishing()||isDestroyed())return;
            setControlsEnabled(content,true);
            CloudDrafts.State state=cloud.state();if(state.generation!=generation||composeGeneration!=generation){popupLoading=false;refreshComposer();return;}composeDraftId=state.id;
            if(error!=null){popupLoading=false;if(composeStatus!=null)composeStatus.setText(state.status);failureDialog(error);return;}
            composeSavedRevision=composeRevision;preferences.edit().remove(recoveryKey()).apply();if(composeStatus!=null)composeStatus.setText(state.status);
            if(afterSave!=null)afterSave.run();
        }));
    }
    private void openDraft(int id){
        if(composeBusy||actionBusy||!requireLogin("compose"))return;
        saveBeforeSwitch(()->{
            if(id==0){clearComposer();show("compose");return;}
            int serial=requestSerial;long generation=composeGeneration,owner=api.sessionGeneration();actionBusy=true;
            io.execute(()->{try{JSONObject draft=api.getObject("/api/forum/drafts/"+id);present(()->{
                actionBusy=false;if(serial!=requestSerial||isFinishing()||isDestroyed())return;
                if(owner!=api.sessionGeneration()||generation!=cloud.generation()){refreshComposer();return;}
                cloud.load(draft);syncCloudEditor();show("compose");
            });}catch(Exception e){present(()->{actionBusy=false;if(serial==requestSerial)failureDialog(e);});}});
        });
    }
    private void saveBeforeSwitch(Runnable action){
        if(cloud.state().dirty){saveComposer(action);}else action.run();
    }
    private void showCloudDraftList(){
        if(popupLoading||ModalDialogs.isShowing(this)||!requireLogin("compose"))return;
        popupLoading=true;saveBeforeSwitch(()->{popupLoading=false;openSpace("drafts");});
    }
    private final Runnable draftTicker=new Runnable(){public void run(){
        if(isFinishing()||isDestroyed())return;
        if("compose".equals(screen)&&composeStatus!=null){CloudDrafts.State state=cloud.state();if(state.generation!=composeGeneration)refreshComposer();else{composeDraftId=state.id;composeStatus.setText(state.status);if(!state.dirty){composeSavedRevision=composeRevision;if(api.isLoggedIn()&&state.id>0)preferences.edit().remove(recoveryKey()).apply();}}}
        ui.postDelayed(this,700);
    }};
    @Override protected void onStart(){super.onStart();ui.removeCallbacks(draftTicker);ui.post(draftTicker);}
    @Override protected void onStop(){ui.removeCallbacks(draftTicker);if("compose".equals(screen)&&api.isLoggedIn())cloud.flush(composeGeneration,null);super.onStop();}
    private void setControlsEnabled(View view,boolean enabled){view.setEnabled(enabled);if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++)setControlsEnabled(group.getChildAt(i),enabled);}}
    private String recoveryKey(){return "cloud_recovery_v021_"+android.util.Base64.encodeToString((api.getBaseUrl()+"\n"+api.accountKey()).getBytes(StandardCharsets.UTF_8),android.util.Base64.NO_WRAP);}
    private void offerDraftRecovery(){
        if(!api.isLoggedIn()||!cloud.state().title.isEmpty()||!cloud.state().body.isEmpty())return;
        String key=recoveryKey();if(key.equals(recoveryOffered)||!preferences.contains(key))return;recoveryOffered=key;
        new ModalDialogs.Builder(this).setTitle("恢复未保存内容？").setMessage("本机保留了此账号上次未确认保存的编辑内容。恢复后会另存为新云端草稿，避免覆盖网页中的修改。")
            .setNegativeButton("暂不恢复",null).setNeutralButton("丢弃备份",(d,w)->preferences.edit().remove(key).apply())
            .setPositiveButton("恢复为新草稿",(d,w)->{try{JSONObject draft=new JSONObject(preferences.getString(key,"{}"));cloud.reset();syncCloudEditor();composeTitle=draft.optString("title");composeBody=draft.optString("body");composeCategoryId=draft.optInt("category_id");composeDraftId=0;composerChanged();loadScreen();}catch(Exception e){failureDialog(e);}}).show();
    }
    private void restoreWebSession(){
        if(api.isLoggedIn()||sessionRestoreAttempted||!preferences.getBoolean("auto_login",false)){loadAfterSession();return;}
        sessionRestoreAttempted=true;String destination=screen;showLoginWaiting();
        java.lang.ref.WeakReference<MainActivity> owner=new java.lang.ref.WeakReference<>(this);
        application.restoreSavedLogin().whenComplete((restored,failure)->{
            MainActivity current=owner.get();if(current==null)return;
            current.present(()->{
                if(current.isFinishing()||current.isDestroyed())return;
                current.finishLoginWaiting();
                current.sessionRestoreFailure=failure instanceof java.util.concurrent.CompletionException&&failure.getCause() instanceof Exception?(Exception)failure.getCause():failure instanceof Exception?(Exception)failure:null;
                current.screen=Boolean.TRUE.equals(restored)?destination:"account";
                current.syncCloudEditor();current.updateSearchHeader();current.refreshNav();current.loadAfterSession();
            });
        });
    }

    private void loadAfterSession(){
        // Startup step 5: dispatch once after session recovery and before page requests.
        // The check stays asynchronous, so an unavailable release server cannot block home.
        if(!externalRoot)application.updates().startupCheck();
        loadScreen();
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
        if (api.isUnconfigured() || !api.isLoggedIn()) {
            publicFailure = api.isUnconfigured() ? connectionFailure() : new ApiClient.ApiException(401, "未登录", false);
            publishedFailure = publicFailure;
            showPublicMember(null, true, null);
            return;
        }
        loading("正在加载公开主页…");
        loadPage(serial,() -> {
            JSONObject user = null, posts = null;
            Exception profileError = null, postsError = null;
            try {
                JSONObject result = api.getObject("/api/me/profile");
                JSONObject account = result.getJSONObject("user");
                user = new JSONObject().put("name", account.getString("name")).put("status", account.optString("status"))
                        .put("avatar_url", account.optString("avatar_url", "")).put("platform_counts", result.getJSONObject("platform_counts"))
                        .put("total_count", result.getInt("total_count")).put("recent_ac",result.optJSONArray("recent_ac"));
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
            JSONObject profile = user, published = posts;
            Exception profileFailure = profileError, postsFailure = postsError;
            present(() -> {
                if (serial != requestSerial) return;
                publicFailure = profileFailure; publishedFailure = postsFailure;
                showPublicMember(profile, true, published);
            });
        });
    }

    private void showPublicProfile(JSONObject profile) {
        showPublicMember(profile == null ? null : profile.optJSONObject("user"), true);
    }

    private void openMember(JSONObject row,String from) {
        if(row==null||ModalDialogs.isShowing(this))return;
        try{JSONObject member=new JSONObject(row.toString());navigate("member",()->{memberPreview=member;memberReturnScreen=from;});}catch(org.json.JSONException e){failureDialog(e);}
    }

    private void renderMember(int serial) {
        String publicId = value(memberPreview, "public_member_id", value(memberPreview, "author_public_member_id", ""));
        if (api.isUnconfigured() || publicId.isEmpty()) {
            publicFailure = api.isUnconfigured() ? connectionFailure() : new ApiClient.UnavailableEndpointException("成员公开主页");
            publishedFailure = publicFailure;
            showPublicMember(memberPreview, false, null); return;
        }
        loading("正在加载成员公开主页…");
        loadPage(serial,() -> {
            JSONObject profile = null, posts = null;
            Exception profileError = null, postsError = null;
            try {
                profile = api.memberProfile(publicId);
                profile.getString("public_member_id"); profile.getString("name"); profile.getJSONObject("platform_counts");
            } catch (Exception e) { profileError = e; profile = null; }
            try { posts = api.memberPosts(publicId, page); posts.getJSONArray("rows"); } catch (Exception e) { postsError = e; posts = null; }
            JSONObject user = profile == null ? memberPreview : profile, published = posts;
            Exception profileFailure = profileError, postsFailure = postsError;
            present(() -> {
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
        defaultAvatar(avatar);
        avatar.setScaleType(android.widget.ImageView.ScaleType.CENTER_CROP);
        avatar.setBackground(shape(ACCENT, size / 2, 0));
        avatar.setClipToOutline(true);
        avatar.setPadding(0, 0, 0, 0);
        return avatar;
    }
    private void defaultAvatar(ImageButton view){view.setImageDrawable(AppIcons.get(this,"avatar",TEXT));view.setImageTintList(null);view.setTag("");if(view==headerAvatar)headerAvatarOwner=api.sessionGeneration();}

    private void loadAvatar(ImageButton view, String path) {
        if(view==headerAvatar){refreshHeaderAvatar(false);return;}
        if (api.isUnconfigured() || path.isEmpty()) return;
        int serial = requestSerial;
        avatarIo.execute(() -> {
            if (serial != requestSerial) return;
            try {
                android.graphics.Bitmap image = api.avatarBitmap(path);
                if (image != null) present(() -> { if (serial == requestSerial) view.setImageBitmap(image); });
            } catch (Exception ignored) { /* Keep the local default avatar if the image is unavailable. */ }
        });
    }

    /** Header loads belong to the account and shell, so changing pages cannot drop them. */
    private void refreshHeaderAvatar(boolean force){
        if(headerAvatar==null||isDestroyed())return;if(!api.isLoggedIn()){defaultAvatar(headerAvatar);return;}
        ImageButton destination=headerAvatar;long owner=api.sessionGeneration();String known=api.currentAvatarUrl();
        if(headerAvatarOwner!=owner||known.isEmpty())defaultAvatar(destination);
        android.graphics.Bitmap cached=api.cachedAvatarBitmap(known);if(cached!=null){destination.setImageBitmap(cached);destination.setTag(known);headerAvatarOwner=owner;}
        if(headerAvatarLoading)return;long now=android.os.SystemClock.elapsedRealtime();boolean check=force||headerCheckOwner!=owner||now-headerCheckedAt>30000;if(!check&&known.equals(destination.getTag()))return;
        headerAvatarLoading=true;avatarIo.execute(()->{android.graphics.Bitmap bitmap=cached;String path=known;boolean checked=false;try{if(check){api.refreshSession();checked=true;path=api.currentAvatarUrl();}if(!path.isEmpty())bitmap=api.avatarBitmap(path);}catch(Exception ignored){if(!path.equals(known))bitmap=null;}android.graphics.Bitmap image=bitmap;String current=path;boolean refreshed=checked;
            present(()->{headerAvatarLoading=false;if(isDestroyed())return;if(destination!=headerAvatar||owner!=api.sessionGeneration()){refreshHeaderAvatar(true);return;}if(!current.equals(api.currentAvatarUrl())){refreshHeaderAvatar(false);return;}if(refreshed){headerCheckedAt=android.os.SystemClock.elapsedRealtime();headerCheckOwner=owner;}if(current.isEmpty())defaultAvatar(destination);else if(image!=null){destination.setImageBitmap(image);destination.setTag(current);headerAvatarOwner=owner;}});
        });
    }

    private void consumePostImage(){if(pendingPostImage!=null&&composeBodyInput!=null&&"compose".equals(screen)){android.net.Uri uri=pendingPostImage;pendingPostImage=null;insertPostImage(uri);}}

    private void choosePostImage(){
        if(choosingPostImage||composeBusy||!requireLogin("compose"))return;imageOwner=api.sessionGeneration();imageDraftGeneration=cloud.generation();choosingPostImage=true;
        Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","image/webp"});
        try{startActivityForResult(picker,PICK_POST_IMAGE);}catch(Exception e){choosingPostImage=false;actionNotice.show("选择图片",e);}
    }
    private void insertPostImage(android.net.Uri uri){
        if(imageOwner!=api.sessionGeneration()||imageDraftGeneration!=cloud.generation()||!"compose".equals(screen)||composeBodyInput==null){actionNotice.show("插入图片",new IllegalArgumentException("账号或草稿已切换，请重新选择图片"));return;}
        final long owner=imageOwner,draft=imageDraftGeneration;final EditText editor=composeBodyInput;composeBusy=true;if(composeStatus!=null)composeStatus.setText("正在上传图片…");
        io.execute(()->{String markdown=null;Exception failure=null;try(InputStream input=getContentResolver().openInputStream(uri);ByteArrayOutputStream bytes=new ByteArrayOutputStream()){
            String mime=getContentResolver().getType(uri);if(!"image/png".equals(mime)&&!"image/jpeg".equals(mime)&&!"image/webp".equals(mime))throw new IllegalArgumentException("请选择 PNG、JPEG 或 WebP 图片");
            if(input==null)throw new IllegalArgumentException("无法读取图片");byte[] buffer=new byte[8192];int count;while((count=input.read(buffer))!=-1){if(bytes.size()+count>20*1024*1024)throw new IllegalArgumentException("原图不能超过 20 MB");bytes.write(buffer,0,count);}if(draft!=cloud.generation())throw new IllegalStateException("草稿已切换，上传已取消");markdown=ForumImages.markdown(api.uploadForumImage(owner,ForumImages.compress(bytes.toByteArray())).getString("url"));
        }catch(Exception e){failure=e;}String content=markdown;Exception error=failure;
            present(()->{composeBusy=false;if(isDestroyed()||owner!=api.sessionGeneration()||draft!=cloud.generation())return;if(error!=null){actionNotice.show("上传图片",error);if(composeStatus!=null)composeStatus.setText("图片上传失败，正文已保留");return;}if(editor!=composeBodyInput||!"compose".equals(screen)){actionNotice.show("插入图片",new IllegalArgumentException("编辑页面已切换，请重新选择图片"));return;}int at=editor.getSelectionStart();if(at<0)at=editor.length();if(editor.length()+content.length()>20000){actionNotice.show("插入图片",new IllegalArgumentException("正文达到 20000 字上限，请精简后重新插入"));return;}editor.getText().insert(at,content);editor.setSelection(at+content.length());});
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
            Button back = action("← 返回", false);
            back.setOnClickListener(v -> onBackPressed());
            content.addView(back);
        }
        String name = user == null ? "资料不可用" : user.optString("name", user.optString("author_name", "ACM 成员"));
        LinearLayout hero = card();
        hero.setBackground(shape(MobileStyle.MODULE,12,0));
        hero.addView(label("ACMFOREVER / " + (own ? "MY PROFILE" : "MEMBER"), 10, MUTED, true));
        space(hero, 36);
        LinearLayout identity = row();
        ImageButton avatar = avatarButton(76);
        identity.addView(avatar, new LinearLayout.LayoutParams(dp(76), dp(76)));
        String avatarPath = value(user, "avatar_url", value(user, "author_avatar_url", ""));
        loadAvatar(avatar, avatarPath);
        if (own) {
            avatar.setContentDescription("进入账号设置");
            avatar.setOnClickListener(v -> show("account"));
            if (avatarPath.isEmpty()) defaultAvatar(headerAvatar);
            else loadAvatar(headerAvatar, avatarPath);
        } else avatar.setContentDescription(name + "的头像");
        LinearLayout copy = column(); copy.setPadding(dp(12), 0, 0, 0);
        copy.addView(label(name, 22, TEXT, true));
        if (user != null && user.has("status")) copy.addView(label(value(user, "status", ""), 12, MUTED, false));
        identity.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        hero.addView(identity);
        space(hero, 12);
        LinearLayout summary=row();hero.addView(summary);publicStat(summary,"累计通过",publicData?count(user,"total_count"):"—");publicStat(summary,"公开话题",publishedPosts==null?"—":String.valueOf(publishedPosts.optInt("total")));
        if(own){
            LinearLayout shortcuts=card();shortcuts.addView(label("我的空间",17,TEXT,true));space(shortcuts,12);LinearLayout tiles=row();shortcuts.addView(tiles);
            quickTile(tiles,"我的话题","forum",()->openOwnCollection("我的话题","/api/forum/mine/posts"));
            quickTile(tiles,"话题收藏","bookmark",()->openOwnCollection("我的收藏","/api/forum/mine/bookmarks"));
            quickTile(tiles,"云端草稿","drafts",this::showCloudDraftList);
            quickTile(tiles,"账号设置","settings",()->show("account"));
        }
        LinearLayout achievements=column();content.addView(achievements,new LinearLayout.LayoutParams(-1,-2));
        LinearLayout tabsCard=column();tabsCard.setPadding(dp(14),dp(16),dp(14),dp(14));tabsCard.setBackground(shape(MobileStyle.MODULE,14,0));achievements.addView(tabsCard);
        tabsCard.addView(label("各平台通过题数",17,TEXT,true));space(tabsCard,12);
        if(!publicData){failureBox(tabsCard,FailureState.title(publicFailure),264,this::loadScreen);}
        else{
            String[] names={"ALL","Codeforces","洛谷","AtCoder","牛客","校 OJ"},ids={"all","codeforces","luogu","atcoder","nowcoder","cjlu"};
            LinearLayout tabs=row();tabsCard.addView(tabs,new LinearLayout.LayoutParams(-1,-2));
            LinearLayout panel=column();panel.setContentDescription("平台详情区域");LinearLayout.LayoutParams panelSize=new LinearLayout.LayoutParams(-1,-2);panelSize.topMargin=dp(12);achievements.addView(panel,panelSize);
            View[] buttons=new View[ids.length];
            for(int i=0;i<ids.length;i++){
                String id=ids[i];LinearLayout tab=column();buttons[i]=tab;tab.setGravity(Gravity.CENTER);tab.setPadding(0,dp(4),0,dp(4));
                android.widget.ImageView logo=new android.widget.ImageView(this){@Override protected void onMeasure(int width,int height){int side=Math.min(dp(46),View.MeasureSpec.getSize(width));super.onMeasure(View.MeasureSpec.makeMeasureSpec(side,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(side,View.MeasureSpec.EXACTLY));}};
                logo.setImageDrawable(PlatformAssets.logo(this,id));logo.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);logo.setPadding(dp(6),dp(6),dp(6),dp(6));logo.setBackground(shape(Color.TRANSPARENT,999,LINE));logo.setTag("platform_logo");tab.addView(logo,new LinearLayout.LayoutParams(-1,dp(46)));
                TextView caption=label(names[i],9,TEXT,false);caption.setPadding(0,dp(6),0,0);caption.setGravity(Gravity.CENTER);caption.setSingleLine(true);caption.setAutoSizeTextTypeUniformWithConfiguration(6,9,1,android.util.TypedValue.COMPLEX_UNIT_SP);tab.addView(caption,new LinearLayout.LayoutParams(-1,-2));
                LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(0,-2,1);if(i>0)size.leftMargin=dp(4);tabs.addView(tab,size);
                tab.setContentDescription("切换平台 "+names[i]);tab.setOnClickListener(v->{profilePlatform=id;for(int j=0;j<buttons.length;j++)stylePlatformTab(buttons[j],ids[j].equals(id));renderPlatformPanel(panel,user,own,id);});
            }
            for(int i=0;i<buttons.length;i++)stylePlatformTab(buttons[i],ids[i].equals(profilePlatform));renderPlatformPanel(panel,user,own,profilePlatform);
        }
        space(content,12);
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
                menuRow(community, post.optString("title"), post.optString("category_name", "话题"), () -> openPost(post.optInt("id")));
            }
            addPager(publishedPosts.optInt("total"), 12);
        }
        if(own&&!api.isLoggedIn()){Button login=action("登录并查看个人中心",true);login.setOnClickListener(v->show("account"));content.addView(login);}
    }

    private void renderAccount(int serial) {
        heading("ACMFOREVER / ACCOUNT", api.isLoggedIn()?"账号设置":"欢迎回来", "登录、资料、安全\n你的 ACMforever 随身社区");
        if (!api.isLoggedIn()) {
            if(sessionRestoreFailure!=null){
                failureBox(card(),FailureState.title(sessionRestoreFailure),160,null);
                Button retrySession=action("重试自动登录",false);retrySession.setOnClickListener(v->{sessionRestoreAttempted=false;sessionRestoreFailure=null;restoreWebSession();});content.addView(retrySession);
            }
            showLogin();
            appearanceEntry();
            return;
        }
        if (api.requiresPasswordChange()) {
            failureBox(card(), "请修改初始密码", 180, null);
            Button change = action("修改初始密码", true);
            change.setOnClickListener(v -> showChangePassword()); content.addView(change); return;
        }
        loading("正在加载账号资料…");
        loadPage(serial,() -> {
            try { if(!api.isReplay())api.refreshSession(); }
            catch (Exception e) {
                present(() -> {
                    if (serial != requestSerial) return;
                    if (api.requiresPasswordChange()) { loadScreen(); return; }
                    error(e);

                    if (!api.isLoggedIn()) showLogin();
                }); return;
            }
            JSONObject profile = null;
            JSONArray posts = null, bookmarks = null, drafts = null;
            Exception[] failures = new Exception[4];
            try { profile = api.getObject("/api/me/profile"); profile.getJSONObject("user"); } catch (Exception e) { failures[0] = e; profile = null; }
            try { posts = api.getArray("/api/forum/mine/posts"); } catch (Exception e) { failures[1] = e; }
            try { bookmarks=api.getArray("/api/forum/mine/bookmarks"); } catch(Exception e){failures[2]=e;}
            try { drafts=api.getArray("/api/forum/drafts"); } catch(Exception e){failures[3]=e;}
            JSONObject account = profile;
            JSONArray mine = posts, saved = bookmarks, editing = drafts;
            present(() -> { if (serial == requestSerial) showAccountProfile(account, mine, saved, editing, failures); });
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
        qq.setTextSize(15);qq.setPadding(dp(14),0,dp(14),0);qq.setBackground(shape(BACKGROUND,10,0));
        box.addView(qq);
        qq.setLayoutParams(new LinearLayout.LayoutParams(-1,dp(52)));space(box,12);
        EditText password = new EditText(this);
        password.setHint("密码"); password.setSingleLine(true);
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setSaveEnabled(false);password.setTextSize(15);password.setPadding(dp(14),0,0,0);password.setBackgroundColor(Color.TRANSPARENT);
        LinearLayout passwordRow=row();passwordRow.setBackground(shape(BACKGROUND,10,0));box.addView(passwordRow,new LinearLayout.LayoutParams(-1,dp(52)));
        passwordRow.addView(password,new LinearLayout.LayoutParams(0,-1,1));
        ImageButton eye=new ImageButton(this);eye.setImageDrawable(AppIcons.get(this,"eye",MUTED));eye.setPadding(dp(12),dp(12),dp(12),dp(12));eye.setBackgroundColor(Color.TRANSPARENT);eye.setContentDescription("显示密码");passwordRow.addView(eye,new LinearLayout.LayoutParams(dp(48),dp(48)));
        final boolean[] visible={false};eye.setOnClickListener(v->{int start=password.getSelectionStart(),end=password.getSelectionEnd();visible[0]=!visible[0];password.setTransformationMethod(visible[0]?android.text.method.HideReturnsTransformationMethod.getInstance():android.text.method.PasswordTransformationMethod.getInstance());if(start>=0&&end>=0)password.setSelection(start,end);eye.setImageDrawable(AppIcons.get(this,visible[0]?"eye-off":"eye",MUTED));eye.setContentDescription(visible[0]?"隐藏密码":"显示密码");});
        final LoginOptions[] options={LoginOptions.read(preferences)};
        CheckBox remember = new CheckBox(this); remember.setText("记住账号");
        CheckBox rememberPassword=new CheckBox(this);rememberPassword.setText("记住密码");
        CheckBox automatic=new CheckBox(this);automatic.setText("自动登录");
        remember.setChecked(options[0].account);rememberPassword.setChecked(options[0].password);automatic.setChecked(options[0].automatic);
        space(box,10);for(CheckBox option:new CheckBox[]{remember,rememberPassword,automatic}){option.setTextColor(TEXT);option.setTextSize(14);option.setMinHeight(dp(44));box.addView(option);}
        password.setText(sessionVault.readPassword(api.getBaseUrl(),loginIdentifier));
        options[0]=LoginOptions.read(preferences);remember.setChecked(options[0].account);rememberPassword.setChecked(options[0].password);automatic.setChecked(options[0].automatic);
        final boolean[] changing={false};
        java.util.function.BiConsumer<String,Boolean> changeOption=(name,checked)->{
            if(changing[0])return;changing[0]=true;
            options[0]=options[0].change(name,checked);options[0].save(preferences,qq.getText().toString().trim());
            if(!options[0].password)sessionVault.clearPassword();else if(!options[0].automatic)sessionVault.clear();
            remember.setChecked(options[0].account);rememberPassword.setChecked(options[0].password);automatic.setChecked(options[0].automatic);changing[0]=false;
        };
        remember.setOnCheckedChangeListener((v,checked)->changeOption.accept("account",checked));
        rememberPassword.setOnCheckedChangeListener((v,checked)->changeOption.accept("password",checked));
        automatic.setOnCheckedChangeListener((v,checked)->changeOption.accept("automatic",checked));
        box.addView(label("自动登录会同时记住账号和密码，仅保存在此设备。",11,MUTED,false));space(box,12);
        qq.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                String account=s.toString().trim();loginIdentifier=account;
                if(!account.equals(preferences.getString("remembered_account",""))){
                    sessionVault.clear();
                    if(preferences.contains("password_cipher")){sessionVault.clearPassword();changeOption.accept("password",false);}
                }
                options[0].save(preferences,account);password.setText(sessionVault.readPassword(api.getBaseUrl(),account));
            }
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

            options[0].save(preferences,user);boolean keepPassword=options[0].password;
            showLoginWaiting();
            io.execute(() -> {
                try {
                    JSONObject result = api.login(user, secret);
                    passwordSaveFailed=keepPassword&&!sessionVault.savePassword(api.getBaseUrl(),user,secret);
                    if(!keepPassword)sessionVault.clearPassword();
                    present(() -> {
                        if (isFinishing() || isDestroyed()) return;
                        finishLoginWaiting();
                        sessionRestoreFailure=null;
                        if(passwordSaveFailed){passwordSaveFailed=false;message("登录成功，但本机保存密码失败，请下次手动登录。");}
                        if (result.optBoolean("must_change_password")) {
                            show("account");
                            showChangePassword();
                        } else show(loginDestination);
                    });
                } catch (Exception e) {
                    if (e instanceof ApiClient.ApiException && ((ApiClient.ApiException) e).status == 401) sessionVault.clearPassword();
                    present(() -> {
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
        Button updates=action("检查更新",false);updates.setOnClickListener(v->checkForUpdates());box.addView(updates);
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
        CodingCatView spinner = new CodingCatView(this);
        wait.addView(spinner, new LinearLayout.LayoutParams(dp(210), dp(140)));
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
        if (avatarPath.isEmpty()) defaultAvatar(headerAvatar);
        else loadAvatar(headerAvatar, avatarPath);
        addAdministratorSection();
        if (user != null) {
        LinearLayout identity = card();
        identity.addView(label("个人资料", 13, BRAND, true));
        menuRow(identity, "修改昵称", value(user, "name", "ACM 成员"), () -> showRename(value(user, "name", "")));
        menuRow(identity, "社区头像", "上传图片或恢复默认", this::showAvatarActions);

        menuRow(identity, "OJ 账号绑定", "App 不支持修改，请到网页端或联系管理员", () -> showBindings(user));
        LinearLayout training = card();
        training.addView(label("我的学习 · 仅自己可见", 13, BRAND, true));
        menuRow(training, "通过题数", "累计 " + result.optInt("total_count") + " 题", () -> showTraining(result));
        menuRow(training, "最近 AC", "题目、平台与通过时间", () -> showRecent(result.optJSONArray("recent_ac")));
        menuRow(training, "今日训练", "稳定基础、主训练、突破上限与挑战历史", () -> show("training"));
        menuRow(training, "赛事复盘", "按比赛查看题目并保存补题状态", () -> show("contests"));
        menuRow(training, "我的题目收藏", "查看自己收藏的题目", () -> navigate("problems",()->problemState="favorite"));
        } else failureBox(card(), FailureState.title(failures[0]), 300, this::loadScreen);
        LinearLayout community = card();community.addView(label("我的社区 · 仅自己可见", 13, TEXT, true));space(community,12);
        LinearLayout shortcuts=row();community.addView(shortcuts);
        communityShortcut(shortcuts,"我的话题","forum",posts,failures[1]);
        communityShortcut(shortcuts,"我的收藏","bookmark",bookmarks,failures[2]);
        communityShortcut(shortcuts,"草稿","drafts",drafts,failures[3]);
        quickTile(shortcuts,"写新话题","compose",()->openDraft(0));
        menuRow(community,"通知中心","回复和审核结果",()->openWebFeature("notifications",0));
        menuRow(community,"投稿进度","查看状态、退回原因与修改记录",()->openWebFeature("submissions",0));
        LinearLayout settings = card();
        settings.addView(label("账号与应用", 13, BRAND, true));
        menuRow(settings,"个性化设置","背景选择 · 主题选择",this::showCoverSettings);
        menuRow(settings, "修改密码", "保护账号安全", this::showChangePassword);
        menuRow(settings, "检查更新", "下载新版 · 自动更新选项", this::checkForUpdates);


        menuRow(settings, "关于 ACMforever", appVersion()+" · 调试版", () -> message("打一辈子爱臭美 / ACMforever\n版本 "+appVersion()+" · 调试版"));
        Button logout = action("退出登录", false);
        logout.setOnClickListener(view -> {
            logout.setEnabled(false);
            io.execute(() -> {
                Exception remoteFailure = null;
                try { api.logout(); }
                catch (Exception e) { remoteFailure = e; }
                Exception logoutFailure = remoteFailure;
                present(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    clearComposer(); commentBody = ""; commentParent = 0;
                    selectedProblem = null; memberPreview = null; loginDestination = "account";
                    show("account");
                    if (logoutFailure != null) message("已退出本机登录。服务端注销未确认：" + FailureState.title(logoutFailure));
                });
            });
        });
        content.addView(logout);
    }

    private boolean isAdministratorAccount() {
        return api.isAdministrator();
    }

    private void addAdministratorSection() { }

    private void showAdministratorMenu() { message("成员、题单与内容管理请使用社团 Web 后台。"); }

    private String value(JSONObject object, String key, String fallback) {
        if (object == null || object.isNull(key)) return fallback;
        String result = object.optString(key, "").trim();
        return result.isEmpty() ? fallback : result;
    }

    private void menuRow(LinearLayout parent, String title, String subtitle, Runnable onClick) {
        LinearLayout line = row();
        line.setPadding(0, dp(12), 0, dp(12));
        line.setMinimumHeight(dp(56));
        LinearLayout copy = column();
        copy.addView(label(title, 15, TEXT, true));
        copy.addView(label(subtitle, 11, MUTED, false));
        line.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
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

    private void postMetric(LinearLayout parent,String icon,int value){
        TextView metric=label(String.valueOf(value),11,MUTED,false);android.graphics.drawable.Drawable image=AppIcons.get(this,icon,MUTED);image.setBounds(0,0,dp(18),dp(18));metric.setCompoundDrawables(image,null,null,null);metric.setCompoundDrawablePadding(dp(4));metric.setPadding(dp(14),0,0,0);parent.addView(metric);
    }
    private LinearLayout quickTile(LinearLayout parent,String title,String icon,Runnable action){
        LinearLayout tile=column();tile.setGravity(Gravity.CENTER);tile.setPadding(0,dp(8),0,dp(8));
        android.widget.ImageView picture=new android.widget.ImageView(this);picture.setImageDrawable(AppIcons.get(this,icon,BRAND));picture.setPadding(dp(8),dp(8),dp(8),dp(8));picture.setBackground(shape(MobileStyle.controlFill(MobileStyle.SELECTED),12,0));tile.addView(picture,new LinearLayout.LayoutParams(dp(46),dp(46)));space(tile,8);
        TextView name=label(title,11,MUTED,false);name.setGravity(Gravity.CENTER);tile.addView(name);tile.setContentDescription(title);tile.setOnClickListener(v->{if(!ModalDialogs.isShowing(this))action.run();});parent.addView(tile,new LinearLayout.LayoutParams(0,-2,1));return tile;
    }
    private void communityShortcut(LinearLayout parent,String title,String icon,JSONArray items,Exception failure){
        quickTile(parent,title,icon,()->{if(items!=null)showPrivateList(title,items);else failureDialog(failure==null?new IllegalStateException("资料不可用"):failure);});
    }

    private AlertDialog detailsDialog(String title, LinearLayout body) {
        body.setPadding(dp(20), dp(8), dp(20), dp(12));
        ScrollView scroll = new ScrollView(this); scroll.addView(body);
        return new ModalDialogs.Builder(this).setTitle(title).setView(scroll).fullPage().show();
    }

    private void showBindings(JSONObject user) {
        LinearLayout body = column();
        body.addView(label("App 不支持账号绑定、改绑、解绑及同步操作，请到网页端或联系管理员。", 14, TEXT, true));
        space(body,12);body.addView(label("以下绑定信息仅本人及管理员可见。", 12, MUTED, false));
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

    private void appearanceEntry(){LinearLayout panel=card();menuRow(panel,"个性化设置","背景选择 · 主题选择",this::showCoverSettings);}
    private void showCoverSettings(){startActivity(new Intent(this,AppearanceActivity.class));}
    private boolean openingSpace;
    private void openSpace(String kind){if(openingSpace)return;openingSpace=true;startActivity(new Intent(this,SpaceActivity.class).putExtra("kind",kind));}
    private void openOwnCollection(String title,String path){
        if(popupLoading||ModalDialogs.isShowing(this)||!requireLogin("mine"))return;
        openSpace(path.contains("bookmarks")?"bookmarks":"posts");
    }
    private void stylePlatformTab(View tab,boolean selected){
        if(tab==null)return;tab.setSelected(selected);View logo=tab.findViewWithTag("platform_logo");if(logo!=null){GradientDrawable circle=shape(Color.TRANSPARENT,999,0);circle.setStroke(dp(selected?3:1),selected?BRAND:LINE);logo.setBackground(circle);}
    }
    private LinearLayout platformCard(LinearLayout panel){LinearLayout box=column();box.setPadding(dp(16),dp(16),dp(16),dp(16));box.setBackground(shape(MobileStyle.MODULE,14,0));LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(-1,-2);size.bottomMargin=dp(12);panel.addView(box,size);return box;}
    private void renderPlatformPanel(LinearLayout panel,JSONObject user,boolean own,String id){
        panel.removeAllViews();JSONObject counts=user.optJSONObject("platform_counts");String number="all".equals(id)?count(user,"total_count"):counts==null||!counts.has(id)?"—":count(counts,id);
        LinearLayout summary=platformCard(panel);summary.setContentDescription("过题数框");LinearLayout row=row(),copy=column();copy.addView(label(PlatformAssets.name(id),17,TEXT,true));space(copy,14);copy.addView(label(number,34,TEXT,true));copy.addView(label("累计通过题数",11,MUTED,false));row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        android.widget.ImageView mark=new android.widget.ImageView(this);mark.setImageDrawable(PlatformAssets.logo(this,id));mark.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);mark.setBackgroundColor(Color.TRANSPARENT);row.addView(mark,new LinearLayout.LayoutParams(dp(88),dp(88)));summary.addView(row);row.setContentDescription(PlatformAssets.name(id)+"通过题数 "+number);
        if(!own){summary.addView(label("公开信息仅展示平台累计通过数。",12,MUTED,false));return;}
        LinearLayout recentBox=platformCard(panel);recentBox.setContentDescription("最近AC框");recentBox.addView(filterSection("最近 AC · 仅自己可见","history"));space(recentBox,10);
        JSONArray recent=user.optJSONArray("recent_ac");if(recent==null){failureBox(recentBox,"无API接口",130,null);return;}
        int shown=0;for(int i=0;i<recent.length()&&shown<10;i++){
            JSONObject item=recent.optJSONObject(i);if(item==null||!"all".equals(id)&&!id.equals(item.optString("platform")))continue;shown++;
            TextView title=label(value(item,"problem_name",value(item,"problem_id","题目")),14,TEXT,true);title.setPadding(0,dp(8),0,dp(4));recentBox.addView(title);
            title.setMinHeight(dp(44));title.setOnClickListener(v->openRecentProblem(item));
            recentBox.addView(label(("all".equals(id)?PlatformAssets.name(item.optString("platform"))+" · ":"")+date(item.optLong("submit_time")),11,MUTED,false));
        }
        if(shown==0)recentBox.addView(label("all".equals(id)?"暂无最近 AC 记录。":"最近记录中暂无该平台的 AC。",12,MUTED,false));
    }

    private void openRecentProblem(JSONObject item){
        String platform=item.optString("platform"),id=item.optString("problem_id");
        if(platform.isEmpty()||id.isEmpty()){failureDialog(new IllegalArgumentException("记录缺少平台或题号"));return;}
        try{JSONObject problem=new JSONObject().put("platform",platform).put("problem_id",id);ModalDialogs.close(this);openProblem(problem);}catch(org.json.JSONException e){failureDialog(e);}
    }

    private void showRecent(JSONArray rows) {
        LinearLayout body = column();
        body.addView(label("这些逐题记录仅自己可见。", 12, MUTED, false));
        if (rows == null || rows.length() == 0) body.addView(label("暂无 AC 记录。", 14, MUTED, false));
        else for (int i = 0; i < rows.length(); i++) {
            JSONObject item = rows.optJSONObject(i); if (item == null) continue;
            space(body, 14);
            TextView title = label(value(item, "problem_name", value(item, "problem_id", "题目")), 15, TEXT, true);
            title.setMinHeight(dp(44));title.setOnClickListener(v -> openRecentProblem(item));
            body.addView(title);
            String date = item.optLong("submit_time") > 0 ? new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.CHINA)
                    .format(new java.util.Date(item.optLong("submit_time") * 1000L)) : "";
            body.addView(label(value(item, "platform", "") + " · " + date, 12, MUTED, false));
        }
        detailsDialog("最近 AC", body);
    }

    private void showPrivateList(String title, JSONArray rows) {
        ModalDialogs.close(this);if("草稿".equals(title)){showCloudDraftList();return;}
        openOwnCollection(title,"我的收藏".equals(title)?"/api/forum/mine/bookmarks":"/api/forum/mine/posts");
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
                    io.execute(() -> { try { api.updateName(name); present(this::loadScreen); }
                    catch (Exception e) { present(() -> failureDialog(e)); } });
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
                    try { api.resetAvatar(); present(this::loadScreen); }
                    catch (Exception e) { present(() -> failureDialog(e)); }
                })).show();
    }

    private String encode(String value) { return UrlEncoding.form(value); }
    private String appVersion(){try{return getPackageManager().getPackageInfo(getPackageName(),0).versionName;}catch(android.content.pm.PackageManager.NameNotFoundException e){return "未知版本";}}

    private void message(String value) {
        new ModalDialogs.Builder(this).setMessage(value).setPositiveButton("知道了", null).show();
    }

    private void openWebFeature(String feature,int id){if(!"wiki".equals(feature)&&!requireLogin("account"))return;startActivity(new Intent(this,WebFeaturesActivity.class).putExtra("feature",feature).putExtra("post_id",id));}
    private void showTools(View anchor) {
        if(ModalDialogs.isShowing(this))return;LinearLayout tools=column();final AlertDialog[] dialog=new AlertDialog[1];
        String[] names={"通知中心","我的投稿","Wiki 手册","比赛进度","训练工具","个性化设置"},targets={"notifications","submissions","wiki","tracker","club","appearance"};
        for(int i=0;i<names.length;i++){String target=targets[i];Button button=action(names[i],false);button.setGravity(Gravity.CENTER);button.setCompoundDrawables(null,null,null,null);button.setCompoundDrawablePadding(0);button.setOnClickListener(v->{dialog[0].dismiss();if("club".equals(target))show("club");else if("appearance".equals(target))showCoverSettings();else openWebFeature(target,0);});tools.addView(button);}
        dialog[0]=new ModalDialogs.Builder(this).setTitle("常用工具").setView(tools).show();
    }

    private void showScanPreview() { message("扫一扫已后置。"); }

    private void openBrowser(String value) {
        try {
            java.net.URI uri=java.net.URI.create(value);
            if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null)throw new IllegalArgumentException("只支持 HTTPS 原题/网页链接。");
            startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(value)));
        }catch(Exception e){message("无法打开链接："+e.getMessage());}
    }

    private void checkForUpdates() { if(openingUpdates)return;openingUpdates=true;startActivity(new Intent(this,UpdateActivity.class)); }


    private String draftKey() {
        return "local_draft_v2_"+android.util.Base64.encodeToString((api.getBaseUrl()+"\n"+(api.isLoggedIn()?api.accountKey():"guest")).getBytes(StandardCharsets.UTF_8),android.util.Base64.NO_WRAP);
    }
    private void loadLocalDraft() {
        try { JSONObject draft=new JSONObject(preferences.getString(draftKey(),"{}"));
            composeTitle=draft.optString("title");composeBody=draft.optString("body");composeCategoryId=draft.optInt("category");composeDraftId=0;composeRevision=0;composeSavedRevision=0;
        }catch(Exception e){clearComposer();}
    }
    private void addClubEntry() {
        LinearLayout box=card(),title=row();title.addView(label("训练工具",13,TEXT,true),new LinearLayout.LayoutParams(0,-2,1));
        TextView all=label("全部  ›",11,MUTED,false);all.setMinHeight(dp(36));all.setGravity(Gravity.CENTER);all.setOnClickListener(v->show("club"));title.addView(all);box.addView(title);
        LinearLayout tools=row();String[] names={"社团题单","我的错题","Wiki","训练打卡"},targets={"sheets","mistakes","templates","checkin"},icons={"problems","forum","templates","checkin"};
        for(int i=0;i<names.length;i++){String target=targets[i];quickTile(tools,names[i],icons[i],()->{if("templates".equals(target))openWebFeature("wiki",0);else show(target);});}box.addView(tools);
        Button progress=action("比赛进度 · 本人 AC 记录",false);progress.setOnClickListener(v->openWebFeature("tracker",0));box.addView(progress);
    }
    private void openTrainingCenter(String target) {
        Intent intent=new Intent(this,ClubActivity.class);intent.putExtra("page",target);
        startActivity(intent);
    }

}
