"""Member profile queries and guarded partial updates; account management stays separate."""
import hashlib
import hmac
import inspect
import json
import math
import re
import sqlite3

from . import binding_service
from .account_lifecycle_service import require_active_user, require_web_actor

EDIT_FIELDS = ("real_name", "name", "school", "status", "cf_handle", "atcoder_handle", "luogu_id", "nowcoder_id")
BINDINGS = {field: platform for platform, (field, _) in binding_service.BINDING_FIELDS.items() if platform != "cf"}
PROFILE_FIELDS = (*EDIT_FIELDS, "cjlu_username", "avatar_url")
VERSION_FIELDS = ("cf_binding_version", "atcoder_binding_version", "luogu_binding_version", "nowcoder_binding_version", "cjlu_binding_version")
META_FIELDS = {"expected_account_epoch", "profile_revision", "confirm_bindings", "expected_bindings", "binding_versions"}


class ProfileError(Exception):
    def __init__(self, code, message, status=400, **details):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


async def row(db, sql, values=()):
    async with db.execute(sql, values) as cursor:
        return await cursor.fetchone()


def serialize(user):
    source = dict(user)
    values = {key: source.get(key) or "" for key in PROFILE_FIELDS}
    versions = {key: int(source.get(key) or 0) for key in VERSION_FIELDS}
    identity = {key: source[key] for key in ("qq_id", "account_epoch", "account_state")}
    fingerprint = json.dumps({**identity, **values, **versions}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**identity, **values, **versions, "role": source.get("role"), "is_active": source.get("is_active"),
            "profile_revision": hashlib.sha256(fingerprint.encode()).hexdigest(),
            "binding_versions": {platform: versions[binding_service.platform_spec(platform)[2]] for platform in BINDINGS.values()}}


async def snapshot(db, qq_id):
    await require_active_user(db, qq_id)
    user = await row(db, "SELECT u.*,a.role,a.is_active FROM users u LEFT JOIN web_accounts a ON a.qq_id=u.qq_id WHERE u.qq_id=?", (qq_id,))
    return serialize(user)


async def listing(db, args):
    try:
        page = max(1, int(args.get("page", 1)))
        size = max(1, min(100, int(args.get("page_size", 20))))
    except (TypeError, ValueError):
        raise ProfileError("invalid_pagination", "分页参数必须为整数。")
    filters, values = ["u.account_state='active'"], []
    search = str(args.get("search", "")).strip()
    if len(search) > 100:
        raise ProfileError("invalid_filter", "关键词不能超过 100 字。")
    if search:
        fields = ("qq_id", *EDIT_FIELDS, "cjlu_username")
        filters.append("(" + " OR ".join(f"LOWER(COALESCE(u.{key},'')) LIKE ?" for key in fields) + ")")
        values.extend(["%" + search.lower() + "%"] * len(fields))
    for key in ("school", "status"):
        value = str(args.get(key, "")).strip()
        if len(value) > (64 if key == "status" else 128):
            raise ProfileError("invalid_filter", "筛选值过长。")
        if value:
            filters.append(f"TRIM(COALESCE(u.{key},''))=?")
            values.append(value)
    where = " WHERE " + " AND ".join(filters)
    # Count and page are from the same read snapshot.
    await db.execute("BEGIN")
    try:
        total = (await row(db, "SELECT COUNT(*) AS n FROM users u" + where, values))["n"]
        page = min(page, max(1, math.ceil(total / size)))
        async with db.execute("SELECT u.*,a.role,a.is_active FROM users u LEFT JOIN web_accounts a ON a.qq_id=u.qq_id" + where + " ORDER BY u.name COLLATE NOCASE,u.qq_id LIMIT ? OFFSET ?", (*values, size, (page - 1) * size)) as cursor:
            items = [serialize(user) for user in await cursor.fetchall()]
        return {"items": items, "total": total, "page": page, "page_size": size}
    finally:
        await db.rollback()


async def options(db, identity, *, secret, deployment, legacy_username):
    async with db.execute("SELECT TRIM(COALESCE(school,'')) school,TRIM(COALESCE(status,'')) status FROM users WHERE account_state='active'") as cursor:
        users = await cursor.fetchall()
    owner = ["legacy", legacy_username] if identity.get("legacy") else ["member", identity["qq_id"], identity["account_epoch"]]
    scope = hmac.new(str(secret).encode(), json.dumps([deployment, owner], ensure_ascii=False).encode(), hashlib.sha256).hexdigest()
    return {"schools": sorted({user["school"] for user in users if user["school"]}),
            "statuses": sorted({user["status"] for user in users if user["status"]}), "draft_scope": scope}


def validate(data):
    if not isinstance(data, dict):
        raise ProfileError("invalid_body", "请提交资料对象。")
    unknown = set(data) - set(EDIT_FIELDS) - META_FIELDS
    if unknown:
        raise ProfileError("invalid_fields", "不允许修改这些字段：" + "、".join(sorted(unknown)))
    if type(data.get("expected_account_epoch")) is not int or data["expected_account_epoch"] < 1:
        raise ProfileError("invalid_epoch", "缺少有效的账号代际。")
    if not isinstance(data.get("profile_revision"), str) or not re.fullmatch(r"[a-f0-9]{64}", data["profile_revision"]):
        raise ProfileError("invalid_revision", "缺少有效的资料版本，请重新读取资料。")
    changes, errors = {}, {}
    for field in EDIT_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is not None and not isinstance(value, str):
            errors[field] = "请填写文本或留空。"
            continue
        value = (value or "").strip()
        limit = 64 if field == "status" or field in BINDINGS else 128
        if len(value) > limit:
            errors[field] = f"最多 {limit} 字符。"
        elif field == "name" and not value:
            errors[field] = "昵称不能为空。"
        else:
            changes[field] = value
    if errors:
        raise ProfileError("invalid_profile", "请检查标出的资料字段。", field_errors=errors)
    return changes


async def patch(db, identity, qq_id, data, submitter=None):
    changes = validate(data)
    await db.execute("BEGIN IMMEDIATE")
    try:
        await require_web_actor(db, identity, roles={"admin", "root"})
        await require_active_user(db, qq_id, expected_epoch=data["expected_account_epoch"])
        before = await snapshot(db, qq_id)
        if before["profile_revision"] != data["profile_revision"]:
            raise ProfileError("profile_conflict", "资料已被其他操作修改，请核对后再保存。", 409, current=before)
        changed_bindings = []
        for field, value in list(changes.items()):
            if field not in BINDINGS:
                continue
            old = before[field].strip()
            if old.casefold() == value.casefold():
                del changes[field]
                continue
            platform = BINDINGS[field]
            if value:
                try:
                    value = binding_service.normalize_account(platform, value)
                except binding_service.BindingError as exc:
                    raise ProfileError(exc.code, str(exc), exc.status, field_errors={field: str(exc)}) from exc
            expected, versions = data.get("expected_bindings"), data.get("binding_versions")
            if data.get("confirm_bindings") is not True or not isinstance(expected, dict) or not isinstance(versions, dict):
                raise ProfileError("confirmation_required", "修改 OJ 绑定前请确认清理影响并提交当前绑定及版本。")
            if expected.get(field) != old or type(versions.get(platform)) is not int or versions[platform] != before["binding_versions"][platform]:
                raise ProfileError("binding_changed", "绑定已变化，请重新核对。", 409, current=before)
            changed_bindings.append((platform, value, (old, before["binding_versions"][platform])))
        ordinary = {key: value for key, value in changes.items() if key not in BINDINGS}
        if ordinary:
            await db.execute("UPDATE users SET " + ",".join(key + "=?" for key in ordinary) + " WHERE qq_id=?", (*ordinary.values(), qq_id))
        for platform, value, previous in changed_bindings:
            await binding_service.apply_binding(db, qq_id, platform, value, expected=previous,
                                                actor=identity.get("qq_id") or "legacy-admin", identity=identity)
        after = await snapshot(db, qq_id)
        await db.commit()
    except sqlite3.IntegrityError as exc:
        await db.rollback()
        if "duplicate account binding" in str(exc):
            raise ProfileError("duplicate_binding", "该平台账号已绑定给其他成员。", 409) from exc
        raise
    except BaseException:
        await db.rollback()
        raise
    # The write is complete. A scheduling failure must not misreport it as unsaved.
    task_id, warnings = None, []
    platforms = [platform for platform, value, _ in changed_bindings if value]
    if platforms:
        try:
            task = submitter(qq_id, platforms) if callable(submitter) else None
            if inspect.isawaitable(task):
                task = await task
            task_id = task.get("id") if isinstance(task, dict) else None
        except Exception:
            task_id = None
        if not task_id:
            warnings.append("资料已保存，旧平台证据已清理；同步任务未创建，请在同步任务页手动同步。")
    return {"success": True, "member": after, "task_id": task_id, "warnings": warnings,
            "message": "资料已保存。" + (" 已启动对应平台同步。" if task_id else "")}, (202 if task_id else 200)
