"""Shared account identity, evidence cleanup and verified Web binding operations."""
import asyncio
import re
import secrets
import time

import aiohttp
from quart import current_app

from .auth_service import verify_password
from .cf_client import cf_request, CFUnavailable
from .crawler import Crawler

BINDING_FIELDS = {
    "cf": ("cf_handle", "codeforces"), "codeforces": ("cf_handle", "codeforces"),
    "luogu": ("luogu_id", "luogu"), "atcoder": ("atcoder_handle", "atcoder"),
    "nowcoder": ("nowcoder_id", "nowcoder"), "cjlu": ("cjlu_username", "cjlu"),
}
LABELS = {"codeforces": "Codeforces", "luogu": "洛谷", "atcoder": "AtCoder", "nowcoder": "牛客", "cjlu": "校 OJ"}

class BindingError(Exception):
    def __init__(self, message, code="binding_conflict", status=409):
        super().__init__(message)
        self.code, self.status = code, status


def platform_spec(platform):
    value = BINDING_FIELDS.get(str(platform).strip().lower())
    if not value:
        raise BindingError("不支持的平台。", "invalid_platform", 400)
    field, canonical = value
    return canonical, field, "cf_binding_version" if canonical == "codeforces" else canonical + "_binding_version"


def normalize_account(platform, value):
    platform, _, _ = platform_spec(platform)
    value = str(value or "").strip()
    pattern = r"[1-9][0-9]{0,19}" if platform in {"luogu", "nowcoder"} else r"[A-Za-z0-9_.-]{1,64}"
    if not re.fullmatch(pattern, value):
        raise BindingError("账号格式不正确，请输入账号标识而非网址或密码。", "invalid_account", 400)
    return value


async def row(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        return await cursor.fetchone()


async def snapshot(db, qq_id, platform):
    _, field, version = platform_spec(platform)
    user = await row(db, f"SELECT {field} AS account,{version} AS version FROM users WHERE qq_id=?", (qq_id,))
    if not user:
        raise BindingError("当前账号没有关联成员资料。", "member_missing", 404)
    return (user["account"] or "").strip(), int(user["version"] or 0)


async def clear_platform_records(db, qq_id, platform):
    """Only account evidence is cleared; QQ-owned favorites and learning archives stay."""
    for table, owner in (("submissions", "user_qq_id"), ("submission_attempts", "owner_qq_id")):
        await db.execute(f"DELETE FROM {table} WHERE {owner}=? AND platform=?", (qq_id, platform))
    await db.execute("UPDATE random_challenges SET status='abandoned' WHERE qq_id=? AND platform=? AND status='active'", (qq_id, platform))
    await db.execute("DELETE FROM user_platform_sync_state WHERE user_qq_id=? AND platform=?", (qq_id, platform))


async def audit(db, actor, qq_id, platform, action, result="success"):
    await db.execute("INSERT INTO binding_audit(actor_qq_id,target_qq_id,platform,action,result,created_at) VALUES(?,?,?,?,?,?)", (str(actor), str(qq_id), platform, action, result, int(time.time())))


async def apply_binding(db, qq_id, platform, account, *, expected=None, actor=None):
    """Caller owns a write transaction. All Web/Bot writers use the same cleanup."""
    canonical, field, _ = platform_spec(platform)
    previous = await snapshot(db, qq_id, canonical)
    if expected is not None and previous != expected:
        raise BindingError("绑定已变化，请刷新后重新操作。", "binding_changed")
    if previous[0].casefold() != (account or "").casefold():
        await db.execute(f"UPDATE users SET {field}=? WHERE qq_id=?", (account or None, qq_id))
        await clear_platform_records(db, qq_id, canonical)
        await db.execute("DELETE FROM binding_provenance WHERE qq_id=? AND platform=?", (qq_id, canonical))
    await db.execute("DELETE FROM account_bind_verifications WHERE qq_id=? AND platform IN (?,?)", (qq_id, canonical, "cf" if canonical == "codeforces" else canonical))
    await audit(db, actor or qq_id, qq_id, canonical, "unbind" if not account else "replace" if previous[0] else "bind")


async def reserve(db, qq_id, platform, action):
    now = int(time.time()); gap = {"verification": 30, "confirm": 3, "unbind": 3, "sync": 60}[action]
    await db.execute("BEGIN IMMEDIATE")
    state = await row(db, "SELECT * FROM binding_rate_limits WHERE qq_id=? AND platform=? AND action=?", (qq_id, platform, action))
    fresh = not state or now - state["window_start"] >= 900
    if state and (now - state["last_at"] < gap or not fresh and state["attempts"] >= 15):
        await db.rollback()
        raise BindingError("操作过于频繁，请稍后重试。", "rate_limited", 429)
    await db.execute("INSERT INTO binding_rate_limits VALUES(?,?,?,?,?,?) ON CONFLICT(qq_id,platform,action) DO UPDATE SET window_start=excluded.window_start,attempts=excluded.attempts,last_at=excluded.last_at", (qq_id, platform, action, now if fresh else state["window_start"], 1 if fresh else state["attempts"] + 1, now))
    await db.commit()


async def require_password(db, qq_id, data, account):
    if data.get("confirmed") is not True or data.get("current_account") != account:
        raise BindingError("请确认当前平台账号及清理影响。", "confirmation_required", 400)
    web = await row(db, "SELECT password_hash,is_active FROM web_accounts WHERE qq_id=?", (qq_id,))
    password = data.get("password")
    if not web or not web["is_active"] or not isinstance(password, str) or len(password) > 256 or not verify_password(password, web["password_hash"]):
        raise BindingError("当前登录密码不正确。", "invalid_password", 403)


async def validate_account(platform, account):
    """Account validation is shared with the bot; network calls hold no write lock."""
    alias = "cf" if platform == "codeforces" else platform
    engine = getattr(current_app, "sync_engine", None)
    config = engine._crawler_config() if engine else {}
    gate = current_app.config.setdefault("BINDING_NETWORK_GATE", asyncio.Semaphore(4))
    async with gate, asyncio.timeout(20), aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        valid, message = await Crawler.validate_account(session, alias, account, config)
    if not valid:
        raise BindingError(message, "upstream_unavailable" if "不可用" in message else "account_not_found", 503 if "不可用" in message else 400)
    return normalize_account(platform, message)


async def verify_ownership(platform, account, code):
    # CF's API fields are editable profile data, unlike comments elsewhere in profile HTML.
    if platform != "codeforces":
        raise BindingError("该平台的网页归属验证尚未开放，请联系管理员。", "verification_unavailable", 503)
    engine = getattr(current_app, "sync_engine", None)
    config = engine._crawler_config() if engine else {}
    gate = current_app.config.setdefault("BINDING_NETWORK_GATE", asyncio.Semaphore(4))
    async with gate, asyncio.timeout(20), aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        users = await cf_request(session, "user.info", {"handles": account}, config)
    if not isinstance(users, list) or not users or str(users[0].get("handle", "")).casefold() != account.casefold():
        raise BindingError("无法确认目标账号，请重新申请验证。", "account_not_found", 400)
    return any(code.casefold() in str(users[0].get(field) or "").casefold() for field in ("firstName", "lastName", "organization"))


async def create_verification(db, qq_id, platform, data):
    platform, field, _ = platform_spec(platform)
    if platform != "codeforces":
        raise BindingError("该平台暂仅支持查看绑定，请联系管理员修改。", "verification_unavailable", 503)
    account = normalize_account(platform, data.get("account"))
    await reserve(db, qq_id, platform, "verification")
    previous = await snapshot(db, qq_id, platform)
    if previous[0].casefold() == account.casefold():
        raise BindingError("该账号已绑定，无需重复验证。", "already_bound")
    owner = await row(db, f"SELECT qq_id FROM users WHERE LOWER(TRIM({field}))=LOWER(?) AND qq_id<>?", (account, qq_id))
    if owner:
        raise BindingError("该 OJ 账号已绑定给其他成员。", "account_occupied")
    identifier, code, now = secrets.token_hex(16), "ACM" + secrets.token_hex(8), int(time.time())
    await db.execute("BEGIN IMMEDIATE")
    if await snapshot(db, qq_id, platform) != previous:
        raise BindingError("绑定已变化，请重新申请。", "binding_changed")
    await db.execute("DELETE FROM account_bind_verifications WHERE qq_id=? AND platform IN ('cf','codeforces')", (qq_id,))
    await db.execute("INSERT INTO account_bind_verifications(qq_id,platform,account,verification_code,created_at,expires_at,verification_id,expected_binding,binding_version,validated_at) VALUES(?,?,?,?,?,?,?,?,?,0)", (qq_id, "cf", account, code, now, now + 600, identifier, previous[0], previous[1]))
    await db.commit()
    try:
        account = await validate_account(platform, account)
    except BaseException:
        await db.execute("DELETE FROM account_bind_verifications WHERE qq_id=? AND verification_id=?", (qq_id, identifier)); await db.commit()
        raise
    await db.execute("BEGIN IMMEDIATE")
    pending = await row(db, "SELECT verification_id FROM account_bind_verifications WHERE qq_id=? AND platform='cf'", (qq_id,))
    if not pending or pending["verification_id"] != identifier or await snapshot(db, qq_id, platform) != previous:
        raise BindingError("验证已被新操作替代，请重新申请。", "verification_changed")
    await db.execute("UPDATE account_bind_verifications SET account=?,validated_at=? WHERE qq_id=? AND verification_id=?", (account, int(time.time()), qq_id, identifier))
    await db.commit()
    return {"verification_id": identifier, "account": account, "code": code, "expires_at": now + 600, "instructions": "将验证码保存到 Codeforces 设置中的 First name（名字）或 Organization（组织），保存后点击确认验证。不需要提供 OJ 密码。"}


async def confirm_verification(db, qq_id, platform, data):
    platform, _, _ = platform_spec(platform)
    await reserve(db, qq_id, platform, "confirm")
    pending = await row(db, "SELECT * FROM account_bind_verifications WHERE qq_id=? AND platform=?", (qq_id, "cf" if platform == "codeforces" else platform))
    if not pending or not pending["validated_at"] or not pending["verification_id"] or pending["verification_id"] != data.get("verification_id") or pending["expires_at"] <= int(time.time()):
        raise BindingError("验证已过期或被替换，请重新申请。", "verification_expired")
    expected = (pending["expected_binding"] or "", pending["binding_version"])
    if await snapshot(db, qq_id, platform) != expected:
        raise BindingError("绑定已变化，请重新申请验证。", "binding_changed")
    if expected[0]:
        await require_password(db, qq_id, data, expected[0])
    if not await verify_ownership(platform, pending["account"], pending["verification_code"]):
        raise BindingError("公开资料中未找到验证码，请保存后稍后重试。", "ownership_unverified", 400)
    await db.execute("BEGIN IMMEDIATE")
    fresh = await row(db, "SELECT verification_id,expires_at FROM account_bind_verifications WHERE qq_id=? AND platform=?", (qq_id, "cf" if platform == "codeforces" else platform))
    if not fresh or fresh["verification_id"] != pending["verification_id"] or fresh["expires_at"] <= int(time.time()):
        raise BindingError("验证已被替换或过期。", "verification_changed")
    if expected[0]:
        await require_password(db, qq_id, data, expected[0])
    await apply_binding(db, qq_id, platform, pending["account"], expected=expected)
    await record_provenance(db, qq_id, platform, "member_verified", actor=qq_id)
    await db.commit()
    return {"success": True, "account": pending["account"], "message": "绑定成功。"}


async def unbind(db, qq_id, platform, data):
    platform, _, _ = platform_spec(platform)
    await reserve(db, qq_id, platform, "unbind")
    await db.execute("BEGIN IMMEDIATE")
    previous = await snapshot(db, qq_id, platform)
    if not previous[0]:
        raise BindingError("该平台尚未绑定账号。", "not_bound", 400)
    await require_password(db, qq_id, data, previous[0])
    await apply_binding(db, qq_id, platform, None, expected=previous)
    await db.commit()
    return {"success": True, "message": "已解绑。已清理该平台 AC、提交证据与同步状态，并结束进行中的挑战；收藏与历史学习资料保留。"}


async def bindings_summary(db, qq_id):
    user = await row(db, "SELECT * FROM users WHERE qq_id=?", (qq_id,))
    if not user:
        raise BindingError("成员资料不存在。", "member_missing", 404)
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_provider")
    tasks = provider() if callable(provider) else []
    result = []
    for platform in LABELS:
        _, field, version_field = platform_spec(platform)
        identity = {"account": user[field] or "", "version": int(user[version_field])}
        state = await row(db, "SELECT * FROM user_platform_sync_state WHERE user_qq_id=? AND platform=?", (qq_id, platform))
        pending = await row(db, "SELECT account,verification_id,verification_code,expires_at FROM account_bind_verifications WHERE qq_id=? AND platform=? AND validated_at>0 AND expires_at>?", (qq_id, "cf" if platform == "codeforces" else platform, int(time.time())))
        active = next((task for task in tasks if str(task.get("qq_id")) == str(qq_id) and platform in str(task.get("platform", "")).split(",") and task.get("status") in {"queued", "running"} and (task.get("bindings") is None or task["bindings"].get(platform) == identity)), None)
        engine = getattr(current_app, "sync_engine", None)
        lock = getattr(engine, "_sync_user_locks", {}).get(str(qq_id))
        token = getattr(engine, "_binding_tokens", {}).get((str(qq_id), platform))
        live_sync = state and state["last_status"] == "running" and lock and lock.locked() and token and token[3] == identity["version"] and token[2].casefold() == identity["account"].casefold()
        account = user[field] or ""
        status = "running" if live_sync else active["status"] if active and account else "success" if state and state["last_status"] in {"success", "backfill"} else "failed" if state and state["last_status"] not in {"never", "migrated"} else "never"
        message = {"never": "账号已绑定，尚无成功同步记录。" if account else "尚未绑定 OJ 账号。", "queued": "同步已排队。", "running": "正在同步，已有记录仍可查看。", "success": "同步成功。", "failed": "最近同步失败或任务已中断，可重试；有效历史数据保留。"}[status]
        result.append({"platform": platform, "label": LABELS[platform], "account": account, "binding_status": "pending" if pending else "bound" if account else "unbound", "self_service": platform == "codeforces", "sync_status": status, "last_success_at": state["last_success_at"] if state else 0, "message": message, "verification": {"account": pending["account"], "verification_id": pending["verification_id"], "code": pending["verification_code"], "expires_at": pending["expires_at"]} if pending else None})
    for item in result:
        provenance = await row(db, "SELECT source,owner_verified_at,existence_status FROM binding_provenance WHERE qq_id=? AND platform=? AND binding_version=? AND account_canonical=?", (qq_id, item["platform"], user[platform_spec(item["platform"])[2]], item["account"].casefold()))
        item["provenance"] = dict(provenance) if provenance else None
    return result

async def record_provenance(db, qq_id, platform, source, *, actor=None, batch_id=None, now=None):
    platform, _, _ = platform_spec(platform)
    account, version = await snapshot(db, qq_id, platform)
    now = int(time.time()) if now is None else now
    await db.execute("INSERT INTO binding_provenance(qq_id,platform,binding_version,account_canonical,source,actor_qq_id,import_batch_id,recorded_at,owner_verified_at,existence_status) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(qq_id,platform) DO UPDATE SET binding_version=excluded.binding_version,account_canonical=excluded.account_canonical,source=excluded.source,actor_qq_id=excluded.actor_qq_id,import_batch_id=excluded.import_batch_id,recorded_at=excluded.recorded_at,owner_verified_at=excluded.owner_verified_at,existence_status=excluded.existence_status", (qq_id, platform, version, account.casefold(), source, str(actor) if actor else None, batch_id, now, now if source == "member_verified" else None, "exists" if source == "member_verified" else "not_checked"))

async def mark_dispatch_failure(db, qq_id, platform, expected):
    _, field, version = platform_spec(platform)
    account, generation = expected
    await db.execute(
        "INSERT INTO user_platform_sync_state(user_qq_id,platform,last_status,last_error_code,last_error_message,last_attempt_at,updated_at) "
        f"SELECT ?,?,'failed','dispatch_failed','同步任务未能排队',?,? FROM users WHERE qq_id=? AND {version}=? AND LOWER(TRIM(COALESCE({field},'')))=LOWER(?) "
        "ON CONFLICT(user_qq_id,platform) DO UPDATE SET last_status=excluded.last_status,last_error_code=excluded.last_error_code,last_error_message=excluded.last_error_message,last_attempt_at=excluded.last_attempt_at,updated_at=excluded.updated_at",
        (qq_id, platform, int(time.time()), int(time.time()), qq_id, generation, account),
    )
    await db.commit()
