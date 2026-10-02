"""Authenticated service-to-service API for the NCatBot adapter."""
import hmac
import time
from functools import wraps

import aiosqlite
from quart import Blueprint, current_app, jsonify, request

from .backend_api import _fetch_leaderboard, _leaderboard_options

bot_api = Blueprint("bot_api", __name__)


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
            "FROM users ORDER BY qq_id LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        return jsonify(rows)
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
