"""Assigned training HTTP contract. Reads never call an OJ or enqueue work."""
from functools import wraps

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
    items = await service.rows(db, "SELECT id FROM training_tasks" + where + " ORDER BY id DESC LIMIT ? OFFSET ?", [*values, size, (page - 1) * size])
    # Detail queries are bounded to one page; progress summaries use batch aggregation (#120).
    items = [await service.get_task(db, item["id"]) for item in items]
    return jsonify({"items": items, "page": page, "page_size": size, "total": total})


@training_task_api.route("/admin/training-tasks/<int:task_id>", methods=["GET", "PATCH", "DELETE"])
@endpoint()
async def task_detail(db, identity, task_id):
    if request.method == "PATCH":
        return jsonify(await service.save_draft(db, identity, await body(), task_id))
    if request.method == "DELETE":
        return jsonify(await service.lifecycle(db, identity, task_id, "delete", await body()))
    return jsonify(await service.detail(db, task_id))


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
