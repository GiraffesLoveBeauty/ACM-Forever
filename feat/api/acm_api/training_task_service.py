"""Transactional assigned training tasks; deliberately separate from random challenges."""
import hashlib
import json
import re
import secrets
import time
from datetime import datetime

from .account_lifecycle_service import web_account_available
from .binding_service import LABELS, platform_spec
from .cf_client import problem_url
from .cf_practice import PracticeError, normalize_problem

MAX_PROBLEMS = 50
PREVIEW_TTL = 600
CAPABILITIES = [
    {"platform": platform, "label": label, "period_ac": platform == "codeforces", "historical_ac": platform == "codeforces",
     "reason": "实际提交时间、重复 AC 与完整历史覆盖" if platform == "codeforces" else "尚未验证完整提交证据，首期不能发布"}
    for platform, label in LABELS.items()
]


class TaskError(Exception):
    def __init__(self, message, code="invalid_request", status=400, **details):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


async def rows(db, sql, values=()):
    async with db.execute(sql, values) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def one(db, sql, values=()):
    result = await rows(db, sql, values)
    return result[0] if result else None


def paging(args):
    try:
        page, size = int(args.get("page", 1)), int(args.get("page_size", 20))
        if page < 1 or size < 1:
            raise ValueError
        return page, min(size, 100)
    except (TypeError, ValueError):
        raise TaskError("分页参数须为正整数。") from None


def timestamp(value):
    if value is None or value == "":
        return None
    if type(value) is int and 0 < value < 4102444800:
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            result = int(parsed.timestamp())
            if parsed.tzinfo and 0 < result < 4102444800:
                return result
        except (ValueError, OverflowError):
            pass
    raise TaskError("时间须为 UTC 秒或带时区的 ISO 时间。")


def phase(task, now=None):
    now = int(time.time()) if now is None else now
    if task["state"] != "published":
        return task["state"]
    return "upcoming" if now < task["starts_at"] else "ended" if now > task["due_at"] else "active"


async def get_task(db, task_id):
    task = await one(db, "SELECT * FROM training_tasks WHERE id=?", (task_id,))
    if not task:
        raise TaskError("训练任务不存在或无权查看。", "not_found", 404)
    return public_task(task)


def public_task(task):
    task["statuses"] = json.loads(task.pop("statuses_json"))
    task["phase"] = phase(task)
    for field in ("preview_hash", "audience_hash", "preview_expires_at", "publish_key", "publish_version"):
        task.pop(field, None)
    return task


async def detail(db, task_id):
    task = await get_task(db, task_id)
    task["problems"] = await rows(db, "SELECT * FROM training_task_problems WHERE task_id=? ORDER BY position", (task_id,))
    for problem in task["problems"]:
        problem["tags"] = json.loads(problem.pop("tags_json"))
        problem["supported"] = problem["platform"] == "codeforces"
    task["recipient_count"] = (await one(db, "SELECT COUNT(*) AS n FROM training_task_recipients WHERE task_id=?", (task_id,)))["n"]
    task["audit"] = await rows(db, "SELECT action,reason,before_json,after_json,created_at FROM training_task_audit WHERE task_id=? ORDER BY id DESC LIMIT 50", (task_id,))
    return task


def check_version(task, data):
    if type(data.get("version")) is not int or data["version"] != task["version"]:
        raise TaskError("任务已被其他操作更新，请重新加载后确认。", "version_conflict", 409, version=task["version"])


async def audit(db, task_id, identity, action, *, reason="", before=None, after=None):
    await db.execute("INSERT INTO training_task_audit(task_id,actor_qq_id,action,reason,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?)",
                     (task_id, identity.get("qq_id"), action, reason, dump(before) if before is not None else None, dump(after) if after is not None else None, int(time.time())))


def canonical_problem(value):
    if not isinstance(value, dict):
        raise TaskError("每道题需提供平台和标准题号。")
    platform = value.get("platform", "codeforces")
    try:
        platform, _, _ = platform_spec(platform)
    except Exception:
        raise TaskError("不支持的题目平台。") from None
    pid = str(value.get("problem_id", "")).strip()
    url = ""
    if platform == "codeforces":
        # Batch input accepts identifiers only, never client-provided URLs.
        if ":" in pid or "/" in pid:
            raise TaskError("请输入标准题号，例如 1843A，不接受任意链接。")
        try:
            normalized = normalize_problem(pid)
        except PracticeError as error:
            raise TaskError(str(error)) from None
        pid, url = "cf_" + normalized["display_id"], normalized["url"]
    elif platform == "atcoder":
        if not re.fullmatch(r"[a-z][a-z0-9]*_[a-z0-9]+", pid):
            raise TaskError("AtCoder 题号格式应类似 abc300_a。")
        url = f"https://atcoder.jp/contests/{pid.split('_')[0]}/tasks/{pid}"
    elif platform == "luogu":
        pid = pid.upper()
        if not re.fullmatch(r"(?:P|B|T|U)[1-9][0-9]{0,8}", pid):
            raise TaskError("洛谷题号格式应类似 P1001。")
        url = "https://www.luogu.com.cn/problem/" + pid
    elif not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", pid):
        raise TaskError("标准题号格式错误。")
    return {"platform": platform, "problem_id": pid, "problem_url": url}


async def resolve_problems(db, inputs):
    if not isinstance(inputs, list) or len(inputs) > 500:
        raise TaskError("单次最多校验 500 条输入，去重后题单最多 50 题。")
    items, errors, seen, duplicates = [], [], set(), 0
    for index, value in enumerate(inputs):
        try:
            item = canonical_problem(value)
            key = (item["platform"], item["problem_id"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            aliases = [item["problem_id"], re.sub(r"^cf_", "", item["problem_id"])]
            entry = await one(db, "SELECT problem_name,problem_rating,tags FROM recommendations WHERE platform=? AND problem_id IN (?,?) ORDER BY id LIMIT 1", (item["platform"], *aliases))
            if item["platform"] == "codeforces" and not entry:
                norm = normalize_problem(item["problem_id"])
                entry = await one(db, "SELECT name AS problem_name,rating AS problem_rating,tags FROM cf_problem_cache WHERE contest_id=? AND problem_index=?", (norm["contest_id"], norm["index"]))
            content = await one(db, "SELECT 1 AS ok FROM crawler_problems WHERE platform=? AND problem_id IN (?,?) AND (statement_html IS NOT NULL OR statement_pdf IS NOT NULL) LIMIT 1", (item["platform"], *aliases))
            tags = (entry or {}).get("tags") or ""
            try:
                tags = json.loads(tags)
            except (ValueError, TypeError):
                tags = str(tags).split(",")
            item.update(problem_name=(entry or {}).get("problem_name") or item["problem_id"], problem_rating=(entry or {}).get("problem_rating"),
                        tags=[str(t) for t in tags if t] if isinstance(tags, list) else [], content_available=bool(content), supported=item["platform"] == "codeforces")
            items.append(item)
        except TaskError as error:
            errors.append({"index": index, "message": str(error)})
    if len(items) > MAX_PROBLEMS:
        raise TaskError(f"去重后的题单最多 {MAX_PROBLEMS} 题。")
    return {"items": items, "errors": errors, "duplicates": duplicates}


async def save_draft(db, identity, data, task_id=None):
    allowed = {"version", "title", "description", "statuses", "starts_at", "due_at", "rule", "problems"}
    if set(data) - allowed:
        raise TaskError("草稿中包含不能修改的字段。")
    old = await get_task(db, task_id) if task_id else None
    if old:
        check_version(old, data)
        if old["state"] != "draft":
            raise TaskError("已发布的名单和题单不可修改。", "immutable_task", 409)
    if old:
        existing = await detail(db, task_id)
        data = {**{key: existing.get(key) for key in allowed if key != "version"}, **data}
    title, description = data.get("title", "未命名训练任务"), data.get("description", "")
    if not isinstance(title, str) or not title.strip() or len(title) > 100 or not isinstance(description, str) or len(description) > 5000:
        raise TaskError("标题须为 1–100 字，说明不能超过 5000 字。")
    statuses = data.get("statuses", [])
    if not isinstance(statuses, list) or len(statuses) > 100 or any(not isinstance(s, str) or not s.strip() or len(s) > 100 for s in statuses):
        raise TaskError("请选择有效的成员身份。")
    statuses = sorted(set(statuses))
    rule = data.get("rule", "period_ac")
    if rule not in {"period_ac", "historical_ac"}:
        raise TaskError("完成规则无效。")
    start, due = timestamp(data.get("starts_at")), timestamp(data.get("due_at"))
    if start and due and start >= due:
        raise TaskError("开始时间必须早于截止时间。")
    problems = await resolve_problems(db, data.get("problems", []))
    if problems["errors"]:
        raise TaskError("题单包含无效题号，请逐项修正。", errors=problems["errors"])
    now = int(time.time())
    values = (title.strip(), description.strip(), dump(statuses), rule, start, due, now)
    if old:
        await db.execute("UPDATE training_tasks SET title=?,description=?,statuses_json=?,rule=?,starts_at=?,due_at=?,updated_at=?,version=version+1,preview_hash=NULL WHERE id=?", (*values, task_id))
        await db.execute("DELETE FROM training_task_problems WHERE task_id=?", (task_id,))
    else:
        actor = await one(db, "SELECT name FROM users WHERE qq_id=?", (identity.get("qq_id"),))
        cursor = await db.execute("INSERT INTO training_tasks(title,description,statuses_json,rule,starts_at,due_at,updated_at,created_at,creator_qq_id,creator_name) VALUES(?,?,?,?,?,?,?,?,?,?)", (*values, now, identity.get("qq_id"), (actor or {}).get("name") or "管理员"))
        task_id = cursor.lastrowid
    await db.executemany("INSERT INTO training_task_problems(task_id,position,platform,problem_id,problem_name,problem_rating,tags_json,problem_url,content_available) VALUES(?,?,?,?,?,?,?,?,?)",
                         [(task_id, i + 1, p["platform"], p["problem_id"], p["problem_name"], p["problem_rating"], dump(p["tags"]), p["problem_url"], p["content_available"]) for i, p in enumerate(problems["items"])])
    await audit(db, task_id, identity, "draft_updated" if old else "created")
    return await detail(db, task_id)


async def audience(db, task):
    statuses = task["statuses"]
    if not statuses:
        raise TaskError("请至少选择一种成员身份。")
    members = await rows(db, "SELECT u.*,a.password_hash,a.is_active,a.must_change_password,a.temporary_password_expires_at,a.credential_version FROM users u LEFT JOIN web_accounts a ON a.qq_id=u.qq_id WHERE u.status IN (" + ",".join("?" for _ in statuses) + ") ORDER BY u.qq_id", statuses)
    result = []
    platforms = {p["platform"] for p in task["problems"]}
    for member in members:
        reason = "account_closed" if member["account_state"] != "active" else "no_web_account" if member["is_active"] is None else "account_disabled" if not member["is_active"] else "account_unavailable" if not web_account_available(member) else None
        bindings = {}
        for platform in sorted(platforms):
            _, field, generation = platform_spec(platform)
            bindings[platform] = {"account": str(member[field] or "").strip().casefold(), "version": member[generation]}
        result.append({"qq_id": member["qq_id"], "account_epoch": member["account_epoch"], "name": "已注销成员" if member["account_state"] != "active" else member["name"], "status": member["status"], "excluded_reason": reason, "bindings": bindings, "unbound": any(not v["account"] for v in bindings.values()), "credential_version": member["credential_version"]})
    return result


def publishable(task):
    if task["state"] != "draft":
        raise TaskError("仅草稿可预览和发布。", "immutable_task", 409)
    if not task["starts_at"] or not task["due_at"] or task["starts_at"] >= task["due_at"]:
        raise TaskError("请设置有效的开始与截止时间。")
    if not task["problems"]:
        raise TaskError("题单至少需要一道题。")
    if any(p["platform"] != "codeforces" for p in task["problems"]):
        raise TaskError("题单存在当前不能可靠核验的平台，请更换题目。", "unsupported_capability")


async def preview(db, task_id, data):
    task = await detail(db, task_id)
    check_version(task, data)
    publishable(task)
    members = await audience(db, task)
    token = secrets.token_urlsafe(32)
    await db.execute("UPDATE training_tasks SET preview_hash=?,audience_hash=?,preview_expires_at=? WHERE id=?", (digest(token), digest(members), int(time.time()) + PREVIEW_TTL, task_id))
    return token, members


async def publish(db, identity, task_id, data, key):
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
        raise TaskError("发布需提供有效的 Idempotency-Key。")
    raw = await one(db, "SELECT * FROM training_tasks WHERE id=?", (task_id,))
    if raw and raw["state"] != "draft" and raw["publish_key"] == digest(key) and raw["publish_version"] == data.get("version"):
        return await detail(db, task_id)
    task = await detail(db, task_id)
    check_version(task, data)
    publishable(task)
    members = await audience(db, task)
    if not raw["preview_hash"] or digest(data.get("preview_token")) != raw["preview_hash"] or not raw["preview_expires_at"] or raw["preview_expires_at"] < int(time.time()) or digest(members) != raw["audience_hash"]:
        raise TaskError("预览已失效或成员信息变化，请重新预览并确认。", "audience_changed", 409)
    selected = [m for m in members if not m["excluded_reason"]]
    if not selected:
        raise TaskError("没有有效接收人，不能发布。", "empty_audience")
    if len(selected) != len(members) and data.get("confirm_exclusions") is not True:
        raise TaskError("存在被排除的成员，请明确确认排除原因。", "exclusions_confirmation_required")
    now = int(time.time())
    publisher = await one(db, "SELECT name FROM users WHERE qq_id=?", (identity.get("qq_id"),))
    await db.execute("UPDATE training_tasks SET state='published',creator_qq_id=?,creator_name=?,original_due_at=due_at,published_at=?,updated_at=?,version=version+1,publish_key=?,publish_version=?,preview_hash=NULL WHERE id=?", (identity.get("qq_id"), (publisher or {}).get("name") or "管理员", now, now, digest(key), task["version"], task_id))
    await db.executemany("INSERT INTO training_task_recipients(task_id,qq_id,account_epoch,name,status_snapshot,bindings_json) VALUES(?,?,?,?,?,?)", [(task_id, m["qq_id"], m["account_epoch"], m["name"], m["status"], dump(m["bindings"])) for m in selected])
    await db.execute("INSERT INTO training_task_progress(recipient_id,problem_id) SELECT r.id,p.id FROM training_task_recipients r JOIN training_task_problems p ON p.task_id=r.task_id WHERE r.task_id=?", (task_id,))
    from .training_task_progress import reconcile
    await reconcile(db, task_id=task_id)
    await audit(db, task_id, identity, "published", after={"recipients": len(selected), "problems": len(task["problems"]), "rule": task["rule"], "starts_at": task["starts_at"], "due_at": task["due_at"]})
    return await detail(db, task_id)


async def lifecycle(db, identity, task_id, action, data):
    task = await detail(db, task_id)
    check_version(task, data)
    if action == "delete":
        if task["state"] != "draft":
            raise TaskError("只能删除草稿。", "immutable_task", 409)
        await db.execute("DELETE FROM training_tasks WHERE id=?", (task_id,))
        return {"deleted": True}
    if task["state"] != "published":
        raise TaskError("只能延期或取消已发布任务。", "immutable_task", 409)
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise TaskError("请填写 1–500 字的操作原因。")
    now = int(time.time())
    if action == "extend-deadline":
        due = timestamp(data.get("due_at"))
        if due is None or due <= task["due_at"]:
            raise TaskError("新截止时间必须晚于当前截止时间。")
        await db.execute("UPDATE training_tasks SET due_at=?,updated_at=?,version=version+1 WHERE id=?", (due, now, task_id))
        from .training_task_progress import reconcile
        await reconcile(db, task_id=task_id)
        await audit(db, task_id, identity, "extended", reason=reason.strip(), before={"due_at": task["due_at"]}, after={"due_at": due})
    else:
        await db.execute("UPDATE training_tasks SET state='cancelled',cancel_reason=?,cancelled_at=?,updated_at=?,version=version+1 WHERE id=?", (reason.strip(), now, now, task_id))
        await audit(db, task_id, identity, "cancelled", reason=reason.strip())
    return await detail(db, task_id)
