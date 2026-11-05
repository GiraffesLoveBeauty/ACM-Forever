"""Authenticated service-to-service API for the NCatBot adapter."""
import hmac
import inspect
import time
from functools import wraps

import aiosqlite
from quart import Blueprint, current_app, jsonify, request

from .backend_api import _clear_platform_records, _fetch_leaderboard, _leaderboard_options
from .cf_client import cf_request
from .database import validate_submission_data
from .account_lifecycle_service import AccountLifecycleError, require_active_user
from .difficulty import challenge_filter, challenge_time_limit, neighboring_difficulties, normalize_platform
from .event_log import remember_identity
from .training_logic import score_candidate

from .binding_service import BINDING_FIELDS as _BINDING_FIELDS, apply_binding, snapshot

bot_api = Blueprint("bot_api", __name__)


@bot_api.errorhandler(AccountLifecycleError)
async def lifecycle_error_response(error):
    return jsonify({"success": False, "code": error.code, "message": str(error)}), error.status


async def _bot_write(db, qq_id, *, allow_missing=False):
    if not db.in_transaction:
        await db.execute("BEGIN IMMEDIATE")
    captured = getattr(request, "lifecycle_snapshot", None)
    epoch = captured["account_epoch"] if captured and captured["qq_id"] == str(qq_id) else None
    return await require_active_user(db, qq_id, expected_epoch=epoch, allow_missing=allow_missing)


def service_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        expected = str(current_app.config.get("BOT_API_TOKEN", "")).strip()
        if not expected:
            return jsonify({"success": False, "message": "Bot API token is not configured."}), 503
        authorization = request.headers.get("Authorization", "")
        supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            return jsonify({"success": False, "message": "Unauthorized."}), 401
        remember_identity({"role": "service"})
        qq_id = (request.view_args or {}).get("qq_id")
        request.lifecycle_snapshot = None
        if qq_id:
            db = await _db()
            try:
                user = await require_active_user(db, qq_id, allow_missing=True)
                request.lifecycle_snapshot = dict(user) if user else None
            finally:
                await db.close()
        return await func(*args, **kwargs)
    return wrapper


async def _db():
    path = current_app.config.get("DB_PATH")
    if not path:
        raise ConnectionError("Database path is not configured.")
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def _codeforces_api_call(method, params):
    engine = getattr(current_app, "sync_engine", None)
    if not engine or not engine._http_session:
        raise ConnectionError("Codeforces API proxy is unavailable.")
    return await cf_request(engine._http_session, method, params, engine._crawler_config())


def _qq(value):
    text = str(value or "").strip()
    return text if text.isdigit() and 4 <= len(text) <= 12 else ""


@bot_api.get("/health")
@service_required
async def bot_health():
    return jsonify({"status": "ok"})


@bot_api.get("/users")
@service_required
async def list_users():
    try:
        limit = max(1, min(5000, int(request.args.get("limit", 1000))))
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit and offset must be integers."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT qq_id,name,real_name,cf_handle,luogu_id,nowcoder_id,"
            "atcoder_handle,cjlu_username,status,school,challenge_rating,last_sync_timestamp "
            "FROM users WHERE account_state='active' ORDER BY qq_id LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        return jsonify(rows)
    finally:
        await db.close()


@bot_api.get("/users/lookup")
@service_required
async def lookup_users():
    query = str(request.args.get("query", "")).strip()[:128]
    if not query:
        return jsonify([])
    db = await _db()
    try:
        async with db.execute(
            "SELECT qq_id,name,cf_handle FROM users WHERE account_state='active' AND (qq_id=? "
            "OR LOWER(cf_handle)=LOWER(?) OR LOWER(name)=LOWER(?)) ORDER BY qq_id LIMIT 25",
            (query, query, query),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>")
@service_required
async def get_user(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT qq_id,name,real_name,cf_handle,luogu_id,nowcoder_id,"
            "atcoder_handle,cjlu_username,status,school,challenge_rating,last_sync_timestamp "
            "FROM users WHERE qq_id=?",
            (qq_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "User not found."}), 404
        return jsonify(dict(row))
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/summary")
@service_required
async def get_user_summary(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    now = int(time.time())
    db = await _db()
    try:
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404
        async with db.execute(
            "SELECT COUNT(*) AS lifetime, "
            "SUM(CASE WHEN submit_time>=? THEN 1 ELSE 0 END) AS today, "
            "SUM(CASE WHEN submit_time>=? THEN 1 ELSE 0 END) AS recent_7d, "
            "SUM(CASE WHEN submit_time>=? THEN 1 ELSE 0 END) AS recent_30d "
            "FROM submissions WHERE user_qq_id=?",
            (now - 86400, now - 7 * 86400, now - 30 * 86400, qq_id),
        ) as cursor:
            counts = dict(await cursor.fetchone())
        async with db.execute(
            "SELECT platform,COUNT(*) AS count FROM submissions WHERE user_qq_id=? GROUP BY platform",
            (qq_id,),
        ) as cursor:
            platform_counts = {row["platform"]: row["count"] for row in await cursor.fetchall()}
        async with db.execute(
            "SELECT platform,problem_rating,COUNT(*) AS count FROM submissions "
            "WHERE user_qq_id=? GROUP BY platform,problem_rating ORDER BY platform,count DESC",
            (qq_id,),
        ) as cursor:
            difficulty = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT DISTINCT submit_time FROM submissions WHERE user_qq_id=? ORDER BY submit_time DESC LIMIT 5000",
            (qq_id,),
        ) as cursor:
            activity_timestamps = [row["submit_time"] for row in await cursor.fetchall()]
        return jsonify({
            "user": dict(user),
            "counts": {key: value or 0 for key, value in counts.items()},
            "platform_counts": platform_counts,
            "difficulty": difficulty,
            "activity_timestamps": activity_timestamps,
        })
    finally:
        await db.close()


@bot_api.patch("/users/<qq_id>/profile")
@service_required
async def update_user_profile(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    if not qq_id or not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid QQ number or JSON body."}), 400
    fields = {key: str(data[key]).strip()[:100] for key in ("name", "status", "school") if key in data}
    if not fields:
        return jsonify({"success": False, "message": "No supported profile fields were supplied."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        assignments = ",".join(f"{field}=?" for field in fields)
        cursor = await db.execute(
            f"UPDATE users SET {assignments} WHERE qq_id=?",
            tuple(fields.values()) + (qq_id,),
        )
        await db.commit()
        if not cursor.rowcount:
            return jsonify({"success": False, "message": "User not found."}), 404
        return jsonify({"success": True, "qq_id": qq_id})
    finally:
        await db.close()


@bot_api.get("/bindings/owner")
@service_required
async def find_binding_owner():
    platform = str(request.args.get("platform", "")).strip().lower()
    account = str(request.args.get("account", "")).strip()
    qq_id = _qq(request.args.get("exclude_qq_id", ""))
    binding = _BINDING_FIELDS.get(platform)
    if not binding or not account:
        return jsonify({"success": False, "message": "A supported platform and account are required."}), 400
    field, _ = binding
    sql = f"SELECT qq_id FROM users WHERE LOWER(TRIM({field}))=LOWER(TRIM(?))"
    params = [account]
    if qq_id:
        sql += " AND qq_id<>?"
        params.append(qq_id)
    sql += " ORDER BY qq_id LIMIT 1"
    db = await _db()
    try:
        async with db.execute(sql, tuple(params)) as cursor:
            row = await cursor.fetchone()
        return jsonify({"qq_id": row["qq_id"] if row else None})
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/bind-verifications")
@service_required
async def list_bind_verifications(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT platform,account,verification_code,created_at,expires_at "
            "FROM account_bind_verifications WHERE qq_id=? ORDER BY created_at DESC",
            (qq_id,),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.put("/users/<qq_id>/bind-verifications/<platform>")
@service_required
async def put_bind_verification(qq_id, platform):
    qq_id = _qq(qq_id)
    platform = str(platform).strip().lower()
    data = await request.get_json(silent=True)
    account = str(data.get("account") or "").strip() if isinstance(data, dict) else ""
    code = str(data.get("verification_code") or "").strip() if isinstance(data, dict) else ""
    try:
        created_at = int(data.get("created_at"))
        expires_at = int(data.get("expires_at"))
    except (TypeError, ValueError, AttributeError):
        return jsonify({"success": False, "message": "Invalid verification timestamps."}), 400
    if not qq_id or platform not in {"cf", "luogu", "nowcoder", "atcoder", "cjlu"} or not account or not code or expires_at <= created_at:
        return jsonify({"success": False, "message": "Invalid pending account verification."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        async with db.execute("SELECT 1 FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            exists = await cursor.fetchone()
        if not exists:
            await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq_id, qq_id))
        await db.execute(
            "INSERT INTO account_bind_verifications(qq_id,platform,account,verification_code,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(qq_id,platform) DO UPDATE SET account=excluded.account, "
            "verification_code=excluded.verification_code,created_at=excluded.created_at,expires_at=excluded.expires_at,verification_id=NULL,expected_binding=NULL,binding_version=NULL,validated_at=0",
            (qq_id, platform, account, code, created_at, expires_at),
        )
        await db.commit()
        return jsonify({"success": True})
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/bind-verifications")
@service_required
async def create_bind_verifications(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    items = data.get("items") if isinstance(data, dict) else None
    if not qq_id or not isinstance(items, list) or not items or len(items) > len(_BINDING_FIELDS):
        return jsonify({"success": False, "message": "Invalid user or verification list."}), 400
    now = int(time.time())
    normalized = []
    seen_platforms = set()
    for item in items:
        if not isinstance(item, dict):
            return jsonify({"success": False, "message": "Verification records must be objects."}), 400
        platform = str(item.get("platform") or "").strip().lower()
        account = str(item.get("account") or "").strip()
        code = str(item.get("verification_code") or "").strip()
        try:
            expires_at = int(item.get("expires_at"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid verification expiry."}), 400
        binding = _BINDING_FIELDS.get(platform)
        if platform not in {"cf", "luogu", "nowcoder", "atcoder", "cjlu"} or not binding or not account or not code or expires_at <= now:
            return jsonify({"success": False, "message": "Invalid pending account verification."}), 400
        if platform in seen_platforms:
            return jsonify({"success": False, "message": "Duplicate platform in verification list."}), 400
        seen_platforms.add(platform)
        normalized.append((platform, account, code, now, expires_at, binding[0]))
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        for platform, account, _code, _created, _expires, field in normalized:
            current = str(user[field] or "").strip() if user else ""
            if current:
                await db.rollback()
                return jsonify({"success": False, "message": f"{platform} already has a bound account."}), 409
            async with db.execute(
                f"SELECT qq_id FROM users WHERE qq_id<>? AND LOWER(TRIM({field}))=LOWER(TRIM(?)) LIMIT 1",
                (qq_id, account),
            ) as cursor:
                owner = await cursor.fetchone()
            if owner:
                await db.rollback()
                return jsonify({"success": False, "message": f"{platform} account is already bound.", "owner_qq_id": owner["qq_id"]}), 409
        await db.executemany(
            "INSERT INTO account_bind_verifications(qq_id,platform,account,verification_code,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(qq_id,platform) DO UPDATE SET account=excluded.account, "
            "verification_code=excluded.verification_code,created_at=excluded.created_at,expires_at=excluded.expires_at,verification_id=NULL,expected_binding=NULL,binding_version=NULL,validated_at=0",
            [(qq_id, platform, account, code, created, expires) for platform, account, code, created, expires, _field in normalized],
        )
        await db.commit()
        return jsonify({"success": True, "created": len(normalized)})
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


@bot_api.delete("/users/<qq_id>/bind-verifications/<platform>")
@service_required
async def delete_bind_verification(qq_id, platform):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        await db.execute(
            "DELETE FROM account_bind_verifications WHERE qq_id=? AND platform=?",
            (qq_id, str(platform).strip().lower()),
        )
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@bot_api.delete("/users/<qq_id>")
@service_required
async def delete_user(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        async with db.execute("SELECT name FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            await db.rollback()
            return jsonify({"success": False, "message": "User not found."}), 404
        async with db.execute("SELECT 1 FROM web_accounts WHERE qq_id=?", (qq_id,)) as cursor:
            if await cursor.fetchone():
                raise AccountLifecycleError("WEB_ACCOUNT_PROTECTED", "Web 账号不能通过 Bot 删除成员资料，请使用本人账号生命周期流程。")
        for table, owner_field in (
            ("submissions", "user_qq_id"),
            ("submission_attempts", "owner_qq_id"),
            ("user_problem_state", "owner_qq_id"),
            ("review_states", "owner_qq_id"),
            ("study_plan_items", "owner_qq_id"),
            ("random_challenges", "qq_id"),
            ("notification_preferences", "qq_id"),
            ("account_bind_verifications", "qq_id"),
            ("user_platform_sync_state", "user_qq_id"),
            ("contest_problem_reviews", "owner_qq_id"),
            ("workspace_items", "owner_qq_id"),
            ("review_drafts", "owner_qq_id"),
        ):
            await db.execute(f"DELETE FROM {table} WHERE {owner_field}=?", (qq_id,))
        await db.execute("DELETE FROM users WHERE qq_id=?", (qq_id,))
        await db.commit()
        return jsonify({"success": True, "name": user["name"]})
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


@bot_api.post("/maintenance/validate-submissions")
@service_required
async def bot_validate_submissions():
    data = await request.get_json(silent=True) or {}
    repair = bool(data.get("repair", False))
    db = await _db()
    try:
        result = await validate_submission_data(db, repair=repair)
        return jsonify(result)
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/bindings/<platform>/confirm")
@service_required
async def confirm_account_binding(qq_id, platform):
    qq_id = _qq(qq_id)
    platform = str(platform).strip().lower()
    binding = _BINDING_FIELDS.get(platform)
    if not qq_id or platform not in {"cf", "luogu", "nowcoder", "atcoder", "cjlu"} or not binding:
        return jsonify({"success": False, "message": "Invalid user or platform."}), 400
    field, normalized_platform = binding
    now = int(time.time())
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        async with db.execute(
            "SELECT account,verification_code,expires_at FROM account_bind_verifications WHERE qq_id=? AND platform=?",
            (qq_id, platform),
        ) as cursor:
            pending = await cursor.fetchone()
        if not pending or int(pending["expires_at"] or 0) < now:
            await db.rollback()
            return jsonify({"success": False, "message": "Pending verification is missing or expired."}), 409
        async with db.execute(f"SELECT {field} FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            current = await cursor.fetchone()
        if current and (current[field] or "").strip():
            await db.rollback()
            return jsonify({"success": False, "message": "A platform account is already bound."}), 409
        if not current:
            await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq_id, qq_id))
        try:
            await apply_binding(db, qq_id, normalized_platform, pending["account"], expected=await snapshot(db, qq_id, normalized_platform), actor="bot")
        except aiosqlite.IntegrityError:
            await db.rollback()
            return jsonify({"success": False, "message": "That OJ account is already bound."}), 409
        await db.commit()
        return jsonify({"success": True, "account": pending["account"], "platform": normalized_platform})
    finally:
        await db.close()


@bot_api.delete("/users/<qq_id>/bindings/<platform>")
@service_required
async def remove_account_binding(qq_id, platform):
    qq_id = _qq(qq_id)
    binding = _BINDING_FIELDS.get(str(platform).strip().lower())
    if not qq_id or not binding:
        return jsonify({"success": False, "message": "Invalid user or platform."}), 400
    field, normalized_platform = binding
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        async with db.execute(f"SELECT {field} FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        await db.execute(
            "DELETE FROM account_bind_verifications WHERE qq_id=? AND platform=?",
            (qq_id, str(platform).strip().lower()),
        )
        if not user or not (user[field] or "").strip():
            await db.commit()
            return jsonify({"success": False, "message": "No account is bound for this platform."}), 404
        await apply_binding(db, qq_id, normalized_platform, None, expected=await snapshot(db, qq_id, normalized_platform), actor="bot")
        await db.commit()
        return jsonify({"success": True})
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/notification-preferences")
@service_required
async def get_notification_preferences(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT inactive_days,enabled,last_notified_at FROM notification_preferences WHERE qq_id=?",
            (qq_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return jsonify(dict(row) if row else {"inactive_days": 7, "enabled": 0, "last_notified_at": 0})
    finally:
        await db.close()


@bot_api.put("/users/<qq_id>/notification-preferences")
@service_required
async def put_notification_preferences(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    if not qq_id or not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid QQ number or JSON body."}), 400
    try:
        inactive_days = max(1, min(365, int(data.get("inactive_days", 7))))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "inactive_days must be an integer."}), 400
    enabled = bool(data.get("enabled", False))
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        await db.execute(
            "INSERT INTO notification_preferences(qq_id,inactive_days,enabled,last_notified_at) VALUES(?,?,?,0) "
            "ON CONFLICT(qq_id) DO UPDATE SET inactive_days=excluded.inactive_days,enabled=excluded.enabled",
            (qq_id, inactive_days, int(enabled)),
        )
        await db.commit()
        return jsonify({"success": True, "inactive_days": inactive_days, "enabled": enabled})
    finally:
        await db.close()


@bot_api.get("/challenges/monthly")
@service_required
async def get_monthly_challenge():
    qq_id = _qq(request.args.get("qq_id", ""))
    month = time.strftime("%Y-%m")
    db = await _db()
    try:
        async with db.execute(
            "SELECT title,target_count FROM challenges WHERE month=? AND active=1",
            (month,),
        ) as cursor:
            challenge = await cursor.fetchone()
        count = 0
        if qq_id:
            start = int(time.mktime(time.strptime(month + "-01", "%Y-%m-%d")))
            async with db.execute(
                "SELECT COUNT(*) FROM submissions WHERE user_qq_id=? AND submit_time>=?",
                (qq_id, start),
            ) as cursor:
                count = int((await cursor.fetchone())[0])
        return jsonify({"month": month, "challenge": dict(challenge) if challenge else None, "count": count})
    finally:
        await db.close()


@bot_api.put("/challenges/monthly")
@service_required
async def put_monthly_challenge():
    data = await request.get_json(silent=True)
    try:
        target_count = int(data.get("target_count")) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        target_count = 0
    if not 1 <= target_count <= 10000:
        return jsonify({"success": False, "message": "target_count must be between 1 and 10000."}), 400
    month = time.strftime("%Y-%m")
    db = await _db()
    try:
        await db.execute(
            "INSERT INTO challenges(month,title,target_count,active,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(month) DO UPDATE SET target_count=excluded.target_count,active=1",
            (month, f"{month} 月度刷题挑战", target_count, 1, int(time.time())),
        )
        await db.commit()
        return jsonify({"success": True, "month": month, "target_count": target_count})
    finally:
        await db.close()


@bot_api.get("/notifications/inactive-candidates")
@service_required
async def inactive_notification_candidates():
    now = int(time.time())
    db = await _db()
    try:
        async with db.execute(
            "SELECT p.qq_id,p.inactive_days,p.last_notified_at,u.name,MAX(s.submit_time) AS last_submit_time "
            "FROM notification_preferences p JOIN users u ON u.qq_id=p.qq_id "
            "LEFT JOIN submissions s ON s.user_qq_id=p.qq_id WHERE p.enabled=1 AND u.account_state='active' "
            "GROUP BY p.qq_id,p.inactive_days,p.last_notified_at,u.name"
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        candidates = []
        for row in rows:
            cutoff = now - int(row["inactive_days"]) * 86400
            if row["last_submit_time"] and row["last_submit_time"] >= cutoff:
                continue
            if row["last_notified_at"] and now - row["last_notified_at"] < 86400:
                continue
            candidates.append({key: row[key] for key in ("qq_id", "inactive_days", "name")})
        return jsonify(candidates)
    finally:
        await db.close()


@bot_api.post("/notifications/inactive/<qq_id>/sent")
@service_required
async def mark_inactive_notification_sent(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        await db.execute(
            "UPDATE notification_preferences SET last_notified_at=? WHERE qq_id=?",
            (int(time.time()), qq_id),
        )
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/random-challenges")
@service_required
async def create_random_challenge(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    if not qq_id or not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid QQ number or JSON body."}), 400
    platform = str(data.get("platform") or "").strip().lower()
    if platform in {"cf", "codeforces"}:
        platform = "codeforces"
    if platform not in {"", "codeforces", "luogu", "nowcoder", "atcoder"}:
        return jsonify({"success": False, "message": "Unsupported random-challenge platform."}), 400
    tag = str(data.get("tag") or "").strip()[:80]
    now = int(time.time())
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        async with db.execute("SELECT challenge_rating FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        rating = int(user["challenge_rating"] or 1000) if user else 1000
        low, high = max(0, rating - 100), rating + 100
        await db.execute(
            "UPDATE random_challenges SET status='expired' WHERE qq_id=? AND status='active' AND expires_at<?",
            (qq_id, now),
        )
        async with db.execute(
            "SELECT 1 FROM random_challenges WHERE qq_id=? AND status='active' LIMIT 1",
            (qq_id,),
        ) as cursor:
            active = await cursor.fetchone()
        if active:
            await db.commit()
            return jsonify({"success": False, "message": "An active challenge already exists."}), 409
        sql = (
            "SELECT r.platform,r.problem_id,r.problem_name,r.problem_rating,r.problem_url,COALESCE(r.tags,'') AS tags "
            "FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations "
            "UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) r "
            "WHERE r.platform<>'cjlu' AND CAST(r.problem_rating AS INTEGER) BETWEEN ? AND ? "
            "AND NOT EXISTS(SELECT 1 FROM submissions s WHERE s.user_qq_id=? AND s.platform=r.platform AND s.problem_id=r.problem_id)"
        )
        params = [low, high, qq_id]
        if platform:
            sql += " AND r.platform=?"
            params.append(platform)
        if tag:
            sql += " AND (r.problem_name LIKE ? OR r.problem_id LIKE ? OR COALESCE(r.tags,'') LIKE ?)"
            params.extend([f"%{tag}%"] * 3)
        sql += " ORDER BY RANDOM() LIMIT 1"
        async with db.execute(sql, tuple(params)) as cursor:
            problem = await cursor.fetchone()
        if not problem:
            await db.commit()
            return jsonify({"success": False, "message": "No matching unsolved problem was found.", "rating": rating}), 404
        minutes = max(10, min(90, 75 - max(0, rating - 800) // 40))
        await db.execute(
            "INSERT INTO random_challenges(qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,challenge_rating,time_limit_minutes,status,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (qq_id, problem["platform"], problem["problem_id"], problem["problem_name"],
             int(problem["problem_rating"] or 0), problem["problem_url"], tag, rating,
             minutes, "active", now, now + minutes * 60),
        )
        async with db.execute(
            "SELECT * FROM random_challenges WHERE qq_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (qq_id,),
        ) as cursor:
            challenge = dict(await cursor.fetchone())
        await db.commit()
        return jsonify({"success": True, "challenge": challenge}), 201
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/random-challenges/active")
@service_required
async def get_active_random_challenge(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        now = int(time.time())
        await db.execute(
            "UPDATE random_challenges SET status='expired' WHERE qq_id=? AND status='active' AND expires_at<?",
            (qq_id, now),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM random_challenges WHERE qq_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (qq_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return jsonify(dict(row) if row else {"challenge": None})
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/random-challenges/done")
@service_required
async def complete_random_challenge(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        now = int(time.time())
        async with db.execute(
            "SELECT * FROM random_challenges WHERE qq_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (qq_id,),
        ) as cursor:
            challenge = await cursor.fetchone()
        if not challenge:
            return jsonify({"success": False, "message": "No active challenge."}), 404
        challenge = dict(challenge)
        if now > int(challenge["expires_at"]):
            await _bot_write(db, qq_id)
            await db.execute("UPDATE random_challenges SET status='expired' WHERE id=?", (challenge["id"],))
            await db.commit()
            return jsonify({"success": False, "message": "Challenge expired."}), 410
        platform = challenge["platform"]
        problem_id = str(challenge["problem_id"])
        candidates = {problem_id}
        prefix = {"codeforces": "cf_", "atcoder": "atc_", "nowcoder": "nc_"}.get(platform, "")
        if prefix:
            candidates.add(problem_id[len(prefix):] if problem_id.startswith(prefix) else prefix + problem_id)
        placeholders = ",".join("?" for _ in candidates)
        query = f"SELECT 1 FROM submissions WHERE user_qq_id=? AND platform=? AND problem_id IN ({placeholders}) AND submit_time>=? LIMIT 1"
        params = (qq_id, platform, *candidates, challenge["created_at"])
        async with db.execute(query, params) as cursor:
            solved = await cursor.fetchone()
        if not solved and platform != "cjlu":
            async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
                user = await cursor.fetchone()
            user = dict(user) if user else None
            if not user:
                return jsonify({"success": False, "message": "No bound account was found."}), 409
            sync_engine = getattr(current_app, "sync_engine", None)
            if sync_engine:
                await sync_engine.sync_single_platform_for_days(qq_id, platform, 1)
            async with db.execute(query, params) as cursor:
                solved = await cursor.fetchone()
        if not solved:
            return jsonify({"success": False, "message": "The problem is not in recent accepted submissions."}), 409
        await _bot_write(db, qq_id)
        await db.execute(
            "UPDATE random_challenges SET status='completed',completed_at=? WHERE id=? AND status='active'",
            (now, challenge["id"]),
        )
        await db.commit()
        return jsonify({"success": True, "challenge": challenge})
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/random-challenges/giveup")
@service_required
async def abandon_random_challenges(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        cursor = await db.execute(
            "UPDATE random_challenges SET status='abandoned' WHERE qq_id=? AND status='active'",
            (qq_id,),
        )
        await db.commit()
        return jsonify({"success": True, "changed": cursor.rowcount})
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/training")
@service_required
async def create_bot_training(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    if not qq_id or not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid QQ number or JSON body."}), 400
    platform = normalize_platform(data.get("platform", ""))
    difficulty = str(data.get("difficulty", "")).strip()
    tags = data.get("tags", [])
    if platform not in {"codeforces", "luogu", "atcoder"} or not isinstance(tags, list) or len(tags) > 5:
        return jsonify({"success": False, "message": "Unsupported platform or invalid tags."}), 400
    tags = [str(tag).strip()[:40] for tag in tags if str(tag).strip()]
    try:
        zones = neighboring_difficulties(platform, difficulty)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        now = int(time.time())
        await db.execute(
            "UPDATE random_challenges SET status='expired' WHERE qq_id=? AND status='active' AND expires_at<?",
            (qq_id, now),
        )
        async with db.execute(
            "SELECT 1 FROM random_challenges WHERE qq_id=? AND status='active' LIMIT 1",
            (qq_id,),
        ) as cursor:
            if await cursor.fetchone():
                await db.rollback()
                return jsonify({"success": False, "message": "An active training already exists."}), 409
        group_id = __import__("uuid").uuid4().hex
        selected = set()
        chosen = []
        for zone, zone_difficulty in zip(("foundation", "core", "challenge"), zones):
            condition, condition_params, _label = challenge_filter(platform, zone_difficulty, "p.problem_rating")
            sql = (
                "SELECT p.platform,p.problem_id,p.problem_name,p.problem_rating,p.problem_url,p.tags "
                "FROM (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations "
                "UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM submissions) p "
                "WHERE p.platform=? AND p.problem_url IS NOT NULL AND TRIM(p.problem_url)<>'' "
                "AND NOT EXISTS(SELECT 1 FROM submissions mine WHERE mine.user_qq_id=? AND mine.platform=p.platform AND mine.problem_id=p.problem_id)"
            )
            params = [platform, qq_id]
            if condition:
                sql += " AND " + condition
                params.extend(condition_params)
            if tags:
                sql += " AND (" + " OR ".join(
                    ["COALESCE(p.problem_name,'') LIKE ? OR COALESCE(p.problem_id,'') LIKE ? OR COALESCE(p.tags,'') LIKE ?"] * len(tags)
                ) + ")"
                for tag in tags:
                    params.extend([f"%{tag}%"] * 3)
            sql += " ORDER BY RANDOM() LIMIT 30"
            async with db.execute(sql, tuple(params)) as cursor:
                candidates = [dict(row) for row in await cursor.fetchall()]
            candidates = [row for row in candidates if row["problem_id"] not in selected]
            candidates.sort(
                key=lambda row: score_candidate(row, zone_difficulty, tags)["score"],
                reverse=True,
            )
            problem = candidates[0] if candidates else None
            if problem:
                selected.add(problem["problem_id"])
            chosen.append((zone, zone_difficulty, problem))
        if not any(problem for _zone, _difficulty, problem in chosen):
            await db.rollback()
            return jsonify({"success": False, "message": "No suitable training problems were found."}), 404
        result = []
        for zone, requested, problem in chosen:
            if not problem:
                continue
            await db.execute(
                "INSERT INTO random_challenges(qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,challenge_rating,time_limit_minutes,status,created_at,expires_at,challenge_group_id,zone,requested_difficulty,requested_tags) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (qq_id, platform, problem["problem_id"], problem["problem_name"],
                 problem["problem_rating"] or "", problem["problem_url"], "|".join(tags),
                 str(requested), challenge_time_limit(platform, requested), "active", now,
                 now + 7 * 86400, group_id, zone, difficulty, "|".join(tags)),
            )
            score = score_candidate(problem, requested, tags)
            result.append({**problem, "zone": zone, "requested_difficulty": str(requested),
                           "challenge_group_id": group_id, "time_limit_minutes": challenge_time_limit(platform, requested),
                           "recommendation_score": score["score"], "recommendation_reason": score["reason"]})
        await db.commit()
        return jsonify({"success": True, "group_id": group_id, "items": result}), 201
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/training")
@service_required
async def list_bot_training(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        now = int(time.time())
        await db.execute(
            "UPDATE random_challenges SET status='expired' WHERE qq_id=? AND status='active' AND expires_at<?",
            (qq_id, now),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM random_challenges WHERE qq_id=? AND status='active' ORDER BY id DESC",
            (qq_id,),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.post("/users/<qq_id>/training/<zone>/complete")
@service_required
async def complete_bot_training(qq_id, zone):
    qq_id = _qq(qq_id)
    zone = str(zone).strip().lower()
    if not qq_id or zone not in {"foundation", "core", "challenge"}:
        return jsonify({"success": False, "message": "Invalid user or training zone."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT * FROM random_challenges WHERE qq_id=? AND zone=? AND status='active' ORDER BY id DESC LIMIT 1",
            (qq_id, zone),
        ) as cursor:
            challenge = await cursor.fetchone()
        if not challenge:
            return jsonify({"success": False, "message": "No active training for this zone."}), 404
        challenge = dict(challenge)
        now = int(time.time())
        if now > int(challenge["expires_at"]):
            await _bot_write(db, qq_id)
            await db.execute("UPDATE random_challenges SET status='expired' WHERE id=?", (challenge["id"],))
            await db.commit()
            return jsonify({"success": False, "message": "Training expired."}), 410
        prefix = {"codeforces": "cf_", "atcoder": "atc_", "nowcoder": "nc_"}.get(challenge["platform"], "")
        problem_id = str(challenge["problem_id"])
        candidates = {problem_id, problem_id[len(prefix):] if prefix and problem_id.startswith(prefix) else prefix + problem_id if prefix else problem_id}
        placeholders = ",".join("?" for _ in candidates)
        query = f"SELECT 1 FROM submissions WHERE user_qq_id=? AND platform=? AND problem_id IN ({placeholders}) AND submit_time>=? LIMIT 1"
        params = (qq_id, challenge["platform"], *candidates, challenge["created_at"])
        async with db.execute(query, params) as cursor:
            solved = await cursor.fetchone()
        if not solved:
            engine = getattr(current_app, "sync_engine", None)
            if engine:
                await engine.sync_single_platform_for_days(qq_id, challenge["platform"], 1)
            async with db.execute(query, params) as cursor:
                solved = await cursor.fetchone()
        if not solved:
            return jsonify({"success": False, "message": "Training problem is not accepted yet."}), 409
        await _bot_write(db, qq_id)
        await db.execute(
            "UPDATE random_challenges SET status='completed',completed_at=? WHERE id=? AND status='active'",
            (now, challenge["id"]),
        )
        await db.commit()
        return jsonify({"success": True, "challenge": challenge})
    finally:
        await db.close()


@bot_api.delete("/users/<qq_id>/training")
@service_required
async def cancel_bot_training(qq_id):
    qq_id = _qq(qq_id)
    zone = str(request.args.get("zone", "")).strip().lower()
    if not qq_id or (zone and zone not in {"foundation", "core", "challenge"}):
        return jsonify({"success": False, "message": "Invalid user or training zone."}), 400
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=False)
        sql = "UPDATE random_challenges SET status='abandoned' WHERE qq_id=? AND status='active'"
        params = [qq_id]
        if zone:
            sql += " AND zone=?"
            params.append(zone)
        cursor = await db.execute(sql, tuple(params))
        await db.commit()
        return jsonify({"success": True, "changed": cursor.rowcount})
    finally:
        await db.close()


@bot_api.post("/accounts/validate")
@service_required
async def validate_oj_account():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid JSON body."}), 400
    platform = str(data.get("platform") or "").strip().lower()
    account = str(data.get("account") or "").strip()
    engine = getattr(current_app, "sync_engine", None)
    if not engine or not engine._http_session:
        return jsonify({"success": False, "message": "Account validation is unavailable."}), 503
    from .crawler import Crawler
    ok, result = await Crawler.validate_account(
        engine._http_session, platform, account, engine._crawler_config()
    )
    if not ok:
        return jsonify({"success": False, "message": str(result)}), 400
    return jsonify({"success": True, "account": result})


@bot_api.post("/accounts/verify")
@service_required
async def verify_oj_account():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid JSON body."}), 400
    platform = str(data.get("platform") or "").strip().lower()
    account = str(data.get("account") or "").strip()
    code = str(data.get("verification_code") or "").strip()
    engine = getattr(current_app, "sync_engine", None)
    if not engine or not engine._http_session:
        return jsonify({"success": False, "message": "Account verification is unavailable."}), 503
    from .crawler import Crawler
    ok, reason = await Crawler.verify_account_ownership(
        engine._http_session, platform, account, code, engine._crawler_config()
    )
    if not ok:
        return jsonify({"success": False, "message": str(reason)}), 400
    return jsonify({"success": True})


@bot_api.get("/codeforces/user-rating")
@service_required
async def codeforces_user_rating():
    handle = str(request.args.get("handle", "")).strip()[:100]
    if not handle:
        return jsonify({"success": False, "message": "A handle and active API service are required."}), 400
    try:
        return jsonify({"status": "OK", "result": await _codeforces_api_call("user.rating", {"handle": handle})})
    except Exception as exc:
        return jsonify({"status": "FAILED", "comment": str(exc)[:300]}), 502


@bot_api.get("/codeforces/profile")
@service_required
async def codeforces_profile():
    handle = str(request.args.get("handle", "")).strip()[:100]
    if not handle:
        return jsonify({"success": False, "message": "A Codeforces handle is required."}), 400
    try:
        users = await _codeforces_api_call("user.info", {"handles": handle})
        if not users:
            return jsonify({"success": False, "message": "Codeforces user not found."}), 404
        canonical = users[0].get("handle") or handle
        rating = await _codeforces_api_call("user.rating", {"handle": canonical})
        submissions = await _codeforces_api_call(
            "user.status", {"handle": canonical, "from": 1, "count": 10000}
        )
        return jsonify({"user": users[0], "rating_history": rating, "submissions": submissions})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)[:300]}), 502


@bot_api.get("/codeforces/upcoming-contests")
@service_required
async def codeforces_upcoming_contests():
    try:
        contests = await _codeforces_api_call("contest.list", {"gym": "false"})
        result = [contest for contest in contests if contest.get("phase") == "BEFORE"
                  and "Kotlin" not in contest.get("name", "")
                  and "Unrated" not in contest.get("name", "")]
        result.reverse()
        return jsonify(result)
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)[:300]}), 502


@bot_api.put("/users/<qq_id>")
@service_required
async def upsert_user(qq_id):
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True)
    if not qq_id or not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid QQ number or JSON body."}), 400
    fields = (
        "name", "real_name", "cf_handle", "luogu_id", "nowcoder_id",
        "atcoder_handle", "cjlu_username", "status", "school",
    )
    values = {key: str(data.get(key) or "").strip() or None for key in fields}
    values["name"] = values["name"] or values["cf_handle"] or qq_id
    db = await _db()
    try:
        await _bot_write(db, qq_id, allow_missing=True)
        await db.execute(
            "INSERT INTO users(qq_id,name,real_name,cf_handle,luogu_id,nowcoder_id,"
            "atcoder_handle,cjlu_username,status,school) VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(qq_id) DO UPDATE SET name=excluded.name,real_name=excluded.real_name,"
            "cf_handle=excluded.cf_handle,luogu_id=excluded.luogu_id,"
            "nowcoder_id=excluded.nowcoder_id,atcoder_handle=excluded.atcoder_handle,"
            "cjlu_username=excluded.cjlu_username,status=excluded.status,school=excluded.school",
            (qq_id,) + tuple(values[key] for key in fields),
        )
        await db.commit()
        return jsonify({"success": True, "qq_id": qq_id})
    except aiosqlite.IntegrityError as exc:
        await db.rollback()
        if "duplicate account binding" in str(exc):
            return jsonify({"success": False, "message": "That OJ account is already bound."}), 409
        raise
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/submissions")
@service_required
async def get_user_submissions(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    platform = str(request.args.get("platform", "")).strip().lower()
    try:
        limit = max(1, min(2000, int(request.args.get("limit", 500))))
        since = max(0, int(request.args.get("since", 0)))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit and since must be integers."}), 400
    sql = (
        "SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time "
        "FROM submissions WHERE user_qq_id=? AND submit_time>=?"
    )
    params = [qq_id, since]
    if platform:
        sql += " AND platform=?"
        params.append(platform)
    sql += " ORDER BY submit_time DESC,id DESC LIMIT ?"
    params.append(limit)
    db = await _db()
    try:
        async with db.execute(sql, tuple(params)) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.post("/submissions/batch")
@service_required
async def add_submissions():
    data = await request.get_json(silent=True)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > 2000:
        return jsonify({"success": False, "message": "items must be a list of at most 2000 records."}), 400
    rows = []
    for item in items:
        if not isinstance(item, dict):
            return jsonify({"success": False, "message": "Every item must be an object."}), 400
        qq_id = _qq(item.get("qq_id"))
        platform = str(item.get("platform") or "").strip().lower()
        problem_id = str(item.get("problem_id") or "").strip()
        try:
            submit_time = int(item.get("submit_time") or 0)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "submit_time must be an integer."}), 400
        if not qq_id or not platform or not problem_id or submit_time <= 0:
            return jsonify({"success": False, "message": "Each item requires qq_id, platform, problem_id and positive submit_time."}), 400
        rows.append((
            qq_id, platform, problem_id,
            str(item.get("problem_name") or "")[:300] or None,
            str(item.get("problem_rating") or "")[:40] or None,
            str(item.get("problem_url") or "")[:1000] or None,
            str(item.get("tags") or "")[:2000],
            submit_time,
        ))
    if not rows:
        return jsonify({"success": True, "inserted": 0})
    db = await _db()
    try:
        qq_ids = sorted({row[0] for row in rows})
        placeholders = ",".join("?" for _ in qq_ids)
        async with db.execute(
            f"SELECT qq_id FROM users WHERE qq_id IN ({placeholders})", tuple(qq_ids)
        ) as cursor:
            found = {row["qq_id"] for row in await cursor.fetchall()}
        missing = sorted(set(qq_ids) - found)
        if missing:
            return jsonify({"success": False, "message": "Unknown users.", "qq_ids": missing}), 404
        await db.execute("BEGIN IMMEDIATE")
        for qq_id in qq_ids:
            await require_active_user(db, qq_id)
        before = db.total_changes
        await db.executemany(
            "INSERT OR IGNORE INTO submissions"
            "(user_qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time) "
            "VALUES(?,?,?,?,?,?,?,?)",
            rows,
        )
        inserted = db.total_changes - before
        await db.commit()
        return jsonify({"success": True, "inserted": inserted})
    finally:
        await db.close()


@bot_api.get("/leaderboard")
@service_required
async def bot_leaderboard():
    db = await _db()
    try:
        days, page, page_size, sort_key, search, platforms = _leaderboard_options(request.args)
        rows, total = await _fetch_leaderboard(
            db, days, page, page_size, sort_key, search, platforms
        )
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
    finally:
        await db.close()


@bot_api.get("/rank")
@service_required
async def bot_rank_data():
    """Compatibility aggregate for the QQ bot's leaderboard image commands."""
    raw_days = str(request.args.get("days", "all")).strip().lower()
    try:
        days = None if raw_days in {"all", "0", ""} else max(1, min(3650, int(raw_days)))
        raw_limit = str(request.args.get("limit", "")).strip()
        limit = max(1, min(2000, int(raw_limit))) if raw_limit else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "days and limit must be integers."}), 400
    status = str(request.args.get("status", "")).strip()[:80]
    include_cjlu = str(request.args.get("include_cjlu", "false")).lower() in {"1", "true", "yes"}
    params = []
    join_condition = "u.qq_id=s.user_qq_id" if include_cjlu else "u.qq_id=s.user_qq_id AND s.platform<>'cjlu'"
    sql = (
        "SELECT COALESCE(NULLIF(u.cf_handle,''),u.name,u.qq_id) AS user_name, "
        "u.status AS user_status, COUNT(s.id) AS total_count, "
        "COUNT(CASE WHEN s.platform='codeforces' THEN 1 END) AS cf_count, "
        "COUNT(CASE WHEN s.platform='luogu' THEN 1 END) AS luogu_count, "
        "COUNT(CASE WHEN s.platform='nowcoder' THEN 1 END) AS nowcoder_count, "
        "COUNT(CASE WHEN s.platform='atcoder' THEN 1 END) AS atcoder_count"
        + (", COUNT(CASE WHEN s.platform='cjlu' THEN 1 END) AS cjlu_count" if include_cjlu else "")
        + f" FROM users u LEFT JOIN submissions s ON {join_condition}"
    )
    filters = []
    if days is not None:
        filters.append("s.submit_time>=?")
        params.append(int(time.time()) - days * 86400)
    if status:
        filters.append("u.status=?")
        params.append(status)
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " GROUP BY u.qq_id HAVING total_count>0 ORDER BY total_count DESC,user_name ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    db = await _db()
    try:
        async with db.execute(sql, tuple(params)) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.get("/reports/recent-solves")
@service_required
async def recent_solves_report():
    try:
        hours = max(1, min(720, int(request.args.get("hours", 1))))
        limit = max(1, min(100, int(request.args.get("limit", 10))))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "hours and limit must be integers."}), 400
    db = await _db()
    try:
        async with db.execute(
            "SELECT s.problem_name,s.platform,s.problem_rating,s.problem_url,s.submit_time,u.name AS user_name "
            "FROM submissions s JOIN users u ON s.user_qq_id=u.qq_id "
            "WHERE s.submit_time>=? ORDER BY s.submit_time DESC LIMIT ?",
            (int(time.time()) - hours * 3600, limit),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.get("/recommendations")
@service_required
async def list_recommendations():
    platform = str(request.args.get("platform", "")).strip().lower()
    db = await _db()
    try:
        sql = (
            "SELECT id,platform,problem_id,problem_name,problem_rating,problem_url,tags "
            "FROM recommendations"
        )
        params = ()
        if platform:
            sql += " WHERE platform=?"
            params = (platform,)
        sql += " ORDER BY platform,problem_id"
        async with db.execute(sql, params) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@bot_api.post("/recommendations")
@service_required
async def add_recommendation():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid JSON body."}), 400
    platform = str(data.get("platform") or "").strip().lower()
    problem_id = str(data.get("problem_id") or "").strip()
    problem_url = str(data.get("problem_url") or "").strip()
    if not platform or not problem_id or not problem_url:
        return jsonify({"success": False, "message": "platform, problem_id and problem_url are required."}), 400
    db = await _db()
    try:
        await db.execute(
            "INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(platform,problem_id) DO UPDATE SET "
            "problem_name=excluded.problem_name,problem_rating=excluded.problem_rating,"
            "problem_url=excluded.problem_url,tags=excluded.tags",
            (
                platform, problem_id,
                str(data.get("problem_name") or "")[:300] or None,
                str(data.get("problem_rating") or "")[:40] or None,
                problem_url[:1000], str(data.get("tags") or "")[:2000],
            ),
        )
        await db.commit()
        return jsonify({"success": True}), 201
    finally:
        await db.close()


@bot_api.delete("/recommendations/<platform>/<problem_id>")
@service_required
async def delete_recommendation(platform, problem_id):
    db = await _db()
    try:
        cursor = await db.execute(
            "DELETE FROM recommendations WHERE platform=? AND problem_id=?",
            (platform.strip().lower(), problem_id.strip()),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": "Recommendation not found."}), 404
        return jsonify({"success": True})
    finally:
        await db.close()


@bot_api.get("/users/<qq_id>/recommendations")
@service_required
async def recommendations_for_user(qq_id):
    qq_id = _qq(qq_id)
    if not qq_id:
        return jsonify({"success": False, "message": "Invalid QQ number."}), 400
    platform = str(request.args.get("platform", "")).strip().lower()
    db = await _db()
    try:
        async with db.execute("SELECT challenge_rating FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            user = await cursor.fetchone()
        rating = int(user["challenge_rating"] or 1000) if user else 1000
        sql = (
            "WITH pool AS (SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations "
            "WHERE platform<>'cjlu' UNION SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags "
            "FROM submissions WHERE platform<>'cjlu') SELECT r.* FROM pool r WHERE NOT EXISTS "
            "(SELECT 1 FROM submissions s WHERE s.user_qq_id=? AND s.platform=r.platform AND s.problem_id=r.problem_id)"
        )
        params = [qq_id]
        if platform:
            sql += " AND r.platform=?"
            params.append(platform)
        sql += " ORDER BY r.platform,r.problem_id LIMIT 500"
        async with db.execute(sql, tuple(params)) as cursor:
            items = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"rating": rating, "items": items})
    finally:
        await db.close()


@bot_api.get("/settings")
@service_required
async def get_settings():
    allowed = {
        "report_enabled", "report_cron_hour", "report_cron_minute",
        "hourly_report_limit", "contest_report_time", "notification_group_id",
    }
    db = await _db()
    try:
        async with db.execute("SELECT key,value FROM settings") as cursor:
            return jsonify({
                row["key"]: row["value"]
                for row in await cursor.fetchall()
                if row["key"] in allowed
            })
    finally:
        await db.close()


@bot_api.post("/sync/accounts/<qq_id>")
@service_required
async def submit_account_sync(qq_id):
    """Queue an account sync on the API service so the bot never opens SQLite."""
    qq_id = _qq(qq_id)
    data = await request.get_json(silent=True) or {}
    platforms = data.get("platforms", [])
    try:
        days = max(0, min(3650, int(data.get("days", 0))))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "days must be an integer."}), 400
    if not qq_id or not isinstance(platforms, list):
        return jsonify({"success": False, "message": "Invalid QQ number or platforms."}), 400
    submit = current_app.config.get("PLUGIN_CONFIG", {}).get("_account_sync_submitter")
    if not submit:
        return jsonify({"success": False, "message": "Account sync is unavailable."}), 503
    result = submit(qq_id, platforms, days=days)
    if inspect.isawaitable(result):
        result = await result
    if not result:
        return jsonify({"success": False, "message": "No supported platforms were selected."}), 400
    return jsonify({"success": True, **result}), 202


@bot_api.post("/sync/accounts")
@service_required
async def submit_all_account_sync():
    submit = current_app.config.get("PLUGIN_CONFIG", {}).get("_all_account_sync_submitter")
    if not submit:
        return jsonify({"success": False, "message": "Account sync is unavailable."}), 503
    data = await request.get_json(silent=True) or {}
    try:
        days = max(0, min(3650, int(data.get("days", 0))))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "days must be an integer."}), 400
    result = submit(days=days)
    if inspect.isawaitable(result):
        result = await result
    if not result:
        return jsonify({"success": False, "message": "An account sync is already running."}), 409
    return jsonify({"success": True, **result}), 202


@bot_api.get("/sync/tasks")
@service_required
async def list_sync_tasks():
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_provider")
    if not provider:
        return jsonify({"success": False, "message": "Sync task status is unavailable."}), 503
    tasks = provider()
    if inspect.isawaitable(tasks):
        tasks = await tasks
    return jsonify({"tasks": tasks})


@bot_api.post("/sync/tasks/<task_id>/cancel")
@service_required
async def cancel_sync_task(task_id):
    cancel = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_canceller")
    if not cancel:
        return jsonify({"success": False, "message": "Sync task cancellation is unavailable."}), 503
    if not cancel(task_id):
        return jsonify({"success": False, "message": "Task not found or already finished."}), 404
    return jsonify({"success": True})


@bot_api.put("/settings/<key>")
@service_required
async def put_setting(key):
    allowed = {
        "report_enabled", "report_cron_hour", "report_cron_minute",
        "hourly_report_limit", "contest_report_time", "notification_group_id",
    }
    if key not in allowed:
        return jsonify({"success": False, "message": "Unsupported setting."}), 400
    data = await request.get_json(silent=True)
    if not isinstance(data, dict) or "value" not in data:
        return jsonify({"success": False, "message": "value is required."}), 400
    value = str(data["value"])[:500]
    if key == "contest_report_time":
        from .reporting import valid_contest_report_time
        if value and not valid_contest_report_time(value):
            return jsonify({"success": False, "message": "time must use HH:MM format."}), 400
    db = await _db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value)
        )
        await db.commit()
        return jsonify({"success": True, "key": key, "value": value})
    finally:
        await db.close()
