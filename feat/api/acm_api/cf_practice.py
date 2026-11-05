"""Snapshot-based member scope, recent AC aggregation and historical deduplication."""
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .cf_client import binding_key, problem_url


BEIJING = timezone(timedelta(hours=8))
MAX_CANDIDATES = 100
ID_RE = re.compile(r"([1-9]\d{0,6})([A-Z]{1,3}\d{0,2})", re.I)


class PracticeError(ValueError):
    def __init__(self, message, code="invalid_request", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, BEIJING).isoformat(timespec="seconds") if timestamp else None


def integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PracticeError(f"{name} 必须为整数")
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise PracticeError(f"{name} 必须为整数") from None
    if not minimum <= result <= maximum:
        raise PracticeError(f"{name} 应在 {minimum}–{maximum} 之间")
    return result


def normalize_problem(raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1024:
        raise PracticeError("题号或链接为空或过长")
    value = raw.strip()
    if "://" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise PracticeError("题目链接格式无效") from None
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"codeforces.com", "www.codeforces.com"}:
            raise PracticeError("仅支持 Codeforces 题目链接")
        match = re.fullmatch(r"/(?:contest|gym)/(\d+)/problem/([A-Za-z]+\d*)/?", parsed.path)
        if not match:
            match = re.fullmatch(r"/problemset/problem/(\d+)/([A-Za-z]+\d*)/?", parsed.path)
        if not match:
            raise PracticeError("链接须指向一道 CF 题目")
        value = "".join(match.groups())
    else:
        value = re.sub(r"^cf_", "", value, flags=re.I)
        value = re.sub(r"\s+", "", value)
    match = ID_RE.fullmatch(value)
    if not match:
        raise PracticeError("题号格式应类似 1843A 或 1843A1")
    contest_id, index = int(match[1]), match[2].upper()
    return {"contest_id": contest_id, "index": index, "display_id": f"{contest_id}{index}", "url": problem_url(contest_id, index)}


def candidate_input(payload):
    has_contest, has_candidates = "contest_id" in payload, "candidates" in payload
    if has_contest == has_candidates:
        raise PracticeError("candidates 与 contest_id 必须且只能提供一个")
    mode = payload.get("mode", "any_submission")
    if not isinstance(mode, str) or mode not in {"any_submission", "ac_only"}:
        raise PracticeError("查重口径无效")
    if has_contest:
        return mode, integer(payload["contest_id"], "比赛 ID", 1, 9999999), []
    inputs = payload["candidates"]
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_CANDIDATES:
        raise PracticeError(f"单次须输入 1–{MAX_CANDIDATES} 条候选题")
    rows, seen = [], {}
    for raw in inputs:
        if not isinstance(raw, str) or len(raw) > 1024:
            raise PracticeError("每条候选输入须为不超过 1024 字符的文本")
        try:
            item = normalize_problem(raw)
        except PracticeError as exc:
            rows.append({"input": raw, "display_id": raw, "invalid_reason": str(exc)})
            continue
        if item["display_id"] in seen:
            seen[item["display_id"]]["inputs"].append(raw)
        else:
            item["inputs"] = [raw]
            seen[item["display_id"]] = item
            rows.append(item)
    if len({row["contest_id"] for row in rows if "contest_id" in row}) > 20:
        raise PracticeError("单次候选题最多来自 20 场比赛")
    return mode, None, rows


def date_range(payload, now):
    if "date_from" in payload or "date_to" in payload:
        values = []
        for key in ("date_from", "date_to"):
            try:
                value = datetime.fromisoformat(payload[key])
                if value.tzinfo is None:
                    raise ValueError()
                values.append(int(value.timestamp()))
            except (KeyError, TypeError, ValueError):
                raise PracticeError("自定义日期须为带时区的 ISO 8601 时间") from None
        start, end = values
        if not 0 <= start <= end <= now + 86400 or end - start > 3660 * 86400:
            raise PracticeError("日期范围无效或超过十年")
        return start, end
    days = integer(payload.get("days", 7), "天数", 1, 3660)
    return max(0, now - days * 86400), now


def paging(payload):
    return integer(payload.get("page", 1), "页码", 1, 100000), integer(payload.get("page_size", 20), "每页条数", 1, 100)


async def options(db):
    async with db.execute("SELECT COALESCE(status,'') AS value, COUNT(*) AS member_count FROM users WHERE account_state='active' GROUP BY COALESCE(status,'') ORDER BY value") as cursor:
        rows = await cursor.fetchall()
    return {"statuses": [{"value": row["value"], "label": row["value"] or "未设置身份", "member_count": row["member_count"]} for row in rows], "max_candidates": MAX_CANDIDATES}


async def resolve_scope(db, payload, ttl_seconds, now=None):
    now = int(time.time()) if now is None else now
    spec = payload.get("scope")
    if not isinstance(spec, dict):
        raise PracticeError("须提供成员范围 scope")
    statuses, excluded = spec.get("statuses"), spec.get("exclude_qq_ids", [])
    if not isinstance(statuses, list) or not 1 <= len(statuses) <= 20 or any(not isinstance(s, str) or len(s) > 64 for s in statuses):
        raise PracticeError("请选择 1–20 个成员身份")
    if not isinstance(excluded, list) or len(excluded) > 2000 or any(not isinstance(q, str) or not re.fullmatch(r"\d{4,12}", q) for q in excluded):
        raise PracticeError("排除名单格式无效")
    statuses, excluded = sorted(set(statuses)), sorted(set(excluded))
    known = {item["value"] for item in (await options(db))["statuses"]}
    expected = payload.get("expected_scope_fingerprint")
    if any(s not in known for s in statuses):
        raise PracticeError("成员身份已变化，请重新选择", "scope_changed" if expected else "invalid_scope", 409 if expected else 400)
    placeholders = ",".join("?" for _ in statuses)
    async with db.execute(
        f"SELECT u.qq_id,u.name,COALESCE(u.status,'') AS status,u.cf_handle,u.cf_binding_version,u.account_state,u.account_epoch,"
        "s.binding_key,s.full_history_at,s.coverage_through_at,s.last_success_at,s.last_status,s.last_error_message "
        "FROM users u LEFT JOIN user_platform_sync_state s ON s.user_qq_id=u.qq_id AND s.platform='codeforces' "
        f"WHERE u.account_state='active' AND COALESCE(u.status,'') IN ({placeholders}) ORDER BY u.qq_id", statuses,
    ) as cursor:
        members = [dict(row) for row in await cursor.fetchall()]
    if not set(excluded) <= {row["qq_id"] for row in members}:
        raise PracticeError("排除名单中的成员已不在所选身份中", "scope_changed" if expected else "invalid_scope", 409 if expected else 400)
    participants = [row for row in members if row["qq_id"] not in excluded]
    fingerprint = hashlib.sha256(json.dumps({
        "statuses": statuses, "excluded": excluded,
        "members": [[row["qq_id"], row["status"], binding_key(row), row["account_epoch"]] for row in participants],
    }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if expected is not None and expected != fingerprint:
        raise PracticeError("成员身份、名单或 CF 绑定已变化，请重新查重", "scope_changed", 409)
    reason_labels = {"unbound": "未绑定 CF", "sync_in_progress": "同步中", "sync_failed": "同步失败", "sync_interrupted": "同步已中断", "binding_changed": "绑定已变化，须补齐历史", "history_incomplete": "全量历史未补齐", "stale": "数据已过期，须刷新", "refresh_required": "须刷新历史数据"}
    for row in members:
        if not (row["cf_handle"] or "").strip():
            reason = "unbound"
        elif row["last_status"] == "running":
            reason = "sync_in_progress"
        elif row["last_status"] == "failed":
            reason = "sync_failed"
        elif row["last_status"] in {"cancelled", "interrupted"}:
            reason = "sync_interrupted"
        elif row["binding_key"] and row["binding_key"] != binding_key(row):
            reason = "binding_changed"
        elif not row["full_history_at"] or not row["coverage_through_at"] or row["binding_key"] != binding_key(row):
            reason = "history_incomplete"
        elif row["last_status"] != "success":
            reason = "refresh_required"
        elif now - row["coverage_through_at"] > ttl_seconds or now - (row["last_success_at"] or 0) > ttl_seconds:
            reason = "stale"
        else:
            reason = None
        row.update(excluded=row["qq_id"] in excluded, ready=reason is None, reason=reason, reason_label=reason_labels.get(reason, "数据就绪"))
    ready = sum(row["ready"] for row in participants)
    coverage = min((row["coverage_through_at"] or 0 for row in participants), default=0)
    public_members = [{key: row[key] for key in ("qq_id", "name", "status", "cf_handle", "excluded", "ready", "reason", "reason_label")} | {"last_success_at": iso(row["last_success_at"]), "history_completed_at": iso(row["full_history_at"]), "error_message": row["last_error_message"]} for row in members]
    public = {"fingerprint": fingerprint, "statuses": statuses, "exclude_qq_ids": excluded, "member_count": len(participants), "bound_member_count": sum(bool((row["cf_handle"] or "").strip()) for row in participants), "ready_member_count": ready, "unknown_member_count": len(participants) - ready, "coverage_as_of": iso(coverage), "members": public_members}
    await db.execute("CREATE TEMP TABLE IF NOT EXISTS cf_scope_members(qq_id TEXT PRIMARY KEY)")
    await db.execute("DELETE FROM cf_scope_members")
    await db.executemany("INSERT INTO cf_scope_members VALUES(?)", [(row["qq_id"],) for row in participants if (row["cf_handle"] or "").strip()])
    return public, participants


async def evidence(db, start=0, end=2147483647, candidates=None):
    canonical = "UPPER(CASE WHEN LOWER(SUBSTR(problem_id,1,3))='cf_' THEN SUBSTR(problem_id,4) ELSE problem_id END)"
    filter_sql = ""
    params = []
    if candidates is not None:
        if not candidates:
            return []
        filter_sql = " WHERE pid IN (" + ",".join("?" for _ in candidates) + ")"
        params.extend(candidates)
    sql = f"""
        WITH raw AS (
          SELECT user_qq_id AS owner,{canonical} AS pid,submit_time AS at,1 AS ac,NULL AS external,
                 problem_name AS name,problem_rating AS rating,tags FROM submissions WHERE platform='codeforces'
          UNION ALL
          SELECT owner_qq_id,{canonical},submitted_at,CASE WHEN verdict='OK' THEN 1 ELSE 0 END,
                 external_submission_id,NULL,NULL,NULL FROM submission_attempts WHERE platform='codeforces'
        ), scoped AS (SELECT raw.* FROM raw JOIN cf_scope_members ON owner=qq_id {filter_sql}),
        ranked AS (
          SELECT *,ROW_NUMBER() OVER(PARTITION BY owner,pid ORDER BY ac DESC,at DESC,external DESC) AS ac_rank,
             ROW_NUMBER() OVER(PARTITION BY owner,pid ORDER BY at DESC,external DESC) AS attempt_rank,
             ROW_NUMBER() OVER(PARTITION BY owner,pid ORDER BY CASE WHEN ac=1 AND at BETWEEN ? AND ? THEN 1 ELSE 0 END DESC,at DESC,external DESC) AS recent_rank
          FROM scoped
        )
        SELECT owner,pid,MAX(CASE WHEN ac=1 THEN at END) AS ac_at,
          MAX(CASE WHEN ac=1 AND at BETWEEN ? AND ? THEN at END) AS recent_ac_at,
          MAX(at) AS attempt_at,MAX(CASE WHEN ac=1 AND ac_rank=1 THEN external END) AS ac_external,
          MAX(CASE WHEN attempt_rank=1 THEN external END) AS attempt_external,
          MAX(CASE WHEN ac=1 AND recent_rank=1 THEN external END) AS recent_external,
          MAX(name) AS name,MAX(rating) AS rating,MAX(tags) AS tags FROM ranked GROUP BY owner,pid
    """
    async with db.execute(sql, params + [start, end, start, end]) as cursor:
        return [dict(row) for row in await cursor.fetchall() if ID_RE.fullmatch(row["pid"])]


async def metadata(db, ids):
    if not ids:
        return {}
    # A temporary keyed table avoids candidate-by-member SQL or network requests.
    await db.execute("CREATE TEMP TABLE IF NOT EXISTS cf_metadata_ids(contest_id INTEGER,problem_index TEXT,PRIMARY KEY(contest_id,problem_index))")
    await db.execute("DELETE FROM cf_metadata_ids")
    await db.executemany("INSERT OR IGNORE INTO cf_metadata_ids VALUES(?,?)", [(item["contest_id"], item["index"]) for item in map(normalize_problem, ids)])
    async with db.execute("SELECT c.* FROM cf_problem_cache c JOIN cf_metadata_ids USING(contest_id,problem_index)") as cursor:
        return {f"{row['contest_id']}{row['problem_index']}": dict(row) for row in await cursor.fetchall()}


def problem_info(item, cached=None, legacy=None):
    cached, legacy = cached or {}, legacy or {}
    raw_rating = cached.get("rating") if cached else legacy.get("rating")
    try:
        rating = int(raw_rating) if raw_rating is not None and int(raw_rating) > 0 else None
    except (ValueError, TypeError):
        rating = None
    tags = cached.get("tags") if cached else legacy.get("tags") or ""
    try:
        tags = json.loads(tags)
    except (ValueError, TypeError):
        tags = [tag.strip() for tag in str(tags or "").split(",") if tag.strip()]
    return {"display_id": item["display_id"], "contest_id": item["contest_id"], "index": item["index"], "url": item["url"], "name": cached.get("name") or legacy.get("name") or "题目资料待核实", "rating": rating, "tags": tags if isinstance(tags, list) else []}


def submission_link(external, contest_id):
    if external and re.fullmatch(r"\d+", str(external).split(":")[-1]):
        section = "gym" if int(contest_id) >= 100000 else "contest"
        return f"https://codeforces.com/{section}/{contest_id}/submission/{str(external).split(':')[-1]}"
    return None


class PracticeQuery:
    def __init__(self, data_ttl=86400, problem_ttl=21600):
        self.data_ttl, self.problem_ttl = data_ttl, problem_ttl

    async def overview(self, db, payload):
        now = int(time.time())
        scope, members = await resolve_scope(db, payload, self.data_ttl, now)
        start, end = date_range(payload, now)
        page, size = paging(payload)
        view = payload.get("view", "problems")
        if not isinstance(view, str) or view not in {"problems", "members"}:
            raise PracticeError("展示方式无效")
        records = await evidence(db, start, end)
        by_problem = defaultdict(list)
        for row in records:
            by_problem[row["pid"]].append(row)
        cache = await metadata(db, list(by_problem))
        people = {row["qq_id"]: row for row in members}
        minimum = payload.get("rating_min")
        maximum = payload.get("rating_max")
        minimum = integer(minimum, "最低 Rating", 0, 5000) if minimum not in (None, "") else None
        maximum = integer(maximum, "最高 Rating", 0, 5000) if maximum not in (None, "") else None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise PracticeError("最低 Rating 不能高于最高 Rating")
        tag, search = payload.get("tag", ""), payload.get("search", "")
        if not isinstance(tag, str) or not isinstance(search, str) or len(tag) > 100 or len(search) > 200:
            raise PracticeError("标签或搜索条件过长")
        rows, available_tags = [], set()
        for pid, entries in by_problem.items():
            recent = [entry for entry in entries if entry["recent_ac_at"]]
            if not recent:
                continue
            info = problem_info(normalize_problem(pid), cache.get(pid), next((entry for entry in entries if entry["name"]), {}))
            available_tags.update(info["tags"])
            if minimum is not None and (info["rating"] is None or info["rating"] < minimum):
                continue
            if maximum is not None and (info["rating"] is None or info["rating"] > maximum):
                continue
            if tag and tag not in info["tags"]:
                continue
            if search and search.casefold() not in (pid + " " + info["name"]).casefold():
                continue
            rows.append(info | {"recent_ac_count": len(recent), "history_ac_count": sum(bool(entry["ac_at"]) for entry in entries), "last_ac_at": iso(max(entry["recent_ac_at"] for entry in recent)), "_recent": recent})
        rows.sort(key=lambda row: (row["last_ac_at"], row["display_id"]), reverse=True)
        if view == "members":
            grouped = {}
            for row in rows:
                for entry in row["_recent"]:
                    person = people[entry["owner"]]
                    group = grouped.setdefault(entry["owner"], {"qq_id": entry["owner"], "name": person["name"], "cf_handle": person["cf_handle"], "problems": []})
                    group["problems"].append({key: value for key, value in row.items() if key != "_recent"} | {"ac_at": iso(entry["recent_ac_at"]), "submission_url": submission_link(entry["recent_external"], row["contest_id"])})
            rows = [{**group, "recent_ac_count": len(group["problems"])} for group in grouped.values()]
            rows.sort(key=lambda row: (-row["recent_ac_count"], row["qq_id"]))
        else:
            for row in rows:
                row.pop("_recent")
        return {"scope": scope, "status": "empty_scope" if not members else "partial" if scope["unknown_member_count"] else "ready", "coverage_as_of": scope["coverage_as_of"], "data_ttl_seconds": self.data_ttl, "date_from": iso(start), "date_to": iso(end), "view": view, "rows": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "page_size": size, "available_tags": sorted(available_tags)}

    async def problem_members(self, db, payload):
        scope, members = await resolve_scope(db, payload, self.data_ttl)
        item = normalize_problem(payload.get("problem_id", ""))
        period = payload.get("period", "history")
        if not isinstance(period, str) or period not in {"recent", "history"}:
            raise PracticeError("证据时间口径无效")
        start, end = date_range(payload, int(time.time())) if period == "recent" else (0, 2147483647)
        page, size = paging(payload)
        records = await evidence(db, start, end, [item["display_id"]])
        people, rows = {row["qq_id"]: row for row in members}, []
        for entry in records:
            if period == "recent" and not entry["recent_ac_at"]:
                continue
            person = people[entry["owner"]]
            ac_at = entry["recent_ac_at"] if period == "recent" else entry["ac_at"]
            rows.append({"qq_id": entry["owner"], "name": person["name"], "cf_handle": person["cf_handle"], "has_ac": bool(ac_at), "ac_at": iso(ac_at), "last_attempt_at": iso(entry["attempt_at"]), "ac_submission_url": submission_link(entry["recent_external"] if period == "recent" else entry["ac_external"], item["contest_id"]), "attempt_submission_url": submission_link(entry["attempt_external"], item["contest_id"])})
        return {"scope": scope, "problem_id": item["display_id"], "period": period, "rows": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "page_size": size}

    async def check(self, db, payload):
        if not isinstance(payload.get("expected_scope_fingerprint"), str) or not payload["expected_scope_fingerprint"]:
            raise PracticeError("请先读取成员概况，再携带范围指纹查重")
        now = int(time.time())
        scope, members = await resolve_scope(db, payload, self.data_ttl, now)
        mode, contest_id, inputs = candidate_input(payload)
        needed_contests, needed_problems, need_catalog = set(), [], False
        if contest_id:
            async with db.execute("SELECT problems,verified_at FROM cf_contest_cache WHERE contest_id=?", (contest_id,)) as cursor:
                contest = await cursor.fetchone()
            if not contest or now - contest["verified_at"] > self.problem_ttl:
                needed_contests.add(contest_id)
                inputs = []
            else:
                problems = json.loads(contest["problems"])
                if len(problems) > MAX_CANDIDATES:
                    raise PracticeError("比赛题目数量超过单次限制")
                inputs = [normalize_problem(f"{contest_id}{index}") for index in problems]
        ids = [row["display_id"] for row in inputs if "contest_id" in row]
        records = await evidence(db, candidates=ids)
        by_problem = defaultdict(list)
        for row in records:
            by_problem[row["pid"]].append(row)
        cache = await metadata(db, ids)
        rows = []
        for item in inputs:
            if "invalid_reason" in item:
                rows.append({**item, "decision": "invalid", "eligible": False, "ac_count": 0, "attempt_count": 0, "reason_code": "invalid_input", "reason": item["invalid_reason"], "rating": None, "tags": []})
                continue
            entries = by_problem[item["display_id"]]
            ac_count = sum(bool(row["ac_at"]) for row in entries)
            info = problem_info(item, cache.get(item["display_id"]), next((entry for entry in entries if entry["name"]), {}))
            verified = bool(cache.get(item["display_id"]) and now - cache[item["display_id"]]["verified_at"] <= self.problem_ttl)
            invalid = False
            if not verified:
                async with db.execute("SELECT problems,verified_at FROM cf_contest_cache WHERE contest_id=?", (item["contest_id"],)) as cursor:
                    contest = await cursor.fetchone()
                if contest and now - contest["verified_at"] <= self.problem_ttl:
                    invalid = item["index"] not in json.loads(contest["problems"])
            if ac_count:
                decision, code, reason = "excluded_ac", "has_ac", "至少一名参与成员已 AC"
            elif mode == "any_submission" and entries:
                decision, code, reason = "excluded_attempted", "has_attempt", "至少一名参与成员提交过"
            elif not members:
                decision, code, reason = "unknown", "empty_scope", "参与范围为空，请先选择成员"
            elif invalid:
                decision, code, reason = "invalid", "problem_not_found", "已核实该比赛题目列表，不包含此题号"
            elif not verified:
                decision, code, reason = "unknown", "problem_unverified", "题目资料尚未核实或已过期"
                need_catalog = True
                needed_contests.add(item["contest_id"])
                needed_problems.append(item["display_id"])
            elif scope["unknown_member_count"]:
                decision, code, reason = "unknown", "members_not_ready", "存在未绑定、未补齐、过期或同步异常的参与成员"
            else:
                decision, code, reason = "eligible", "no_history_evidence", "题目已核实，全员数据就绪，没有符合当前口径的历史证据"
            rows.append(info | {"inputs": item.get("inputs", [item["display_id"]]), "ac_count": ac_count, "attempt_count": len(entries), "decision": decision, "eligible": decision == "eligible", "reason_code": code, "reason": reason})
        counts = {decision: sum(row["decision"] == decision for row in rows) for decision in ("eligible", "excluded_ac", "excluded_attempted", "unknown", "invalid")}
        result = {"status": "empty_scope" if not members else "partial" if scope["unknown_member_count"] or counts["unknown"] else "ready", "scope": scope, "mode": mode, "checked_at": iso(now), "coverage_as_of": scope["coverage_as_of"], "rows": rows, "counts": counts, "total": len(rows)}
        return result, {"contests": sorted(needed_contests), "catalog": need_catalog, "problems": needed_problems, "require_contest_list": bool(contest_id)} if members and needed_contests else None
