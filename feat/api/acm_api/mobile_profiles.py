"""Stable public identities, independent of private QQ and OJ account fields."""
import secrets


async def ensure_public_profiles(db):
    async with db.execute(
        "SELECT u.qq_id,u.account_epoch FROM users u LEFT JOIN mobile_public_profiles p ON p.qq_id=u.qq_id "
        "WHERE u.account_state='active' AND (p.qq_id IS NULL OR p.account_epoch<>u.account_epoch)"
    ) as cursor:
        missing = await cursor.fetchall()
    if missing:
        await db.executemany(
            "INSERT INTO mobile_public_profiles(qq_id,public_member_id,account_epoch) VALUES(?,?,?) "
            "ON CONFLICT(qq_id) DO UPDATE SET public_member_id=excluded.public_member_id,"
            "account_epoch=excluded.account_epoch,motto='',updated_at=0 "
            "WHERE mobile_public_profiles.account_epoch<>excluded.account_epoch",
            [(row["qq_id"], secrets.token_urlsafe(24), row["account_epoch"]) for row in missing],
        )
    return bool(missing)


async def initialize_mobile_profiles(db):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS mobile_public_profiles ("
        "qq_id TEXT PRIMARY KEY REFERENCES users(qq_id) ON DELETE CASCADE, "
        "public_member_id TEXT NOT NULL UNIQUE, motto TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT 0, "
        "account_epoch INTEGER NOT NULL DEFAULT 1)"
    )
    async with db.execute("PRAGMA table_info(mobile_public_profiles)") as cursor:
        columns = {row["name"] for row in await cursor.fetchall()}
    if "account_epoch" not in columns:
        # Old IDs belong to the original incarnation; never attach them to a recreated account.
        await db.execute("ALTER TABLE mobile_public_profiles ADD COLUMN account_epoch INTEGER NOT NULL DEFAULT 1")
    await ensure_public_profiles(db)


async def prepare_public_profiles(db):
    if await ensure_public_profiles(db):
        await db.commit()
