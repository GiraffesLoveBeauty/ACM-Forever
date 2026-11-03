"""Self-service closure policy and atomic database transition.

Only opaque receipt hashes and non-password intent fingerprints are persisted.
Physical I/O belongs to the durable cleanup worker, after this transaction.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid

from .account_lifecycle_service import AccountLifecycleError, require_web_actor, web_account

POLICY_VERSION = "closure-v1"
RECEIPT_SECONDS = 24 * 60 * 60
AUDIT_DAYS = 180
BACKUP_DAYS = 30
CLOSED_NAME = "已注销用户"
# One rule source drives both the preview and deletion; never describe a delete
# without including the table here (special content/resource rules follow).
PRIVATE_TABLES = {
    "submissions": "user_qq_id", "submission_attempts": "owner_qq_id",
    "user_problem_state": "owner_qq_id", "review_states": "owner_qq_id",
    "contest_problem_reviews": "owner_qq_id", "study_plan_items": "owner_qq_id",
    "workspace_items": "owner_qq_id", "review_drafts": "owner_qq_id",
    "random_challenges": "qq_id", "notification_preferences": "qq_id",
    "forum_notifications": "recipient_qq_id", "forum_bookmarks": "qq_id",
    "forum_post_likes": "qq_id", "forum_drafts": "author_qq_id",
    "account_bind_verifications": "qq_id", "user_platform_sync_state": "user_qq_id",
    "binding_rate_limits": "qq_id",
}
RETENTION_NOTICE = {
    "immediate": True, "recovery_supported": False, "reopen_supported": False,
    "audit_days": AUDIT_DAYS, "backup_days": BACKUP_DAYS,
    "audit_access": "root", "receipt_hours": 24,
    "text": "注销即时生效且不可恢复，同一 QQ 不能重新开户。删除私有训练记录、源码、收藏、草稿与平台绑定；已发布的帖子、评论、Wiki 历史和公共引用图片继续保留，作者显示为已注销用户。保留禁止重开的最小账号墓碑及必要受限引用，审计保留 180 天，备份最长保留 30 天（由部署方执行）。不会删除外部 OJ 账号或退出 QQ 群。公共正文中自行填写的个人信息不自动识别，可通过社区已有举报渠道申请人工处理。",
}


async def one(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def rows(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def intent(data):
    # Deliberately excludes password, its length/hash and all authentication data.
    return digest(json.dumps({key: data.get(key) for key in (
        "confirm_text", "policy_version", "expected_account_epoch"
    )}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def validate_body(data):
    allowed = {"current_password", "confirm_text", "policy_version", "expected_account_epoch"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise AccountLifecycleError("INVALID_REQUEST", "注销请求只能指定当前本人。", 400)
    if data.get("confirm_text") != "注销账号":
        raise AccountLifecycleError("INVALID_CONFIRMATION", "请输入完整确认词：注销账号。", 400)
    if data.get("policy_version") != POLICY_VERSION:
        raise AccountLifecycleError("POLICY_CHANGED", "注销规则已变化，请重新阅读并预览。")
    if type(data.get("expected_account_epoch")) is not int or data["expected_account_epoch"] < 1:
        raise AccountLifecycleError("INVALID_REQUEST", "账号版本无效。", 400)
    password = data.get("current_password")
    if not isinstance(password, str) or not 1 <= len(password) <= 256:
        raise AccountLifecycleError("INVALID_REQUEST", "请输入当前密码（最多 256 字符）。", 400)


async def rate_limit(db, secret, action, subjects, *, now=None, window=900):
    """Reserve a cross-worker budget before expensive or secret-checking work."""
    now = int(time.time()) if now is None else now
    key = secret.encode() if isinstance(secret, str) else secret
    await db.execute("BEGIN IMMEDIATE")
    try:
        for subject, maximum in subjects:
            hashed = hmac.new(key, (action + ":" + subject).encode(), hashlib.sha256).hexdigest()
            row = await one(db, "SELECT * FROM account_sensitive_action_limits WHERE action=? AND subject_hash=?", (action, hashed))
            fresh = not row or now - row["window_start"] >= window
            count = 0 if fresh else row["attempts"]
            if count >= maximum:
                raise AccountLifecycleError("RATE_LIMITED", "操作过于频繁，请稍后再试。", 429)
            await db.execute("INSERT INTO account_sensitive_action_limits VALUES(?,?,?,?) ON CONFLICT(action,subject_hash) DO UPDATE SET window_start=excluded.window_start,attempts=excluded.attempts", (action, hashed, now if fresh else row["window_start"], count + 1))
        await db.execute("DELETE FROM account_sensitive_action_limits WHERE window_start<?", (now - 86400,))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def audit(db, subject, result, *, counts=None, now=None):
    await db.execute("INSERT INTO account_lifecycle_audit(subject_qq_id,action,result_code,policy_version,created_at,counts_json) VALUES(?,'self_close',?,?,?,?)", (subject, result, POLICY_VERSION, int(time.time()) if now is None else now, json.dumps(counts, sort_keys=True) if counts is not None else None))


async def blockers(db, account):
    result = []
    if account["must_change_password"]:
        result.append({"code": "MUST_CHANGE_PASSWORD", "message": "请先完成强制修改密码，再申请注销。"})
    if account["role"] in {"admin", "root"}:
        result.append({"code": "ROLE_HANDOVER_REQUIRED", "message": "请先完成管理职责交接，由另一位有效 Web root 将你降为普通成员，再由本人注销。"})
        if account["role"] == "root":
            from .account_lifecycle_service import web_account_available
            roots = await rows(db, "SELECT a.*,u.account_state,u.account_epoch FROM web_accounts a JOIN users u USING(qq_id) WHERE a.role='root' AND a.qq_id<>?", (account["qq_id"],))
            if not any(web_account_available(root) for root in roots):
                result.insert(0, {"code": "LAST_ROOT_PROTECTED", "message": "当前账号是最后一个可用的 Web root，必须先建立并交接给另一有效 root。"})
    return result


async def closure_plan(db, qq_id):
    deleted = {}
    for table, owner in PRIVATE_TABLES.items():
        item = await one(db, f"SELECT COUNT(*) n FROM {table} WHERE {owner}=?", (qq_id,))
        deleted[table] = item["n"]
    # Only never-public posts can be physically removed. Shared history stays
    # attributable solely through its restricted tombstone reference.
    posts = await rows(db, "SELECT id FROM forum_posts p WHERE author_qq_id=? AND status<>'published' AND NOT EXISTS(SELECT 1 FROM forum_post_history h WHERE h.post_id=p.id AND h.status='published')", (qq_id,))
    deleted["unpublished_posts"] = len(posts)
    deleted["unpublished_versions"] = (await one(db, "SELECT COUNT(*) n FROM forum_post_history h JOIN forum_posts p ON p.id=h.post_id WHERE p.author_qq_id=? AND h.status<>'published'", (qq_id,)))["n"]
    retained = {}
    for label, query in {
        "posts": "SELECT COUNT(*) n FROM forum_posts WHERE author_qq_id=?",
        "comments": "SELECT COUNT(*) n FROM forum_comments WHERE author_qq_id=?",
        "wiki_revisions": "SELECT COUNT(*) n FROM wiki_revisions WHERE author=?",
    }.items():
        retained[label] = (await one(db, query, (qq_id,)))["n"]
    retained["posts"] -= len(posts)
    assets = []
    user = await one(db, "SELECT avatar_url FROM users WHERE qq_id=?", (qq_id,))
    match = re.fullmatch(r"/uploads/avatars/([a-f0-9]{32}\.(?:png|jpg|webp))", user["avatar_url"] or "")
    if match:
        assets.append(("avatar", match[1], None))
    # Scan shared content once, instead of once per owned resource. Immutable
    # history retains referenced assets even if a revision is currently hidden.
    public_forum = {row["image_id"] for row in await rows(db, "SELECT DISTINCT l.image_id FROM forum_image_links l JOIN forum_posts p ON p.id=l.post_id WHERE p.status='published'")}
    public_markdown = {row["asset_id"] for row in await rows(db, "SELECT DISTINCT a.asset_id FROM markdown_asset_references a LEFT JOIN forum_posts p ON a.document_type='forum_post' AND p.id=a.document_id WHERE a.document_type='wiki' OR p.status='published'")}
    for document in await rows(db, "SELECT body FROM wiki_revisions WHERE body LIKE '%/api/%' UNION ALL SELECT body FROM forum_posts WHERE status='published' AND body LIKE '%/api/%' UNION ALL SELECT body FROM forum_post_history WHERE status='published' AND body LIKE '%/api/%'"):
        for kind, asset_id in re.findall(r"/api/(forum/images|markdown/assets)/([a-f0-9]{32})", document["body"]):
            (public_forum if kind == "forum/images" else public_markdown).add(asset_id)
    owned_images = await rows(db, "SELECT id FROM forum_images WHERE owner_qq_id=? AND NOT EXISTS(SELECT 1 FROM account_closure_resource_revocations v WHERE v.resource_kind='forum' AND v.resource_id=forum_images.id)", (qq_id,))
    owned_markdown = await rows(db, "SELECT id,storage_name FROM markdown_assets WHERE owner=? AND NOT EXISTS(SELECT 1 FROM account_closure_resource_revocations v WHERE v.resource_kind='markdown' AND v.resource_id=markdown_assets.id)", (qq_id,))
    for image in owned_images:
        if image["id"] not in public_forum:
            assets.extend([("forum", image["id"] + ".webp", image["id"]), ("forum_thumb", image["id"] + ".webp", image["id"])])
    for asset in owned_markdown:
        if asset["id"] not in public_markdown:
            assets.append(("markdown", asset["storage_name"], asset["id"]))
    deleted["private_resource_files"] = len(assets)
    retained["public_resources"] = len(owned_images) + len(owned_markdown) - sum(kind in {"forum", "markdown"} for kind, _, _ in assets)
    return {"delete_counts": deleted, "retain_counts": retained, "post_ids": [p["id"] for p in posts], "resources": assets}


async def create_preview(db, identity):
    await db.execute("BEGIN IMMEDIATE")
    try:
        await require_web_actor(db, identity)
        account = await web_account(db, identity["qq_id"])
        if identity.get("legacy") or not account:
            raise AccountLifecycleError("LEGACY_IDENTITY_UNSUPPORTED", "旧管理入口不支持注销，请使用真实成员账号。", 403)
        plan = await closure_plan(db, identity["qq_id"])
        problems = await blockers(db, account)
        request_id, token, now = uuid.uuid4().hex, secrets.token_urlsafe(32), int(time.time())
        data = {"confirm_text": "注销账号", "policy_version": POLICY_VERSION, "expected_account_epoch": account["account_epoch"]}
        await db.execute("INSERT INTO account_closure_requests(request_id,user_qq_id,idempotency_key_hash,intent_fingerprint,policy_version,account_epoch,credential_version,created_at,receipt_token_hash,receipt_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (request_id, identity["qq_id"], digest(request_id), intent(data), POLICY_VERSION, account["account_epoch"], account["credential_version"], now, digest(token), now + RECEIPT_SECONDS))
        await db.commit()
        return {"policy_version": POLICY_VERSION, "request_id": request_id, "receipt_token": token, "receipt_expires_at": now + RECEIPT_SECONDS, "account_epoch": account["account_epoch"], "can_close": not problems, "blockers": problems, "delete_counts": plan["delete_counts"], "retain_counts": plan["retain_counts"], "retention_notice": RETENTION_NOTICE}
    except BaseException:
        await db.rollback()
        raise


async def receipt_record(db, request_id, token):
    if not re.fullmatch(r"[a-f0-9]{32}", request_id or "") or not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise AccountLifecycleError("NOT_FOUND", "回执不存在或已过期。", 404)
    row = await one(db, "SELECT * FROM account_closure_requests WHERE request_id=?", (request_id,))
    if not row or row["receipt_expires_at"] <= int(time.time()) or not hmac.compare_digest(row["receipt_token_hash"], digest(token)):
        raise AccountLifecycleError("NOT_FOUND", "回执不存在或已过期。", 404)
    return row


def receipt_result(record):
    return {"request_id": record["request_id"], "policy_version": record["policy_version"], "status": "closed" if record["committed_at"] else "pending", "committed_at": record["committed_at"], "cleanup_state": record["cleanup_state"] if record["committed_at"] else "not_started"}


def scrub_snapshot(value, identifiers, field=None):
    """Scrub identity snapshots while preserving problem IDs and task semantics."""
    if isinstance(value, dict):
        return {key: scrub_snapshot(item, identifiers, key) for key, item in value.items()
                if not (re.fullmatch(r"\d{4,12}", str(key)) and str(key).casefold() in identifiers)}
    if isinstance(value, list):
        return [scrub_snapshot(item, identifiers, field) for item in value
                if field not in {"exclude_qq_ids", "qq_ids", "member_qq_ids"}
                or str(item).casefold() not in identifiers]
    identity_fields = {"qq_id", "user_qq_id", "owner_qq_id", "target_qq_id", "author", "author_qq_id", "handle", "cf_handle", "name", "real_name", "maintainer", "school", "account"}
    if field in identity_fields and str(value).casefold() in identifiers:
        return CLOSED_NAME
    # Shared catalog keys and aggregation values do not represent a person.
    if field in {"status", "statuses", "platform", "problem_id", "problem_index", "contest_id", "candidates", "problems", "scope_fingerprint", "expected_scope_fingerprint"}:
        return value
    if isinstance(value, str):
        for identifier in sorted(identifiers, key=len, reverse=True):
            if len(identifier) >= 3:
                value = re.sub(r"(?<![\w])" + re.escape(identifier) + r"(?![\w])", CLOSED_NAME, value, flags=re.I)
    return value


async def redact_jobs(db, identifiers, qq_id, now):
    for job in await rows(db, "SELECT id,kind,payload,result,error_message FROM cf_practice_jobs"):
        values = []
        for field in ("payload", "result"):
            try:
                parsed = json.loads(job[field]) if job[field] else None
                values.append(json.dumps(scrub_snapshot(parsed, identifiers), ensure_ascii=False) if parsed is not None else None)
            except (TypeError, ValueError):
                # An invalid legacy snapshot cannot be safely made public.
                values.append("{}" if field == "payload" else None)
        values.append(scrub_snapshot(job["error_message"], identifiers))
        await db.execute("UPDATE cf_practice_jobs SET payload=?,result=?,error_message=?,privacy_revision=privacy_revision+1 WHERE id=?", (*values, job["id"]))
        if job["kind"] != "sync":
            await db.execute("UPDATE cf_practice_jobs SET status='failed',result=NULL,error_code='scope_changed',error_message='成员范围已变化，请重新核验',finished_at=? WHERE id=?", (now, job["id"]))
    await db.execute("UPDATE cf_practice_job_members SET status='cancelled',handle=NULL,binding_key=NULL,error_code='account_closed',error_message='成员已注销',finished_at=? WHERE qq_id=?", (now, qq_id))


async def close_account(db, identity, request_id, token, data, verified_account):
    """Caller has reauthenticated outside the lock; this owns the final commit."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        record = await receipt_record(db, request_id, token)
        if record["policy_version"] != POLICY_VERSION or data["policy_version"] != POLICY_VERSION:
            raise AccountLifecycleError("POLICY_CHANGED", "注销规则已变化，请重新预览。")
        if record["intent_fingerprint"] != intent(data):
            raise AccountLifecycleError("IDEMPOTENCY_CONFLICT", "相同请求编号不能用于不同的注销意图。")
        if record["committed_at"]:
            await db.rollback()
            return receipt_result(record)
        if record["user_qq_id"] != identity["qq_id"]:
            raise AccountLifecycleError("INVALID_REQUEST", "只能注销本人账号。", 403)
        await require_web_actor(db, identity)
        account = await web_account(db, identity["qq_id"])
        if (account["account_epoch"] != data["expected_account_epoch"] or account["account_epoch"] != record["account_epoch"] or account["credential_version"] != record["credential_version"] or account["password_hash"] != verified_account["password_hash"] or account["credential_version"] != verified_account["credential_version"]):
            raise AccountLifecycleError("ACCOUNT_CHANGED", "账号或密码已变化，请重新预览并认证。")
        problems = await blockers(db, account)
        if problems:
            raise AccountLifecycleError(problems[0]["code"], problems[0]["message"])
        plan = await closure_plan(db, identity["qq_id"])
        qq_id, now = identity["qq_id"], int(time.time())
        user = await one(db, "SELECT * FROM users WHERE qq_id=?", (qq_id,))
        identifiers = {str(user[field]).casefold() for field in ("qq_id", "name", "real_name", "cf_handle", "luogu_id", "nowcoder_id", "atcoder_handle", "cjlu_username") if user.get(field)}
        # FK rows remain; their personal fields and all reusable credentials go.
        await db.execute("UPDATE users SET account_state='closed',account_epoch=account_epoch+1,closed_at=?,name=?,real_name=NULL,school=NULL,status=NULL,avatar_url=NULL,last_sync_timestamp=0,challenge_rating=1000,cf_handle=NULL,luogu_id=NULL,nowcoder_id=NULL,atcoder_handle=NULL,cjlu_username=NULL,cf_binding_version=cf_binding_version+1,luogu_binding_version=luogu_binding_version+1,nowcoder_binding_version=nowcoder_binding_version+1,atcoder_binding_version=atcoder_binding_version+1,cjlu_binding_version=cjlu_binding_version+1 WHERE qq_id=?", (now, CLOSED_NAME, qq_id))
        await db.execute("UPDATE web_accounts SET is_active=0,role='member',password_hash='!account-closed!',credential_version=credential_version+1,must_change_password=0,temporary_password_expires_at=NULL,last_login_at=NULL,updated_at=? WHERE qq_id=?", (now, qq_id))
        # Drop private document references before their rows disappear.
        await db.execute("DELETE FROM markdown_asset_references WHERE document_type='forum_draft' AND document_id IN (SELECT id FROM forum_drafts WHERE author_qq_id=?)", (qq_id,))
        for table, owner in PRIVATE_TABLES.items():
            await db.execute(f"DELETE FROM {table} WHERE {owner}=?", (qq_id,))
        for post_id in plan["post_ids"]:
            await db.execute("DELETE FROM markdown_asset_references WHERE document_type='forum_post' AND document_id=?", (post_id,))
            await db.execute("DELETE FROM forum_drafts WHERE source_post_id=?", (post_id,))
            await db.execute("DELETE FROM forum_posts WHERE id=?", (post_id,))
        # An unpublished edit of a once-public post cannot remain approvable.
        await db.execute("UPDATE forum_posts SET status='removed',title=COALESCE((SELECT title FROM forum_post_history h WHERE h.post_id=forum_posts.id AND h.status='published' ORDER BY content_version DESC LIMIT 1),title),body=COALESCE((SELECT body FROM forum_post_history h WHERE h.post_id=forum_posts.id AND h.status='published' ORDER BY content_version DESC LIMIT 1),body),cover_image_id=NULL,review_reason='',reviewed_by=NULL WHERE author_qq_id=? AND status<>'published'", (qq_id,))
        await db.execute("DELETE FROM forum_post_history WHERE status<>'published' AND post_id IN (SELECT id FROM forum_posts WHERE author_qq_id=?)", (qq_id,))
        await db.execute("UPDATE forum_notifications SET actor_qq_id=NULL WHERE actor_qq_id=?", (qq_id,))
        await redact_jobs(db, identifiers, qq_id, now)
        # Idempotent Wiki response snapshots may contain a former author's name.
        for item in await rows(db, "SELECT actor,operation,key,response FROM wiki_requests"):
            try:
                response = json.dumps(scrub_snapshot(json.loads(item["response"]), identifiers), ensure_ascii=False)
            except (TypeError, ValueError):
                response = "{}"
            await db.execute("UPDATE wiki_requests SET response=? WHERE actor=? AND operation=? AND key=?", (response, item["actor"], item["operation"], item["key"]))
        for kind, key, asset_id in plan["resources"]:
            if kind == "forum":
                await db.execute("INSERT OR IGNORE INTO account_closure_resource_revocations VALUES('forum',?,?,?)", (asset_id, request_id, now))
                await db.execute("DELETE FROM forum_image_links WHERE image_id=?", (asset_id,))
                await db.execute("DELETE FROM forum_images WHERE id=?", (asset_id,))
            elif kind == "markdown":
                await db.execute("INSERT OR IGNORE INTO account_closure_resource_revocations VALUES('markdown',?,?,?)", (asset_id, request_id, now))
                await db.execute("DELETE FROM markdown_asset_references WHERE asset_id=?", (asset_id,))
                await db.execute("DELETE FROM markdown_assets WHERE id=?", (asset_id,))
            await db.execute("INSERT OR IGNORE INTO account_closure_cleanup_tasks(request_id,resource_kind,resource_key,updated_at) VALUES(?,?,?,?)", (request_id, kind, key, now))
        await db.execute("UPDATE forum_images SET owner_qq_id=NULL WHERE owner_qq_id=?", (qq_id,))
        await db.execute("UPDATE markdown_assets SET owner='' WHERE owner=?", (qq_id,))
        await db.execute("UPDATE wiki_settings SET public_content_version=public_content_version+1 WHERE id=1")
        cleanup = "pending" if plan["resources"] else "completed"
        await db.execute("UPDATE account_closure_requests SET committed_at=?,receipt_expires_at=?,cleanup_state=? WHERE request_id=?", (now, now + RECEIPT_SECONDS, cleanup, request_id))
        # Other pending previews no longer carry valid capabilities.
        await db.execute("DELETE FROM account_closure_requests WHERE user_qq_id=? AND request_id<>? AND committed_at IS NULL", (qq_id, request_id))
        await audit(db, qq_id, "CLOSED", counts={"delete": plan["delete_counts"], "retain": plan["retain_counts"]}, now=now)
        await db.commit()
        return {"request_id": request_id, "policy_version": POLICY_VERSION, "status": "closed", "committed_at": now, "cleanup_state": cleanup}
    except BaseException:
        await db.rollback()
        raise
