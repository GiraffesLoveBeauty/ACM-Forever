"""Persistent previews, fenced chunks and one-response credentials for Excel imports."""
import asyncio
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from quart import current_app

from . import binding_service
from .account_import_excel import COLUMNS, MAX_FILE_BYTES, MAX_ROWS, TEMPLATE_VERSION
from .web_account_service import (
    AccountCreationError, create_import_account, creation_state, fingerprint,
    prepare_password, strong_temporary_password, valid_qq,
)
from .auth_service import temporary_password_expiry

PREVIEW_SECONDS = 1800
EXECUTION_SECONDS = 7200
PAYLOAD_SECONDS = 86400
LEDGER_SECONDS = 90 * 86400
CHUNK_SIZE = 10
LEASE_SECONDS = 90
ELIGIBLE = {"create_member_and_account", "create_web_account_only"}
row = binding_service.row


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ImportError(AccountCreationError):
    pass


async def initialize_imports(db):
    await db.executescript(Path(__file__).with_name("account_import.sql").read_text(encoding="utf-8"))
    for platform in binding_service.LABELS:
        _, field, _ = binding_service.platform_spec(platform)
        await db.execute(f"CREATE TRIGGER IF NOT EXISTS import_provenance_reset_{platform} AFTER UPDATE OF {field} ON users WHEN LOWER(TRIM(COALESCE(NEW.{field},'')))<>LOWER(TRIM(COALESCE(OLD.{field},''))) BEGIN DELETE FROM binding_provenance WHERE qq_id=NEW.qq_id AND platform='{platform}'; END")
    async with db.execute("PRAGMA table_info(users)") as cursor:
        columns = {r["name"] for r in await cursor.fetchall()}
    if "account_state" in columns:
        # Installed when #83's real lifecycle schema is present. All redaction is in
        # the same transaction as closure; a new generation cannot inherit a batch.
        await db.executescript("""
        CREATE TRIGGER IF NOT EXISTS account_import_closure AFTER UPDATE OF account_state ON users
        WHEN NEW.account_state='closed' AND OLD.account_state<>'closed' BEGIN
          DELETE FROM binding_provenance WHERE qq_id=NEW.qq_id;
          UPDATE binding_provenance SET actor_qq_id=NULL WHERE actor_qq_id=NEW.qq_id;
          UPDATE account_import_chunks SET result_json='{}' WHERE batch_id IN
            (SELECT batch_id FROM account_import_rows WHERE qq_id=NEW.qq_id UNION SELECT id FROM account_import_batches WHERE actor_qq_id=NEW.qq_id);
          UPDATE account_import_rows SET qq_id='',payload_json='{}',snapshot_hash='',errors_json='["成员已注销"]',warnings_json='[]',ignored_json='[]',status=CASE WHEN status='created' THEN status ELSE 'cancelled' END
            WHERE qq_id=NEW.qq_id OR batch_id IN (SELECT id FROM account_import_batches WHERE actor_qq_id=NEW.qq_id);
          UPDATE account_import_batches SET actor_qq_id='',status='cancelled',continuation_token=NULL,payload_purged=1 WHERE actor_qq_id=NEW.qq_id;
        END;
        """)


async def actor_snapshot(db, identity, batch=None):
    if not identity or identity.get("legacy") or not identity.get("qq_id"):
        raise ImportError("请使用个人 Web 管理账号登录后导入。", "named_admin_required", 403)
    value = await row(db, "SELECT u.*,a.role AS web_role,a.credential_version,a.is_active,a.must_change_password FROM users u JOIN web_accounts a USING(qq_id) WHERE u.qq_id=?", (identity["qq_id"],))
    if (not value or not value["is_active"] or value["must_change_password"] or value["web_role"] not in {"admin", "root"} or value["credential_version"] != identity.get("credential_version") or ("account_state" in value.keys() and value["account_state"] != "active")):
        raise ImportError("管理身份发生变化，请重新登录后核对结果。", "actor_changed", 403)
    epoch = value["account_epoch"] if "account_epoch" in value.keys() else 1
    if batch and (batch["actor_qq_id"] != identity["qq_id"] or batch["actor_epoch"] != epoch or batch["actor_credential_version"] != value["credential_version"]):
        raise ImportError("此批次的操作者身份已变化，请重新预检。", "actor_changed", 403)
    return {"qq_id": identity["qq_id"], "credential_version": value["credential_version"], "epoch": epoch, "role": value["web_role"]}


async def get_batch(db, identity, batch_id, *, write=False):
    actor = await actor_snapshot(db, identity)
    batch = await row(db, "SELECT * FROM account_import_batches WHERE id=?", (batch_id,))
    if not batch:
        raise ImportError("导入批次不存在或无权访问。", "batch_not_found", 404)
    owner = batch["actor_qq_id"] == actor["qq_id"] and batch["actor_epoch"] == actor["epoch"]
    if not owner and (write or actor["role"] != "root" or batch["actor_qq_id"] == actor["qq_id"] or not batch["actor_qq_id"]):
        raise ImportError("导入批次不存在或无权访问。", "batch_not_found", 404)
    if write:
        await actor_snapshot(db, identity, batch)
    if not batch["payload_purged"] and batch["payload_purge_at"] <= int(time.time()):
        owns_transaction = not db.in_transaction
        await db.execute("UPDATE account_import_rows SET payload_json='{}',snapshot_hash='',errors_json='[]',warnings_json='[]',ignored_json='[]' WHERE batch_id=?", (batch_id,))
        await db.execute("UPDATE account_import_chunks SET result_json=NULL WHERE batch_id=?", (batch_id,))
        await db.execute("UPDATE account_import_batches SET payload_purged=1 WHERE id=?", (batch_id,))
        if owns_transaction:
            await db.commit()
        batch = await row(db, "SELECT * FROM account_import_batches WHERE id=?", (batch_id,))
    return batch, owner


async def recover_lease(db, batch_id, now):
    # Must hold BEGIN IMMEDIATE. The old worker is fenced by status + token.
    cursor = await db.execute("UPDATE account_import_chunks SET status='interrupted',finished_at=? WHERE batch_id=? AND status='processing' AND lease_until<=?", (now, batch_id, now))
    if cursor.rowcount:
        await db.execute("UPDATE account_import_batches SET status='paused',continuation_token=? WHERE id=? AND status='committing'", (secrets.token_urlsafe(24), batch_id))


async def summary(db, identity, batch_id):
    batch, owner = await get_batch(db, identity, batch_id)
    now = int(time.time())
    await db.execute("BEGIN IMMEDIATE")
    await recover_lease(db, batch_id, now)
    await db.commit()
    batch, owner = await get_batch(db, identity, batch_id)
    async with db.execute("SELECT action,status,selected,COUNT(*) n FROM account_import_rows WHERE batch_id=? GROUP BY action,status,selected", (batch_id,)) as cursor:
        groups = await cursor.fetchall()
    counts = {"total": 0, "ready": 0, "created": 0, "skipped": 0, "invalid": 0, "conflict": 0, "remaining": 0, "selected": 0, "create_member_and_account": 0, "create_web_account_only": 0}
    for item in groups:
        n, status = item["n"], item["status"]
        counts["total"] += n
        if item["action"] in ELIGIBLE:
            counts[item["action"]] += n
        if item["selected"]:
            counts["selected"] += n
            if status in {"ready", "retryable"}:
                counts["remaining"] += n
        key = status if status in counts else "skipped" if status in {"skipped", "blocked", "cancelled"} else None
        if key:
            counts[key] += n
    status = batch["status"]
    expires = batch["execution_expires_at"] if batch["confirmed_at"] else batch["preview_expires_at"]
    if status in {"preview_ready", "paused", "committing"} and expires <= now:
        status = "expired"
    active = await row(db, "SELECT id,status,lease_until FROM account_import_chunks WHERE batch_id=? AND status='processing'", (batch_id,))
    return {"id": batch_id, "template_version": batch["template_version"], "preview_version": batch["preview_version"], "status": status, "expires_at": expires, "summary": counts, "selection_digest": batch["selection_digest"], "next_chunk_token": batch["continuation_token"] if owner else None, "read_only": not owner or batch["actor_credential_version"] != identity.get("credential_version"), "payload_purged": bool(batch["payload_purged"]), "temporary_password_ttl_hours": batch["temporary_password_ttl_hours"], "active_chunk": dict(active) if active else None, "credentials_replayed": False}


def public_row(value):
    payload = json.loads(value["payload_json"])
    return {"row_id": value["id"], "excel_row_number": value["excel_row_number"], "qq_id": value["qq_id"], "name": payload.get("name", ""), "action": value["action"], "status": value["status"], "selected": bool(value["selected"]), "can_submit": value["status"] == "ready" and value["action"] in ELIGIBLE, "errors": json.loads(value["errors_json"]), "warnings": json.loads(value["warnings_json"]), "ignored_fields": json.loads(value["ignored_json"]), "result_code": value["result_code"], "created_account_at": value["created_account_at"], "bindings": {field: payload[field] for _, field, _ in COLUMNS[5:] if payload.get(field)}}


async def list_rows(db, identity, batch_id, *, status="all", page=1, page_size=100):
    batch, _ = await get_batch(db, identity, batch_id)
    if status not in {"all", "ready", "invalid", "skipped", "created", "conflict", "retryable", "cancelled"} or type(page) is not int or page < 1 or not 1 <= page_size <= 100:
        raise ImportError("筛选或页码无效。", "invalid_pagination", 400)
    where, args = "batch_id=?", [batch_id]
    if status == "skipped":
        where += " AND status IN ('skipped','blocked')"
    elif status != "all":
        where += " AND status=?"
        args.append(status)
    total = (await row(db, "SELECT COUNT(*) n FROM account_import_rows WHERE " + where, args))["n"]
    async with db.execute("SELECT * FROM account_import_rows WHERE " + where + " ORDER BY excel_row_number LIMIT ? OFFSET ?", (*args, page_size, (page - 1) * page_size)) as cursor:
        items = [public_row(value) for value in await cursor.fetchall()]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "payload_purged": bool(batch["payload_purged"])}


async def parse_upload(content):
    app = current_app._get_current_object()
    if app.extensions.get("account_import_parser_busy"):
        raise ImportError("另一个文件正在解析，请稍后再试。", "parse_busy", 429)
    app.extensions["account_import_parser_busy"] = True
    path, process = None, None
    try:
        directory = Path(app.config["DB_PATH"]).parent / "private" / "account-imports"
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, path = tempfile.mkstemp(prefix="import-", suffix=".xlsx", dir=directory)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("account_import_worker.py")), path, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=2 * 1024 * 1024)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=8)
        except asyncio.TimeoutError:
            raise ImportError("文件解析超过8秒，已终止；请拆分或重新下载模板。", "parse_timeout", 422)
        if process.returncode or len(stdout) > 1024 * 1024:
            raise ImportError("文件无法安全解析，请重新下载模板。", "invalid_workbook", 422)
        result = json.loads(stdout)
        if "error" in result:
            raise ImportError(str(result["error"])[:256], str(result.get("code", "invalid_workbook"))[:64], 422)
        rows = result.get("rows")
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            raise ImportError("解析结果格式无效。", "invalid_workbook", 422)
        for value in rows:
            if (not isinstance(value, dict) or set(value) != {"excel_row_number", "payload", "errors", "warnings"} or type(value["excel_row_number"]) is not int or not 2 <= value["excel_row_number"] <= 1000 or not isinstance(value["payload"], dict) or set(value["payload"]) != {field for _, field, _ in COLUMNS}):
                raise ImportError("解析结果格式无效。", "invalid_workbook", 422)
            for _, field, maximum in COLUMNS:
                if not isinstance(value["payload"][field], str) or len(value["payload"][field]) > maximum:
                    raise ImportError("解析字段超出限制。", "invalid_workbook", 422)
            if any(not isinstance(value[key], list) or len(value[key]) > 20 or any(not isinstance(msg, str) or len(msg) > 256 for msg in value[key]) for key in ("errors", "warnings")):
                raise ImportError("解析提示格式无效。", "invalid_workbook", 422)
        return rows
    except (ValueError, TypeError, KeyError):
        raise ImportError("文件无法安全解析，请重新下载模板。", "invalid_workbook", 422)
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        if path:
            Path(path).unlink(missing_ok=True)
        app.extensions["account_import_parser_busy"] = False


async def check_capacity(db, actor):
    now = int(time.time())
    counts = await row(db, "SELECT COUNT(*) n,SUM(CASE WHEN actor_qq_id=? THEN 1 ELSE 0 END) own FROM account_import_batches WHERE payload_purged=0 AND payload_purge_at>?", (actor["qq_id"], now))
    if counts["n"] >= 100 or (counts["own"] or 0) >= 10:
        raise ImportError("保留中的导入批次较多，请稍后再上传。", "capacity_limit", 429)


async def preview(db, identity, content, parsed, ttl_hours):
    actor = await actor_snapshot(db, identity)
    await check_capacity(db, actor)
    # Batch reads for all members, accounts, status suggestions and OJ occupancy.
    ids = list({v["payload"]["qq_id"] for v in parsed if valid_qq(v["payload"]["qq_id"])})
    placeholders = ",".join("?" for _ in ids) or "NULL"
    async with db.execute(f"SELECT * FROM users WHERE qq_id IN ({placeholders})", ids) as cursor:
        users = {v["qq_id"]: dict(v) for v in await cursor.fetchall()}
    async with db.execute(f"SELECT * FROM web_accounts WHERE qq_id IN ({placeholders})", ids) as cursor:
        accounts = {v["qq_id"]: dict(v) for v in await cursor.fetchall()}
    async with db.execute("SELECT DISTINCT status FROM users WHERE status IS NOT NULL AND TRIM(status)<>'' LIMIT 100") as cursor:
        known_statuses = {v["status"] for v in await cursor.fetchall()}
    occupancy = {}
    for platform in binding_service.LABELS:
        _, field, _ = binding_service.platform_spec(platform)
        values = {v["payload"][field].casefold() for v in parsed if v["payload"].get(field)}
        marks = ",".join("?" for _ in values) or "NULL"
        async with db.execute(f"SELECT LOWER(TRIM({field})) account FROM users WHERE LOWER(TRIM({field})) IN ({marks})", list(values)) as cursor:
            occupancy[field] = {v["account"] for v in await cursor.fetchall()}
    duplicates = Counter(v["payload"]["qq_id"] for v in parsed if v["payload"]["qq_id"])
    oj_duplicates = {field: Counter(v["payload"][field].casefold() for v in parsed if v["payload"][field] and v["payload"]["qq_id"] not in users) for _, field, _ in COLUMNS[5:]}
    from .web_account_service import creation_state_value
    prepared = []
    for value in parsed:
        payload = dict(value["payload"])
        qq_id = payload["qq_id"]
        action, snapshot, member = creation_state_value(users.get(qq_id), accounts.get(qq_id))
        errors, warnings, ignored = list(value["errors"]), list(value["warnings"]), []
        if not valid_qq(qq_id):
            errors.append("QQ号必须为4–12位数字且首位非0")
        if duplicates[qq_id] > 1:
            errors.append("同表QQ重复，所有重复行均不执行")
        if member:
            ignored = [label for label, field, _ in COLUMNS[1:] if payload[field] and payload[field] != str(member.get(field) or "")]
            payload = {"qq_id": qq_id, "name": member["name"], "real_name": member.get("real_name") or ""}
            if ignored:
                warnings.append("已有成员只补开户，忽略表内资料和OJ，不改原档案")
        else:
            payload["name"] = payload["name"] or qq_id
            if payload["status"] and payload["status"] not in known_statuses:
                warnings.append("身份为当前未使用的文本值；确认创建即采用此身份，不影响Web角色")
            for platform in binding_service.LABELS:
                _, field, _ = binding_service.platform_spec(platform)
                if payload[field]:
                    try:
                        payload[field] = binding_service.normalize_account(platform, payload[field])
                    except binding_service.BindingError as exc:
                        warnings.append(f"{binding_service.LABELS[platform]}：已跳过绑定（{exc}）")
                        payload[field] = ""
                    if payload[field] and payload[field].casefold() in occupancy[field]:
                        warnings.append(f"{binding_service.LABELS[platform]}账号已被占用，已跳过绑定")
                        payload[field] = ""
                    if payload[field] and oj_duplicates[field][payload[field].casefold()] > 1:
                        warnings.append(f"同表{binding_service.LABELS[platform]}账号重复，已跳过绑定")
                        payload[field] = ""
                    if not payload[field]:
                        ignored.append(next(label for label, key, _ in COLUMNS if key == field))
            if any(payload.get(field) for _, field, _ in COLUMNS[5:]):
                warnings.append("OJ由管理员录入，尚未核验本人归属，尚未同步")
        if action == "blocked_closed":
            warnings.append("此QQ已注销；请在单个创建入口显式新建账号，导入不恢复旧账号")
        state = "invalid" if errors else "ready" if action in ELIGIBLE else "skipped" if action == "skipped_existing" else "blocked"
        prepared.append((secrets.token_urlsafe(18), value["excel_row_number"], qq_id, action, state, encode(payload), snapshot, encode(errors), encode(warnings), encode(ignored)))
    now, batch_id = int(time.time()), secrets.token_urlsafe(24)
    await db.execute("BEGIN IMMEDIATE")
    try:
        actor = await actor_snapshot(db, identity)
        await check_capacity(db, actor)
        await db.execute("INSERT INTO account_import_batches(id,actor_qq_id,actor_epoch,actor_credential_version,template_version,file_sha256,normalized_sha256,status,created_at,preview_expires_at,payload_purge_at,temporary_password_ttl_hours) VALUES(?,?,?,?,?,?,?,'preview_ready',?,?,?,?)", (batch_id, actor["qq_id"], actor["epoch"], actor["credential_version"], TEMPLATE_VERSION, hashlib.sha256(content).hexdigest(), fingerprint(parsed), now, now + PREVIEW_SECONDS, now + PAYLOAD_SECONDS, ttl_hours))
        await db.executemany("INSERT INTO account_import_rows(id,batch_id,excel_row_number,qq_id,action,status,payload_json,snapshot_hash,errors_json,warnings_json,ignored_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)", [(p[0], batch_id, *p[1:]) for p in prepared])
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return await summary(db, identity, batch_id)


async def _lease_valid(db, batch, chunk, identity, now):
    now = int(time.time())
    fresh = await row(db, "SELECT * FROM account_import_chunks WHERE id=?", (chunk["id"],))
    current = await row(db, "SELECT * FROM account_import_batches WHERE id=?", (batch["id"],))
    if (not fresh or fresh["status"] != "processing" or fresh["lease_token"] != chunk["lease_token"] or fresh["lease_until"] <= now or current["status"] != "committing" or current["execution_expires_at"] <= now):
        raise ImportError("本段已暂停、过期或被其他请求接管，请查询结果。", "lease_lost", 409)
    await actor_snapshot(db, identity, current)


async def acquire_chunk(db, identity, batch_id, data):
    if not isinstance(data, dict):
        raise ImportError("请求格式错误。", "invalid_request", 400)
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", key):
        raise ImportError("请提供有效的随机请求标识。", "invalid_idempotency_key", 400)
    request_hash, now = fingerprint(data), int(time.time())
    await db.execute("BEGIN IMMEDIATE")
    try:
        batch, _ = await get_batch(db, identity, batch_id, write=True)
        await recover_lease(db, batch_id, now)
        previous = await row(db, "SELECT * FROM account_import_chunks WHERE batch_id=? AND idempotency_key=?", (batch_id, key))
        if previous:
            if previous["request_hash"] != request_hash:
                raise ImportError("同一个请求标识对应了不同操作。", "idempotency_conflict", 409)
            await db.commit()
            return dict(previous), False
        active = await row(db, "SELECT id FROM account_import_chunks WHERE batch_id=? AND status='processing'", (batch_id,))
        if active:
            raise ImportError("该批次已有正在处理的段，请查询进度。", "batch_busy", 409)
        batch, _ = await get_batch(db, identity, batch_id, write=True)
        if batch["payload_purged"] or batch["status"] not in {"preview_ready", "paused", "committing"}:
            raise ImportError("该批次不能继续，请重新上传或查看结果。", "batch_not_executable", 409)
        if batch["selection_digest"]:
            if set(data) != {"preview_version", "selection_digest", "continuation_token", "idempotency_key"} or data.get("selection_digest") != batch["selection_digest"] or data.get("continuation_token") != batch["continuation_token"]:
                raise ImportError("后续范围或继续标识不匹配，请刷新进度。", "selection_changed", 409)
            expiry = batch["execution_expires_at"]
        else:
            if set(data) != {"preview_version", "selected_row_ids", "acknowledge_admin_binding", "idempotency_key"}:
                raise ImportError("首次确认参数不正确。", "invalid_request", 400)
            selected = data.get("selected_row_ids")
            if (not isinstance(selected, list) or not 1 <= len(selected) <= MAX_ROWS or any(not isinstance(v, str) for v in selected) or len(set(selected)) != len(selected) or type(data.get("acknowledge_admin_binding")) is not bool):
                raise ImportError("请选择本批次可执行行。", "invalid_selection", 400)
            async with db.execute("SELECT * FROM account_import_rows WHERE batch_id=?", (batch_id,)) as cursor:
                candidates = {v["id"]: v for v in await cursor.fetchall()}
            if any(v not in candidates or candidates[v]["status"] != "ready" or candidates[v]["action"] not in ELIGIBLE for v in selected):
                raise ImportError("所选行不是本批次可执行行。", "invalid_selection", 400)
            has_bindings = any(candidates[v]["action"] == "create_member_and_account" and any(json.loads(candidates[v]["payload_json"]).get(field) for _, field, _ in COLUMNS[5:]) for v in selected)
            if has_bindings and data["acknowledge_admin_binding"] is not True:
                raise ImportError("请确认OJ账号与成员的对应关系。", "binding_acknowledgement_required", 400)
            expiry = batch["preview_expires_at"]
            await db.executemany("UPDATE account_import_rows SET selected=1 WHERE id=? AND batch_id=?", [(v, batch_id) for v in selected])
            await db.execute("UPDATE account_import_batches SET selection_digest=?,acknowledged_binding=?,confirmed_at=?,execution_expires_at=?,payload_purge_at=? WHERE id=?", (fingerprint(sorted(selected)), int(data["acknowledge_admin_binding"]), now, now + EXECUTION_SECONDS, now + EXECUTION_SECONDS + PAYLOAD_SECONDS, batch_id))
        if type(data.get("preview_version")) is not int or data["preview_version"] != batch["preview_version"]:
            raise ImportError("预检版本不匹配，请重新上传。", "preview_changed", 409)
        if expiry <= now:
            raise ImportError("批次已过期，请重新上传。", "batch_expired", 410)
        async with db.execute("SELECT id FROM account_import_rows WHERE batch_id=? AND selected=1 AND status IN ('ready','retryable') ORDER BY excel_row_number LIMIT ?", (batch_id, CHUNK_SIZE)) as cursor:
            ids = [v["id"] for v in await cursor.fetchall()]
        if not ids:
            raise ImportError("没有可继续的行。", "nothing_to_commit", 409)
        chunk_id, token = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        await db.execute("INSERT INTO account_import_chunks(id,batch_id,idempotency_key,request_hash,row_ids_json,status,lease_token,lease_until,created_at) VALUES(?,?,?,?,?,'processing',?,?,?)", (chunk_id, batch_id, key, request_hash, encode(ids), token, now + LEASE_SECONDS, now))
        await db.execute("UPDATE account_import_batches SET status='committing',continuation_token=NULL WHERE id=?", (batch_id,))
        await db.commit()
        return dict(await row(db, "SELECT * FROM account_import_chunks WHERE id=?", (chunk_id,))), True
    except BaseException:
        await db.rollback()
        raise


async def commit(db, identity, batch_id, data):
    chunk, original = await acquire_chunk(db, identity, batch_id, data)
    if not original:
        result = await summary(db, identity, batch_id)
        return {**result, "chunk_id": chunk["id"], "chunk_status": chunk["status"], "results": json.loads(chunk["result_json"] or "[]"), "credentials": [], "credentials_replayed": False}, 202 if chunk["status"] == "processing" else 200
    batch, _ = await get_batch(db, identity, batch_id, write=True)
    credentials, stopped, started = [], False, time.monotonic()
    paused_reason = None
    try:
        for row_id in json.loads(chunk["row_ids_json"]):
            if time.monotonic() - started > 20:
                stopped = True
                break
            current = await row(db, "SELECT * FROM account_import_rows WHERE id=?", (row_id,))
            password = strong_temporary_password()
            password_hash = await prepare_password(password)
            now = int(time.time())
            expires = temporary_password_expiry(now, batch["temporary_password_ttl_hours"])
            try:
                await db.execute("BEGIN IMMEDIATE")
                await _lease_valid(db, batch, chunk, identity, now)
                payload = json.loads(current["payload_json"])
                warnings = json.loads(current["warnings_json"])
                ignored = json.loads(current["ignored_json"])
                if current["action"] == "create_member_and_account":
                    # The write lock makes the occupancy recheck and creation atomic.
                    # Optional OJ bindings must never turn a valid QQ into a failed account.
                    for platform in binding_service.LABELS:
                        _, field, _ = binding_service.platform_spec(platform)
                        if payload.get(field) and await row(db, f"SELECT 1 FROM users WHERE LOWER(TRIM({field}))=LOWER(?) LIMIT 1", (payload[field],)):
                            payload[field] = ""
                            warnings.append(f"{binding_service.LABELS[platform]}账号在预检后被占用，已跳过绑定")
                            ignored.append(next(label for label, key, _ in COLUMNS if key == field))
                await create_import_account(db, payload, current["action"], current["snapshot_hash"], password_hash, actor=identity["qq_id"], batch_id=batch_id, now=now, expires_at=expires)
                await _lease_valid(db, batch, chunk, identity, int(time.time()))
                await db.execute("UPDATE account_import_rows SET status='created',chunk_id=?,result_code='created',created_account_at=?,payload_json=?,warnings_json=?,ignored_json=?,attempt_count=attempt_count+1 WHERE id=?", (chunk["id"], now, encode(payload), encode(warnings), encode(ignored), row_id))
                await db.commit()
                credentials.append({"row_id": row_id, "qq_id": current["qq_id"], "name": payload["name"], "real_name": payload.get("real_name", ""), "username": current["qq_id"], "temporary_password": password, "expires_at": expires})
            except (AccountCreationError, sqlite3.IntegrityError) as exc:
                await db.rollback()
                if isinstance(exc, AccountCreationError) and exc.code in {"actor_changed", "lease_lost", "named_admin_required"}:
                    stopped = True
                    break
                await db.execute("BEGIN IMMEDIATE")
                await _lease_valid(db, batch, chunk, identity, int(time.time()))
                code = exc.code if isinstance(exc, AccountCreationError) else "creation_conflict"
                message = str(exc) if isinstance(exc, AccountCreationError) else "状态或唯一性冲突，请重新预检"
                await db.execute("UPDATE account_import_rows SET status='conflict',result_code=?,errors_json=?,chunk_id=?,attempt_count=attempt_count+1 WHERE id=?", (code, encode([message]), chunk["id"], row_id))
                await db.commit()
            except sqlite3.OperationalError:
                await db.rollback()
                stopped = True
                break
            finally:
                password = password_hash = None
    except asyncio.CancelledError:
        await db.rollback()
        raise  # Lease recovery records interruption; no password replay.
    except Exception as exc:
        await db.rollback()
        stopped = True
        paused_reason = exc.code if isinstance(exc, AccountCreationError) else "temporary_failure"
    await db.execute("BEGIN IMMEDIATE")
    try:
        owned = await row(db, "SELECT * FROM account_import_chunks WHERE id=? AND lease_token=? AND status='processing' AND lease_until>?", (chunk["id"], chunk["lease_token"], int(time.time())))
        if owned:
            async with db.execute("SELECT id AS row_id,qq_id,status AS result,result_code FROM account_import_rows WHERE chunk_id=? ORDER BY excel_row_number", (chunk["id"],)) as cursor:
                results = [dict(v) for v in await cursor.fetchall()]
            await db.execute("UPDATE account_import_chunks SET status=?,finished_at=?,result_json=? WHERE id=?", ("interrupted" if stopped else "completed", int(time.time()), encode(results), chunk["id"]))
            remaining = (await row(db, "SELECT COUNT(*) n FROM account_import_rows WHERE batch_id=? AND selected=1 AND status IN ('ready','retryable')", (batch_id,)))["n"]
            failed = (await row(db, "SELECT COUNT(*) n FROM account_import_rows WHERE batch_id=? AND selected=1 AND status='conflict'", (batch_id,)))["n"]
            state = "paused" if remaining else "completed_with_errors" if failed else "completed"
            await db.execute("UPDATE account_import_batches SET status=?,continuation_token=?,finished_at=?,payload_purge_at=MIN(payload_purge_at,?) WHERE id=? AND status='committing'", (state, secrets.token_urlsafe(24) if remaining else None, None if remaining else int(time.time()), int(time.time()) + PAYLOAD_SECONDS if not remaining else batch["payload_purge_at"], batch_id))
        else:
            results, credentials = [], []
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    # Recheck current permission immediately before serializing secrets.
    fresh, _ = await get_batch(db, identity, batch_id, write=True)
    await actor_snapshot(db, identity, fresh)
    result = await summary(db, identity, batch_id)
    return {**result, "chunk_id": chunk["id"], "chunk_status": "interrupted" if stopped else "completed", "paused_reason": paused_reason, "results": results, "processed": len(results), "credentials": credentials, "credentials_replayed": False}, 200


async def cancel(db, identity, batch_id):
    await db.execute("BEGIN IMMEDIATE")
    try:
        batch, _ = await get_batch(db, identity, batch_id, write=True)
        if batch["status"] not in {"completed", "completed_with_errors", "expired"}:
            await db.execute("UPDATE account_import_batches SET status='cancelled',continuation_token=NULL,finished_at=?,payload_purge_at=MIN(payload_purge_at,?) WHERE id=?", (int(time.time()), int(time.time())+PAYLOAD_SECONDS, batch_id))
            await db.execute("UPDATE account_import_rows SET status='cancelled' WHERE batch_id=? AND status IN ('ready','retryable')", (batch_id,))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return await summary(db, identity, batch_id)


async def cleanup(db, now=None):
    now = int(time.time()) if now is None else now
    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute("UPDATE account_import_batches SET status='expired',continuation_token=NULL WHERE (status='preview_ready' AND preview_expires_at<=?) OR (status IN ('committing','paused') AND execution_expires_at<=?)", (now, now))
        async with db.execute("SELECT id FROM account_import_batches WHERE payload_purged=0 AND payload_purge_at<=? LIMIT 100", (now,)) as cursor:
            ids = [v["id"] for v in await cursor.fetchall()]
        for batch_id in ids:
            await db.execute("UPDATE account_import_rows SET payload_json='{}',snapshot_hash='',errors_json='[]',warnings_json='[]',ignored_json='[]' WHERE batch_id=?", (batch_id,))
            await db.execute("UPDATE account_import_chunks SET result_json=NULL WHERE batch_id=?", (batch_id,))
            await db.execute("UPDATE account_import_batches SET payload_purged=1 WHERE id=?", (batch_id,))
        await db.execute("DELETE FROM account_import_batches WHERE id IN (SELECT id FROM account_import_batches WHERE created_at<? LIMIT 100)", (now - LEDGER_SECONDS,))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
