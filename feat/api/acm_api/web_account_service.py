"""Shared account creation primitives; callers own short write transactions."""
import asyncio
import hashlib
import json
import re
import secrets
import string
from concurrent.futures import ThreadPoolExecutor

from quart import current_app

from . import binding_service
from .auth_service import hash_password


class AccountCreationError(Exception):
    def __init__(self, message, code="account_changed", status=409):
        super().__init__(message)
        self.code, self.status = code, status


class PasswordExecutor:
    """Bound both running work and queue; cancellation does not release a running slot."""
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="account-password")
        self.pending = 0

    async def hash(self, password):
        if self.pending >= 8:
            raise AccountCreationError("开户正在处理，请稍后重试。", "hash_busy", 429)
        self.pending += 1
        future = asyncio.get_running_loop().run_in_executor(self.pool, hash_password, password)
        future.add_done_callback(lambda _: setattr(self, "pending", self.pending - 1))
        return await asyncio.shield(future)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


async def prepare_password(password):
    if "account_password_executor" not in current_app.extensions:
        current_app.extensions["account_password_executor"] = PasswordExecutor()
    executor = current_app.extensions["account_password_executor"]
    return await executor.hash(password)


def strong_temporary_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(24))
        if all(any(c in group for c in value) for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits)):
            return value


def valid_qq(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{3,11}", value) is not None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def creation_state(db, qq_id):
    user = await binding_service.row(db, "SELECT * FROM users WHERE qq_id=?", (qq_id,))
    account = await binding_service.row(db, "SELECT * FROM web_accounts WHERE qq_id=?", (qq_id,))
    return creation_state_value(user, account)


def creation_state_value(user, account):
    if user and "account_state" in user.keys() and user["account_state"] != "active":
        action = "blocked_closed"
    elif account:
        action = "skipped_existing" if account["is_active"] else "blocked_inactive"
    else:
        action = "create_web_account_only" if user else "create_member_and_account"
    fields = ["qq_id", "name", "real_name", "status", "school", "account_state", "account_epoch"]
    for platform in binding_service.LABELS:
        _, field, version = binding_service.platform_spec(platform)
        fields.extend((field, version))
    snapshot = {key: user[key] for key in fields if user and key in user.keys()}
    snapshot["web_account"] = {key: account[key] for key in ("role", "is_active", "credential_version", "created_at")} if account else None
    return action, fingerprint(snapshot), dict(user) if user else None


async def insert_web_account(db, qq_id, password_hash, *, role="member", now, expires_at):
    """Never upsert credentials or reopen a closed identity."""
    action, _, _ = await creation_state(db, qq_id)
    if action != "create_web_account_only":
        raise AccountCreationError("成员状态已变化，请重新核对。", action)
    await db.execute(
        "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at,temporary_password_expires_at) VALUES(?,?,?,1,1,1,?,?,?)",
        (qq_id, password_hash, role, now, now, expires_at),
    )


async def assert_binding_available(db, payload):
    for platform in binding_service.LABELS:
        _, field, _ = binding_service.platform_spec(platform)
        if payload.get(field):
            found = await binding_service.row(db, f"SELECT 1 FROM users WHERE LOWER(TRIM({field}))=LOWER(?) LIMIT 1", (payload[field],))
            if found:
                raise AccountCreationError(f"{binding_service.LABELS[platform]} 账号已被占用。", "binding_occupied")


async def create_import_account(db, payload, expected_action, expected_snapshot, password_hash, *, actor, batch_id, now, expires_at):
    qq_id = payload["qq_id"]
    action, snapshot, _ = await creation_state(db, qq_id)
    if action != expected_action or snapshot != expected_snapshot:
        raise AccountCreationError("预检后成员或账号状态发生变化，请重新上传。")
    if action == "create_member_and_account":
        # Evidence without a member is anomalous; do not erase it as part of creation.
        for table, owner in (("submissions", "user_qq_id"), ("submission_attempts", "owner_qq_id"), ("user_platform_sync_state", "user_qq_id")):
            if await binding_service.row(db, f"SELECT 1 FROM {table} WHERE {owner}=? LIMIT 1", (qq_id,)):
                raise AccountCreationError("该 QQ 存在待核对的历史证据，请先人工处理。", "orphan_evidence")
        await assert_binding_available(db, payload)
        await db.execute("INSERT INTO users(qq_id,name,real_name,status,school) VALUES(?,?,?,?,?)", tuple(payload.get(key) or None for key in ("qq_id", "name", "real_name", "status", "school")))
        for platform in binding_service.LABELS:
            _, field, _ = binding_service.platform_spec(platform)
            if payload.get(field):
                await binding_service.apply_binding(db, qq_id, platform, payload[field], expected=("", 0), actor=actor)
                await binding_service.record_provenance(db, qq_id, platform, "admin_import", actor=actor, batch_id=batch_id, now=now)
    elif action != "create_web_account_only":
        raise AccountCreationError("该账号不能通过导入开户。", action)
    await insert_web_account(db, qq_id, password_hash, now=now, expires_at=expires_at)
