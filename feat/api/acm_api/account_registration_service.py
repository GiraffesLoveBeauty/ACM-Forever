"""Create a fresh generation for a QQ whose previous account was closed."""
from .account_lifecycle_service import AccountLifecycleError, user_lifecycle
from .account_closure_service import archive_authorship, PRIVATE_TABLES


async def register_again(db, qq_id, snapshot, *, name, status, school, password_hash,
                         role, now, temporary_password_expires_at):
    if not db.in_transaction:
        raise RuntimeError("Account registration requires a write transaction")
    current = await user_lifecycle(db, qq_id)
    if not snapshot or not current or dict(current) != dict(snapshot):
        raise AccountLifecycleError("ACCOUNT_CHANGED", "账号状态已变化，请重新创建。")
    if current["account_state"] != "closed":
        raise AccountLifecycleError("ACCOUNT_EXISTS", "该 QQ 已有账号。")
    if not name:
        raise AccountLifecycleError("INVALID_REQUEST", "重新开户必须填写新账号昵称。", 400)
    # Also covers v1 tombstones created before the content ledger existed.
    await archive_authorship(db, qq_id, current["closed_at"] or now)
    await db.execute(
        "INSERT INTO account_registrations(qq_id,closed_epoch,new_epoch,created_at) VALUES(?,?,?,?)",
        (qq_id, current["account_epoch"], current["account_epoch"] + 1, now),
    )
    await db.execute(
        "UPDATE users SET account_state='active',account_epoch=account_epoch+1,closed_at=NULL,"
        "name=?,status=?,school=?,real_name=NULL,avatar_url=NULL,last_sync_timestamp=0,"
        "challenge_rating=1000,cf_handle=NULL,luogu_id=NULL,nowcoder_id=NULL,atcoder_handle=NULL,cjlu_username=NULL "
        "WHERE qq_id=?", (name, status, school, qq_id),
    )
    await db.execute(
        "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,"
        "credential_version,created_at,updated_at,temporary_password_expires_at) "
        "VALUES(?,?,?,1,1,1,?,?,?) ON CONFLICT(qq_id) DO UPDATE SET "
        "password_hash=excluded.password_hash,role=excluded.role,must_change_password=1,is_active=1,"
        "credential_version=web_accounts.credential_version+1,created_at=excluded.created_at,"
        "updated_at=excluded.updated_at,last_login_at=NULL,"
        "temporary_password_expires_at=excluded.temporary_password_expires_at",
        (qq_id, password_hash, role, now, now, temporary_password_expires_at),
    )
    # Neither old private state nor idempotency responses belong to a reused QQ.
    for table, owner in PRIVATE_TABLES.items():
        await db.execute(f"DELETE FROM {table} WHERE {owner}=?", (qq_id,))
    await db.execute("DELETE FROM wiki_requests WHERE actor=?", (qq_id,))
    await db.execute("DELETE FROM wiki_delete_previews WHERE actor=?", (qq_id,))
    await db.execute("UPDATE wiki_settings SET public_content_version=public_content_version+1 WHERE id=1")
