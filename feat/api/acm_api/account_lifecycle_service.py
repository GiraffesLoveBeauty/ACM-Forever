"""Account lifecycle checks shared by Web, Bot, import and background writers.

Call write guards after BEGIN IMMEDIATE on the connection that performs the write.
Account creation is explicit; ordinary writes cannot revive a closed generation.
"""
import time

from .auth_service import password_hash_usable


class AccountLifecycleError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code = code
        self.status = status


async def migrate_account_lifecycle(db):
    """Add metadata without changing member status, roles, credentials or data."""
    async with db.execute("PRAGMA table_info(users)") as cursor:
        columns = {item["name"] for item in await cursor.fetchall()}
    additions = {
        "account_state": "TEXT NOT NULL DEFAULT 'active' CHECK(account_state IN ('active','closed'))",
        "account_epoch": "INTEGER NOT NULL DEFAULT 1 CHECK(typeof(account_epoch)='integer' AND account_epoch>=1)",
        "closed_at": "INTEGER",
    }
    for name, definition in additions.items():
        if name not in columns:
            await db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_users_account_state ON users(account_state,qq_id)")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS account_registrations ("
        "qq_id TEXT NOT NULL REFERENCES users(qq_id), closed_epoch INTEGER NOT NULL, "
        "new_epoch INTEGER NOT NULL, created_at INTEGER NOT NULL, "
        "PRIMARY KEY(qq_id,closed_epoch), CHECK(new_epoch=closed_epoch+1))"
    )
    # Replace the v1 guard atomically during initialization. Re-registration is
    # possible only with an explicit generation record in the same transaction.
    await db.execute("DROP TRIGGER IF EXISTS users_closed_no_reopen")
    # Narrow invariants also protect against REPLACE's implicit delete, even with
    # recursive_triggers off. Ordinary UPSERTs of active members remain supported.
    triggers = {
        "users_closed_no_reopen": (
            "BEFORE UPDATE OF account_state ON users "
            "WHEN OLD.account_state='closed' AND NEW.account_state<>'closed' AND NOT ("
            "NEW.account_state='active' AND NEW.account_epoch=OLD.account_epoch+1 AND EXISTS("
            "SELECT 1 FROM account_registrations r WHERE r.qq_id=OLD.qq_id "
            "AND r.closed_epoch=OLD.account_epoch AND r.new_epoch=NEW.account_epoch)) "
            "BEGIN SELECT RAISE(ABORT,'ACCOUNT_REOPEN_UNSUPPORTED'); END"
        ),
        "users_closed_no_delete": (
            "BEFORE DELETE ON users WHEN OLD.account_state='closed' "
            "BEGIN SELECT RAISE(ABORT,'ACCOUNT_CLOSED'); END"
        ),
        "users_closed_no_replace": (
            "BEFORE INSERT ON users WHEN EXISTS(SELECT 1 FROM users "
            "WHERE qq_id=NEW.qq_id AND account_state='closed') "
            "BEGIN SELECT RAISE(ABORT,'ACCOUNT_REOPEN_UNSUPPORTED'); END"
        ),
        "users_registration_epoch_insert": (
            "AFTER INSERT ON users WHEN NEW.account_epoch<COALESCE(("
            "SELECT MAX(new_epoch) FROM account_registrations WHERE qq_id=NEW.qq_id),1) "
            "BEGIN SELECT RAISE(ABORT,'ACCOUNT_CHANGED'); END"
        ),
        "users_epoch_monotonic": (
            "BEFORE UPDATE OF account_epoch,account_state ON users "
            "WHEN NEW.account_epoch<OLD.account_epoch OR "
            "(OLD.account_state='active' AND NEW.account_state='closed' "
            "AND NEW.account_epoch<=OLD.account_epoch) "
            "BEGIN SELECT RAISE(ABORT,'ACCOUNT_CHANGED'); END"
        ),
    }
    for name, definition in triggers.items():
        await db.execute(f"CREATE TRIGGER IF NOT EXISTS {name} {definition}")


async def user_lifecycle(db, qq_id):
    async with db.execute(
        "SELECT qq_id,account_state,account_epoch,closed_at FROM users WHERE qq_id=?",
        (str(qq_id),),
    ) as cursor:
        return await cursor.fetchone()


async def require_active_user(db, qq_id, *, expected_epoch=None, allow_missing=False):
    user = await user_lifecycle(db, qq_id)
    if user is None:
        if allow_missing:
            return None
        raise AccountLifecycleError("MEMBER_NOT_FOUND", "成员资料不存在。", 404)
    if user["account_state"] != "active":
        raise AccountLifecycleError("ACCOUNT_CLOSED", "账号已注销，不能执行此操作。")
    if expected_epoch is not None and (
        type(expected_epoch) is not int or user["account_epoch"] != expected_epoch
    ):
        raise AccountLifecycleError("ACCOUNT_CHANGED", "账号状态已变化，请重新操作。")
    return user


def snapshot_epoch(user):
    """Legacy task snapshots must not silently bypass the lifecycle fence."""
    try:
        value = user["account_epoch"]
        state = user["account_state"]
    except (KeyError, IndexError):
        raise AccountLifecycleError("ACCOUNT_CHANGED", "旧任务缺少账号版本，需重新排队。") from None
    if state != "active":
        raise AccountLifecycleError("ACCOUNT_CLOSED", "账号已注销，任务已停止。")
    if type(value) is not int or value < 1:
        raise AccountLifecycleError("ACCOUNT_CHANGED", "账号版本无效，需重新排队。")
    return value


async def require_snapshot(db, user):
    return await require_active_user(db, user["qq_id"], expected_epoch=snapshot_epoch(user))


def web_account_available(account, now=None):
    """The same availability definition is used for login, sessions and roots."""
    now = int(time.time()) if now is None else now
    return bool(
        account and account["account_state"] == "active" and account["is_active"]
        and password_hash_usable(account["password_hash"])
        and not (account["must_change_password"] and account["temporary_password_expires_at"]
                 and int(account["temporary_password_expires_at"]) <= now)
    )


async def web_account(db, qq_id):
    async with db.execute(
        "SELECT a.qq_id,a.password_hash,a.role,a.must_change_password,a.is_active,"
        "a.credential_version,a.temporary_password_expires_at,u.account_state,u.account_epoch "
        "FROM web_accounts a "
        "JOIN users u ON u.qq_id=a.qq_id WHERE a.qq_id=?", (str(qq_id),),
    ) as cursor:
        return await cursor.fetchone()


async def require_web_actor(db, identity, *, roles=None):
    """Recheck captured credentials and roles while holding the final write lock."""
    if not db.in_transaction:
        raise RuntimeError("Web actor checks require a write transaction")
    if not identity:
        raise AccountLifecycleError("AUTH_REQUIRED", "请先登录。", 401)
    if identity.get("legacy"):
        if roles and "root" not in roles:
            raise AccountLifecycleError("FORBIDDEN", "当前角色无权执行此操作。", 403)
        return identity
    if type(identity.get("account_epoch")) is not int:
        raise AccountLifecycleError("ACCOUNT_CHANGED", "账号版本缺失，请重新登录。", 401)
    await require_active_user(db, identity["qq_id"], expected_epoch=identity["account_epoch"])
    account = await web_account(db, identity["qq_id"])
    if (not web_account_available(account)
            or account["credential_version"] != identity.get("credential_version")):
        raise AccountLifecycleError("AUTH_REQUIRED", "登录状态已变化，请重新登录。", 401)
    if roles and account["role"] not in roles:
        raise AccountLifecycleError("FORBIDDEN", "当前角色无权执行此操作。", 403)
    return {**identity, "role": account["role"]}


async def protect_last_root(db, qq_id, *, role, is_active, now=None):
    """Caller owns BEGIN IMMEDIATE; a configured legacy login is not a successor."""
    if not db.in_transaction:
        raise RuntimeError("Root protection requires a write transaction")
    target = await web_account(db, qq_id)
    if not target or target["role"] != "root" or (role == "root" and is_active):
        return
    async with db.execute(
        "SELECT a.qq_id,a.password_hash,a.role,a.must_change_password,a.is_active,"
        "a.credential_version,a.temporary_password_expires_at,u.account_state,u.account_epoch "
        "FROM web_accounts a "
        "JOIN users u ON u.qq_id=a.qq_id WHERE a.role='root' AND a.qq_id<>?",
        (str(qq_id),),
    ) as cursor:
        roots = await cursor.fetchall()
    if not any(web_account_available(account, now) for account in roots):
        raise AccountLifecycleError("LAST_ROOT_PROTECTED", "不能停用或降级最后一个可用的 Web root。")


async def bootstrap_root(db, qq_id, password_hash, now):
    """A stale empty-account check must not overwrite a new account or tombstone.

    The caller validates configuration and hashes the password before this lock.
    """
    await db.execute("BEGIN IMMEDIATE")
    try:
        async with db.execute("SELECT 1 FROM web_accounts LIMIT 1") as cursor:
            any_account = await cursor.fetchone()
        user = await user_lifecycle(db, qq_id)
        if any_account or (user and user["account_state"] != "active"):
            await db.rollback()
            return False
        if not user:
            await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq_id, qq_id))
        await db.execute(
            "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,"
            "credential_version,created_at,updated_at) VALUES(?,?,'root',0,1,1,?,?)",
            (qq_id, password_hash, now, now),
        )
        await db.commit()
        return True
    except BaseException:
        await db.rollback()
        raise
