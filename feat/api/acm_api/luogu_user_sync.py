"""Luogu public AC snapshots; unknown acceptance time is stored as zero, never now."""
import re

from .luogu_client import ORIGIN, luogu_get, page_context
from .luogu_problem import classifications, load_taxonomy

MAX_PASSED_PROBLEMS = 100000


def uid(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("洛谷 UID 必须是正整数，请由管理员在成员资料中填写")
    return value


def canonical_pid(value):
    if not isinstance(value, str):
        raise ValueError("洛谷已通过题目缺少有效题号")
    value = value.strip()
    if value.lower().startswith("luogu_"):
        value = value[6:]
    if re.fullmatch(r"(?:P|B|T|U|SP)[1-9][0-9]{0,12}|CF[1-9][0-9]{0,9}[A-Z][0-9]{0,2}", value, re.I):
        return value.upper()
    if re.fullmatch(r"AT_[A-Za-z0-9_]{1,100}", value, re.I):
        return "AT_" + value[3:]
    raise ValueError("洛谷已通过题号格式异常")


def practice_snapshot(raw, expected_uid):
    """Require an explicit public passed list and matching owner before any writes."""
    context = page_context(raw)
    if context.get("status") != 200:
        raise ValueError("洛谷练习页状态异常，保留已有记录")
    data = context["data"]
    user = data.get("user")
    if not isinstance(user, dict) or uid(user.get("uid")) != uid(expected_uid):
        raise ValueError("洛谷练习页账号不匹配，保留已有记录")
    passed = data.get("passed", data.get("passedProblems"))
    if not isinstance(passed, list) or len(passed) > MAX_PASSED_PROBLEMS:
        raise ValueError("洛谷练习页缺少完整的已通过题目列表，保留已有记录")
    result = {}
    for item in passed:
        if isinstance(item, str):
            item = {"pid": item}
        if not isinstance(item, dict):
            raise ValueError("洛谷已通过列表格式异常，保留已有记录")
        pid = canonical_pid(item.get("pid"))
        title = item.get("name", item.get("title"))
        if title is not None and (not isinstance(title, str) or len(title) > 1000):
            raise ValueError("洛谷已通过题目名称格式异常")
        difficulty = item.get("difficulty")
        if difficulty is not None and (type(difficulty) is not int or not 0 <= difficulty <= 100):
            raise ValueError("洛谷已通过题目难度格式异常")
        # Practice pages prove AC membership, not the time of acceptance.
        result.setdefault(pid.casefold(), {"pid": pid, "name": (title or "").strip(), "difficulty": difficulty})
    return list(result.values())


async def sync_public_practice(session, user, db, config):
    from .binding_guard import BindingGuard

    account = uid(user["luogu_id"])
    raw = await luogu_get(
        session, ORIGIN + "/user/" + account + "/practice",
        interval=config.get("luogu_request_interval", 2.0),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        timeout=30,
    )
    passed = practice_snapshot(raw, account)
    taxonomy = await load_taxonomy(db)
    async with db.execute("SELECT problem_id FROM submissions WHERE user_qq_id=? AND platform='luogu'", (user["qq_id"],)) as cursor:
        existing = set()
        for row in await cursor.fetchall():
            try:
                existing.add(canonical_pid(row["problem_id"]).casefold())
            except ValueError:
                continue  # Preserve unknown historical IDs without interpreting them.
    catalog = {}
    missing = [item for item in passed if item["pid"].casefold() not in existing]
    for start in range(0, len(missing), 400):
        ids = [item["pid"] for item in missing[start:start + 400]]
        placeholders = ",".join("?" for _ in ids)
        async with db.execute("SELECT problem_id,problem_name,problem_rating,problem_url,tags FROM crawler_problems WHERE platform='luogu' AND problem_id IN (" + placeholders + ")", ids) as cursor:
            catalog.update({row["problem_id"].casefold(): dict(row) for row in await cursor.fetchall()})
    values = []
    for item in missing:
        pid = item["pid"]
        local = catalog.get(pid.casefold(), {})
        level, _ = classifications({"difficulty": item["difficulty"]}, taxonomy)
        values.append((str(user["qq_id"]), "luogu", pid, local.get("problem_name") or item["name"] or pid,
                       local.get("problem_rating") or level.get("name"), ORIGIN + "/problem/" + pid,
                       local.get("tags") or "", 0))
    writer = db if isinstance(db, BindingGuard) else BindingGuard(db, user, "luogu")
    # Even an empty snapshot must pass the captured binding/account generation fence.
    try:
        cursor = await writer.executemany(
            "INSERT OR IGNORE INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time) VALUES(?,?,?,?,?,?,?,?)",
            values,
        )
        added = max(0, cursor.rowcount)
        await writer.commit()
        return added
    except BaseException:
        await writer.rollback()
        raise
