"""Narrow receipt authentication survives invalidation of the normal session."""
import asyncio
import sqlite3
from quart import Blueprint, current_app, jsonify, request, session

from . import account_closure_service as service
from .account_lifecycle_service import AccountLifecycleError, web_account
from .auth_service import verify_password
from .backend_api import _client_key, _csrf_valid, _session_identity, get_db

account_closure_api = Blueprint("account_closure_api", __name__)


@account_closure_api.after_request
async def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.vary.add("Cookie")
    return response


@account_closure_api.errorhandler(AccountLifecycleError)
async def policy_error(error):
    response = jsonify({"success": False, "code": error.code, "message": str(error)})
    if error.status == 429:
        response.headers["Retry-After"] = "900"
    return response, error.status


@account_closure_api.errorhandler(sqlite3.Error)
async def storage_error(error):
    code = "STORAGE_BUSY" if "locked" in str(error).lower() or "busy" in str(error).lower() else "STORAGE_UNAVAILABLE"
    return jsonify({"success": False, "code": code, "message": "存储暂时不可用，请保留回执并查询结果；不要把退出登录视为注销成功。"}), 503


def require_feature():
    if not current_app.config.get("ACCOUNT_CLOSURE_ENABLED", False):
        raise AccountLifecycleError("FEATURE_DISABLED", "账号注销暂未开放。", 404)


def reject_targets():
    if request.args:
        raise AccountLifecycleError("INVALID_REQUEST", "本接口不接受目标账号参数。", 400)


async def limited(db, action, identity=None):
    budgets = {
        "preview": (10, 60), "reauth": (5, 20),
        "receipt": (60, 120), "submit": (30, 60),
    }
    per_account, per_ip = budgets[action]
    subjects = [("ip:" + _client_key(), per_ip)]
    if identity and identity.get("qq_id"):
        subjects.append(("account:" + identity["qq_id"], per_account))
    await service.rate_limit(db, current_app.secret_key, action, subjects)


async def current_identity():
    identity = await _session_identity()
    if not identity:
        raise AccountLifecycleError("AUTH_REQUIRED", "请先登录。", 401)
    if identity.get("legacy"):
        raise AccountLifecycleError("LEGACY_IDENTITY_UNSUPPORTED", "旧管理身份不支持注销。", 403)
    return identity


@account_closure_api.get("/me/account-closure/preview")
async def preview():
    require_feature()
    reject_targets()
    identity = await current_identity()
    db = await get_db()
    try:
        await limited(db, "preview", identity)
        return jsonify(await service.create_preview(db, identity))
    finally:
        await db.close()


@account_closure_api.get("/account-closures/<request_id>")
async def receipt(request_id):
    reject_targets()
    db = await get_db()
    try:
        await limited(db, "receipt")
        record = await service.receipt_record(db, request_id, request.headers.get("X-Closure-Receipt", ""))
        return jsonify(service.receipt_result(record))
    finally:
        await db.close()


async def commit_on_own_connection(identity, request_id, token, data, account):
    db = await get_db()
    try:
        return await service.close_account(db, identity, request_id, token, data, account)
    finally:
        await db.close()


@account_closure_api.post("/me/account-closure")
async def close():
    reject_targets()
    if not request.headers.get("Idempotency-Key"):
        require_feature()
    data = await request.get_json(silent=True)
    service.validate_body(data)
    request_id = request.headers.get("Idempotency-Key", "")
    token = request.headers.get("X-Closure-Receipt", "")
    db = await get_db()
    identity = None
    try:
        await limited(db, "submit")
        # A committed result is a secret-authenticated read-only replay. Normal
        # sessions and their CSRF token have already been revoked at this point.
        record = await service.receipt_record(db, request_id, token)
        if record["intent_fingerprint"] != service.intent(data):
            raise AccountLifecycleError("IDEMPOTENCY_CONFLICT", "相同请求编号对应的注销意图不同。")
        if record["committed_at"]:
            # Do not clear a different account's newly established session.
            if session.get("webui_qq_id") == record["user_qq_id"]:
                session.clear()
            return jsonify(service.receipt_result(record))
        require_feature()
        identity = await current_identity()
        if not _csrf_valid():
            raise AccountLifecycleError("CSRF_INVALID", "请求校验已失效，请刷新后重试。", 403)
        if record["user_qq_id"] != identity["qq_id"]:
            raise AccountLifecycleError("INVALID_REQUEST", "只能注销本人账号。", 403)
        account = await web_account(db, identity["qq_id"])
        problems = await service.blockers(db, account)
        if problems:
            raise AccountLifecycleError(problems[0]["code"], problems[0]["message"])
        await limited(db, "reauth", identity)
        if not await asyncio.to_thread(verify_password, data["current_password"], account["password_hash"]):
            raise AccountLifecycleError("REAUTH_FAILED", "当前密码不正确。", 403)
        # Shield only the short final transaction, never the password or I/O.
        task = asyncio.create_task(commit_on_own_connection(identity, request_id, token, data, account))
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        session.clear()
        notifier = current_app.config.get("PLUGIN_CONFIG", {}).get("_account_closure_notifier")
        if callable(notifier):
            try:
                notifier(identity["qq_id"])
            except Exception:
                current_app.logger.warning("Account closed; local task cancellation will rely on epoch fences")
        worker = current_app.extensions.get("account_closure_cleanup")
        if worker:
            worker.wake()
        return jsonify(result)
    except AccountLifecycleError as error:
        await db.rollback()
        if identity:
            await service.audit(db, identity["qq_id"], error.code)
            await db.commit()
        raise
    except sqlite3.Error:
        await db.rollback()
        if identity:
            try:
                await service.audit(db, identity["qq_id"], "STORAGE_UNAVAILABLE")
                await db.commit()
            except sqlite3.Error:
                await db.rollback()
        raise
    finally:
        await db.close()


@account_closure_api.get("/admin/account-closures/audit")
async def audit_log():
    identity = await current_identity()
    if identity.get("must_change_password"):
        raise AccountLifecycleError("MUST_CHANGE_PASSWORD", "请先完成修改密码。", 428)
    if identity["role"] != "root":
        raise AccountLifecycleError("FORBIDDEN", "仅限有效 Web root 查看注销审计。", 403)
    try:
        page = int(request.args.get("page", "1"))
        if not 1 <= page <= 100000:
            raise ValueError()
    except (TypeError, ValueError):
        raise AccountLifecycleError("INVALID_REQUEST", "分页参数无效。", 400)
    from .account_lifecycle_service import require_web_actor
    db = await get_db()
    try:
        await db.execute("BEGIN")
        await require_web_actor(db, identity, roles={"root"})
        items = await service.rows(db, "SELECT id,subject_qq_id,action,result_code,policy_version,created_at,counts_json FROM account_lifecycle_audit ORDER BY id DESC LIMIT 50 OFFSET ?", ((page - 1) * 50,))
        for item in items:
            subject = item.pop("subject_qq_id")
            edge = 1 if subject and len(subject) < 6 else 2
            item["subject"] = (subject[:edge] + "****" + subject[-edge:]) if subject else None
        return jsonify({"items": items, "page": page})
    finally:
        await db.rollback()
        await db.close()
