// A short-lived capability is scoped to this tab; never store passwords or QQ.
const key = 'acm-account-closure-receipt';
export function readClosure(storage, now = Date.now()) {
  try {
    storage ??= globalThis.sessionStorage;
    const saved = JSON.parse(storage.getItem(key) || 'null');
    if (!saved) return null;
    if (
      !/^[a-f0-9]{32}$/.test(saved.preview?.request_id || '') ||
      typeof saved.preview?.receipt_token !== 'string' ||
      !/^[A-Za-z0-9_-]{32,128}$/.test(saved.preview.receipt_token) ||
      !Number.isFinite(saved.preview.receipt_expires_at) ||
      saved.preview.receipt_expires_at * 1000 <= now
    ) {
      storage.removeItem(key);
      return null;
    }
    return saved;
  } catch {
    return null;
  }
}
export function rememberClosure(preview, submitted = false, storage) {
  // Explicit allowlist prevents form fields from leaking through object spreading.
  const safe = Object.fromEntries(
    [
      'request_id',
      'receipt_token',
      'receipt_expires_at',
      'policy_version',
      'account_epoch',
      'can_close',
      'blockers',
      'delete_counts',
      'retain_counts',
      'retention_notice',
    ].map((field) => [field, preview[field]]),
  );
  try {
    (storage ?? globalThis.sessionStorage).setItem(
      key,
      JSON.stringify({ preview: safe, submitted }),
    );
  } catch {
    /* The in-memory capability remains usable until this tab is closed. */
  }
}
export const closureLabels = {
  submissions: 'AC 记录',
  submission_attempts: '提交尝试与源码',
  user_problem_state: '题目收藏与状态',
  review_states: '历史复习记录',
  contest_problem_reviews: '赛事逐题状态',
  study_plan_items: '历史学习计划',
  workspace_items: '历史工作台',
  review_drafts: '历史复盘草稿',
  random_challenges: '训练挑战',
  notification_preferences: '提醒订阅',
  forum_notifications: '个人通知',
  forum_bookmarks: '社区收藏',
  forum_post_likes: '点赞',
  forum_drafts: '社区草稿',
  account_bind_verifications: '待验证绑定',
  user_platform_sync_state: '平台同步状态',
  binding_rate_limits: '绑定操作状态',
  unpublished_posts: '未公开投稿',
  unpublished_versions: '未公开的投稿历史',
  private_resource_files: '私有资源文件',
  posts: '公共话题与历史',
  comments: '公共评论',
  wiki_revisions: 'Wiki 修订',
  public_resources: '公共引用图片',
};
