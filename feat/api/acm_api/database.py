# -*- coding: utf-8 -*-
"""数据库初始化、设置读写与排行榜查询。"""
import time

import aiosqlite


async def connect_db(db_path):
    """打开（或创建）数据库并初始化表结构，返回连接。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);")
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('report_enabled', 'true');")
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('report_cron_hour', '*');")
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('report_cron_minute', '0');")
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('hourly_report_limit', '10');")
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('contest_report_time', '');")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS users (qq_id TEXT PRIMARY KEY, name TEXT NOT NULL, cf_handle TEXT, luogu_id TEXT, nowcoder_id TEXT, atcoder_handle TEXT, status TEXT, school TEXT, last_sync_timestamp INTEGER DEFAULT 0);"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS web_accounts ("
        "qq_id TEXT PRIMARY KEY REFERENCES users(qq_id) ON DELETE CASCADE, "
        "password_hash TEXT NOT NULL, "
        "role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','admin','root')), "
        "must_change_password INTEGER NOT NULL DEFAULT 1 CHECK(must_change_password IN (0,1)), "
        "is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)), "
        "credential_version INTEGER NOT NULL DEFAULT 1, "
        "created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, last_login_at INTEGER, "
        "temporary_password_expires_at INTEGER)"
    )
    async with db.execute("PRAGMA table_info(web_accounts)") as cursor:
        web_account_cols = {row["name"] for row in await cursor.fetchall()}
    if "temporary_password_expires_at" not in web_account_cols:
        await db.execute("ALTER TABLE web_accounts ADD COLUMN temporary_password_expires_at INTEGER")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_web_accounts_role_active ON web_accounts(role,is_active)")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS account_bind_verifications ("
        "qq_id TEXT NOT NULL, platform TEXT NOT NULL, account TEXT NOT NULL, "
        "verification_code TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, "
        "PRIMARY KEY (qq_id, platform))"
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_bind_verifications_expiry ON account_bind_verifications(expires_at)")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_qq_id TEXT NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL, problem_name TEXT, problem_rating TEXT, problem_url TEXT, tags TEXT NOT NULL DEFAULT '', submit_time INTEGER NOT NULL, UNIQUE(user_qq_id, platform, problem_id));"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS challenges (id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL UNIQUE, title TEXT NOT NULL, target_count INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS notification_preferences (qq_id TEXT PRIMARY KEY, inactive_days INTEGER NOT NULL DEFAULT 7, enabled INTEGER NOT NULL DEFAULT 0, last_notified_at INTEGER NOT NULL DEFAULT 0)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS recommendations (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, problem_id TEXT NOT NULL, problem_name TEXT, problem_rating TEXT, problem_url TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', UNIQUE(platform, problem_id))"
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_submissions_user_time ON submissions(user_qq_id, submit_time)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_submissions_time ON submissions(submit_time)")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS user_platform_sync_state ("
        "user_qq_id TEXT NOT NULL, platform TEXT NOT NULL, cursor_timestamp INTEGER NOT NULL DEFAULT 0, "
        "last_attempt_at INTEGER NOT NULL DEFAULT 0, last_success_at INTEGER NOT NULL DEFAULT 0, "
        "last_status TEXT NOT NULL DEFAULT 'never', last_error_code TEXT, last_error_message TEXT, "
        "consecutive_failures INTEGER NOT NULL DEFAULT 0, next_retry_at INTEGER NOT NULL DEFAULT 0, "
        "updated_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_qq_id, platform))"
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_sync_state_status ON user_platform_sync_state(last_status, next_retry_at)")
    await db.execute("CREATE TABLE IF NOT EXISTS workspace_items (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_qq_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, body_md TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo', priority INTEGER NOT NULL DEFAULT 0, due_at INTEGER, context_type TEXT, context_id TEXT, sort_order INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, completed_at INTEGER)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_owner_status ON workspace_items(owner_qq_id, status, sort_order)")
    await db.execute("CREATE TABLE IF NOT EXISTS user_problem_state (owner_qq_id TEXT NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL, is_favorite INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'inbox', note_md TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL, PRIMARY KEY(owner_qq_id, platform, problem_id))")
    await db.execute("CREATE TABLE IF NOT EXISTS submission_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_qq_id TEXT NOT NULL, platform TEXT NOT NULL, external_submission_id TEXT, problem_id TEXT NOT NULL, contest_id TEXT, verdict TEXT, language TEXT, submitted_at INTEGER NOT NULL, source_code TEXT, created_at INTEGER NOT NULL, UNIQUE(platform, external_submission_id))")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_owner_time ON submission_attempts(owner_qq_id, submitted_at DESC)")
    await db.execute("CREATE TABLE IF NOT EXISTS review_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_qq_id TEXT NOT NULL, context_type TEXT NOT NULL, context_id TEXT NOT NULL, draft_md TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft', model TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
    await db.execute("CREATE TABLE IF NOT EXISTS random_challenges (id INTEGER PRIMARY KEY AUTOINCREMENT, qq_id TEXT NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL, problem_name TEXT, problem_rating INTEGER, problem_url TEXT NOT NULL, tags TEXT DEFAULT '', challenge_rating INTEGER NOT NULL, time_limit_minutes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, completed_at INTEGER)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_random_challenges_user_status ON random_challenges(qq_id, status, expires_at)")
    async with db.execute("PRAGMA table_info(random_challenges)") as cursor:
        challenge_cols = {row["name"] for row in await cursor.fetchall()}
    for col, definition in (("challenge_group_id", "TEXT"), ("zone", "TEXT"), ("requested_difficulty", "TEXT"), ("requested_tags", "TEXT DEFAULT ''")):
        if col not in challenge_cols:
            await db.execute(f"ALTER TABLE random_challenges ADD COLUMN {col} {definition}")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_random_challenges_group_zone ON random_challenges(qq_id, challenge_group_id, zone, status)")
    await db.execute("CREATE TABLE IF NOT EXISTS review_states (owner_qq_id TEXT NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL, grade TEXT NOT NULL DEFAULT 'new', interval_days INTEGER NOT NULL DEFAULT 0, ease REAL NOT NULL DEFAULT 2.5, due_at INTEGER NOT NULL DEFAULT 0, review_count INTEGER NOT NULL DEFAULT 0, last_review_at INTEGER NOT NULL DEFAULT 0, difficulty INTEGER NOT NULL DEFAULT 0, mistakes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(owner_qq_id, platform, problem_id))")
    await db.execute("CREATE TABLE IF NOT EXISTS contest_problem_reviews (owner_qq_id TEXT NOT NULL, contest_id TEXT NOT NULL, problem_id TEXT NOT NULL, verdict TEXT, rating INTEGER, note_md TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo', updated_at INTEGER NOT NULL, PRIMARY KEY(owner_qq_id, contest_id, problem_id))")
    await db.execute("CREATE TABLE IF NOT EXISTS study_plan_items (owner_qq_id TEXT NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', position INTEGER NOT NULL DEFAULT 0, added_at INTEGER NOT NULL, completed_at INTEGER, PRIMARY KEY(owner_qq_id, platform, problem_id))")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_study_plan_owner_status ON study_plan_items(owner_qq_id, status, position)")


    await db.execute("CREATE INDEX IF NOT EXISTS idx_review_due ON review_states(owner_qq_id, due_at, grade)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_problem ON submission_attempts(owner_qq_id, platform, problem_id, submitted_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_contest ON submission_attempts(owner_qq_id, platform, contest_id, problem_id, submitted_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_contest_review_queue ON contest_problem_reviews(owner_qq_id, status, updated_at DESC)")

    for table in ("submissions", "recommendations"):
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            cols = {row["name"] for row in await cursor.fetchall()}
        if "tags" not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN tags TEXT DEFAULT ''")
    async with db.execute("PRAGMA table_info(users)") as cursor:
        user_cols = {row["name"] for row in await cursor.fetchall()}
    if "challenge_rating" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN challenge_rating INTEGER NOT NULL DEFAULT 1000")
    if "real_name" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN real_name TEXT")
    # 老库迁移：补充牛客 / AtCoder / 校OJ 列
    async with db.execute("PRAGMA table_info(users)") as cursor:
        user_cols = {row["name"] for row in await cursor.fetchall()}
    for col in ("nowcoder_id", "atcoder_handle", "cjlu_username"):
        if col not in user_cols:
            await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")

    # 账号绑定的最终防线：即使来自 WebUI 或其他代码路径，也不能把同一平台账号
    # 绑定给多个 QQ。使用触发器而不是唯一索引，是为了兼容旧库中已经存在的重复数据；
    # 旧数据不自动删除，但新的插入/修改会被拒绝。
    account_fields = (
        ("cf_handle", "Codeforces"),
        ("luogu_id", "Luogu"),
        ("nowcoder_id", "Nowcoder"),
        ("atcoder_handle", "AtCoder"),
        ("cjlu_username", "CJLU"),
    )
    duplicate_checks_insert = []
    duplicate_checks_update = []
    for field, label in account_fields:
        duplicate_checks_insert.append(
            "SELECT RAISE(ABORT, 'duplicate account binding: " + field + "') "
            "WHERE COALESCE(NULLIF(LOWER(TRIM(NEW." + field + ")), ''), '') <> '' "
            "AND EXISTS (SELECT 1 FROM users AS other WHERE other.qq_id <> NEW.qq_id "
            "AND LOWER(TRIM(other." + field + ")) = LOWER(TRIM(NEW." + field + ")))"
        )
        duplicate_checks_update.append(
            "SELECT RAISE(ABORT, 'duplicate account binding: " + field + "') "
            "WHERE COALESCE(NULLIF(LOWER(TRIM(NEW." + field + ")), ''), '') <> '' "
            "AND COALESCE(NULLIF(LOWER(TRIM(NEW." + field + ")), ''), '') <> "
            "COALESCE(NULLIF(LOWER(TRIM(OLD." + field + ")), ''), '') "
            "AND EXISTS (SELECT 1 FROM users AS other WHERE other.qq_id <> NEW.qq_id "
            "AND LOWER(TRIM(other." + field + ")) = LOWER(TRIM(NEW." + field + ")))"
        )
    await db.execute(
        "CREATE TRIGGER IF NOT EXISTS users_prevent_duplicate_account_insert "
        "BEFORE INSERT ON users BEGIN " + "; ".join(duplicate_checks_insert) + "; END"
    )
    await db.execute(
        "CREATE TRIGGER IF NOT EXISTS users_prevent_duplicate_account_update "
        "BEFORE UPDATE OF cf_handle, luogu_id, nowcoder_id, atcoder_handle, cjlu_username ON users BEGIN "
        + "; ".join(duplicate_checks_update) + "; END"
    )
    for platform, field in (("codeforces", "cf_handle"), ("luogu", "luogu_id"), ("nowcoder", "nowcoder_id"), ("atcoder", "atcoder_handle"), ("cjlu", "cjlu_username")):
        await db.execute(
            "INSERT OR IGNORE INTO user_platform_sync_state "
            "(user_qq_id, platform, cursor_timestamp, last_success_at, last_status, updated_at) "
            f"SELECT qq_id, ?, COALESCE(last_sync_timestamp, 0), COALESCE(last_sync_timestamp, 0), "
            "CASE WHEN COALESCE(last_sync_timestamp, 0) > 0 THEN 'migrated' ELSE 'never' END, "
            "? FROM users WHERE " + field + " IS NOT NULL AND TRIM(" + field + ") <> ''",
            (platform, int(time.time())),
        )
    await db.execute("UPDATE users SET name = cf_handle WHERE cf_handle IS NOT NULL AND TRIM(cf_handle) <> '' AND (name IS NULL OR TRIM(name) = '' OR name = qq_id)")
    await db.commit()
    return db


async def get_setting(db, key, default=None):
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
        return row["value"] if row else default


async def set_setting(db, key, value):
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    await db.commit()


async def get_all_settings(db) -> dict:
    settings = {}
    async with db.execute("SELECT key, value FROM settings") as cursor:
        async for row in cursor:
            settings[row["key"]] = row["value"]
    return settings


async def validate_submission_data(db, repair=False) -> dict:
    """检查并可选清理同一用户同平台的规范化重复题目 ID。"""
    prefix_map = {"nc_": "nowcoder", "atc_": "atcoder", "cf_": "codeforces", "luogu_": "luogu", "cjlu_": "cjlu"}
    async with db.execute("SELECT * FROM submissions ORDER BY id") as cursor:
        rows = await cursor.fetchall()
    seen = set()
    remove_ids = []
    rename_rows = []
    legacy_count = duplicate_count = 0
    for row in rows:
        pid = row["problem_id"] or ""
        canonical = pid
        for prefix, platform in prefix_map.items():
            if row["platform"] == platform and pid.startswith(prefix):
                canonical = pid[len(prefix):]
                legacy_count += 1
                break
        key = (row["user_qq_id"], row["platform"], canonical)
        if key in seen:
            duplicate_count += 1
            remove_ids.append((row["id"],))
        else:
            seen.add(key)
            if canonical != pid:
                rename_rows.append((canonical, row["id"]))
    if repair:
        if remove_ids:
            await db.executemany("DELETE FROM submissions WHERE id = ?", remove_ids)
        if rename_rows:
            await db.executemany("UPDATE submissions SET problem_id = ? WHERE id = ?", rename_rows)
        if remove_ids or rename_rows:
            await db.commit()
    return {"duplicates": duplicate_count, "legacy": legacy_count, "removed": len(remove_ids) if repair else 0, "normalized": len(rename_rows) if repair else 0}
