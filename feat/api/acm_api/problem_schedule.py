"""Persistent per-OJ problem-bank scheduling, independent of member AC jobs."""
import json
from datetime import datetime, timedelta, timezone

PLATFORMS = ("atcoder", "codeforces", "luogu")
TIMEZONE = timezone(timedelta(hours=8))
HOUR = 4
PREFIX = "problem_sync_enabled_"


def default_enabled(platform, config):
    return platform != "luogu" or bool(config.get("luogu_daily_problem_sync_enabled", False))


async def enabled(db, platform, config):
    async with db.execute("SELECT value FROM settings WHERE key=?", (PREFIX + platform,)) as cursor:
        row = await cursor.fetchone()
    return row[0] == "true" if row is not None else default_enabled(platform, config)


async def snapshot(db, config, now=None):
    now = now or datetime.now(TIMEZONE)
    today = now.date().isoformat()
    due = now.replace(hour=HOUR, minute=0, second=0, microsecond=0)
    master = config.get("daily_problem_sync_enabled", True)
    rows = []
    for platform in PLATFORMS:
        preference = await enabled(db, platform, config)
        async with db.execute("SELECT key,value FROM settings WHERE key IN (?,?)", (
                "daily_problem_sync_" + platform, "daily_problem_sync_result_" + platform)) as cursor:
            state = dict(await cursor.fetchall())
        claimed = state.get("daily_problem_sync_" + platform)
        try:
            last = json.loads(state.get("daily_problem_sync_result_" + platform, "null"))
        except (ValueError, TypeError):
            last = None
        next_due = due + timedelta(days=1) if claimed and claimed >= today else max(due, now)
        rows.append({"platform": platform, "enabled": preference,
                     "effective_enabled": bool(master and preference), "last_scheduled_day": claimed,
                     "last_result": last, "next_run_at": int(next_due.timestamp()) if master and preference else None})
    return {"global_enabled": bool(master), "timezone": "Asia/Shanghai", "hour": HOUR, "platforms": rows}


async def update(db, data):
    if not isinstance(data, dict) or set(data) != {"platforms"}:
        raise ValueError("请求须仅包含 platforms 对象")
    values = data["platforms"]
    if not isinstance(values, dict) or not values or set(values) - set(PLATFORMS) or any(type(value) is not bool for value in values.values()):
        raise ValueError("platforms 须包含有效 OJ 名称及布尔开关")
    await db.execute("BEGIN IMMEDIATE")
    try:
        for platform, value in values.items():
            await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (PREFIX + platform, "true" if value else "false"))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def claim(db, platform, day, config):
    # Serialize checking the saved switch with claiming a day; disabled OJs do
    # not consume their day, so enabling one after 04:00 can still run today.
    await db.execute("BEGIN IMMEDIATE")
    try:
        if not config.get("daily_problem_sync_enabled", True) or not await enabled(db, platform, config):
            await db.rollback()
            return False
        async with db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE "
                              "SET value=excluded.value WHERE settings.value<excluded.value",
                              ("daily_problem_sync_" + platform, day)) as cursor:
            claimed = cursor.rowcount == 1
        await db.commit()
        return claimed
    except BaseException:
        await db.rollback()
        raise


async def remember_result(db, task):
    result = task.get("result") or {}
    summary = {"id": task["id"], "status": task["status"], "finished_at": task.get("finished_at"),
               **{key: result[key] for key in ("success_count", "failure_count", "remaining_count", "error") if key in result}}
    await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     ("daily_problem_sync_result_" + task["platform"], json.dumps(summary, ensure_ascii=False)))
    await db.commit()
