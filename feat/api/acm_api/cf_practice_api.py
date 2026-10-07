"""Admin-only CF practice endpoints using the existing session and CSRF guard."""
from quart import Blueprint, current_app, jsonify, request

from .backend_api import admin_required, get_db
from .cf_practice import PracticeError, options


cf_practice_api = Blueprint("cf_practice", __name__)


async def payload():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        raise PracticeError("请求须为 JSON 对象")
    return data


async def snapshot(operation, data):
    db = await get_db()
    try:
        await db.execute("BEGIN")
        return await operation(db, data)
    finally:
        await db.rollback()
        await db.close()


@cf_practice_api.errorhandler(PracticeError)
async def invalid_request(error):
    return jsonify({"success": False, "code": error.code, "message": str(error)}), error.status


@cf_practice_api.get("/admin/cf/options")
@admin_required
async def cf_options():
    async def read(db, _):
        return await options(db)
    result = await snapshot(read, None)
    result["data_ttl_seconds"] = current_app.config["CF_PRACTICE_QUERY"].data_ttl
    return jsonify(result)


@cf_practice_api.post("/admin/cf/overview")
@admin_required
async def cf_overview():
    return jsonify(await snapshot(current_app.config["CF_PRACTICE_QUERY"].overview, await payload()))


@cf_practice_api.post("/admin/cf/problem-members")
@admin_required
async def cf_problem_members():
    return jsonify(await snapshot(current_app.config["CF_PRACTICE_QUERY"].problem_members, await payload()))


@cf_practice_api.post("/admin/cf/check")
@admin_required
async def cf_check():
    data = await payload()
    result, pending = await snapshot(current_app.config["CF_PRACTICE_QUERY"].check, data)
    if pending:
        job_id = await current_app.config["CF_PRACTICE_JOBS"].submit("check", data)
        return jsonify({"status": "queued", "job_id": job_id, "scope": result["scope"], "preview": result}), 202
    return jsonify(result)


@cf_practice_api.post("/admin/cf/sync")
@admin_required
async def cf_sync():
    data = await payload()
    job_id = await current_app.config["CF_PRACTICE_JOBS"].submit("sync", data)
    return jsonify({"status": "queued", "job_id": job_id}), 202


@cf_practice_api.get("/admin/cf/jobs/<job_id>")
@admin_required
async def cf_job(job_id):
    return jsonify(await current_app.config["CF_PRACTICE_JOBS"].get(job_id))
