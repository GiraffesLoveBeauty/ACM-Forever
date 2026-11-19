"""匿名读取洛谷公开练习页的历史 AC；未知通过时间存 0，不冒用同步时间。"""
import re
import time

from .luogu_client import ORIGIN, LuoguResponseError, luogu_get, page_context, response_failed, response_recovered
from .luogu_problem import canonical_problem_id as canonical_pid, classifications, load_taxonomy

MAX_PASSED_PROBLEMS = 100000


def uid(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("洛谷 UID 必须是正整数，请由管理员在成员资料中填写")
    return value


def practice_snapshot(raw, expected_uid):
    """写库前校验页面状态、账号归属及完整的已通过列表，失败时保留原有 AC。"""
    context = page_context(raw)
    if context.get("status") != 200:
        raise ValueError(f"洛谷练习页内嵌状态异常（context.status={context.get('status')!r}），保留已有记录")
    data = context["data"]
    user = data.get("user")
    if not isinstance(user, dict) or uid(user.get("uid")) != uid(expected_uid):
        raise ValueError("洛谷练习页账号不匹配，保留已有记录")
    # 只读取 passed / passedProblems（已通过）；提交过 submitted 不等于 AC。
    passed = data.get("passed", data.get("passedProblems"))
    if not isinstance(passed, list) or len(passed) > MAX_PASSED_PROBLEMS:
        raise ValueError("洛谷练习页缺少完整的已通过题目列表，保留已有记录")
    result = {}
    for item in passed:
        if isinstance(item, str):
            item = {"pid": item}
        if not isinstance(item, dict):
            raise ValueError("洛谷已通过列表格式异常，保留已有记录")
        value = item.get("pid")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("洛谷已通过题目缺少有效题号")
        value = value.strip()
        if value[:6].casefold() == "luogu_":
            value = value[6:]
        if not value:
            raise ValueError("洛谷已通过题目缺少有效题号")
        if not value.upper().startswith("P"):
            continue  # 与当前洛谷题库保持一致，只处理公开 P 题；不映射其他 OJ 的镜像题。
        pid = canonical_pid(value)
        title = item.get("name", item.get("title"))
        if title is not None and (not isinstance(title, str) or len(title) > 1000):
            raise ValueError("洛谷已通过题目名称格式异常")
        difficulty = item.get("difficulty")
        if difficulty is not None and (type(difficulty) is not int or not 0 <= difficulty <= 100):
            raise ValueError("洛谷已通过题目难度格式异常")
        # 练习页能证明历史 AC，但没有 AC 时间；这里只收集题号、标题和原生难度。
        result.setdefault(pid.casefold(), {"pid": pid, "name": (title or "").strip(), "difficulty": difficulty})
    return list(result.values())


async def sync_public_practice(session, user, db, config):
    from .binding_guard import BindingGuard

    account = uid(user["luogu_id"])
    requested_at = time.time()
    # 该 URL 无需登录；不传登录 Cookie/CSRF，不请求每道题的题面或全站成员数据。
    # 如原站设置匿名会话 Cookie，由现有 session 保存，仅用于正常的匿名页面初始化。
    raw = await luogu_get(
        session, ORIGIN + "/user/" + account + "/practice",
        interval=config.get("luogu_request_interval", 2.0),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        timeout=30, recover_on_response=False,
    )
    try:
        passed = practice_snapshot(raw, account)
    except ValueError as error:
        # HTTP 200 只代表拿到响应；解析失败仍需明确标记，不能误当作“没有 AC”。
        raise response_failed(LuoguResponseError(f"洛谷同步失败：{error}（HTTP 200）", status=200)) from error
    # 从请求返回到完整校验没有 await；确认是当前 UID 的完整快照后才解除共享门禁。
    response_recovered()
    observed_at = int(time.time())
    taxonomy = await load_taxonomy(db)
    # 只查当前成员的洛谷 AC，并按题号去重；元数据优先复用本地题库。
    async with db.execute("SELECT problem_id FROM submissions WHERE user_qq_id=? AND platform='luogu'", (user["qq_id"],)) as cursor:
        existing = set()
        for row in await cursor.fetchall():
            try:
                existing.add(canonical_pid(row["problem_id"]).casefold())
            except ValueError:
                continue  # Preserve unknown historical IDs without interpreting them.
    catalog = {}
    missing = [item for item in passed if item["pid"].casefold() not in existing]
    # 批量读取新增题号的本地元数据，避免每题一次 SQL 或额外原站请求。
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
    # 即使快照为空，也必须校验绑定版本和账号代际，防止改绑/注销后的旧响应串号。
    # AC 写入与训练进度更新使用同一事务；任一步失败都回滚，保留原有记录。
    try:
        cursor = await writer.executemany(
            "INSERT OR IGNORE INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time) VALUES(?,?,?,?,?,?,?,?)",
            values,
        )
        added = max(0, cursor.rowcount)
        from .training_task_progress import record_luogu_snapshot
        # 新增 0 条也要更新训练任务；洛谷按历史 AC 判定，不要求周期内重新通过。
        await record_luogu_snapshot(writer, user, {item["pid"].casefold() for item in passed}, existing,
                                    requested_at=requested_at, observed_at=observed_at)
        await writer.commit()
        return added
    except BaseException:
        await writer.rollback()
        raise
