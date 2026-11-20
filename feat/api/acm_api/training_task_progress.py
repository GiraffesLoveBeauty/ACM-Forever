"""Local, batched AC evidence aggregation. No external requests in this module."""
import json
import time
from collections import defaultdict

from . import training_task_service as tasks
from .binding_service import platform_spec
from . import training_task_snapshot as snapshots


def evidence(value):
    return json.loads(value) if value else None


def first_evidence(values):
    return min(values, key=lambda item: item["accepted_at"]) if values else None


def live_state(row, now):
    """Derive verification from current identity; frozen evidence stays intact."""
    if not tasks.supports_ac(row, row):
        return None, 0, False, "unsupported"
    platform, field, version_field = platform_spec(row["platform"])
    bindings = json.loads(row["bindings_json"])
    original = bindings.get(platform, {})
    anchor = row["binding_key"] or (f'{original["account"]}:{original["version"]}' if original.get("account") else None)
    generation = row.get("binding_version", 0) if row["binding_key"] else original.get("version", 0)
    account = str(row.get(field) or "").strip().casefold()
    current = f'{account}:{row[version_field]}' if account else None
    active = not row["closed"] and row["account_state"] == "active" and row["account_epoch"] == row["current_epoch"]
    legacy_luogu = platform == "luogu" and platform not in bindings
    if active and not anchor and current and (legacy_luogu or row[version_field] == original.get("version", 0) + 1):
        anchor, generation = current, row[version_field]
    valid = bool(active and anchor and anchor == current)
    snapshot = evidence(row.get("snapshot_json")) or {}
    snapshot_checked = row.get("snapshot_checked_at", snapshot.get("last_checked_at", 0)) or 0
    conclusive = row.get("unresolved_problems") == 0 if "unresolved_problems" in row else bool(
        row.get("on_time_json") or row.get("late_json") or (platform == "luogu" or row.get("rule") == "historical_ac") and row.get("history_json"))
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
    elif row["sync_status"] == "waiting" and not conclusive:
        verification = "sync_waiting"
    elif row["sync_status"] in {"failed", "error"}:
        verification = "sync_failed"
    elif platform == "luogu":
        if row.get("snapshot_conflict", snapshot.get("conflict", False)):
            verification = "snapshot_conflict"
        elif conclusive:
            verification = "verified"
        elif not snapshot_checked:
            verification = "baseline_missing"
        elif snapshot_checked < now - 900:
            verification = "pending_sync"
        else:
            verification = "verified"
    elif row["sync_binding"] != anchor or not row["full_history_at"]:
        verification = "coverage_missing"
    elif (row["coverage_through_at"] or 0) < min(now - 60, row["due_at"]):
        verification = "pending_sync"
    else:
        verification = "verified"
    return anchor, generation, valid, verification


async def progress_records(db, where, params):
    return await tasks.rows(db, """
        SELECT x.*,r.qq_id,r.account_epoch,r.bindings_json,r.closed,
        t.starts_at,t.due_at,t.rule,t.luogu_snapshot,t.state,p.platform,p.problem_id AS canonical_id,
        u.cf_handle,u.cf_binding_version,u.luogu_id,u.luogu_binding_version,
        u.account_state,u.account_epoch AS current_epoch,a.is_active,
        s.binding_key AS sync_binding,s.full_history_at,s.coverage_through_at,s.last_status AS sync_status,s.last_success_at
        FROM training_task_progress x JOIN training_task_recipients r ON r.id=x.recipient_id
        JOIN training_task_problems p ON p.id=x.problem_id JOIN training_tasks t ON t.id=r.task_id
        LEFT JOIN users u ON u.qq_id=r.qq_id LEFT JOIN web_accounts a ON a.qq_id=r.qq_id
        LEFT JOIN user_platform_sync_state s ON s.user_qq_id=r.qq_id AND s.platform=p.platform
        WHERE """ + where, params)


async def store_snapshot(db, row, snapshot, now):
    history, timely, late, uncertain = snapshots.classify(
        snapshot, starts_at=row["starts_at"], due_at=row["due_at"], rule=row["rule"],
        problem_id=row["canonical_id"], review=evidence(row["review_json"]))
    encoded = [tasks.dump(value) if value else None for value in (snapshot, history, timely, late, uncertain)]
    changed = any(row.get(key) != value for key, value in zip(
        ("snapshot_json", "history_json", "on_time_json", "late_json", "uncertain_json"), encoded))
    current = {**row, "snapshot_json": encoded[0], "history_json": encoded[1], "on_time_json": encoded[2], "late_json": encoded[3]}
    anchor, generation, _, verification = live_state(current, now)
    await db.execute("""UPDATE training_task_progress SET binding_key=?,binding_version=?,snapshot_json=?,
        history_json=?,on_time_json=?,late_json=?,uncertain_json=?,verification=?,checked_at=?,sync_success_at=?,
        evidence_version=evidence_version+? WHERE recipient_id=? AND problem_id=?""",
        (anchor, generation, *encoded, verification, now,
         (snapshot or {}).get("last_checked_at", 0) or row.get("sync_success_at", 0), int(changed), row["recipient_id"], row["problem_id"]))


async def record_luogu_snapshot(db, user, passed, known, *, requested_at, observed_at):
    """Called inside the guarded AC write transaction, including zero-new-AC syncs."""
    records = await progress_records(db, "t.state='published' AND r.qq_id=? AND p.platform='luogu'", [str(user["qq_id"])])
    for row in records:
        _, _, valid, _ = live_state(row, observed_at)
        if not valid:
            continue
        pid = row["canonical_id"].casefold()
        snapshot = snapshots.observe(evidence(row["snapshot_json"]), accepted=pid in passed,
                                     known_ac=pid in known, requested_at=requested_at, observed_at=observed_at)
        if snapshot == evidence(row["snapshot_json"]):
            continue
        await store_snapshot(db, row, snapshot, observed_at)


async def reconcile(db, *, qq_id=None, task_id=None, platform=None, now=None):
    """Caller holds the write transaction; never join evidence across a binding fence."""
    now = int(time.time()) if now is None else now
    clauses, params = ["t.state='published'"], []
    if qq_id is not None:
        clauses.append("r.qq_id=?")
        params.append(str(qq_id))
    if task_id is not None:
        clauses.append("t.id=?")
        params.append(task_id)
    if platform is not None:
        clauses.append("p.platform=?")
        params.append(platform)
    where = " AND ".join(clauses)
    records = await progress_records(db, where, params)
    # Three minimum timestamps per assigned problem retain repeat AC information.
    found = []
    if any(r["platform"] == "codeforces" for r in records):
        found = await tasks.rows(db, """
            SELECT r.id AS recipient_id,p.id AS problem_id,
            MIN(CASE WHEN a.submitted_at<t.starts_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS historical,
            MIN(CASE WHEN a.submitted_at>=t.starts_at AND a.submitted_at<=t.due_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS timely,
            MIN(CASE WHEN a.submitted_at>t.due_at THEN printf('%012d|',a.submitted_at)||COALESCE(a.external_submission_id,'') END) AS late
            FROM training_task_recipients r JOIN training_tasks t ON t.id=r.task_id
            JOIN training_task_problems p ON p.task_id=t.id
            JOIN submission_attempts a ON a.owner_qq_id=r.qq_id AND a.platform=p.platform
              AND a.problem_id IN(p.problem_id,substr(p.problem_id,4)) AND a.verdict='OK' AND a.submitted_at<=?
            WHERE """ + where + " AND p.platform='codeforces' GROUP BY r.id,p.id", [now, *params])
    found = {(r["recipient_id"], r["problem_id"]): r for r in found}
    local_ac = set()
    if any(r["platform"] == "luogu" and not (evidence(r["snapshot_json"]) or {}).get("first_seen_at") for r in records):
        positives = await tasks.rows(db, """
            SELECT r.id AS recipient_id,p.id AS problem_id
            FROM training_task_recipients r JOIN training_tasks t ON t.id=r.task_id
            JOIN training_task_problems p ON p.task_id=t.id
            JOIN submissions a ON a.user_qq_id=r.qq_id AND a.platform='luogu'
             AND a.problem_id COLLATE NOCASE IN(p.problem_id,'luogu_'||p.problem_id)
            WHERE """ + where + " AND p.platform='luogu'", params)
        local_ac = {(r["recipient_id"], r["problem_id"]) for r in positives}
    updates = []
    for row in records:
        anchor, generation, valid, verification = live_state(row, now)
        if row["platform"] == "luogu":
            if not tasks.supports_ac(row, row):
                continue
            snapshot = evidence(row["snapshot_json"])
            if valid and not (snapshot or {}).get("first_seen_at") and (row["recipient_id"], row["problem_id"]) in local_ac:
                snapshot = snapshots.local_positive(now)
            await store_snapshot(db, row, snapshot, now)
            continue
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
        ontime, late = row.get("luogu_completed_problems", 0), 0
    else:
        row["completion"] = "on_time" if total and ontime == total else "late" if total and ontime + late == total else "timing_unknown" if row.get("uncertain_problems") else "incomplete"
    row["on_time_problems"], row["late_problems"] = ontime, late
    row["completed_problems"] = ontime + late
    row["account_status"] = "closed" if row["closed"] else "changed" if row["current_epoch"] != row["account_epoch"] else "disabled" if not row["is_active"] else "active"
    row["pending"] = bool(row["pending_problems"] or row["binding_warnings"] or row.get("uncertain_problems") or row["account_status"] != "active")
    for key in ("cf_handle", "cf_binding_version", "luogu_id", "luogu_binding_version", "snapshot_checked_at", "snapshot_conflict", "unresolved_problems", "current_epoch", "is_active", "bindings_json", "platform", "binding_key", "binding_version", "account_state", "sync_binding", "full_history_at", "coverage_through_at", "sync_status"):
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
        SELECT r.*{name_column},t.starts_at,t.due_at,t.state,t.rule,t.luogu_snapshot,u.account_epoch AS current_epoch,u.account_state,
        u.cf_handle,u.cf_binding_version,u.luogu_id,u.luogu_binding_version,a.is_active,p.platform,x.binding_key,MAX(x.binding_version) AS binding_version,
        s.binding_key AS sync_binding,s.full_history_at,s.coverage_through_at,s.last_status AS sync_status,
        COUNT(x.problem_id) AS problem_count,
        SUM(CASE WHEN p.platform='luogu' AND x.history_json IS NOT NULL THEN 1 ELSE 0 END) AS luogu_completed_problems,
        SUM(CASE WHEN x.on_time_json IS NOT NULL OR ((t.rule='historical_ac' OR p.platform='luogu') AND x.history_json IS NOT NULL) THEN 1 ELSE 0 END) AS on_time_problems,
        SUM(CASE WHEN x.on_time_json IS NULL AND NOT((t.rule='historical_ac' OR p.platform='luogu') AND x.history_json IS NOT NULL) AND x.late_json IS NOT NULL THEN 1 ELSE 0 END) AS late_problems,
        SUM(CASE WHEN x.uncertain_json IS NOT NULL THEN 1 ELSE 0 END) AS uncertain_problems,
        SUM(CASE WHEN x.history_json IS NOT NULL OR x.on_time_json IS NOT NULL OR x.late_json IS NOT NULL OR x.uncertain_json IS NOT NULL THEN 1 ELSE 0 END) AS ac_problems,
        SUM(CASE WHEN x.on_time_json IS NULL AND x.late_json IS NULL AND NOT((t.rule='historical_ac' OR p.platform='luogu') AND x.history_json IS NOT NULL) THEN 1 ELSE 0 END) AS unresolved_problems,
        MIN(COALESCE(json_extract(x.snapshot_json,'$.last_checked_at'),0)) AS snapshot_checked_at,
        MAX(COALESCE(json_extract(x.snapshot_json,'$.conflict'),0)) AS snapshot_conflict,
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
        row["unsupported_problems"] = row["problem_count"] if verification == "unsupported" else 0
        if verification == "unsupported":
            for key in ("on_time_problems", "late_problems", "uncertain_problems", "ac_problems"):
                row[key] = 0
        row["pending_problems"] = row["problem_count"] if verification not in {"verified", "unsupported"} else 0
        row["binding_warnings"] = row["problem_count"] if not valid and verification != "unsupported" else 0
        previous = grouped.get(row["id"])
        if previous is None:
            grouped[row["id"]] = row
        else:
            had_supported = previous["problem_count"] > previous["unsupported_problems"]
            for key in ("problem_count", "on_time_problems", "late_problems", "pending_problems", "binding_warnings", "uncertain_problems", "ac_problems", "unsupported_problems", "luogu_completed_problems"):
                previous[key] += row[key]
            for key in ("checked_at", "last_success_at"):
                if verification != "unsupported":
                    previous[key] = min(previous[key], row[key]) if had_supported else row[key]
    return [recipient_state(row, now) for row in grouped.values()]


def summary(recipients):
    return {"recipient_count": len(recipients), "on_time_count": sum(r["completion"] == "on_time" for r in recipients),
            "late_count": sum(r["completion"] == "late" for r in recipients), "pending_count": sum(r["pending"] for r in recipients),
            "uncertain_count": sum(bool(r.get("uncertain_problems")) for r in recipients),
            "uncertain_problem_count": sum(r.get("uncertain_problems", 0) for r in recipients),
            "ac_problem_count": sum(r.get("ac_problems", 0) for r in recipients),
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
      SELECT p.*,x.history_json,x.on_time_json,x.late_json,x.uncertain_json,x.snapshot_json,x.review_json,
      x.evidence_version AS progress_version,x.checked_at,x.sync_success_at,x.binding_key,x.binding_version,
      r.bindings_json,r.account_epoch,r.closed,t.due_at,t.starts_at,t.rule,t.luogu_snapshot,t.state,u.account_state,u.account_epoch AS current_epoch,a.is_active,
      u.cf_handle,u.cf_binding_version,u.luogu_id,u.luogu_binding_version,s.binding_key AS sync_binding,s.full_history_at,s.last_status AS sync_status,s.coverage_through_at
      FROM training_task_problems p JOIN training_task_progress x ON x.problem_id=p.id AND x.recipient_id=?
      JOIN training_task_recipients r ON r.id=x.recipient_id JOIN training_tasks t ON t.id=r.task_id
      LEFT JOIN users u ON u.qq_id=r.qq_id LEFT JOIN web_accounts a ON a.qq_id=r.qq_id
      LEFT JOIN user_platform_sync_state s ON s.user_qq_id=r.qq_id AND s.platform=p.platform
      WHERE p.task_id=? ORDER BY p.position""", (recipient["id"], recipient["task_id"]))
    for row in records:
        _, _, valid, row["verification"] = live_state(row, now)
        row["tags"] = json.loads(row.pop("tags_json"))
        historical, timely, late, uncertain = [evidence(row.pop(key)) for key in ("history_json", "on_time_json", "late_json", "uncertain_json")]
        row["supported"] = tasks.supports_ac(row, row)
        if not row["supported"]:
            historical = timely = late = uncertain = None
        accepted = timely or (historical if row["platform"] == "luogu" or recipient["rule"] == "historical_ac" else None)
        row["status"] = "unverified" if not row["supported"] else "not_started" if recipient["phase"] == "upcoming" else "on_time" if accepted else "late" if late else "history_ac" if historical else "timing_unknown" if uncertain else "pending"
        row["evidence"] = accepted or late or historical or uncertain
        row["is_ac"] = bool(row["evidence"])
        row.pop("review_json")
        row["review"] = None
        row["can_review"] = False
        row["can_clear_review"] = False
        row["can_reset_binding"] = row["platform"] == "luogu" and row["state"] == "published" and row["verification"] == "binding_changed" and bool(row["luogu_id"]) and not (accepted or late)
        row.pop("snapshot_json", None)
        for key in ("cf_handle", "cf_binding_version", "luogu_id", "luogu_binding_version", "rule", "state", "starts_at", "binding_key", "binding_version", "bindings_json", "account_epoch", "closed", "due_at", "account_state", "current_epoch", "is_active", "sync_binding", "full_history_at"):
            row.pop(key, None)
    await tasks.attach_problem_state(db, records, recipient)
    return records


async def xcpc_scoreboard(db, task, recipients, *, now=None):
    """Build one batched presentation payload for the admin XCPC-style table.

    The recipient list has already been filtered and ordered by the API handler. Cells
    deliberately expose evidence state rather than inventing submission attempts when
    a platform does not provide them. Penalty is the elapsed minute from the task start
    for accepted evidence after the start; historical AC contributes zero penalty.
    """
    now = int(time.time()) if now is None else now
    columns = []
    for problem in task.get("problems", []):
        columns.append({"key": str(problem.get("id", problem.get("problem_id", ""))),
                        "label": chr(65 + len(columns)) if len(columns) < 26 else str(len(columns) + 1),
                        "problem_id": problem.get("problem_id", ""),
                        "problem_name": problem.get("problem_name", ""),
                        "platform": problem.get("platform", "")})
    rows = []
    starts = int(task.get("starts_at") or 0)
    for recipient in recipients:
        details = await problem_progress(db, recipient, now=now)
        by_key = {str(item.get("id", item.get("problem_id", ""))): item for item in details}
        cells = []
        penalty = 0
        solved = 0
        for column in columns:
            item = by_key.get(column["key"], {})
            status = item.get("status", "pending")
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else None
            accepted = int(evidence.get("accepted_at", 0)) if evidence else 0
            is_ac = bool(item.get("is_ac"))
            if is_ac:
                solved += 1
                if accepted and starts and accepted >= starts:
                    penalty += max(0, (accepted - starts) // 60)
                cells.append({"state": "solved", "label": "+1", "accepted_at": accepted})
            elif status in {"pending", "timing_unknown", "unverified"}:
                cells.append({"state": "pending", "label": "?"})
            else:
                cells.append({"state": "empty", "label": "—"})
        rows.append({"id": recipient.get("id"), "rank": recipient.get("rank"),
                     "name": recipient.get("name", ""), "real_name": recipient.get("real_name"),
                     "completed_problems": solved, "problem_count": len(columns),
                     "penalty_minutes": penalty, "cells": cells})
    return {"columns": columns, "rows": rows, "penalty_definition": "按时段内首次已核验 AC 的分钟数；历史 AC 不计罚时，未知尝试显示为状态，不伪造次数。"}
