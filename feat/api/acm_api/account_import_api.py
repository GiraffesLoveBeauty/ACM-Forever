"""HTTP boundary for the named-admin Excel import workflow."""
import asyncio
import time
from functools import wraps
from pathlib import Path

from quart import Blueprint, Response, current_app, jsonify, request

from . import account_import_service as service
from .account_import_excel import MAX_FILE_BYTES, MAX_ROWS, MIME, TEMPLATE_VERSION, report_bytes, template_bytes
from .backend_api import _session_identity, _temporary_password_ttl_hours, admin_required, get_db

account_import_api = Blueprint("account_import_api", __name__, url_prefix="/api/admin/account-imports")


def endpoint(*, enabled=True):
    def decorate(func):
        @admin_required
        @wraps(func)
        async def handler(*args, **kwargs):
            db = await get_db()
            try:
                identity = await _session_identity()
                await service.actor_snapshot(db, identity)
                if enabled and not current_app.config.get("ACCOUNT_IMPORT_ENABLED", False):
                    raise service.ImportError("Excel导入尚未启用，请联系管理员。", "import_disabled", 503)
                return await func(db, identity, *args, **kwargs)
            except service.AccountCreationError as exc:
                return jsonify({"success": False, "code": exc.code, "message": str(exc)}), exc.status
            finally:
                await db.close()
        return handler
    return decorate


@account_import_api.after_request
async def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@account_import_api.get("/capabilities")
@endpoint(enabled=False)
async def capabilities(db, identity):
    async with db.execute("SELECT DISTINCT status FROM users WHERE status IS NOT NULL AND TRIM(status)<>'' LIMIT 100") as cursor:
        statuses = [v["status"] for v in await cursor.fetchall()]
    return jsonify({"enabled": bool(current_app.config.get("ACCOUNT_IMPORT_ENABLED", False)), "template_version": TEMPLATE_VERSION, "max_file_bytes": MAX_FILE_BYTES, "max_rows": MAX_ROWS, "chunk_size": service.CHUNK_SIZE, "preview_ttl_seconds": service.PREVIEW_SECONDS, "execution_ttl_seconds": service.EXECUTION_SECONDS, "temporary_password_ttl_hours": _temporary_password_ttl_hours(), "statuses": statuses})


def workbook_response(content, filename):
    return Response(content, mimetype=MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@account_import_api.get("/template")
@endpoint()
async def download_template(db, identity):
    content = await asyncio.to_thread(template_bytes)
    await service.actor_snapshot(db, identity)
    return workbook_response(content, "account-import-v1.xlsx")


@account_import_api.post("/preview")
@endpoint()
async def upload_preview(db, identity):
    actor = await service.actor_snapshot(db, identity)
    await service.cleanup(db)
    await service.check_capacity(db, actor)
    files, form = await request.files, await request.form
    if set(files) != {"file"} or len(files.getlist("file")) != 1 or form:
        raise service.ImportError("上传只接受一个file文件，不接受额外参数。", "invalid_upload", 400)
    upload = files["file"]
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise service.ImportError("只接受.xlsx模板文件。", "invalid_extension", 400)
    content = upload.read(MAX_FILE_BYTES + 1)
    if not content or len(content) > MAX_FILE_BYTES:
        raise service.ImportError("文件为空或超过5MiB。", "file_size", 413)
    parsed = await service.parse_upload(content)
    result = await service.preview(db, identity, content, parsed, _temporary_password_ttl_hours())
    return jsonify(result), 201


@account_import_api.get("/<batch_id>")
@endpoint(enabled=False)
async def get_summary(db, identity, batch_id):
    return jsonify(await service.summary(db, identity, batch_id))


@account_import_api.get("/<batch_id>/rows")
@endpoint(enabled=False)
async def get_rows(db, identity, batch_id):
    try:
        page, size = int(request.args.get("page", "1")), int(request.args.get("page_size", "100"))
    except (ValueError, TypeError):
        raise service.ImportError("页码无效。", "invalid_pagination", 400)
    return jsonify(await service.list_rows(db, identity, batch_id, status=request.args.get("status", "all"), page=page, page_size=size))


@account_import_api.post("/<batch_id>/commit")
@endpoint()
async def commit_chunk(db, identity, batch_id):
    result, status = await service.commit(db, identity, batch_id, await request.get_json(silent=True))
    return jsonify(result), status


@account_import_api.post("/<batch_id>/cancel")
@endpoint(enabled=False)
async def cancel_batch(db, identity, batch_id):
    data = await request.get_json(silent=True)
    if data not in (None, {}):
        raise service.ImportError("取消操作不接受额外参数。", "invalid_request", 400)
    return jsonify(await service.cancel(db, identity, batch_id))


@account_import_api.get("/<batch_id>/report")
@endpoint(enabled=False)
async def download_report(db, identity, batch_id):
    batch, _ = await service.get_batch(db, identity, batch_id)
    if batch["payload_purged"] or batch["payload_purge_at"] <= int(time.time()):
        raise service.ImportError("报告明细已到期，保留最小开户台账。", "report_expired", 410)
    async with db.execute("SELECT * FROM account_import_rows WHERE batch_id=? ORDER BY excel_row_number", (batch_id,)) as cursor:
        rows = [service.public_row(v) for v in await cursor.fetchall()]
    content = await asyncio.to_thread(report_bytes, rows)
    await service.get_batch(db, identity, batch_id)
    return workbook_response(content, "account-import-results.xlsx")


async def maintenance_once(app):
    async with app.app_context():
        db = await get_db()
        try:
            await service.cleanup(db)
        finally:
            await db.close()
        directory = Path(app.config["DB_PATH"]).parent / "private" / "account-imports"
        if directory.is_dir():
            now = time.time()
            for path in list(directory.glob("import-*.xlsx"))[:100]:
                try:
                    if path.is_file() and not path.is_symlink() and path.stat().st_mtime < now - 3600:
                        path.unlink(missing_ok=True)
                except OSError:
                    app.logger.warning("Could not remove expired import upload")


async def maintenance_loop(app):
    while True:
        await asyncio.sleep(3600)
        try:
            await maintenance_once(app)
        except Exception:
            app.logger.exception("Account import maintenance failed")
