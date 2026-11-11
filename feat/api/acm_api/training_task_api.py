"""Assigned training HTTP contract. Reads never call an OJ or enqueue work."""
import inspect
import time
from functools import wraps

from . import training_task_progress as progress

from quart import Blueprint, current_app, g, jsonify, request

from . import training_task_service as service
from .account_lifecycle_service import AccountLifecycleError, require_web_actor
from .backend_api import admin_required, get_db, member_required

training_task_api = Blueprint("training_task_api", __name__, url_prefix="/api")


def endpoint(*, admin=True):
    def decorate(func):
        @wraps(func)
        async def handler(*args, **kwargs):
            db = await get_db()
            try:
                identity = request.web_identity
                if request.method not in {"GET", "HEAD"}:
                    await db.execute("BEGIN IMMEDIATE")
                    await require_web_actor(db, identity, roles={"admin", "root"} if admin else None)
                result = await func(db, identity, *args, **kwargs)
                await db.commit()
                return result
            except (service.TaskError, AccountLifecycleError) as error:
                await db.rollback()
                return jsonify({"success": False, "code": error.code, "message": str(error), "request_id": getattr(g, "log_request_id", None), **getattr(error, "details", {})}), error.status
            finally:
                await db.close()
        return (admin_required if admin else member_required)(handler)
    return decorate


async def body():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        raise service.TaskError("请求内容须为 JSON 对象。")
    return data


@training_task_api.after_request
async def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@training_task_api.get("/admin/training-tasks/options")
@endpoint()
async def options(db, identity):
    statuses = await service.rows(db, "SELECT DISTINCT status FROM users WHERE status IS NOT NULL AND TRIM(status)<>'' ORDER BY status")
    return jsonify({"enabled": current_app.config.get("TRAINING_TASKS_ENABLED", False), "statuses": [s["status"] for s in statuses], "capabilities": service.CAPABILITIES, "max_problems": service.MAX_PROBLEMS, "timezone": "Asia/Shanghai"})


@training_task_api.post("/admin/training-tasks/resolve-problems")
@endpoint()
async def resolve_problems(db, identity):
    data = await body()
    return jsonify(await service.resolve_problems(db, data.get("problems")))


@training_task_api.route("/admin/training-tasks", methods=["GET", "POST"])
@endpoint()
async def tasks(db, identity):
    if request.method == "POST":
        return jsonify(await service.save_draft(db, identity, await body())), 201
    page, size = service.paging(request.args)
    state, search = request.args.get("state", ""), request.args.get("search", "").strip()[:100]
    clauses, values = [], []
    if state:
        if state not in {"draft", "published", "cancelled"}:
            raise service.TaskError("任务状态无效。")
        clauses.append("state=?")
        values.append(state)
    if search:
        clauses.append("title LIKE ?")
        values.append("%" + search + "%")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = (await service.one(db, "SELECT COUNT(*) AS n FROM training_tasks" + where, values))["n"]
    items = await service.rows(db, "SELECT * FROM training_tasks" + where + " ORDER BY id DESC LIMIT ? OFFSET ?", [*values, size, (page - 1) * size])
    items = [service.public_task(item) for item in items]
    await progress.add_summaries(db, items)
    return jsonify({"items": items, "page": page, "page_size": size, "total": total})


@training_task_api.route("/admin/training-tasks/<int:task_id>", methods=["GET", "PATCH", "DELETE"])
@endpoint()
async def task_detail(db, identity, task_id):
    if request.method == "PATCH":
        return jsonify(await service.save_draft(db, identity, await body(), task_id))
    if request.method == "DELETE":
        return jsonify(await service.lifecycle(db, identity, task_id, "delete", await body()))
    task = await service.detail(db, task_id)
    await progress.add_summaries(db, [task])
    return jsonify(task)


@training_task_api.post("/admin/training-tasks/<int:task_id>/audience-preview")
@endpoint()
async def audience_preview(db, identity, task_id):
    page, size = service.paging(request.args)
    token, members = await service.preview(db, task_id, await body())
    eligible = [m for m in members if not m["excluded_reason"]]
    public = [{k: v for k, v in m.items() if k not in {"bindings", "credential_version", "account_epoch"}} for m in members]
    return jsonify({"preview_token": token, "expires_in": service.PREVIEW_TTL, "total": len(members), "recipient_count": len(eligible), "excluded_count": len(members) - len(eligible), "unbound_count": sum(m["unbound"] for m in eligible), "items": public[(page - 1) * size:page * size], "page": page, "page_size": size})


@training_task_api.post("/admin/training-tasks/<int:task_id>/publish")
@endpoint()
async def publish(db, identity, task_id):
    if not current_app.config.get("TRAINING_TASKS_ENABLED", False):
        raise service.TaskError("训练任务发放尚未开放，历史记录仍可查看。", "feature_disabled", 503)
    return jsonify(await service.publish(db, identity, task_id, await body(), request.headers.get("Idempotency-Key")))


@training_task_api.post("/admin/training-tasks/<int:task_id>/extend-deadline")
@training_task_api.post("/admin/training-tasks/<int:task_id>/cancel")
@endpoint()
async def lifecycle(db, identity, task_id):
    action = request.path.rsplit("/", 1)[-1]
    return jsonify(await service.lifecycle(db, identity, task_id, action, await body()))


@training_task_api.get("/admin/training-tasks/<int:task_id>/progress")
@endpoint()
async def admin_progress(db, identity, task_id):
    await service.get_task(db, task_id)
    page, size = service.paging(request.args)
    members = await progress.recipient_summaries(db, [task_id])
    overview = progress.summary(members)
    status = request.args.get("status", "")
    cohort = request.args.get("identity", "")
    if status not in {"", "on_time", "late", "incomplete", "not_started", "pending", "abnormal"}:
        raise service.TaskError("完成状态筛选无效。")
    search = request.args.get("search", "").strip().casefold()[:100]
    selected = [r for r in members if (not cohort or r["status_snapshot"] == cohort)
                and (not search or search in r["name"].casefold() or search in str(r["qq_id"] or ""))
                and (not status or (r["pending"] if status == "pending" else r["account_status"] != "active" if status == "abnormal" else r["completion"] == status))]
    return jsonify({"summary": overview, "items": selected[(page - 1) * size:page * size], "total": len(selected), "page": page, "page_size": size})


@training_task_api.get("/admin/training-tasks/<int:task_id>/progress/<int:recipient_id>")
@endpoint()
async def recipient_progress(db, identity, task_id, recipient_id):
    recipients = await progress.recipient_summaries(db, [task_id])
    recipient = next((r for r in recipients if r["id"] == recipient_id), None)
    if not recipient:
        raise service.TaskError("接收记录不存在。", "not_found", 404)
    return jsonify({"recipient": recipient, "problems": await progress.problem_progress(db, recipient)})


async def queue_snapshots():
    provider = current_app.config.get("PLUGIN_CONFIG", {}).get("_task_provider")
    result = provider() if callable(provider) else []
    return await result if inspect.isawaitable(result) else result


def public_refresh(item):
    return {key: item.get(key) for key in ("id", "status", "started_at", "finished_at", "error", "result")}


@training_task_api.get("/me/training-tasks")
@endpoint(admin=False)
async def my_tasks(db, identity):
    page, size = service.paging(request.args)
    tab = request.args.get("tab", "active")
    now = int(time.time())
    conditions = {"active": "t.state='published' AND t.starts_at<=? AND t.due_at>=?", "upcoming": "t.state='published' AND t.starts_at>?", "history": "(t.state='cancelled' OR t.due_at<?)", "all": "1=1"}
    if tab not in conditions:
        raise service.TaskError("任务分组无效。")
    times = [now, now] if tab == "active" else [now] if tab in {"upcoming", "history"} else []
    values = [identity["qq_id"], identity["account_epoch"], *times]
    where = " FROM training_tasks t JOIN training_task_recipients r ON r.task_id=t.id WHERE r.qq_id=? AND r.account_epoch=? AND t.state<>'draft' AND " + conditions[tab]
    total = (await service.one(db, "SELECT COUNT(*) AS n" + where, values))["n"]
    items = await service.rows(db, "SELECT t.*" + where + " ORDER BY t.due_at,t.id DESC LIMIT ? OFFSET ?", [*values, size, (page - 1) * size])
    items = [service.public_task(t) for t in items]
    recipients = {r["task_id"]: r for r in await progress.recipient_summaries(db, [t["id"] for t in items], qq_id=identity["qq_id"], epoch=identity["account_epoch"])}
    for task in items:
        task.pop("creator_qq_id", None)
        task["recipient"] = recipients[task["id"]]
    return jsonify({"items": items, "total": total, "page": page, "page_size": size})


@training_task_api.get("/me/training-tasks/<int:task_id>")
@endpoint(admin=False)
async def my_task(db, identity, task_id):
    result = await progress.personal_detail(db, task_id, identity)
    task_id_in_queue = result["recipient"].get("refresh_task_id")
    found = next((t for t in await queue_snapshots() if t["id"] == task_id_in_queue and str(t.get("qq_id")) == identity["qq_id"] and t.get("account_epoch") == identity["account_epoch"]), None)
    result["refresh"] = public_refresh(found) if found else {"id": task_id_in_queue, "status": "interrupted"} if task_id_in_queue else None
    return jsonify(result)


@training_task_api.post("/me/training-tasks/<int:task_id>/refresh")
@endpoint(admin=False)
async def refresh(db, identity, task_id):
    data = await body()
    if data:
        raise service.TaskError("刷新由当前会话确定成员，不接受额外参数。")
    detail = await progress.personal_detail(db, task_id, identity)
    if detail["state"] != "published":
        raise service.TaskError("任务已取消，不能发起同步。", "task_cancelled", 409)
    user = await service.one(db, "SELECT * FROM users WHERE qq_id=?", (identity["qq_id"],))
    if not user["cf_handle"]:
        raise service.TaskError("请先在个人中心绑定 Codeforces 账号，再返回当前任务。", "binding_required", 409)
    for task in await queue_snapshots():
        if str(task.get("qq_id")) == identity["qq_id"] and task.get("account_epoch") == identity["account_epoch"] and "codeforces" in str(task.get("platform", "")) and task.get("status") in {"queued", "running"}:
            captured = task.get("bindings", {}).get("codeforces")
            if captured and (str(captured.get("account", "")).casefold() != str(user["cf_handle"]).casefold() or captured.get("version") != user["cf_binding_version"]):
                continue
            await db.execute("UPDATE training_task_recipients SET refresh_task_id=? WHERE id=?", (task["id"], detail["recipient"]["id"]))
            return jsonify({"status": task["status"], "task": public_refresh(task), "deduplicated": True}), 202
    now = int(time.time())
    limit = await service.one(db, "SELECT last_at FROM binding_rate_limits WHERE qq_id=? AND platform='codeforces' AND action='training_task_refresh'", (identity["qq_id"],))
    if limit and now - limit["last_at"] < 60:
        raise service.TaskError("同步请求过于频繁，请稍后重试。", "refresh_rate_limited", 429, retry_after=60 - (now - limit["last_at"]))
    submitter = current_app.config.get("PLUGIN_CONFIG", {}).get("_account_sync_submitter")
    if not callable(submitter):
        raise service.TaskError("同步服务暂不可用，已有进度保留。", "sync_unavailable", 503)
    queued = submitter(identity["qq_id"], ["codeforces"], 0, expected_epoch=identity["account_epoch"])
    if inspect.isawaitable(queued):
        queued = await queued
    if not queued:
        raise service.TaskError("同步队列繁忙，请稍后重试。", "sync_busy", 409)
    await db.execute("INSERT INTO binding_rate_limits(qq_id,platform,action,window_start,attempts,last_at) VALUES(?,'codeforces','training_task_refresh',?,1,?) ON CONFLICT(qq_id,platform,action) DO UPDATE SET last_at=excluded.last_at,attempts=binding_rate_limits.attempts+1", (identity["qq_id"], now, now))
    await db.execute("UPDATE training_task_recipients SET refresh_task_id=?,refresh_at=? WHERE id=?", (queued["id"], now, detail["recipient"]["id"]))
    return jsonify({"status": "queued", "task": {**queued, "status": "queued"}}), 202
