# -*- coding: utf-8 -*-
"""WebUI 后台 API（移植自 astrbot_plugin_acm_helper/backend/api.py）"""
import hashlib
import hmac
import inspect
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from functools import wraps

import aiohttp
import aiosqlite
from quart import Blueprint, Response, current_app, jsonify, request, session

import logging

from .auth_service import (
    generate_temporary_password,
    hash_password,
    resolve_client_ip,
    temporary_password_expiry,
    validate_password,
    verify_password,
)
from .reporting import valid_contest_report_time

LOG = logging.getLogger("acm_api")
api = Blueprint("api", __name__)

_LOGIN_ATTEMPTS = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_FAILURES = 5
_LOGIN_IP_MAX_FAILURES = 100
_ACCOUNT_FIELDS = (
    ("cf", "cf_handle", "Codeforces"),
    ("luogu", "luogu_id", "洛谷"),
    ("nowcoder", "nowcoder_id", "牛客"),
    ("atcoder", "atcoder_handle", "AtCoder"),
    ("cjlu", "cjlu_username", "校OJ"),
)


def _client_key():
    config = current_app.config.get("PLUGIN_CONFIG", {})
    trusted = config.get("webui_trusted_proxies", [])
    if isinstance(trusted, str):
        trusted = [item.strip() for item in trusted.replace("，", ",").split(",") if item.strip()]
    return resolve_client_ip(
        request.remote_addr,
        request.headers.get("X-Forwarded-For", ""),
        trusted,
    )


def _temporary_password_ttl_hours():
    value = current_app.config.get("PLUGIN_CONFIG", {}).get("webui_temporary_password_ttl_hours", 72)
    try:
        hours = int(value)
    except (TypeError, ValueError):
        hours = 72
    return hours if 1 <= hours <= 720 else 72


def _temporary_password_expiry(now=None):
    now = int(time.time()) if now is None else int(now)
    return temporary_password_expiry(now, _temporary_password_ttl_hours())


def _configured_password():
    config = current_app.config.get("PLUGIN_CONFIG", {})
    return (
        config.get("webui_admin_password_hash")
        or os.environ.get("ACM_WEBUI_ADMIN_PASSWORD_HASH")
        or config.get("webui_admin_password")
        or os.environ.get("ACM_WEBUI_ADMIN_PASSWORD")
        or ""
    ).strip()


def _legacy_login_enabled():
    value = current_app.config.get("PLUGIN_CONFIG", {}).get("webui_legacy_admin_login", True)
    return value if isinstance(value, bool) else str(value).strip().lower() not in {"false", "0", "off", "no"}


def _verify_password(password, configured):
    if configured.startswith("pbkdf2_sha256$"):
        return verify_password(password, configured)
    # Backward compatibility for existing deployments; new deployments should use a hash.
    return hmac.compare_digest(password, configured)


def _csrf_valid():
    token = request.headers.get("X-CSRF-Token", "")
    expected = session.get("webui_csrf", "")
    return bool(token and expected and hmac.compare_digest(token, expected))


def _field(data, key, limit=128):
    value = data.get(key, "")
    if not isinstance(value, (str, int)):
        return ""
    return str(value).strip()[:limit]


def _valid_qq(value):
    return value.isdigit() and 4 <= len(value) <= 12


def _changed_account_platforms(account_values, existing=None):
    """返回因本次 WebUI 保存而需要重建做题记录的平台。"""
    changed = []
    for platform, field, label in _ACCOUNT_FIELDS:
        account = str(account_values.get(field) or "").strip()
        old_account = str(existing[field] or "").strip() if existing else ""
        account_values[field] = account or None
        if old_account.casefold() != account.casefold():
            changed.append(("codeforces" if platform == "cf" else platform, label, bool(account)))
    return changed


async def _clear_platform_records(db, qq_id, platform):
    """账号变更后清理旧账号遗留的平台数据和同步游标。"""
    for table, owner_field in (
        ("submissions", "user_qq_id"),
        ("submission_attempts", "owner_qq_id"),
        ("user_problem_state", "owner_qq_id"),
        ("review_states", "owner_qq_id"),
        ("study_plan_items", "owner_qq_id"),
    ):
        await db.execute(
            f"DELETE FROM {table} WHERE {owner_field}=? AND platform=?", (qq_id, platform)
        )
    await db.execute(
        "UPDATE random_challenges SET status='abandoned' "
        "WHERE qq_id=? AND platform=? AND status='active'",
        (qq_id, platform),
    )
    await db.execute(
        "DELETE FROM user_platform_sync_state WHERE user_qq_id=? AND platform=?",
        (qq_id, platform),
    )


async def get_db():
    db_path = current_app.config.get("DB_PATH")
    if not db_path:
        raise ConnectionError("DB path not configured.")
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


def _admin_configured():
    config = current_app.config.get("PLUGIN_CONFIG", {})
    username = config.get("webui_admin_username") or os.environ.get("ACM_WEBUI_ADMIN_USERNAME")
    return bool(username and _configured_password() and current_app.secret_key)


async def _session_identity():
    """Resolve the current identity from the database on every protected request."""
    if session.get("webui_legacy"):
        if _legacy_login_enabled() and _admin_configured():
            return {"qq_id": None, "role": "root", "must_change_password": False, "legacy": True}
        session.clear()
        return None
    if not session.get("webui_authenticated"):
        return None
    qq_id = str(session.get("webui_qq_id", ""))
    if not _valid_qq(qq_id):
        session.clear()
        return None
    try:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT role,must_change_password,is_active,credential_version,temporary_password_expires_at "
                "FROM web_accounts WHERE qq_id=?", (qq_id,)
            ) as cursor:
                account = await cursor.fetchone()
        finally:
            await db.close()
    except Exception:
        LOG.exception("验证 Web 会话时读取账号失败。")
        return None
    if (not account or not account["is_active"]
            or int(account["credential_version"]) != int(session.get("webui_credential_version", -1))):
        session.clear()
        return None
    if (account["must_change_password"] and account["temporary_password_expires_at"]
            and int(account["temporary_password_expires_at"]) <= int(time.time())):
        session.clear()
        return None
    return {
        "qq_id": qq_id,
        "role": account["role"],
        "must_change_password": bool(account["must_change_password"]),
        "credential_version": int(account["credential_version"]),
        "legacy": False,
    }


async def _login_required_response(allow_password_change=False):
    identity = await _session_identity()
    if identity is None:
        return None, (jsonify({"success": False, "message": "请先登录。"}), 401)
    if identity["must_change_password"] and not allow_password_change:
        return None, (jsonify({"success": False, "message": "首次登录请先修改密码。", "must_change_password": True}), 428)
    return identity, None


def _rate_limit_keys(ip_key, account_key):
    return (f"ip:{ip_key}", f"account:{account_key}")


def _login_rate_limited(keys, now):
    for key in keys:
        attempts = _LOGIN_ATTEMPTS[key]
        while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        limit = _LOGIN_IP_MAX_FAILURES if key.startswith("ip:") else _LOGIN_MAX_FAILURES
        if len(attempts) >= limit:
            return True
    return False


def _record_login_failure(keys, now):
    for key in keys:
        _LOGIN_ATTEMPTS[key].append(now)
    if len(_LOGIN_ATTEMPTS) > 10_000:
        cutoff = now - _LOGIN_WINDOW_SECONDS
        for key in [key for key, attempts in _LOGIN_ATTEMPTS.items() if not attempts or attempts[-1] <= cutoff]:
            _LOGIN_ATTEMPTS.pop(key, None)


def _clear_login_failures(keys):
    for key in keys:
        _LOGIN_ATTEMPTS.pop(key, None)


def admin_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        identity, error = await _login_required_response()
        if error:
            return error
        if identity["role"] not in {"admin", "root"}:
            return jsonify({"success": False, "message": "此操作仅限 Web 管理员。"}), 403
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _csrf_valid():
            return jsonify({"success": False, "message": "CSRF 校验失败。"}), 403
        return await func(*args, **kwargs)
    return wrapper


def member_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        identity, error = await _login_required_response()
        if error:
            return error
        if not _valid_qq(str(identity.get("qq_id") or "")):
            return jsonify({"success": False, "message": "当前会话没有绑定成员 QQ。"}), 403
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _csrf_valid():
            return jsonify({"success": False, "message": "CSRF 校验失败。"}), 403
        request.web_identity = identity
        return await func(*args, **kwargs)
    return wrapper


def _webui_is_root():
    return session.get("webui_role") == "root" or bool(session.get("webui_legacy"))


def _root_required_response():
    if not _webui_is_root():
        return jsonify({"success": False, "message": "此操作仅限 root。"}), 403
    return None


def _admin_snapshot():
    config = current_app.config.get("PLUGIN_CONFIG", {})
    provider = config.get("_admin_config_provider")
    snapshot = provider() if callable(provider) else {"root": [], "admins": []}
    return {
        "root": {str(value).strip() for value in snapshot.get("root", [])},
        "admins": {str(value).strip() for value in snapshot.get("admins", [])},
    }


@api.route("/auth/login", methods=["POST"])
async def api_auth_login():
    now = time.monotonic()
    now_epoch = int(time.time())
    if not current_app.secret_key:
        return jsonify({"success": False, "message": "WebUI 尚未配置安全密钥。"}), 503
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    qq_id = str(data.get("qq_id", "")).strip()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    legacy_username = str(data.get("username", ""))
    account_key = qq_id if qq_id else f"legacy:{legacy_username[:128]}"
    rate_keys = _rate_limit_keys(_client_key(), account_key)
    if _login_rate_limited(rate_keys, now):
        return jsonify({"success": False, "message": "登录尝试过于频繁，请稍后再试。"}), 429
    account = None
    temporary_password_expired = False
    if _valid_qq(qq_id):
        db = await get_db()
        try:
            async with db.execute(
                "SELECT password_hash,role,must_change_password,is_active,credential_version,temporary_password_expires_at "
                "FROM web_accounts WHERE qq_id=?", (qq_id,)
            ) as cursor:
                account = await cursor.fetchone()
            if (account and account["is_active"] and account["must_change_password"]
                    and account["temporary_password_expires_at"]
                    and int(account["temporary_password_expires_at"]) <= now_epoch):
                temporary_password_expired = True
                account = None
            elif account and account["is_active"] and verify_password(password, account["password_hash"]):
                await db.execute("UPDATE web_accounts SET last_login_at=?,updated_at=? WHERE qq_id=?", (int(time.time()), int(time.time()), qq_id))
                await db.commit()
            else:
                account = None
        finally:
            await db.close()
    config = current_app.config.get("PLUGIN_CONFIG", {})
    configured_username = str(config.get("webui_admin_username") or os.environ.get("ACM_WEBUI_ADMIN_USERNAME") or "")
    legacy_login = bool(
        not account and not temporary_password_expired and _legacy_login_enabled() and _admin_configured()
        and hmac.compare_digest(legacy_username, configured_username)
        and _verify_password(password, _configured_password())
    )
    if not account and not legacy_login:
        _record_login_failure(rate_keys, now)
        LOG.warning("WebUI 登录失败，来源=%s", _client_key())
        message = "临时密码已过期，请联系管理员重新发放。" if temporary_password_expired else "QQ号或密码错误。"
        return jsonify({"success": False, "message": message}), 401
    _clear_login_failures(rate_keys)
    session.clear()
    if legacy_login:
        session["webui_legacy"] = True
        session["webui_role"] = "root"
        session["webui_qq_id"] = None
        role = "root"
        must_change_password = False
    else:
        session["webui_authenticated"] = True
        session["webui_qq_id"] = qq_id
        session["webui_role"] = account["role"]
        session["webui_credential_version"] = int(account["credential_version"])
        role = account["role"]
        must_change_password = bool(account["must_change_password"])
    session["webui_csrf"] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({"success": True, "csrf_token": session["webui_csrf"], "root": role == "root", "role": role, "qq_id": qq_id or None, "must_change_password": must_change_password})


@api.route("/auth/logout", methods=["POST"])
async def api_auth_logout():
    if session.get("webui_authenticated") or session.get("webui_legacy"):
        if not _csrf_valid():
            return jsonify({"success": False, "message": "CSRF 校验失败。"}), 403
    session.clear()
    return jsonify({"success": True})


@api.route("/auth/me", methods=["GET"])
async def api_auth_me():
    identity = await _session_identity()
    if not identity:
        return jsonify({"authenticated": False, "csrf_token": None, "root": False, "role": None, "qq_id": None, "must_change_password": False})
    return jsonify({"authenticated": True, "csrf_token": session.get("webui_csrf"), "root": identity["role"] == "root", "role": identity["role"], "qq_id": identity["qq_id"], "must_change_password": identity["must_change_password"]})


@api.route("/auth/change-password", methods=["POST"])
async def api_auth_change_password():
    identity = await _session_identity()
    if identity is None:
        return jsonify({"success": False, "message": "请先登录。"}), 401
    if not _csrf_valid():
        return jsonify({"success": False, "message": "CSRF 校验失败。"}), 403
    if identity["legacy"]:
        return jsonify({"success": False, "message": "请先由现有 Web 管理员创建并验证 QQ Web 管理员账号。"}), 409
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    old_password = str(data.get("old_password", ""))
    new_password = str(data.get("new_password", ""))
    if not old_password or len(old_password) > 128:
        return jsonify({"success": False, "message": "当前密码错误。"}), 400
    validation_error = validate_password(new_password)
    if validation_error:
        return jsonify({"success": False, "message": validation_error}), 400
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT password_hash,credential_version,is_active FROM web_accounts WHERE qq_id=?",
            (identity["qq_id"],),
        ) as cursor:
            account = await cursor.fetchone()
        if not account or not account["is_active"] or not verify_password(old_password, account["password_hash"]):
            await db.rollback()
            return jsonify({"success": False, "message": "当前密码错误。"}), 400
        new_version = int(account["credential_version"]) + 1
        now = int(time.time())
        await db.execute(
            "UPDATE web_accounts SET password_hash=?,must_change_password=0,temporary_password_expires_at=NULL,credential_version=?,updated_at=? WHERE qq_id=?",
            (hash_password(new_password), new_version, now, identity["qq_id"]),
        )
        await db.commit()
        session["webui_credential_version"] = new_version
        session["webui_role"] = identity["role"]
        return jsonify({"success": True, "must_change_password": False})
    except Exception:
        await db.rollback()
        LOG.exception("修改 Web 账号密码失败，QQ=%s", identity["qq_id"])
        return jsonify({"success": False, "message": "修改密码失败，请稍后重试。"}), 500
    finally:
        await db.close()


@api.route("/admin/web-accounts", methods=["GET", "POST"])
@admin_required
async def api_web_accounts():
    db = await get_db()
    try:
        if request.method == "GET":
            async with db.execute(
                "SELECT a.qq_id,a.role,a.must_change_password,a.is_active,a.created_at,a.updated_at,a.last_login_at,"
                "a.temporary_password_expires_at,u.name,u.status,u.school "
                "FROM web_accounts a JOIN users u ON u.qq_id=a.qq_id ORDER BY a.created_at DESC"
            ) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])

        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        qq_id = _field(data, "qq_id", 12)
        initial_password = str(data.get("initial_password", ""))
        name = _field(data, "name", 100)
        status = _field(data, "status", 64) or None
        school = _field(data, "school", 128) or None
        role = str(data.get("role", "member")).strip().lower()
        actor = await _session_identity()
        if not _valid_qq(qq_id):
            return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
        if role not in {"member", "admin", "root"}:
            return jsonify({"success": False, "message": "角色必须为 member、admin 或 root。"}), 400
        if role != "member" and (not actor or actor["role"] != "root"):
            return jsonify({"success": False, "message": "只有 Web root 可以创建管理员账号。"}), 403
        if (error := validate_password(initial_password)):
            return jsonify({"success": False, "message": error}), 400
        now = int(time.time())
        password_hash = hash_password(initial_password)
        temporary_password_expires_at = _temporary_password_expiry(now) if role == "member" else None
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute("SELECT qq_id FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            member = await cursor.fetchone()
        if not member and not name:
            await db.rollback()
            return jsonify({"success": False, "message": "新成员必须填写昵称。"}), 400
        async with db.execute("SELECT 1 FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            existing_account = await cursor.fetchone()
        if existing_account:
            await db.rollback()
            return jsonify({"success": False, "message": "该 QQ 已有 Web 账号。"}), 409
        if not member:
            await db.execute(
                "INSERT INTO users(qq_id,name,status,school) VALUES(?,?,?,?)",
                (qq_id, name, status, school),
            )
        await db.execute(
            "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at,temporary_password_expires_at) "
            "VALUES(?,?,?,1,1,1,?,?,?)",
            (qq_id, password_hash, role, now, now, temporary_password_expires_at),
        )
        await db.commit()
        _clear_login_failures((f"account:{qq_id}",))
        message = "成员资料与 Web 账号已创建。" if not member else "Web 账号已绑定到现有成员资料。"
        return jsonify({"success": True, "qq_id": qq_id, "role": role, "must_change_password": True, "message": message}), 201
    except sqlite3.IntegrityError:
        await db.rollback()
        return jsonify({"success": False, "message": "账号创建冲突，请确认成员 QQ 号唯一。"}), 409
    except Exception:
        await db.rollback()
        LOG.exception("创建 Web 账号失败。")
        return jsonify({"success": False, "message": "创建 Web 账号失败，请稍后重试。"}), 500
    finally:
        await db.close()


@api.route("/admin/web-account-candidates", methods=["GET"])
@admin_required
async def api_web_account_candidates():
    search = str(request.args.get("search", "")).strip()[:80]
    include_issued = str(request.args.get("include_issued", "")).strip().lower() in {"1", "true", "yes"}
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(100, int(request.args.get("page_size", 20))))
    except (TypeError, ValueError):
        page_size = 20

    conditions = []
    params = []
    if not include_issued:
        conditions.append("a.qq_id IS NULL")
    if search:
        conditions.append("(u.qq_id LIKE ? OR lower(COALESCE(u.name,'')) LIKE ? OR lower(COALESCE(u.school,'')) LIKE ?)")
        pattern = f"%{search.lower()}%"
        params.extend((f"%{search}%", pattern, pattern))
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    db = await get_db()
    try:
        async with db.execute(
            "SELECT COUNT(*) FROM users u LEFT JOIN web_accounts a ON a.qq_id=u.qq_id" + where,
            tuple(params),
        ) as cursor:
            total = int((await cursor.fetchone())[0])
        async with db.execute(
            "SELECT u.qq_id,u.name,u.school,u.status,a.role,a.is_active,a.must_change_password,"
            "a.temporary_password_expires_at "
            "FROM users u LEFT JOIN web_accounts a ON a.qq_id=u.qq_id" + where +
            " ORDER BY u.name COLLATE NOCASE,u.qq_id LIMIT ? OFFSET ?",
            tuple(params + [page_size, (page - 1) * page_size]),
        ) as cursor:
            items = []
            for row in await cursor.fetchall():
                item = dict(row)
                item["has_web_account"] = item["role"] is not None
                if item["is_active"] is not None:
                    item["is_active"] = bool(item["is_active"])
                if item["must_change_password"] is not None:
                    item["must_change_password"] = bool(item["must_change_password"])
                items.append(item)
        return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})
    finally:
        await db.close()


@api.route("/admin/web-accounts/batch", methods=["POST"])
@admin_required
async def api_batch_create_web_accounts():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"qq_ids"} or not isinstance(data["qq_ids"], list):
        return jsonify({"success": False, "message": "请求仅接受 qq_ids 数组。"}), 400
    qq_ids = data["qq_ids"]
    if not 1 <= len(qq_ids) <= 20:
        return jsonify({"success": False, "message": "每批须选择 1–20 位成员。"}), 400

    skipped = []
    unique_ids = []
    seen = set()
    for value in qq_ids:
        qq_id = value.strip() if isinstance(value, str) else ""
        if not _valid_qq(qq_id):
            skipped.append({"qq_id": qq_id[:12], "reason": "invalid_qq"})
        elif qq_id in seen:
            skipped.append({"qq_id": qq_id, "reason": "duplicate_in_request"})
        else:
            seen.add(qq_id)
            unique_ids.append(qq_id)

    if not unique_ids:
        return jsonify({"created": [], "skipped": skipped})

    eligible = []
    db = await get_db()
    try:
        for qq_id in unique_ids:
            async with db.execute(
                "SELECT u.qq_id,u.name,a.qq_id AS account_qq_id FROM users u "
                "LEFT JOIN web_accounts a ON a.qq_id=u.qq_id WHERE u.qq_id=?",
                (qq_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                skipped.append({"qq_id": qq_id, "reason": "member_not_found"})
            elif row["account_qq_id"]:
                skipped.append({"qq_id": qq_id, "reason": "already_exists"})
            else:
                eligible.append({"qq_id": qq_id, "name": row["name"]})
    finally:
        await db.close()

    used_passwords = set()
    for item in eligible:
        temporary_password = generate_temporary_password(used_passwords)
        item["temporary_password"] = temporary_password
        item["password_hash"] = hash_password(temporary_password)

    created = []
    if eligible:
        now = int(time.time())
        expires_at = _temporary_password_expiry(now)
        db = await get_db()
        try:
            await db.execute("BEGIN IMMEDIATE")
            for item in eligible:
                async with db.execute(
                    "SELECT 1 FROM users WHERE qq_id=?", (item["qq_id"],)
                ) as cursor:
                    member_exists = await cursor.fetchone()
                if not member_exists:
                    skipped.append({"qq_id": item["qq_id"], "reason": "member_not_found"})
                    continue
                async with db.execute(
                    "SELECT 1 FROM web_accounts WHERE qq_id=?", (item["qq_id"],)
                ) as cursor:
                    account_exists = await cursor.fetchone()
                if account_exists:
                    skipped.append({"qq_id": item["qq_id"], "reason": "already_exists"})
                    continue
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,"
                    "credential_version,created_at,updated_at,temporary_password_expires_at) "
                    "VALUES(?,?, 'member',1,1,1,?,?,?)",
                    (item["qq_id"], item["password_hash"], now, now, expires_at),
                )
                created.append({
                    "qq_id": item["qq_id"],
                    "name": item["name"],
                    "temporary_password": item["temporary_password"],
                    "expires_at": expires_at,
                })
            await db.commit()
        except Exception:
            await db.rollback()
            LOG.exception("批量创建 Web 成员账号失败，数量=%s", len(eligible))
            return jsonify({"success": False, "message": "批量创建失败；本批未发放，请重试。"}), 500
        finally:
            await db.close()

        for item in created:
            _clear_login_failures((f"account:{item['qq_id']}",))

    LOG.info("批量 Web 临时账号发放完成：成功 %s，跳过 %s。", len(created), len(skipped))
    return jsonify({"created": created, "skipped": skipped})


@api.route("/admin/web-accounts/<qq_id>", methods=["PATCH"])
@admin_required
async def api_update_web_account(qq_id):
    qq_id = str(qq_id).strip()
    if not _valid_qq(qq_id):
        return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute("SELECT role,is_active FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            target = await cursor.fetchone()
        if not target:
            await db.rollback()
            return jsonify({"success": False, "message": "Web 账号不存在。"}), 404
        actor = await _session_identity()
        if target["role"] in {"admin", "root"} and (not actor or actor["role"] != "root"):
            await db.rollback()
            return jsonify({"success": False, "message": "只有 Web root 可以修改管理员账号。"}), 403
        role = str(data.get("role", target["role"])).strip().lower()
        active = data.get("is_active", bool(target["is_active"]))
        if role not in {"member", "admin", "root"} or not isinstance(active, bool):
            await db.rollback()
            return jsonify({"success": False, "message": "角色或启用状态无效。"}), 400
        if role != "member" and (not actor or actor["role"] != "root"):
            await db.rollback()
            return jsonify({"success": False, "message": "只有 Web root 可以授予管理员角色。"}), 403
        legacy_admin_available = _legacy_login_enabled() and _admin_configured()
        if target["role"] == "root" and (role != "root" or not active) and not legacy_admin_available:
            async with db.execute("SELECT COUNT(*) AS count FROM web_accounts WHERE role='root' AND is_active=1 AND qq_id<>?", (qq_id,)) as cursor:
                other_roots = int((await cursor.fetchone())["count"])
            if other_roots == 0:
                await db.rollback()
                return jsonify({"success": False, "message": "不能停用或降级最后一个 Web root。"}), 409
        now = int(time.time())
        await db.execute(
            "UPDATE web_accounts SET role=?,is_active=?,credential_version=credential_version+1,updated_at=? WHERE qq_id=?",
            (role, int(active), now, qq_id),
        )
        await db.commit()
        return jsonify({"success": True, "qq_id": qq_id, "role": role, "is_active": active})
    except Exception:
        await db.rollback()
        LOG.exception("更新 Web 账号失败，QQ=%s", qq_id)
        return jsonify({"success": False, "message": "更新 Web 账号失败，请稍后重试。"}), 500
    finally:
        await db.close()


@api.route("/admin/web-accounts/<qq_id>/reset-password", methods=["POST"])
@admin_required
async def api_reset_web_account_password(qq_id):
    qq_id = str(qq_id).strip()
    if not _valid_qq(qq_id):
        return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    initial_password = str(data.get("initial_password", ""))
    if (error := validate_password(initial_password)):
        return jsonify({"success": False, "message": error}), 400
    db = await get_db()
    try:
        async with db.execute("SELECT role FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            target = await cursor.fetchone()
        if not target:
            return jsonify({"success": False, "message": "Web 账号不存在。"}), 404
        actor = await _session_identity()
        if target["role"] in {"admin", "root"} and (not actor or actor["role"] != "root"):
            return jsonify({"success": False, "message": "只有 Web root 可以重置管理员密码。"}), 403
        now = int(time.time())
        await db.execute(
            "UPDATE web_accounts SET password_hash=?,must_change_password=1,temporary_password_expires_at=?,credential_version=credential_version+1,updated_at=? WHERE qq_id=?",
            (hash_password(initial_password), _temporary_password_expiry(now) if target["role"] == "member" else None, now, qq_id),
        )
        await db.commit()
        _clear_login_failures((f"account:{qq_id}",))
        return jsonify({"success": True, "qq_id": qq_id, "must_change_password": True})
    finally:
        await db.close()


@api.route("/admin/web-accounts/<qq_id>/reset-temporary-password", methods=["POST"])
@admin_required
async def api_reset_temporary_web_account_password(qq_id):
    qq_id = str(qq_id).strip()
    if not _valid_qq(qq_id):
        return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400

    db = await get_db()
    try:
        async with db.execute(
            "SELECT role,must_change_password,is_active,credential_version,password_hash FROM web_accounts WHERE qq_id=?", (qq_id,)
        ) as cursor:
            target = await cursor.fetchone()
        if not target:
            return jsonify({"success": False, "message": "Web 账号不存在。"}), 404
        if target["role"] != "member" or not target["must_change_password"]:
            return jsonify({"success": False, "message": "仅可为仍需首次改密的成员账号重发临时密码。"}), 409
        if not target["is_active"]:
            return jsonify({"success": False, "message": "账号已停用，启用后才能重发临时密码。"}), 409
    finally:
        await db.close()

    initial_version = int(target["credential_version"])
    temporary_password = generate_temporary_password()
    while verify_password(temporary_password, target["password_hash"]):
        temporary_password = generate_temporary_password()
    password_hash = hash_password(temporary_password)
    now = int(time.time())
    expires_at = _temporary_password_expiry(now)
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT role,must_change_password,is_active,credential_version FROM web_accounts WHERE qq_id=?", (qq_id,)
        ) as cursor:
            target = await cursor.fetchone()
        if (not target or target["role"] != "member" or not target["must_change_password"]
                or not target["is_active"] or int(target["credential_version"]) != initial_version):
            await db.rollback()
            return jsonify({"success": False, "message": "账号状态已变化，请刷新列表后重试。"}), 409
        await db.execute(
            "UPDATE web_accounts SET password_hash=?,temporary_password_expires_at=?,"
            "credential_version=credential_version+1,updated_at=? WHERE qq_id=?",
            (password_hash, expires_at, now, qq_id),
        )
        await db.commit()
        _clear_login_failures((f"account:{qq_id}",))
        return jsonify({
            "qq_id": qq_id,
            "temporary_password": temporary_password,
            "expires_at": expires_at,
            "must_change_password": True,
        })
    except Exception:
        await db.rollback()
        LOG.exception("重发 Web 临时密码失败，QQ=%s", qq_id)
        return jsonify({"success": False, "message": "重发临时密码失败，请稍后重试。"}), 500
    finally:
        await db.close()


@api.route("/admins", methods=["GET", "PUT"])
@admin_required
async def api_admins():
    config = current_app.config.get("PLUGIN_CONFIG", {})
    provider = config.get("_admin_config_provider")
    updater = config.get("_admin_config_updater")
    if request.method == "GET":
        result = provider() if callable(provider) else {"root": [], "admins": []}
        return jsonify({**result, "can_manage": _webui_is_root()})
    root_error = _root_required_response()
    if root_error:
        return root_error
    data = await request.get_json(silent=True) or {}
    admins = data.get("admins")
    if not isinstance(admins, list):
        return jsonify({"success": False, "message": "admins 必须是 QQ 号列表。"}), 400
    normalized = []
    for value in admins:
        qq_id = str(value).strip()
        if not _valid_qq(qq_id):
            return jsonify({"success": False, "message": f"无效的 QQ 号：{qq_id}"}), 400
        if qq_id not in normalized:
            normalized.append(qq_id)
    if not callable(updater):
        return jsonify({"success": False, "message": "管理员配置服务尚未就绪。"}), 503
    result = updater(normalized)
    LOG.info("WebUI 管理员列表已更新：%s", normalized)
    return jsonify({"success": True, **result})


@api.route("/tasks", methods=["GET"])
@admin_required
async def api_tasks():
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_provider")
    return jsonify(provider() if callable(provider) else [])


@api.route("/tasks/<task_id>/cancel", methods=["POST"])
@admin_required
async def api_cancel_task(task_id):
    canceller = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_canceller")
    ok = bool(canceller and canceller(task_id))
    return jsonify({"success": ok, "message": "任务已取消。" if ok else "任务不存在或已结束。"}), (200 if ok else 404)


@api.route("/register", methods=["POST"])
@admin_required
async def api_register_user():
    db = await get_db()
    try:
        data = await request.get_json()
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        qq_id_str = _field(data, "qq_id", 12)
        name = _field(data, "name", 100)
        if not _valid_qq(qq_id_str) or not name:
            return jsonify({"success": False, "message": "QQ号必须为4-12位数字，用户名不能为空。"}), 400
        async with db.execute("SELECT * FROM users WHERE qq_id = ?", (qq_id_str,)) as cursor:
            existing_user = await cursor.fetchone()
        account_values = {
            field: _field(data, field) or None
            for _, field, _ in _ACCOUNT_FIELDS
        }
        changed_platforms = _changed_account_platforms(account_values, existing_user)
        await db.execute(
            "INSERT INTO users (qq_id, name, cf_handle, luogu_id, nowcoder_id, atcoder_handle, cjlu_username, status, school, last_sync_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(qq_id) DO UPDATE SET name=excluded.name, cf_handle=excluded.cf_handle, "
            "luogu_id=excluded.luogu_id, nowcoder_id=excluded.nowcoder_id, atcoder_handle=excluded.atcoder_handle, "
            "cjlu_username=excluded.cjlu_username, status=excluded.status, school=excluded.school",
            (qq_id_str, name, account_values["cf_handle"],
             account_values["luogu_id"], account_values["nowcoder_id"],
             account_values["atcoder_handle"], account_values["cjlu_username"],
             _field(data, "status", 64) or None,
             _field(data, "school", 128) or None, existing_user["last_sync_timestamp"] if existing_user else 0),
        )
        for platform, _, _ in changed_platforms:
            await _clear_platform_records(db, qq_id_str, platform)
        await db.commit()
        message = "注册/更新成功！"
        task_id = None
        status_code = 200
        sync_platforms = [platform for platform, _, has_account in changed_platforms if has_account]
        if sync_platforms:
            submitter = current_app.config.get("PLUGIN_CONFIG", {}).get("_account_sync_submitter")
            task = submitter(qq_id_str, sync_platforms) if callable(submitter) else None
            if task:
                task_id = task["id"]
                status_code = 202
                message += " 账号做题记录已进入后台全量同步任务。"
            else:
                message += " 账号已保存，但全量同步任务未能创建，请稍后在任务页发起深度同步。"
        return jsonify({"success": True, "message": message, "task_id": task_id}), status_code
    except sqlite3.IntegrityError as exc:
        await db.rollback()
        if "duplicate account binding" in str(exc):
            return jsonify({"success": False, "message": "该平台账号已绑定给其他成员。"}), 409
        LOG.error(f"[API Error] /register: {exc}", exc_info=True)
        return jsonify({"success": False, "message": "保存账号失败。"}), 400
    except Exception as e:
        await db.rollback()
        LOG.error(f"[API Error] /register: {e}", exc_info=True)
        return jsonify({"success": False, "message": "服务器内部错误"}), 500
    finally:
        await db.close()


@api.route("/member/<qq_id>", methods=["GET"])
@admin_required
async def api_member_detail(qq_id):
    db = await get_db()
    try:
        qq_id = str(qq_id).strip()
        if not _valid_qq(qq_id):
            return jsonify({"error": "invalid qq_id"}), 400
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            return jsonify({"error": "user not found"}), 404
        async with db.execute("SELECT platform, COUNT(*) AS count FROM submissions WHERE user_qq_id=? GROUP BY platform", (qq_id,)) as cursor:
            platform_counts = {row["platform"]: row["count"] for row in await cursor.fetchall()}
        async with db.execute("SELECT platform, problem_id, problem_name, problem_rating, problem_url, tags, submit_time FROM submissions WHERE user_qq_id=? ORDER BY submit_time DESC, id DESC LIMIT 20", (qq_id,)) as cursor:
            recent_ac = [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT platform, problem_rating, COUNT(*) AS count FROM submissions WHERE user_qq_id=? GROUP BY platform, problem_rating ORDER BY platform, problem_rating", (qq_id,)) as cursor:
            difficulty = [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT role FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            web_account = await cursor.fetchone()
        result = {"user": dict(user), "recent_ac": recent_ac, "challenge_rating": user["challenge_rating"] if "challenge_rating" in user.keys() else 1000, "platform_counts": platform_counts, "permissions": {"role": web_account["role"] if web_account else "member", "can_manage": _webui_is_root()}, "cf": {"rating": None, "contests": []}, "atcoder": {"rating": None, "contests": []}, "nowcoder": {"contests": []}}
        cf_tags = {}
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if user["cf_handle"]:
                try:
                    async with session.get("https://codeforces.com/api/user.rating", params={"handle": user["cf_handle"]}) as response:
                        data = await response.json()
                    if data.get("status") == "OK":
                        records = data.get("result", [])
                        result["cf"]["rating"] = records[-1].get("newRating") if records else None
                        result["cf"]["contests"] = [{"name": item.get("contestName"), "rank": item.get("rank"), "rating": item.get("newRating"), "delta": item.get("newRating", 0) - item.get("oldRating", 0), "time": item.get("ratingUpdateTimeSeconds"), "url": f"https://codeforces.com/contest/{item.get('contestId')}" if item.get("contestId") else "https://codeforces.com/"} for item in records[-30:]]
                except Exception:
                    LOG.warning("获取 CF 成员详情失败: %s", user["cf_handle"])
                if any(item["platform"] == "codeforces" for item in recent_ac):
                    try:
                        async with session.get("https://codeforces.com/api/user.status", params={"handle": user["cf_handle"], "from": 1, "count": 100}) as response:
                            status_data = await response.json()
                        if status_data.get("status") == "OK":
                            for submission in status_data.get("result", []):
                                problem = submission.get("problem") or {}
                                contest_id = problem.get("contestId")
                                problem_index = problem.get("index")
                                tags = problem.get("tags")
                                if contest_id and problem_index and isinstance(tags, list) and tags:
                                    cf_tags[f"cf_{contest_id}{problem_index}"] = tags
                    except Exception:
                        LOG.warning("获取 CF 题目标签失败: %s", user["cf_handle"])
            if user["atcoder_handle"]:
                try:
                    async with session.get(f"https://atcoder.jp/users/{user['atcoder_handle']}/history/json") as response:
                        history = await response.json()
                    if history:
                        latest = history[-1]
                        result["atcoder"]["rating"] = latest.get("NewRating", latest.get("newRating"))
                        result["atcoder"]["contests"] = [{"name": item.get("ContestName", item.get("contestName")), "rank": item.get("Rank", item.get("rank")), "rating": item.get("NewRating", item.get("newRating")), "delta": (item.get("NewRating", item.get("newRating", 0)) or 0) - (item.get("OldRating", item.get("oldRating", 0)) or 0), "time": item.get("EndTime", item.get("endTime")), "url": f"https://atcoder.jp/contests/{item.get('ContestScreenName')}" if item.get("ContestScreenName") else "https://atcoder.jp/"} for item in history[-30:]]
                except Exception:
                    LOG.warning("获取 AtCoder 成员详情失败: %s", user["atcoder_handle"])
        for item in recent_ac:
            if item["platform"] != "codeforces":
                continue
            stored_tags = item.get("tags")
            if isinstance(stored_tags, str):
                stored_tags = [tag.strip() for tag in stored_tags.split(",") if tag.strip()]
            elif not isinstance(stored_tags, list):
                stored_tags = []
            item["tags"] = stored_tags or cf_tags.get(item["problem_id"], [])
        result["recent_ac"] = recent_ac
        return jsonify(result)
    finally:
        await db.close()


@api.route("/member/<qq_id>/permissions", methods=["PUT"])
@admin_required
async def api_update_member_permissions(qq_id):
    root_error = _root_required_response()
    if root_error:
        return root_error
    qq_id = str(qq_id).strip()
    if not _valid_qq(qq_id):
        return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    role = str(data.get("role", "member")).strip().lower()
    if role not in {"admin", "member"}:
        return jsonify({"success": False, "message": "Web 权限只能设置为 admin 或 member；root 仅能通过 Web 账号创建流程授予。"}), 400
    db = await get_db()
    try:
        async with db.execute("SELECT role FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            account = await cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "该成员尚无 Web 账号，请先创建账号。"}), 404
        if account["role"] == "root":
            return jsonify({"success": False, "message": "Web root 不可从成员资料页降级。"}), 409
        await db.execute("UPDATE web_accounts SET role=?,credential_version=credential_version+1,updated_at=? WHERE qq_id=?", (role,int(time.time()),qq_id))
        await db.commit()
    finally:
        await db.close()
    LOG.info("WebUI root 更新 Web 账号 QQ %s 权限为 %s", qq_id, role)
    return jsonify({"success": True, "role": role})


@api.route("/stats", methods=["GET"])
@admin_required
async def api_stats():
    db = await get_db()
    try:
        qq_id = str(request.args.get("qq_id", "")).strip()
        if not qq_id:
            return jsonify({"error": "qq_id required"}), 400
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            return jsonify({"error": "user not found"}), 404
        async with db.execute("SELECT platform, problem_name, problem_rating, problem_url, submit_time FROM submissions WHERE user_qq_id=? ORDER BY submit_time DESC LIMIT 20", (qq_id,)) as cursor:
            recent = [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT platform, problem_rating, COUNT(*) count FROM submissions WHERE user_qq_id=? GROUP BY platform, problem_rating", (qq_id,)) as cursor:
            difficulty = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"user": dict(user), "recent": recent, "difficulty": difficulty, "data_as_of": int(time.time())})
    finally:
        await db.close()


@api.route("/challenge/start", methods=["POST"])
@admin_required
async def api_challenge_start():
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_challenge_provider")
    if not callable(provider):
        return jsonify({"success": False, "message": "挑战服务尚未就绪。"}), 503
    platform = _field(data, "platform", 32).lower()
    tag = _field(data, "tag", 100)
    difficulty = data.get("difficulty", data.get("rating"))
    owner = _field(data, "owner_qq_id", 32)
    weak_tag = bool(data.get("weak_tag"))
    if weak_tag and not tag and owner:
        weak_db = await get_db()
        try:
            async with weak_db.execute("SELECT platform,problem_id,tags,submit_time AS last_submit,1 AS attempts FROM submissions WHERE user_qq_id=?", (owner,)) as cursor:
                weak_rows = await cursor.fetchall()
            weak = _tag_rows_from_submissions(weak_rows)
            if weak:
                tag = weak[0]["tag"]
        finally:
            await weak_db.close()
    try:
        result = await provider(platform, tag, difficulty, owner_qq_id=owner)
    except TypeError:
        result = await provider(platform, tag, difficulty)
    result.setdefault("source", "weak_tag" if weak_tag and tag else "random")
    result.setdefault("weak_tag", tag if weak_tag else "")
    return jsonify(result), (200 if result.get("success") else 400)


@api.route("/challenge/list", methods=["GET"])
@admin_required
async def api_challenge_list():
    qq_id = str(request.args.get("qq_id", "")).strip()
    db = await get_db()
    try:
        query = "SELECT id,qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,challenge_rating,time_limit_minutes,status,created_at,expires_at,completed_at FROM random_challenges"
        params = ()
        if qq_id:
            query += " WHERE qq_id=?"; params = (qq_id,)
        query += " ORDER BY id DESC LIMIT 100"
        async with db.execute(query, params) as cursor: rows = [dict(row) for row in await cursor.fetchall()]
        return jsonify(rows)
    finally:
        await db.close()


@api.route("/challenge/rating", methods=["POST"])
@admin_required
async def api_challenge_rating():
    data = await request.get_json() or {}; qq_id = str(data.get("qq_id", "")).strip()
    try: rating = max(800, min(3000, int(data.get("rating", 1000))))
    except (TypeError, ValueError): return jsonify({"success": False, "message": "Rating 必须是整数。"}), 400
    db = await get_db()
    try:
        await db.execute("UPDATE users SET challenge_rating=? WHERE qq_id=?", (rating, qq_id)); await db.commit()
        return jsonify({"success": True, "rating": rating})
    finally: await db.close()


@api.route("/user", methods=["GET"])
@admin_required
async def api_get_user():
    db = await get_db()
    try:
        qq_id = str(request.args.get("qq_id", "")).strip()
        if not qq_id:
            return jsonify({"error": "qq_id required"}), 400
        async with db.execute("SELECT qq_id, name, real_name, cf_handle, luogu_id, nowcoder_id, atcoder_handle, cjlu_username, status, school FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            return jsonify({"error": "user not found"}), 404
        return jsonify(dict(user))
    finally:
        await db.close()


@api.route("/user", methods=["PUT"])
@admin_required
async def api_update_user():
    db = await get_db()
    try:
        data = await request.get_json() or {}
        qq_id = str(data.get("qq_id", "")).strip()
        if not _valid_qq(qq_id):
            return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
        values = [_field(data, key, 64 if key == "status" else 128) for key in ("name", "real_name", "cf_handle", "luogu_id", "nowcoder_id", "atcoder_handle", "cjlu_username", "status", "school")]
        if not values[0]: values[0] = values[2] or qq_id
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            existing = await cursor.fetchone()
            if not existing: return jsonify({"success": False, "message": "用户不存在，请先注册。"}), 404
        if "real_name" not in data:
            values[1] = existing["real_name"]
        account_values = {
            field: values[index]
            for index, (_, field, _) in enumerate(_ACCOUNT_FIELDS, start=2)
        }
        changed_platforms = _changed_account_platforms(account_values, existing)
        values[2] = account_values["cf_handle"] or ""
        values[3] = account_values["luogu_id"] or ""
        values[4] = account_values["nowcoder_id"] or ""
        values[5] = account_values["atcoder_handle"] or ""
        values[6] = account_values["cjlu_username"] or ""
        await db.execute("UPDATE users SET name=?, real_name=?, cf_handle=?, luogu_id=?, nowcoder_id=?, atcoder_handle=?, cjlu_username=?, status=?, school=? WHERE qq_id=?", tuple(value or None for value in values) + (qq_id,))
        for platform, _, _ in changed_platforms:
            await _clear_platform_records(db, qq_id, platform)
        await db.commit()
        sync_platforms = [platform for platform, _, has_account in changed_platforms if has_account]
        task_id = None
        message = "用户资料已更新。"
        if sync_platforms:
            submitter = current_app.config.get("PLUGIN_CONFIG", {}).get("_account_sync_submitter")
            task = submitter(qq_id, sync_platforms) if callable(submitter) else None
            if task:
                task_id = task["id"]
                message += " 已清理旧做题记录，并创建对应平台的全量同步任务。"
            else:
                message += " 已清理旧做题记录，但全量同步任务未能创建，请稍后在任务页发起深度同步。"
        elif changed_platforms:
            message += " 已清理已解绑平台的做题记录。"
        return jsonify({"success": True, "message": message, "task_id": task_id}), (202 if task_id else 200)
    except sqlite3.IntegrityError as exc:
        await db.rollback()
        if "duplicate account binding" in str(exc):
            return jsonify({"success": False, "message": "该平台账号已绑定给其他成员。"}), 409
        LOG.error("[API Error] /user: %s", exc, exc_info=True)
        return jsonify({"success": False, "message": "保存账号失败。"}), 400
    except Exception:
        await db.rollback()
        LOG.exception("[API Error] /user")
        return jsonify({"success": False, "message": "服务器内部错误"}), 500
    finally:
        await db.close()


@api.route("/user/real-name", methods=["PUT"])
@admin_required
async def api_update_real_name():
    """只更新排行榜使用的真实姓名，避免覆盖其他用户资料。"""
    db = await get_db()
    try:
        data = await request.get_json(silent=True) or {}
        qq_id = str(data.get("qq_id", "")).strip()
        if not _valid_qq(qq_id):
            return jsonify({"success": False, "message": "QQ号必须为4-12位数字。"}), 400
        real_name = _field(data, "real_name", 128)
        async with db.execute("SELECT 1 FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            if not await cursor.fetchone():
                return jsonify({"success": False, "message": "用户不存在，请先注册。"}), 404
        await db.execute("UPDATE users SET real_name=? WHERE qq_id=?", (real_name or None, qq_id))
        await db.commit()
        return jsonify({"success": True, "real_name": real_name or None})
    finally:
        await db.close()


@api.route("/workspace/items", methods=["GET", "POST"])
@admin_required
async def api_workspace_items():
    db = await get_db()
    try:
        if request.method == "GET":
            owner = _field(request.args, "owner_qq_id", 32)
            query = "SELECT * FROM workspace_items WHERE owner_qq_id=? ORDER BY sort_order, updated_at DESC LIMIT 500"
            async with db.execute(query, (owner,)) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}
        owner = _field(data, "owner_qq_id", 32)
        title = _field(data, "title", 240)
        if not owner or not title:
            return jsonify({"success": False, "message": "owner_qq_id 和 title 必填。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "INSERT INTO workspace_items(owner_qq_id,kind,title,body_md,status,priority,due_at,context_type,context_id,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (owner, _field(data, "kind", 20) or "note", title, _field(data, "body_md", 12000), _field(data, "status", 20) or "todo", int(data.get("priority", 0) or 0), int(data.get("due_at") or 0) or None, _field(data, "context_type", 40) or None, _field(data, "context_id", 160) or None, int(data.get("sort_order", 0) or 0), now, now),
        )
        item_id = cursor.lastrowid
        await db.commit()
        return jsonify({"success": True, "id": item_id}), 201
    finally:
        await db.close()


@api.route("/workspace/items/<int:item_id>", methods=["PATCH", "DELETE"])
@admin_required
async def api_workspace_item(item_id):
    db = await get_db()
    try:
        if request.method == "DELETE":
            await db.execute("DELETE FROM workspace_items WHERE id=?", (item_id,))
            await db.commit()
            return jsonify({"success": True})
        data = await request.get_json(silent=True) or {}
        allowed = {"title": _field(data, "title", 240), "body_md": _field(data, "body_md", 12000), "status": _field(data, "status", 20), "priority": int(data.get("priority", 0) or 0), "due_at": int(data.get("due_at") or 0) or None, "sort_order": int(data.get("sort_order", 0) or 0)}
        fields = [key for key in allowed if key in data]
        if fields:
            values = [allowed[key] for key in fields]
            await db.execute(f"UPDATE workspace_items SET {', '.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?", values + [int(time.time()), item_id])
            await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@api.route("/problems", methods=["GET"])
@admin_required
async def api_problems():
    db = await get_db()
    try:
        owner = _field(request.args, "owner_qq_id", 32)
        platform = _field(request.args, "platform", 24)
        tag = _field(request.args, "tag", 100)
        state = _field(request.args, "state", 20)
        query = """SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,COALESCE(s.is_favorite,0) AS is_favorite,COALESCE(s.state,'inbox') AS user_state,s.note_md FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) p LEFT JOIN user_problem_state s ON s.owner_qq_id=? AND s.platform=p.platform AND s.problem_id=p.problem_id WHERE 1=1"""
        params = [owner]
        if platform: query += " AND p.platform=?"; params.append(platform)
        if tag: query += " AND (p.problem_name LIKE ? OR p.problem_id LIKE ? OR COALESCE(p.tags,'') LIKE ?)"; params.extend([f"%{tag}%", f"%{tag}%", f"%{tag}%"])
        if state == "favorite": query += " AND COALESCE(s.is_favorite,0)=1"
        elif state == "inbox": query += " AND COALESCE(s.state,'inbox')='inbox'"
        count_query = "SELECT COUNT(*) FROM (" + query + ") filtered"
        async with db.execute(count_query, tuple(params)) as cursor:
            total = int((await cursor.fetchone())[0])
        query += " ORDER BY CAST(p.problem_rating AS INTEGER), p.platform, p.problem_id LIMIT 500"
        async with db.execute(query, tuple(params)) as cursor:
            items = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"items": items, "total": total, "returned": len(items)})
    finally:
        await db.close()


@api.route("/problems/<platform>/<problem_id>/state", methods=["PUT"])
@admin_required
async def api_problem_state(platform, problem_id):
    db = await get_db()
    try:
        data = await request.get_json(silent=True) or {}; owner = _field(data, "owner_qq_id", 32)
        if not owner: return jsonify({"success": False, "message": "owner_qq_id 必填。"}), 400
        now = int(time.time())
        await db.execute("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,state,note_md,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,platform,problem_id) DO UPDATE SET is_favorite=excluded.is_favorite,state=excluded.state,note_md=excluded.note_md,updated_at=excluded.updated_at", (owner, platform[:24], problem_id[:160], int(bool(data.get("is_favorite", False))), _field(data, "state", 20) or "inbox", _field(data, "note_md", 12000), now))
        await db.commit(); return jsonify({"success": True})
    finally:
        await db.close()


@api.route("/submissions/attempts", methods=["GET", "POST"])
@admin_required
async def api_submission_attempts():
    db = await get_db()
    try:
        if request.method == "GET":
            owner = _field(request.args, "owner_qq_id", 32)
            async with db.execute("SELECT id,owner_qq_id,platform,external_submission_id,problem_id,contest_id,verdict,language,submitted_at,source_code FROM submission_attempts WHERE owner_qq_id=? ORDER BY submitted_at DESC LIMIT 500", (owner,)) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}; owner = _field(data, "owner_qq_id", 32); platform = _field(data, "platform", 24); problem_id = _field(data, "problem_id", 160)
        if not owner or not platform or not problem_id: return jsonify({"success": False, "message": "owner_qq_id、platform、problem_id 必填。"}), 400
        now = int(time.time()); submitted = int(data.get("submitted_at") or now)
        await db.execute("INSERT OR IGNORE INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,contest_id,verdict,language,submitted_at,source_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (owner,platform,_field(data,"external_submission_id",80) or None,problem_id,_field(data,"contest_id",80) or None,_field(data,"verdict",40),_field(data,"language",100),submitted,_field(data,"source_code",200000),now))
        await db.commit(); return jsonify({"success": True}), 201
    finally:
        await db.close()


@api.route("/reviews/drafts", methods=["GET", "POST"])
@admin_required
async def api_review_drafts():
    db = await get_db()
    try:
        if request.method == "GET":
            owner = _field(request.args, "owner_qq_id", 32)
            async with db.execute("SELECT * FROM review_drafts WHERE owner_qq_id=? ORDER BY updated_at DESC LIMIT 100", (owner,)) as cursor: return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}; owner = _field(data,"owner_qq_id",32); context = _field(data,"context_id",160)
        if not owner or not context: return jsonify({"success": False, "message": "owner_qq_id 和 context_id 必填。"}), 400
        now = int(time.time())
        cursor = await db.execute("INSERT INTO review_drafts(owner_qq_id,context_type,context_id,draft_md,status,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (owner, _field(data, "context_type", 40) or "contest", context, _field(data, "draft_md", 30000), "draft", _field(data, "model", 100), now, now))
        draft_id = cursor.lastrowid
        await db.commit()
        return jsonify({"success": True, "id": draft_id}), 201
    finally:
        await db.close()


@api.route("/ui/preferences", methods=["GET", "PUT"])
@admin_required
async def api_ui_preferences():
    db = await get_db()
    try:
        key = "webui_preferences"
        if request.method == "GET":
            async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cursor: row = await cursor.fetchone()
            try: return jsonify(json.loads(row["value"]) if row else {})
            except (TypeError, ValueError): return jsonify({})
        data = await request.get_json(silent=True) or {}; value = {"nav_order": list(data.get("nav_order", []))[:20], "nav_hidden": list(data.get("nav_hidden", []))[:20], "font_scale": max(.8, min(1.5, float(data.get("font_scale", 1)))), "review_full_page": bool(data.get("review_full_page", False))}
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False))); await db.commit(); return jsonify(value)
    finally:
        await db.close()


@api.route("/settings/contest-report", methods=["GET", "PUT"])
@admin_required
async def api_contest_report_settings():
    db = await get_db()
    try:
        if request.method == "GET":
            async with db.execute("SELECT value FROM settings WHERE key='contest_report_time'") as cursor:
                row = await cursor.fetchone()
            async with db.execute("SELECT value FROM settings WHERE key='notification_group_id'") as cursor:
                group = await cursor.fetchone()
            return jsonify({
                "time": row["value"] if row else "",
                "group_id": group["value"] if group else "",
            })
        data = await request.get_json(silent=True) or {}
        schedule_time = str(data.get("time", "") or "").strip()
        if schedule_time and not valid_contest_report_time(schedule_time):
            return jsonify({"success": False, "message": "时间格式应为 24 小时制 HH:MM，例如 08:30。"}), 400
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('contest_report_time',?)", (schedule_time,))
        await db.commit()
        updater = current_app.config.get("PLUGIN_CONFIG", {}).get("_contest_report_updater")
        if callable(updater):
            result = updater()
            if inspect.isawaitable(result):
                await result
        async with db.execute("SELECT value FROM settings WHERE key='notification_group_id'") as cursor:
            group = await cursor.fetchone()
        return jsonify({"time": schedule_time, "group_id": group["value"] if group else ""})
    finally:
        await db.close()


def _tag_rows_from_submissions(rows):
    from .training_logic import split_tags, tag_mastery
    return tag_mastery([{**dict(row), "tags": split_tags(row["tags"])} for row in rows])


@api.route("/training/weak-tags", methods=["GET"])
@admin_required
async def api_training_weak_tags():
    owner = _field(request.args, "owner_qq_id", 32)
    platform = _field(request.args, "platform", 24)
    try:
        limit = max(1, min(30, int(request.args.get("limit", 8))))
    except (TypeError, ValueError):
        limit = 8
    if not owner:
        return jsonify({"tags": [], "generated_at": int(time.time())})
    db = await get_db()
    try:
        query = "SELECT s.platform,s.problem_id,s.tags,s.submit_time AS last_submit,COUNT(a.id) AS attempts FROM submissions s LEFT JOIN submission_attempts a ON a.owner_qq_id=s.user_qq_id AND a.platform=s.platform AND a.problem_id=s.problem_id WHERE s.user_qq_id=?"
        params = [owner]
        if platform:
            query += " AND s.platform=?"
            params.append(platform)
        query += " GROUP BY s.platform,s.problem_id,s.tags,s.submit_time"
        async with db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
        tags = _tag_rows_from_submissions(rows)[:limit]
        async with db.execute("SELECT platform,problem_id,mistakes FROM review_states WHERE owner_qq_id=?", (owner,)) as cursor:
            reviews = await cursor.fetchall()
        async with db.execute("SELECT platform,problem_id,tags FROM submissions WHERE user_qq_id=?", (owner,)) as cursor:
            problem_tags = {(row["platform"], row["problem_id"]): row["tags"] for row in await cursor.fetchall()}
        mistake_by_tag = {}
        from .training_logic import split_tags
        for review in reviews:
            problem_tag_value = problem_tags.get((review["platform"], review["problem_id"]))
            for item in split_tags(problem_tag_value):
                key = item.casefold()
                if key in {entry["tag"].casefold() for entry in tags}:
                    mistake_by_tag[key] = mistake_by_tag.get(key, 0) + int(review["mistakes"] or 0)
        for item in tags:
            item["review_mistakes"] = mistake_by_tag.get(item["tag"].casefold(), 0)
            if item["review_mistakes"]:
                item["mastery"] = round(max(0.0, item["mastery"] - min(0.35, item["review_mistakes"] * 0.05)), 3)
        tags.sort(key=lambda item: (item["mastery"], -item["review_mistakes"], -item["solved"]))
        return jsonify({"tags": tags, "generated_at": int(time.time())})
    finally:
        await db.close()


@api.route("/review/queue", methods=["GET"])
@admin_required
async def api_review_queue():
    db = await get_db()
    try:
        owner = _field(request.args, "owner_qq_id", 32)
        if not owner: return jsonify([])
        now = int(time.time())
        query = """SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,COUNT(DISTINCT s.id) AS attempts,MAX(s.submit_time) AS last_submit,COALESCE(r.grade,'new') AS grade,COALESCE(r.interval_days,0) AS interval_days,COALESCE(r.due_at,0) AS due_at,COALESCE(r.review_count,0) AS review_count,COALESCE(r.difficulty,0) AS difficulty,COALESCE(r.mistakes,0) AS mistakes,COALESCE(ups.is_favorite,0) AS is_favorite,cr.contest_id,cr.verdict AS contest_verdict,cr.status AS contest_status,CASE WHEN cr.status IN ('unsolved','queued') THEN 'upsolve' ELSE 'review' END AS queue_type FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions UNION SELECT 'codeforces' AS platform,problem_id,problem_id AS problem_name,NULL AS problem_rating,'https://codeforces.com/' AS problem_url,'' AS tags FROM submission_attempts GROUP BY platform,problem_id) p LEFT JOIN submissions s ON s.user_qq_id=? AND s.platform=p.platform AND s.problem_id=p.problem_id LEFT JOIN review_states r ON r.owner_qq_id=? AND r.platform=p.platform AND r.problem_id=p.problem_id LEFT JOIN user_problem_state ups ON ups.owner_qq_id=? AND ups.platform=p.platform AND ups.problem_id=p.problem_id LEFT JOIN contest_problem_reviews cr ON cr.owner_qq_id=? AND cr.problem_id=p.problem_id AND p.platform='codeforces' WHERE (s.id IS NOT NULL OR cr.status IN ('unsolved','queued')) GROUP BY p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,r.grade,r.interval_days,r.due_at,r.review_count,r.difficulty,r.mistakes,ups.is_favorite,cr.contest_id,cr.verdict,cr.status ORDER BY CASE WHEN cr.status IN ('unsolved','queued') THEN 0 WHEN COALESCE(r.due_at,0)>0 AND r.due_at<=? THEN 1 ELSE 2 END, COALESCE(r.due_at,0), last_submit DESC LIMIT 200"""
        async with db.execute(query, (owner, owner, owner, owner, now)) as cursor: rows=[dict(row) for row in await cursor.fetchall()]
        return jsonify(rows)
    finally: await db.close()


@api.route("/review/feedback", methods=["POST"])
@admin_required
async def api_review_feedback():
    data = await request.get_json(silent=True) or {}; owner=_field(data,"owner_qq_id",32); platform=_field(data,"platform",24); problem_id=_field(data,"problem_id",160); grade=_field(data,"grade",12)
    if not owner or not platform or not problem_id or grade not in {"again","hard","good","easy"}: return jsonify({"success":False,"message":"owner_qq_id、platform、problem_id 和有效 grade 必填。"}),400
    db=await get_db()
    try:
        async with db.execute("SELECT interval_days,ease,review_count,mistakes FROM review_states WHERE owner_qq_id=? AND platform=? AND problem_id=?",(owner,platform,problem_id)) as cursor: old=await cursor.fetchone()
        interval=int(old["interval_days"] if old else 0); ease=float(old["ease"] if old else 2.5); count=int(old["review_count"] if old else 0); mistakes=int(old["mistakes"] if old else 0)
        if grade=="again": interval=1; ease=max(1.3,ease-0.2); mistakes+=1
        elif grade=="hard": interval=max(2,round(max(1,interval)*1.25)); ease=max(1.3,ease-0.05)
        elif grade=="good": interval=5 if interval<=0 else min(120,round(max(5,interval)*ease))
        else: interval=14 if interval<=0 else min(180,round(max(14,interval)*ease*1.25)); ease=min(3.2,ease+0.15)
        now=int(time.time()); due=now+interval*86400
        await db.execute("INSERT INTO review_states(owner_qq_id,platform,problem_id,grade,interval_days,ease,due_at,review_count,last_review_at,difficulty,mistakes) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,platform,problem_id) DO UPDATE SET grade=excluded.grade,interval_days=excluded.interval_days,ease=excluded.ease,due_at=excluded.due_at,review_count=excluded.review_count,last_review_at=excluded.last_review_at,mistakes=excluded.mistakes",(owner,platform,problem_id,grade,interval,ease,due,count+1,now,0,mistakes));await db.commit();return jsonify({"success":True,"grade":grade,"interval_days":interval,"due_at":due})
    finally: await db.close()
@api.route("/training/summary", methods=["GET"])
@admin_required
async def api_training_summary():
    owner = _field(request.args, "owner_qq_id", 32)
    db = await get_db()
    try:
        async with db.execute("SELECT DISTINCT date(submit_time,'unixepoch','localtime') AS day FROM submissions WHERE user_qq_id=? ORDER BY day DESC LIMIT 365", (owner,)) as cursor:
            days = [row["day"] for row in await cursor.fetchall()]
        day_set = set(days); streak = 0; day = time.localtime()
        while time.strftime("%Y-%m-%d", day) in day_set:
            streak += 1
            day = time.localtime(time.mktime(day) - 86400)
        return jsonify({"streak_days": streak, "active_days": len(days), "days": days[:90]})
    finally:
        await db.close()


@api.route("/submissions/analytics", methods=["GET"])
@admin_required
async def api_submission_analytics():
    owner = _field(request.args, "owner_qq_id", 32)
    db = await get_db()
    try:
        async with db.execute("SELECT platform,COUNT(*) AS solved,COUNT(DISTINCT problem_id) AS problems,MIN(submit_time) AS first_at,MAX(submit_time) AS last_at FROM submissions WHERE user_qq_id=? GROUP BY platform ORDER BY solved DESC", (owner,)) as cursor:
            platforms = [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT date(submit_time,'unixepoch','localtime') AS day,COUNT(*) AS solved FROM submissions WHERE user_qq_id=? GROUP BY day ORDER BY day DESC LIMIT 90", (owner,)) as cursor:
            daily = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"platforms": platforms, "daily": daily})
    finally:
        await db.close()


@api.route("/contest/reviews", methods=["GET", "PUT"])
@admin_required
async def api_contest_problem_reviews():
    db = await get_db()
    try:
        if request.method == "GET":
            owner = _field(request.args, "owner_qq_id", 32); contest = _field(request.args, "contest_id", 80)
            async with db.execute("SELECT * FROM contest_problem_reviews WHERE owner_qq_id=? AND contest_id=? ORDER BY problem_id", (owner, contest)) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}; owner = _field(data, "owner_qq_id", 32); contest = _field(data, "contest_id", 80); problem = _field(data, "problem_id", 160)
        if not owner or not contest or not problem: return jsonify({"success": False, "message": "owner_qq_id、contest_id、problem_id 必填。"}), 400
        now = int(time.time())
        status = _field(data, "status", 20) or "todo"
        if status not in {"todo", "unsolved", "queued", "solved", "ignored"}:
            return jsonify({"success": False, "message": "无效的赛事复盘状态。"}), 400
        verdict = _field(data, "verdict", 40)
        rating = int(data.get("rating") or 0) or None
        await db.execute("INSERT INTO contest_problem_reviews(owner_qq_id,contest_id,problem_id,verdict,rating,note_md,status,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,contest_id,problem_id) DO UPDATE SET verdict=excluded.verdict,rating=excluded.rating,note_md=excluded.note_md,status=excluded.status,updated_at=excluded.updated_at", (owner, contest, problem, verdict, rating, _field(data, "note_md", 12000), status, now))
        if status in {"unsolved", "queued"}:
            await db.execute("INSERT OR IGNORE INTO study_plan_items(owner_qq_id,platform,problem_id,status,position,added_at) VALUES(?,?,?,?,?,?)", (owner, "codeforces", problem, "pending", 0, now))
            await db.execute("INSERT INTO review_states(owner_qq_id,platform,problem_id,grade,interval_days,ease,due_at,review_count,last_review_at,difficulty,mistakes) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,platform,problem_id) DO UPDATE SET due_at=MIN(review_states.due_at, excluded.due_at), grade=CASE WHEN review_states.grade='new' THEN excluded.grade ELSE review_states.grade END", (owner, "codeforces", problem, "again", 0, 2.5, now, 0, 0, 0, 1))
        elif status == "solved":
            await db.execute("UPDATE study_plan_items SET status='done',completed_at=? WHERE owner_qq_id=? AND platform='codeforces' AND problem_id=?", (now, owner, problem))
        await db.commit(); return jsonify({"success": True, "status": status})
    finally:
        await db.close()


@api.route("/study-plan", methods=["GET", "POST", "PATCH", "DELETE"])
@admin_required
async def api_study_plan():
    db = await get_db()
    try:
        data = await request.get_json(silent=True) or {}
        owner = _field(request.args if request.method == "GET" else data, "owner_qq_id", 32)
        if not owner: return jsonify([] if request.method == "GET" else {"success": False, "message": "owner_qq_id 必填。"}), (200 if request.method == "GET" else 400)
        if request.method == "GET":
            async with db.execute("SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,i.status,i.position,i.added_at,i.completed_at FROM study_plan_items i LEFT JOIN (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) p ON p.platform=i.platform AND p.problem_id=i.problem_id WHERE i.owner_qq_id=? ORDER BY i.position,i.added_at", (owner,)) as cursor: return jsonify([dict(row) for row in await cursor.fetchall()])
        platform=_field(data,"platform",24); problem_id=_field(data,"problem_id",160)
        if not platform or not problem_id: return jsonify({"success":False,"message":"platform 和 problem_id 必填。"}),400
        now=int(time.time())
        if request.method == "POST":
            await db.execute("INSERT OR IGNORE INTO study_plan_items(owner_qq_id,platform,problem_id,status,position,added_at) VALUES(?,?,?,?,?,?)",(owner,platform,problem_id,"pending",int(data.get("position") or 0),now))
        elif request.method == "PATCH":
            status=_field(data,"status",20) or "pending"; await db.execute("UPDATE study_plan_items SET status=?,position=?,completed_at=? WHERE owner_qq_id=? AND platform=? AND problem_id=?",(status,int(data.get("position") or 0),now if status=="done" else None,owner,platform,problem_id))
        else:
            await db.execute("DELETE FROM study_plan_items WHERE owner_qq_id=? AND platform=? AND problem_id=?",(owner,platform,problem_id))
        await db.commit(); return jsonify({"success":True})
    finally: await db.close()


def _me_qq_id():
    identity = getattr(request, "web_identity", None) or {}
    return str(identity.get("qq_id") or "")


@api.route("/me/profile", methods=["GET", "PUT"])
@member_required
async def api_me_profile():
    qq_id = _me_qq_id()
    if not qq_id:
        return jsonify({"success": False, "message": "当前会话没有成员 QQ 绑定。"}), 403
    db = await get_db()
    try:
        if request.method == "PUT":
            data = await request.get_json(silent=True) or {}
            if not isinstance(data, dict):
                return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
            name = _field(data, "name", 100)
            if not name:
                return jsonify({"success": False, "message": "昵称不能为空。"}), 400
            await db.execute("UPDATE users SET name=? WHERE qq_id=?", (name, qq_id))
            await db.commit()
        async with db.execute(
        "SELECT name,status,cf_handle,luogu_id,nowcoder_id,atcoder_handle,cjlu_username,challenge_rating "
            "FROM users WHERE qq_id=?", (qq_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "成员资料不存在。"}), 404
        async with db.execute("SELECT platform,COUNT(*) AS count FROM submissions WHERE user_qq_id=? GROUP BY platform", (qq_id,)) as cursor:
            platform_counts = {item["platform"]: item["count"] for item in await cursor.fetchall()}
        async with db.execute(
            "SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time "
            "FROM submissions WHERE user_qq_id=? ORDER BY submit_time DESC,id DESC LIMIT 20", (qq_id,)
        ) as cursor:
            recent_ac = [dict(item) for item in await cursor.fetchall()]
        async with db.execute("SELECT COUNT(*) AS count FROM submissions WHERE user_qq_id=?", (qq_id,)) as cursor:
            total = (await cursor.fetchone())["count"]
        return jsonify({
            "user": dict(row),
            "platform_counts": platform_counts,
            "total_count": total,
            "recent_ac": recent_ac,
        })
    finally:
        await db.close()


@api.route("/me/leaderboard", methods=["GET"])
@member_required
async def api_me_leaderboard():
    db = await get_db()
    try:
        days, page, page_size, sort_key, _, platforms = _leaderboard_options(request.args)
        rows, total = await _fetch_leaderboard(db, days, page, page_size, sort_key, "", platforms)
        async with db.execute("SELECT qq_id,name FROM users") as cursor:
            names = {row["qq_id"]: row["name"] for row in await cursor.fetchall()}
        public_rows = [{
            "name": names.get(row["qq_id"], "未命名"),
            "total_count": row["total_count"],
            "cf_count": row["cf_count"],
            "luogu_count": row["luogu_count"],
            "nowcoder_count": row["nowcoder_count"],
            "atcoder_count": row["atcoder_count"],
            "cjlu_count": row["cjlu_count"],
        } for row in rows]
        return jsonify({"rows": public_rows, "total": total, "page": page, "page_size": page_size, "days": days})
    finally:
        await db.close()


@api.route("/me/training/challenges", methods=["GET"])
@member_required
async def api_me_training_challenges():
    qq_id = _me_qq_id()
    if not qq_id:
        return jsonify({"success": False, "message": "当前会话没有成员 QQ 绑定。"}), 403
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id,platform,problem_id,problem_name,problem_rating,problem_url,tags,challenge_rating,time_limit_minutes,status,created_at,expires_at,completed_at "
            "FROM random_challenges WHERE qq_id=? ORDER BY id DESC LIMIT 100", (qq_id,)
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@api.route("/me/challenge/start", methods=["POST"])
@member_required
async def api_me_challenge_start():
    qq_id = _me_qq_id()
    if not qq_id:
        return jsonify({"success": False, "message": "当前会话没有成员 QQ 绑定。"}), 403
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_challenge_provider")
    if not callable(provider):
        return jsonify({"success": False, "message": "挑战服务尚未就绪。"}), 503
    platform = _field(data, "platform", 32).lower()
    tag = _field(data, "tag", 100)
    difficulty = data.get("difficulty", data.get("rating"))
    weak_tag = bool(data.get("weak_tag"))
    if weak_tag and not tag:
        weak_db = await get_db()
        try:
            async with weak_db.execute(
                "SELECT platform,problem_id,tags,submit_time AS last_submit,1 AS attempts FROM submissions WHERE user_qq_id=?",
                (qq_id,),
            ) as cursor:
                weak_rows = await cursor.fetchall()
            weak = _tag_rows_from_submissions(weak_rows)
            if weak:
                tag = weak[0]["tag"]
        finally:
            await weak_db.close()
    try:
        result = await provider(platform, tag, difficulty, owner_qq_id=qq_id)
    except TypeError:
        result = await provider(platform, tag, difficulty)
    result.setdefault("source", "weak_tag" if weak_tag and tag else "random")
    result.setdefault("weak_tag", tag if weak_tag else "")
    return jsonify(result), (200 if result.get("success") else 400)


@api.route("/me/challenge/rating", methods=["PUT"])
@member_required
async def api_me_challenge_rating():
    qq_id = _me_qq_id()
    data = await request.get_json(silent=True) or {}
    try:
        rating = max(800, min(3000, int(data.get("rating", 1000))))
    except (AttributeError, TypeError, ValueError):
        return jsonify({"success": False, "message": "Rating 必须是整数。"}), 400
    db = await get_db()
    try:
        await db.execute("UPDATE users SET challenge_rating=? WHERE qq_id=?", (rating, qq_id))
        await db.commit()
        return jsonify({"success": True, "rating": rating})
    finally:
        await db.close()


@api.route("/me/training/summary", methods=["GET"])
@member_required
async def api_me_training_summary():
    qq_id = _me_qq_id()
    db = await get_db()
    try:
        async with db.execute("SELECT DISTINCT date(submit_time,'unixepoch','localtime') AS day FROM submissions WHERE user_qq_id=? ORDER BY day DESC LIMIT 365", (qq_id,)) as cursor:
            days = [row["day"] for row in await cursor.fetchall()]
        day_set = set(days)
        streak = 0
        day = time.localtime()
        while time.strftime("%Y-%m-%d", day) in day_set:
            streak += 1
            day = time.localtime(time.mktime(day) - 86400)
        return jsonify({"streak_days": streak, "active_days": len(days), "days": days[:90]})
    finally:
        await db.close()


@api.route("/me/problems", methods=["GET"])
@member_required
async def api_me_problems():
    qq_id = _me_qq_id()
    platform = _field(request.args, "platform", 24)
    tag = _field(request.args, "tag", 100)
    state = _field(request.args, "state", 20)
    db = await get_db()
    try:
        query = """SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,
          COALESCE(s.is_favorite,0) AS is_favorite,COALESCE(s.state,'inbox') AS user_state,s.note_md
          FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations
          UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) p
          LEFT JOIN user_problem_state s ON s.owner_qq_id=? AND s.platform=p.platform AND s.problem_id=p.problem_id WHERE 1=1"""
        params = [qq_id]
        if platform:
            query += " AND p.platform=?"
            params.append(platform)
        if tag:
            query += " AND (p.problem_name LIKE ? OR p.problem_id LIKE ? OR COALESCE(p.tags,'') LIKE ?)"
            params.extend([f"%{tag}%", f"%{tag}%", f"%{tag}%"])
        if state == "favorite":
            query += " AND COALESCE(s.is_favorite,0)=1"
        elif state == "inbox":
            query += " AND COALESCE(s.state,'inbox')='inbox'"
        count_query = "SELECT COUNT(*) FROM (" + query + ") filtered"
        async with db.execute(count_query, tuple(params)) as cursor:
            total = int((await cursor.fetchone())[0])
        query += " ORDER BY CAST(p.problem_rating AS INTEGER),p.platform,p.problem_id LIMIT 500"
        async with db.execute(query, tuple(params)) as cursor:
            items = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"items": items, "total": total, "returned": len(items)})
    finally:
        await db.close()


@api.route("/me/problems/<platform>/<problem_id>/state", methods=["PUT"])
@member_required
async def api_me_problem_state(platform, problem_id):
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,state,note_md,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,platform,problem_id) DO UPDATE SET "
            "is_favorite=excluded.is_favorite,state=excluded.state,note_md=excluded.note_md,updated_at=excluded.updated_at",
            (_me_qq_id(), platform[:24], problem_id[:160], int(bool(data.get("is_favorite", False))),
             _field(data, "state", 20) or "inbox", _field(data, "note_md", 12000), now),
        )
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@api.route("/me/submissions/attempts", methods=["GET"])
@member_required
async def api_me_submission_attempts():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id,platform,external_submission_id,problem_id,contest_id,verdict,language,submitted_at "
            "FROM submission_attempts WHERE owner_qq_id=? ORDER BY submitted_at DESC LIMIT 500",
            (_me_qq_id(),),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@api.route("/me/submissions/analytics", methods=["GET"])
@member_required
async def api_me_submission_analytics():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT platform,COUNT(*) AS solved,COUNT(DISTINCT problem_id) AS problems,MIN(submit_time) AS first_at,MAX(submit_time) AS last_at "
            "FROM submissions WHERE user_qq_id=? GROUP BY platform ORDER BY solved DESC", (_me_qq_id(),)
        ) as cursor:
            platforms = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT date(submit_time,'unixepoch','localtime') AS day,COUNT(*) AS solved FROM submissions "
            "WHERE user_qq_id=? GROUP BY day ORDER BY day DESC LIMIT 90", (_me_qq_id(),)
        ) as cursor:
            daily = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"platforms": platforms, "daily": daily})
    finally:
        await db.close()


@api.route("/me/reviews/weak-tags", methods=["GET"])
@member_required
async def api_me_review_weak_tags():
    qq_id = _me_qq_id()
    platform = _field(request.args, "platform", 24)
    try:
        limit = max(1, min(30, int(request.args.get("limit", 8))))
    except (TypeError, ValueError):
        limit = 8
    db = await get_db()
    try:
        query = "SELECT s.platform,s.problem_id,s.tags,s.submit_time AS last_submit,COUNT(a.id) AS attempts FROM submissions s LEFT JOIN submission_attempts a ON a.owner_qq_id=s.user_qq_id AND a.platform=s.platform AND a.problem_id=s.problem_id WHERE s.user_qq_id=?"
        params = [qq_id]
        if platform:
            query += " AND s.platform=?"
            params.append(platform)
        query += " GROUP BY s.platform,s.problem_id,s.tags,s.submit_time"
        async with db.execute(query, tuple(params)) as cursor:
            tags = _tag_rows_from_submissions(await cursor.fetchall())[:limit]
        async with db.execute("SELECT platform,problem_id,mistakes FROM review_states WHERE owner_qq_id=?", (qq_id,)) as cursor:
            reviews = await cursor.fetchall()
        async with db.execute("SELECT platform,problem_id,tags FROM submissions WHERE user_qq_id=?", (qq_id,)) as cursor:
            problem_tags = {(row["platform"], row["problem_id"]): row["tags"] for row in await cursor.fetchall()}
        from .training_logic import split_tags
        selected = {entry["tag"].casefold() for entry in tags}
        mistakes_by_tag = {}
        for review in reviews:
            for value in split_tags(problem_tags.get((review["platform"], review["problem_id"]))):
                key = value.casefold()
                if key in selected:
                    mistakes_by_tag[key] = mistakes_by_tag.get(key, 0) + int(review["mistakes"] or 0)
        for item in tags:
            item["review_mistakes"] = mistakes_by_tag.get(item["tag"].casefold(), 0)
            if item["review_mistakes"]:
                item["mastery"] = round(max(0.0, item["mastery"] - min(0.35, item["review_mistakes"] * 0.05)), 3)
        tags.sort(key=lambda item: (item["mastery"], -item["review_mistakes"], -item["solved"]))
        return jsonify({"tags": tags, "generated_at": int(time.time())})
    finally:
        await db.close()


@api.route("/me/reviews", methods=["GET"])
@member_required
async def api_me_reviews():
    qq_id = _me_qq_id()
    db = await get_db()
    try:
        now = int(time.time())
        query = """SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,
          COUNT(DISTINCT s.id) AS attempts,MAX(s.submit_time) AS last_submit,COALESCE(r.grade,'new') AS grade,
          COALESCE(r.interval_days,0) AS interval_days,COALESCE(r.due_at,0) AS due_at,
          COALESCE(r.review_count,0) AS review_count,COALESCE(r.difficulty,0) AS difficulty,
          COALESCE(r.mistakes,0) AS mistakes,COALESCE(ups.is_favorite,0) AS is_favorite,
          cr.contest_id,cr.verdict AS contest_verdict,cr.status AS contest_status,
          CASE WHEN cr.status IN ('unsolved','queued') THEN 'upsolve' ELSE 'review' END AS queue_type
          FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations
          UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions
          UNION SELECT 'codeforces',problem_id,problem_id,NULL,'https://codeforces.com/','' FROM submission_attempts WHERE owner_qq_id=? GROUP BY problem_id) p
          LEFT JOIN submissions s ON s.user_qq_id=? AND s.platform=p.platform AND s.problem_id=p.problem_id
          LEFT JOIN review_states r ON r.owner_qq_id=? AND r.platform=p.platform AND r.problem_id=p.problem_id
          LEFT JOIN user_problem_state ups ON ups.owner_qq_id=? AND ups.platform=p.platform AND ups.problem_id=p.problem_id
          LEFT JOIN contest_problem_reviews cr ON cr.owner_qq_id=? AND cr.problem_id=p.problem_id AND p.platform='codeforces'
          WHERE (s.id IS NOT NULL OR cr.status IN ('unsolved','queued'))
          GROUP BY p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,r.grade,r.interval_days,r.due_at,r.review_count,r.difficulty,r.mistakes,ups.is_favorite,cr.contest_id,cr.verdict,cr.status
          ORDER BY CASE WHEN cr.status IN ('unsolved','queued') THEN 0 WHEN COALESCE(r.due_at,0)>0 AND r.due_at<=? THEN 1 ELSE 2 END,COALESCE(r.due_at,0),last_submit DESC LIMIT 200"""
        async with db.execute(query, (qq_id, qq_id, qq_id, qq_id, qq_id, now)) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@api.route("/me/reviews/feedback", methods=["POST"])
@member_required
async def api_me_review_feedback():
    data = await request.get_json(silent=True) or {}
    platform = _field(data, "platform", 24)
    problem_id = _field(data, "problem_id", 160)
    grade = _field(data, "grade", 12)
    if not platform or not problem_id or grade not in {"again", "hard", "good", "easy"}:
        return jsonify({"success": False, "message": "platform、problem_id 和有效 grade 必填。"}), 400
    owner = _me_qq_id()
    db = await get_db()
    try:
        async with db.execute("SELECT interval_days,ease,review_count,mistakes FROM review_states WHERE owner_qq_id=? AND platform=? AND problem_id=?", (owner, platform, problem_id)) as cursor:
            old = await cursor.fetchone()
        interval = int(old["interval_days"] if old else 0)
        ease = float(old["ease"] if old else 2.5)
        count = int(old["review_count"] if old else 0)
        mistakes = int(old["mistakes"] if old else 0)
        if grade == "again": interval=1; ease=max(1.3,ease-0.2); mistakes+=1
        elif grade == "hard": interval=max(2,round(max(1,interval)*1.25)); ease=max(1.3,ease-0.05)
        elif grade == "good": interval=5 if interval<=0 else min(120,round(max(5,interval)*ease))
        else: interval=14 if interval<=0 else min(180,round(max(14,interval)*ease*1.25)); ease=min(3.2,ease+0.15)
        now = int(time.time())
        due = now + interval * 86400
        await db.execute(
            "INSERT INTO review_states(owner_qq_id,platform,problem_id,grade,interval_days,ease,due_at,review_count,last_review_at,difficulty,mistakes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner_qq_id,platform,problem_id) DO UPDATE SET grade=excluded.grade,interval_days=excluded.interval_days,ease=excluded.ease,due_at=excluded.due_at,review_count=excluded.review_count,last_review_at=excluded.last_review_at,mistakes=excluded.mistakes",
            (owner,platform,problem_id,grade,interval,ease,due,count+1,now,0,mistakes),
        )
        await db.commit()
        return jsonify({"success": True, "grade": grade, "interval_days": interval, "due_at": due})
    finally:
        await db.close()


@api.route("/me/workspace/items", methods=["GET", "POST"])
@member_required
async def api_me_workspace_items():
    owner = _me_qq_id()
    db = await get_db()
    try:
        if request.method == "GET":
            async with db.execute(
                "SELECT id,kind,title,body_md,status,priority,due_at,context_type,context_id,sort_order,created_at,updated_at,completed_at "
                "FROM workspace_items WHERE owner_qq_id=? ORDER BY sort_order,updated_at DESC LIMIT 500", (owner,)
            ) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        title = _field(data, "title", 240)
        if not title:
            return jsonify({"success": False, "message": "title 必填。"}), 400
        try:
            priority = max(-100, min(100, int(data.get("priority", 0) or 0)))
            due_at = int(data.get("due_at") or 0) or None
            sort_order = int(data.get("sort_order", 0) or 0)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "优先级、截止时间和排序必须是整数。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "INSERT INTO workspace_items(owner_qq_id,kind,title,body_md,status,priority,due_at,context_type,context_id,sort_order,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (owner,_field(data,"kind",20) or "note",title,_field(data,"body_md",12000),
             _field(data,"status",20) or "todo",priority,due_at,_field(data,"context_type",40) or None,
             _field(data,"context_id",160) or None,sort_order,now,now),
        )
        await db.commit()
        return jsonify({"success": True, "id": cursor.lastrowid}), 201
    finally:
        await db.close()


@api.route("/me/workspace/items/<int:item_id>", methods=["PATCH", "DELETE"])
@member_required
async def api_me_workspace_item(item_id):
    owner = _me_qq_id()
    db = await get_db()
    try:
        if request.method == "DELETE":
            cursor = await db.execute("DELETE FROM workspace_items WHERE id=? AND owner_qq_id=?", (item_id, owner))
            if cursor.rowcount == 0:
                return jsonify({"success": False, "message": "记录不存在。"}), 404
            await db.commit()
            return jsonify({"success": True})
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        allowed = {
            "title": _field(data, "title", 240),
            "body_md": _field(data, "body_md", 12000),
            "status": _field(data, "status", 20),
        }
        if "priority" in data:
            try: allowed["priority"] = max(-100, min(100, int(data["priority"])))
            except (TypeError, ValueError): return jsonify({"success": False, "message": "priority 必须是整数。"}), 400
        if "due_at" in data:
            try: allowed["due_at"] = int(data["due_at"] or 0) or None
            except (TypeError, ValueError): return jsonify({"success": False, "message": "due_at 必须是整数。"}), 400
        if "sort_order" in data:
            try: allowed["sort_order"] = int(data["sort_order"] or 0)
            except (TypeError, ValueError): return jsonify({"success": False, "message": "sort_order 必须是整数。"}), 400
        fields = [key for key in allowed if key in data]
        if not fields:
            return jsonify({"success": False, "message": "没有可更新的字段。"}), 400
        values = [allowed[key] for key in fields]
        cursor = await db.execute(
            f"UPDATE workspace_items SET {', '.join(f'{key}=?' for key in fields)},updated_at=? WHERE id=? AND owner_qq_id=?",
            values + [int(time.time()), item_id, owner],
        )
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": "记录不存在。"}), 404
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@api.route("/me/study-plan", methods=["GET", "POST", "PATCH", "DELETE"])
@member_required
async def api_me_study_plan():
    owner = _me_qq_id()
    db = await get_db()
    try:
        data = await request.get_json(silent=True) or {}
        if request.method == "GET":
            async with db.execute(
                "SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags,i.status,i.position,i.added_at,i.completed_at "
                "FROM study_plan_items i LEFT JOIN (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations "
                "UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) p "
                "ON p.platform=i.platform AND p.problem_id=i.problem_id WHERE i.owner_qq_id=? ORDER BY i.position,i.added_at", (owner,)
            ) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        platform = _field(data, "platform", 24)
        problem_id = _field(data, "problem_id", 160)
        if not platform or not problem_id:
            return jsonify({"success": False, "message": "platform 和 problem_id 必填。"}), 400
        now = int(time.time())
        if request.method == "POST":
            try: position = int(data.get("position", 0) or 0)
            except (TypeError, ValueError): return jsonify({"success": False, "message": "position 必须是整数。"}), 400
            await db.execute("INSERT OR IGNORE INTO study_plan_items(owner_qq_id,platform,problem_id,status,position,added_at) VALUES(?,?,?,?,?,?)", (owner,platform,problem_id,"pending",position,now))
        elif request.method == "PATCH":
            status = _field(data, "status", 20) or "pending"
            if status not in {"pending", "done"}:
                return jsonify({"success": False, "message": "status 无效。"}), 400
            try: position = int(data.get("position", 0) or 0)
            except (TypeError, ValueError): return jsonify({"success": False, "message": "position 必须是整数。"}), 400
            await db.execute("UPDATE study_plan_items SET status=?,position=?,completed_at=? WHERE owner_qq_id=? AND platform=? AND problem_id=?", (status,position,now if status=="done" else None,owner,platform,problem_id))
        else:
            await db.execute("DELETE FROM study_plan_items WHERE owner_qq_id=? AND platform=? AND problem_id=?", (owner,platform,problem_id))
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@api.route("/me/contest/reviews", methods=["GET", "PUT"])
@member_required
async def api_me_contest_reviews():
    owner = _me_qq_id()
    db = await get_db()
    try:
        if request.method == "GET":
            contest = _field(request.args, "contest_id", 80)
            async with db.execute("SELECT contest_id,problem_id,verdict,rating,note_md,status,updated_at FROM contest_problem_reviews WHERE owner_qq_id=? AND contest_id=? ORDER BY problem_id", (owner,contest)) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        contest = _field(data, "contest_id", 80)
        problem = _field(data, "problem_id", 160)
        if not contest or not problem:
            return jsonify({"success": False, "message": "contest_id 和 problem_id 必填。"}), 400
        status = _field(data, "status", 20) or "todo"
        if status not in {"todo", "unsolved", "queued", "solved", "ignored", "reviewed"}:
            return jsonify({"success": False, "message": "无效的赛事复盘状态。"}), 400
        try: rating = int(data.get("rating") or 0) or None
        except (TypeError, ValueError): return jsonify({"success": False, "message": "rating 必须是整数。"}), 400
        now = int(time.time())
        await db.execute(
            "INSERT INTO contest_problem_reviews(owner_qq_id,contest_id,problem_id,verdict,rating,note_md,status,updated_at) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(owner_qq_id,contest_id,problem_id) DO UPDATE SET verdict=excluded.verdict,rating=excluded.rating,note_md=excluded.note_md,status=excluded.status,updated_at=excluded.updated_at",
            (owner,contest,problem,_field(data,"verdict",40),rating,_field(data,"note_md",12000),status,now),
        )
        if status in {"unsolved", "queued"}:
            await db.execute("INSERT OR IGNORE INTO study_plan_items(owner_qq_id,platform,problem_id,status,position,added_at) VALUES(?,?,?,?,?,?)", (owner,"codeforces",problem,"pending",0,now))
        elif status == "solved":
            await db.execute("UPDATE study_plan_items SET status='done',completed_at=? WHERE owner_qq_id=? AND platform='codeforces' AND problem_id=?", (now,owner,problem))
        await db.commit()
        return jsonify({"success": True, "status": status})
    finally:
        await db.close()


@api.route("/me/reviews/drafts", methods=["GET", "POST"])
@member_required
async def api_me_review_drafts():
    owner = _me_qq_id()
    db = await get_db()
    try:
        if request.method == "GET":
            async with db.execute("SELECT id,context_type,context_id,draft_md,status,model,created_at,updated_at FROM review_drafts WHERE owner_qq_id=? ORDER BY updated_at DESC LIMIT 100", (owner,)) as cursor:
                return jsonify([dict(row) for row in await cursor.fetchall()])
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "请求数据格式错误。"}), 400
        context = _field(data, "context_id", 160)
        if not context:
            return jsonify({"success": False, "message": "context_id 必填。"}), 400
        now = int(time.time())
        cursor = await db.execute("INSERT INTO review_drafts(owner_qq_id,context_type,context_id,draft_md,status,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (owner,_field(data,"context_type",40) or "contest",context,_field(data,"draft_md",30000),"draft",_field(data,"model",100),now,now))
        await db.commit()
        return jsonify({"success": True, "id": cursor.lastrowid}), 201
    finally:
        await db.close()


_LEADERBOARD_SORT_COLUMNS = {
    "total_count": "total_count",
    "cf_count": "cf_count",
    "luogu_count": "luogu_count",
    "nowcoder_count": "nowcoder_count",
    "atcoder_count": "atcoder_count",
    "cjlu_count": "cjlu_count",
}
_LEADERBOARD_PLATFORMS = (
    "codeforces",
    "luogu",
    "nowcoder",
    "atcoder",
    "cjlu",
)


def _leaderboard_options(args):
    raw_days = str(args.get("days", "7")).strip().lower()
    if raw_days in {"all", "0", ""}:
        days = None
    else:
        try:
            days = max(1, min(3650, int(raw_days)))
        except (TypeError, ValueError):
            days = 7
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(5, min(100, int(args.get("page_size", 20))))
    except (TypeError, ValueError):
        page_size = 20
    sort_key = str(args.get("sort", "total_count")).strip()
    if sort_key not in _LEADERBOARD_SORT_COLUMNS:
        sort_key = "total_count"
    search = str(args.get("search", "")).strip()[:80]
    raw_platforms = str(args.get("platforms", "")).strip().lower()
    selected_platforms = tuple(platform for platform in _LEADERBOARD_PLATFORMS if platform in raw_platforms.split(","))
    if not selected_platforms:
        selected_platforms = _LEADERBOARD_PLATFORMS
    return days, page, page_size, sort_key, search, selected_platforms


def _leaderboard_user_filter(search):
    if not search:
        return "", []
    pattern = f"%{search.lower()}%"
    return (
        " WHERE lower(COALESCE(NULLIF(u.cf_handle, ''), u.name, u.qq_id)) LIKE ?"
        " OR lower(COALESCE(u.real_name, '')) LIKE ?"
        " OR lower(COALESCE(u.school, '')) LIKE ?"
        " OR u.qq_id LIKE ?",
        [pattern, pattern, pattern, pattern],
    )


async def _fetch_leaderboard(db, days, page, page_size, sort_key, search, platforms, paginate=True):
    cutoff = int(time.time()) - days * 24 * 60 * 60 if days is not None else None
    time_sql = " AND s.submit_time >= ?" if cutoff is not None else ""
    select_params = []
    platform_counts = []
    for platform, alias in (
        ("codeforces", "cf_count"),
        ("luogu", "luogu_count"),
        ("nowcoder", "nowcoder_count"),
        ("atcoder", "atcoder_count"),
        ("cjlu", "cjlu_count"),
    ):
        platform_counts.append(
            f"COUNT(DISTINCT CASE WHEN s.platform = '{platform}'{time_sql} THEN s.problem_id END) AS {alias}"
        )
        if cutoff is not None:
            select_params.append(cutoff)
    platform_sql = ", ".join(f"'{platform}'" for platform in platforms)
    total_sql = f"COUNT(DISTINCT CASE WHEN s.platform IN ({platform_sql})" + time_sql + " THEN s.platform || ':' || s.problem_id END) AS total_count"
    if cutoff is not None:
        select_params.append(cutoff)
    where_sql, where_params = _leaderboard_user_filter(search)
    query = (
        "SELECT u.qq_id, COALESCE(NULLIF(u.cf_handle, ''), u.name, u.qq_id) AS name, "
        "u.real_name, u.status, u.school, "
        + ", ".join(platform_counts)
        + ", "
        + total_sql
        + " FROM users u LEFT JOIN submissions s ON u.qq_id = s.user_qq_id"
        + where_sql
        + " GROUP BY u.qq_id, u.name, u.cf_handle, u.real_name, u.status, u.school"
        + f" ORDER BY {_LEADERBOARD_SORT_COLUMNS[sort_key]} DESC, name ASC, u.qq_id ASC"
    )
    params = select_params + where_params
    if paginate:
        query += " LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
    async with db.execute(query, tuple(params)) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]

    count_query = "SELECT COUNT(*) FROM users u" + where_sql
    async with db.execute(count_query, tuple(where_params)) as cursor:
        total = int((await cursor.fetchone())[0])
    return rows, total


@api.route("/leaderboard", methods=["GET"])
@admin_required
async def api_get_leaderboard():
    db = await get_db()
    try:
        days, page, page_size, sort_key, search, platforms = _leaderboard_options(request.args)
        rows, total = await _fetch_leaderboard(db, days, page, page_size, sort_key, search, platforms)
        return jsonify({
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "days": days,
            "sort": sort_key,
            "search": search,
            "platforms": list(platforms),
        })
    except Exception as e:
        LOG.error(f"[API Error] /leaderboard: {e}", exc_info=True)
        return jsonify({"rows": [], "total": 0, "message": "排行榜查询失败。"}), 500
    finally:
        await db.close()


@api.route("/leaderboard/export", methods=["GET"])
@admin_required
async def api_export_leaderboard():
    db = await get_db()
    try:
        days, _, _, sort_key, search, platforms = _leaderboard_options(request.args)
        rows, _ = await _fetch_leaderboard(db, days, 1, 0, sort_key, search, platforms, paginate=False)
        import csv
        from io import StringIO

        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["排名", "成员昵称", "真实姓名", "Codeforces", "洛谷", "牛客", "AtCoder", "校OJ", "总题数", "身份", "学校", "QQ号"])
        for index, row in enumerate(rows, 1):
            writer.writerow([
                index,
                row.get("name") or "未命名",
                row.get("real_name") or "—",
                row.get("cf_count") or 0,
                row.get("luogu_count") or 0,
                row.get("nowcoder_count") or 0,
                row.get("atcoder_count") or 0,
                row.get("cjlu_count") or 0,
                row.get("total_count") or 0,
                row.get("status") or "—",
                row.get("school") or "—",
                row.get("qq_id") or "",
            ])
        label = "all" if days is None else f"{days}d"
        response = Response(output.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="acm_leaderboard_{label}.csv"'
        return response
    finally:
        await db.close()
