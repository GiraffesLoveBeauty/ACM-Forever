"""Stable public identities, independent of private QQ and OJ account fields."""
import secrets


async def ensure_public_profiles(db):
    async with db.execute(
        "SELECT u.qq_id FROM users u LEFT JOIN mobile_public_profiles p ON p.qq_id=u.qq_id WHERE p.qq_id IS NULL"
    ) as cursor:
        missing = await cursor.fetchall()
    if missing:
        await db.executemany(
            "INSERT OR IGNORE INTO mobile_public_profiles(qq_id,public_member_id) VALUES(?,?)",
            [(row["qq_id"], secrets.token_urlsafe(24)) for row in missing],
        )
    return bool(missing)


async def initialize_mobile_profiles(db):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS mobile_public_profiles ("
        "qq_id TEXT PRIMARY KEY REFERENCES users(qq_id) ON DELETE CASCADE, "
        "public_member_id TEXT NOT NULL UNIQUE, motto TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT 0)"
    )
    await ensure_public_profiles(db)


async def prepare_public_profiles(db):
    if await ensure_public_profiles(db):
        await db.commit()
