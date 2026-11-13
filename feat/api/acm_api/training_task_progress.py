"""Local, batched AC evidence aggregation. No external requests in this module."""
import json
import time
from collections import defaultdict

from . import training_task_service as tasks
from .cf_client import binding_key


def evidence(value):
    return json.loads(value) if value else None


def first_evidence(values):
    return min(values, key=lambda item: item["accepted_at"]) if values else None


def live_state(row, now):
    """Derive current verification from local data without mutating frozen evidence."""
    original = json.loads(row["bindings_json"]).get(row["platform"], {})
    anchor = row["binding_key"] or (f'{original["account"]}:{original["version"]}' if original.get("account") else None)
    generation = row.get("binding_version", 0) if row["binding_key"] else original.get("version", 0)
    current = binding_key(row) if row["cf_handle"] else None
    active = not row["closed"] and row["account_state"] == "active" and row["account_epoch"] == row["current_epoch"]
    # Only the first binding generation can fill an initially empty snapshot.
    if active and not anchor and current and row["cf_binding_version"] == original.get("version", 0) + 1:
        anchor, generation = current, row["cf_binding_version"]
    valid = bool(active and anchor and anchor == current)
    if not active:
        verification = "account_closed" if row["closed"] else "account_changed"
    elif not row["is_active"]:
        verification = "account_disabled"
    elif not current:
        verification = "unbound"
    elif not valid:
        verification = "binding_changed"
    elif row["sync_status"] == "paused":
        verification = "sync_paused"
    elif row["sync_status"] in {"failed", "error"}:
        verification = "sync_failed"
    elif row["sync_binding"] != anchor or not row["full_history_at"]:
        verification = "coverage_missing"
    elif (row["coverage_through_at"] or 0) < min(now - 60, row["due_at"]):
        verification = "pending_sync"
    else:
        verification = "verified"
    return anchor, generation, valid, verification


async def reconcile(db, *, qq_id=None, task_id=None, now=None):
    """Caller holds the write transaction; never join evidence across a binding fence."""
    now = int(time.time()) if now is None else now
    clauses, params = ["t.state='published'"], []
    if qq_id is not None:
        clauses.append("r.qq_id=?")
        params.append(str(qq_id))
    if task_id is not None:
        clauses.append("t.id=?")
        params.append(task_id)
    where = " AND ".join(clauses)
    records = await tasks.rows(db, """
        SELECT x.*,r.qq_id,r.account_epoch,r.bindings_json,r.closed,
        t.starts_at,t.due_at,t.rule,p.platform,p.problem_id AS canonical_id,
        u.cf_handle,u.cf_binding_version,u.account_state,u.account_epoch AS current_epoch,a.is_active,
        s.binding_key AS sync_binding,s.full_history_at,s.coverage_through_at,s.last_status AS sync_status,s.last_success_at
        FROM training_task_progress x JOIN training_task_recipients r ON r.id=x.recipient_id
        JOIN training_task_problems p ON p.id=x.problem_id JOIN training_tasks t ON t.id=r.task_id
        LEFT JOIN users u ON u.qq_id=r.qq_id LEFT JOIN web_accounts a ON a.qq_id=r.qq_id
        LEFT JOIN user_platform_sync_state s ON s.user_qq_id=r.qq_id AND s.platform=p.platform
        WHERE """ + where, params)
    # Three minimum timestamps per assigned problem retain repeat AC information.
    found = await tasks.rows(db, """
        SELECT r.id AS recipient_id,p.id AS problem_id,
        MIN(CASE WHEN a.submitted_at<t.starts_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS historical,
        MIN(CASE WHEN a.submitted_at>=t.starts_at AND a.submitted_at<=t.due_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS timely,
        MIN(CASE WHEN a.submitted_at>t.due_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS late
        FROM training_task_recipients r JOIN training_tasks t ON t.id=r.task_id
        JOIN training_task_problems p ON p.task_id=t.id
        JOIN submission_attempts a ON a.owner_qq_id=r.qq_id AND a.platform=p.platform
          AND a.problem_id IN(p.problem_id,substr(p.problem_id,4)) AND a.verdict='OK' AND a.submitted_at<=?
        WHERE """ + where + " GROUP BY r.id,p.id", [now, *params])
    found = {(r["recipient_id"], r["problem_id"]): r for r in found}
    updates = []
    for row in records:
        anchor, generation, valid, verification = live_state(row, now)
        candidates = [evidence(row[k]) for k in ("history_json", "on_time_json", "late_json") if row[k]]
        if valid and row["sync_binding"] == anchor:
            for raw in (found.get((row["recipient_id"], row["problem_id"])) or {}).values():
                if not isinstance(raw, str) or "|" not in raw:
                    continue
                stamp, external = raw.split("|", 1)
                candidates.append({"platform": row["platform"], "problem_id": row["canonical_id"], "accepted_at": int(stamp), "external_submission_id": external.rsplit(":", 1)[-1] or None, "source": "codeforces_user_status"})
        history = first_evidence([e for e in candidates if e["accepted_at"] < row["starts_at"]])
        timely = first_evidence([e for e in candidates if row["starts_at"] <= e["accepted_at"] <= row["due_at"]])
        late = first_evidence([e for e in candidates if e["accepted_at"] > row["due_at"]])
        updates.append((anchor, generation, tasks.dump(history) if history else None, tasks.dump(timely) if timely else None, tasks.dump(late) if late else None,
                        verification, now, row["last_success_at"] or 0, row["recipient_id"], row["problem_id"]))
    await db.executemany("UPDATE training_task_progress SET binding_key=?,binding_version=?,history_json=?,on_time_json=?,late_json=?,verification=?,checked_at=?,sync_success_at=? WHERE recipient_id=? AND problem_id=?", updates)


def recipient_state(row, now):
    row["phase"] = tasks.phase(row, now)
    total, ontime, late = row["problem_count"], row["on_time_problems"], row["late_problems"]
    if now < row["starts_at"]:
        row["completion"] = "not_started"
        ontime = late = 0
    else:
        row["completion"] = "on_time" if total and ontime == total else "late" if total and ontime + late == total else "incomplete"
    row["on_time_problems"], row["late_problems"] = ontime, late
    row["completed_problems"] = ontime + late
    row["account_status"] = "closed" if row["closed"] else "changed" if row["current_epoch"] != row["account_epoch"] else "disabled" if not row["is_active"] else "active"
    row["pending"] = bool(row["pending_problems"] or row["binding_warnings"] or row["account_status"] != "active")
    for key in ("cf_handle", "cf_binding_version", "current_epoch", "is_active", "bindings_json", "platform", "binding_key", "binding_version", "account_state", "sync_binding", "full_history_at", "coverage_through_at", "sync_status"):
        row.pop(key, None)
    return row


async def recipient_summaries(db, task_ids, *, qq_id=None, epoch=None, now=None, include_real_name=False):
    if not task_ids:
        return []
    now = int(time.time()) if now is None else now
    where = "r.task_id IN (" + ",".join("?" for _ in task_ids) + ")"
    values = list(task_ids)
    if qq_id is not None:
        where += " AND r.qq_id=? AND r.account_epoch=?"
        values.extend([str(qq_id), epoch])
    name_column = """
        ,CASE WHEN r.closed=0 AND u.account_state='active' AND u.account_epoch=r.account_epoch
         THEN NULLIF(TRIM(u.real_name),'') ELSE NULL END AS real_name""" if include_real_name else ""
    result = await tasks.rows(db, f"""
        SELECT r.*{name_column},t.starts_at,t.due_at,t.state,t.rule,u.account_epoch AS current_epoch,u.account_state,
        u.cf_handle,u.cf_binding_version,a.is_active,p.platform,x.binding_key,MAX(x.binding_version) AS binding_version,
        s.binding_key AS sync_binding,s.full_history_at,s.coverage_through_at,s.last_status AS sync_status,
        COUNT(x.problem_id) AS problem_count,
        SUM(CASE WHEN x.on_time_json IS NOT NULL OR (t.rule='historical_ac' AND x.history_json IS NOT NULL) THEN 1 ELSE 0 END) AS on_time_problems,
        SUM(CASE WHEN x.on_time_json IS NULL AND NOT(t.rule='historical_ac' AND x.history_json IS NOT NULL) AND x.late_json IS NOT NULL THEN 1 ELSE 0 END) AS late_problems,
        MIN(x.checked_at) AS checked_at,MIN(x.sync_success_at) AS last_success_at
        FROM training_task_recipients r JOIN training_tasks t ON t.id=r.task_id
        LEFT JOIN users u ON u.qq_id=r.qq_id LEFT JOIN web_accounts a ON a.qq_id=r.qq_id
        JOIN training_task_progress x ON x.recipient_id=r.id JOIN training_task_problems p ON p.id=x.problem_id
        LEFT JOIN user_platform_sync_state s ON s.user_qq_id=r.qq_id AND s.platform=p.platform
        WHERE """ + where + " GROUP BY r.id,p.platform,x.binding_key ORDER BY r.id", values)
    # Aggregate groups sharing one binding; no per-recipient query or stale verification cache.
    grouped = {}
    for row in result:
        _, _, valid, verification = live_state(row, now)
        row["pending_problems"] = row["problem_count"] if verification != "verified" else 0
        row["binding_warnings"] = row["problem_count"] if not valid else 0
        previous = grouped.get(row["id"])
        if previous is None:
            grouped[row["id"]] = row
        else:
            for key in ("problem_count", "on_time_problems", "late_problems", "pending_problems", "binding_warnings"):
                previous[key] += row[key]
            for key in ("checked_at", "last_success_at"):
                previous[key] = min(previous[key], row[key])
    return [recipient_state(row, now) for row in grouped.values()]


def summary(recipients):
    return {"recipient_count": len(recipients), "on_time_count": sum(r["completion"] == "on_time" for r in recipients),
            "late_count": sum(r["completion"] == "late" for r in recipients), "pending_count": sum(r["pending"] for r in recipients),
            "abnormal_count": sum(r["account_status"] != "active" for r in recipients),
            "completed_problem_count": sum(r["completed_problems"] for r in recipients), "total_problem_count": sum(r["problem_count"] for r in recipients)}


async def add_summaries(db, items):
    grouped = defaultdict(list)
    for recipient in await recipient_summaries(db, [t["id"] for t in items]):
        grouped[recipient["task_id"]].append(recipient)
    counts = await tasks.rows(db, "SELECT task_id,COUNT(*) AS n FROM training_task_problems WHERE task_id IN (" + ",".join("?" for _ in items) + ") GROUP BY task_id", [t["id"] for t in items]) if items else []
    counts = {row["task_id"]: row["n"] for row in counts}
    for item in items:
        item["summary"] = summary(grouped[item["id"]])
        item["problem_count"] = counts.get(item["id"], 0)
    return items


async def personal_detail(db, task_id, identity):
    task = await tasks.get_task(db, task_id)
    if task["state"] == "draft":
        raise tasks.TaskError("训练任务不存在或无权查看。", "not_found", 404)
    now = int(time.time())
    recipients = await recipient_summaries(db, [task_id], qq_id=identity["qq_id"], epoch=identity["account_epoch"], now=now)
    if not recipients:
        raise tasks.TaskError("训练任务不存在或无权查看。", "not_found", 404)
    task = await tasks.detail(db, task_id)
    task.pop("recipient_count", None)
    task.pop("creator_qq_id", None)
    task.pop("audit", None)
    task["recipient"] = recipients[0]
    task["problems"] = await problem_progress(db, recipients[0], now=now)
    return task


async def problem_progress(db, recipient, *, now=None):
    now = int(time.time()) if now is None else now
    records = await tasks.rows(db, """
      SELECT p.*,x.history_json,x.on_time_json,x.late_json,x.checked_at,x.sync_success_at,x.binding_key,x.binding_version,
      r.bindings_json,r.account_epoch,r.closed,t.due_at,u.account_state,u.account_epoch AS current_epoch,a.is_active,
      u.cf_handle,u.cf_binding_version,s.binding_key AS sync_binding,s.full_history_at,s.last_status AS sync_status,s.coverage_through_at
      FROM training_task_problems p JOIN training_task_progress x ON x.problem_id=p.id AND x.recipient_id=?
      JOIN training_task_recipients r ON r.id=x.recipient_id JOIN training_tasks t ON t.id=r.task_id
      LEFT JOIN users u ON u.qq_id=r.qq_id LEFT JOIN web_accounts a ON a.qq_id=r.qq_id
      LEFT JOIN user_platform_sync_state s ON s.user_qq_id=r.qq_id AND s.platform=p.platform
      WHERE p.task_id=? ORDER BY p.position""", (recipient["id"], recipient["task_id"]))
    for row in records:
        _, _, _, row["verification"] = live_state(row, now)
        row["tags"] = json.loads(row.pop("tags_json"))
        historical, timely, late = [evidence(row.pop(key)) for key in ("history_json", "on_time_json", "late_json")]
        accepted = timely or (historical if recipient["rule"] == "historical_ac" else None)
        row["status"] = "not_started" if recipient["phase"] == "upcoming" else "on_time" if accepted else "late" if late else "history_ac" if historical else "pending"
        row["evidence"] = accepted or late or historical
        for key in ("cf_handle", "cf_binding_version", "binding_key", "binding_version", "bindings_json", "account_epoch", "closed", "due_at", "account_state", "current_epoch", "is_active", "sync_binding", "full_history_at"):
            row.pop(key, None)
    return records
