"""Server problem catalog initialization and atomic statement/sample writes."""

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


async def initialize_problem_bank(db):
    schema = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    for statement in schema.split(";"):
        if statement.strip():
            await db.execute(statement)
    async with db.execute("PRAGMA table_info(crawler_problems)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if "statement_pdf" not in columns:
        await db.execute("ALTER TABLE crawler_problems ADD COLUMN statement_pdf BLOB")


async def problem_bank_status(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
        tables = {row[0] for row in await cursor.fetchall()}
    required = {"settings", "users", "web_accounts", "recommendations", "crawler_problems"}
    platforms = []
    if "crawler_problems" in tables:
        async with db.execute(
            "SELECT platform,COUNT(*) AS total,"
            "SUM(CASE WHEN last_fetch_status='ok' AND (statement_html IS NOT NULL OR statement_pdf IS NOT NULL) THEN 1 ELSE 0 END) AS collected,"
            "SUM(CASE WHEN last_fetch_status='failed' THEN 1 ELSE 0 END) AS failed,"
            "SUM(sample_count) AS samples FROM crawler_problems GROUP BY platform ORDER BY platform"
        ) as cursor:
            platforms = [dict(row) for row in await cursor.fetchall()]
    return {"initialized": required <= tables, "missing_tables": sorted(required - tables), "platforms": platforms}


def merge_metadata(old, metadata):
    merged = json.loads(old["metadata_json"]) if old else {}
    for key, value in metadata.items():
        if metadata.get("platform") == "luogu":
            if key == "luogu":
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
            continue
        if (key == "problem_rating" and value is None) or (key == "tags" and not value):
            merged.setdefault(key, value)
        else:
            merged[key] = value
    if merged.get("platform") == "luogu":
        merged["problem_rating"] = None
    return merged


async def save_catalog_entry(db, merged):
    await db.execute(
        """INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags)
        VALUES (?,?,?,?,?,?) ON CONFLICT(platform,problem_id) DO UPDATE SET
        problem_name=excluded.problem_name,problem_url=excluded.problem_url,
        problem_rating=CASE WHEN excluded.platform='luogu' THEN NULL ELSE COALESCE(excluded.problem_rating,recommendations.problem_rating) END,
        tags=CASE WHEN excluded.platform='luogu' OR excluded.tags<>'' THEN excluded.tags ELSE recommendations.tags END""",
        (merged["platform"], merged["problem_id"], merged["problem_name"], merged.get("problem_rating"),
         merged["problem_url"], ",".join(merged.get("tags", []))),
    )


async def save_metadata_batch(db, items):
    """Publish a catalog batch while preserving previously collected bodies and samples."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        for metadata in items:
            async with db.execute("SELECT metadata_json FROM crawler_problems WHERE platform=? AND problem_id=?",
                                  (metadata["platform"], metadata["problem_id"])) as cursor:
                merged = merge_metadata(await cursor.fetchone(), metadata)
            now = utc_now()
            await db.execute(
                """INSERT INTO crawler_problems
                (platform,problem_id,contest_id,problem_index,problem_name,problem_rating,problem_url,tags,metadata_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,problem_id) DO UPDATE SET
                contest_id=excluded.contest_id,problem_index=excluded.problem_index,problem_name=excluded.problem_name,
                problem_rating=excluded.problem_rating,problem_url=excluded.problem_url,tags=excluded.tags,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                (merged["platform"], merged["problem_id"], merged["contest_id"], merged.get("problem_index"),
                 merged["problem_name"], merged.get("problem_rating"), merged["problem_url"],
                 json.dumps(merged.get("tags", []), ensure_ascii=False), json.dumps(merged, ensure_ascii=False), now, now),
            )
            await save_catalog_entry(db, merged)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def save_problem(db, metadata, content):
    """Commit the problem body, samples and the existing catalog entry together."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        async with db.execute(
            "SELECT sample_count,metadata_json FROM crawler_problems WHERE platform=? AND problem_id=?",
            (metadata["platform"], metadata["problem_id"]),
        ) as cursor:
            old = await cursor.fetchone()
        if old and old["sample_count"] and not content["samples"] and not content.get("statement_pdf"):
            raise ValueError("新页面未解析到样例，保留已有题面和样例")
        merged = merge_metadata(old, metadata)
        now = utc_now()
        await db.execute(
            """INSERT INTO crawler_problems
            (platform,problem_id,contest_id,problem_index,problem_name,problem_rating,problem_url,
             tags,metadata_json,statement_html,statement_text,statement_pdf,statement_language,requested_language,
             samples,sample_count,statement_source_url,statement_sha256,statement_fetched_at,
             last_fetch_status,last_attempt_at,last_error,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ok',?,NULL,?,?)
            ON CONFLICT(platform,problem_id) DO UPDATE SET
            contest_id=excluded.contest_id,problem_index=excluded.problem_index,
            problem_name=excluded.problem_name,problem_rating=excluded.problem_rating,
            problem_url=excluded.problem_url,tags=excluded.tags,metadata_json=excluded.metadata_json,
            statement_html=excluded.statement_html,statement_text=excluded.statement_text,statement_pdf=excluded.statement_pdf,
            statement_language=excluded.statement_language,requested_language=excluded.requested_language,
            samples=excluded.samples,sample_count=excluded.sample_count,
            statement_source_url=excluded.statement_source_url,statement_sha256=excluded.statement_sha256,
            statement_fetched_at=excluded.statement_fetched_at,last_fetch_status='ok',
            last_attempt_at=excluded.last_attempt_at,last_error=NULL,updated_at=excluded.updated_at""",
            (merged["platform"], merged["problem_id"], merged["contest_id"], merged.get("problem_index"),
             merged["problem_name"], merged.get("problem_rating"), merged["problem_url"],
             json.dumps(merged.get("tags", []), ensure_ascii=False), json.dumps(merged, ensure_ascii=False),
             content["statement_html"], content["statement_text"], content.get("statement_pdf"), content["statement_language"],
             content["requested_language"], json.dumps(content["samples"], ensure_ascii=False),
             len(content["samples"]), content["source_url"], content["sha256"], now, now, now, now),
        )
        await save_catalog_entry(db, merged)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def record_problem_failure(db, platform, problem_id, error):
    await db.execute(
        "UPDATE crawler_problems SET last_fetch_status='failed',last_attempt_at=?,last_error=? "
        "WHERE platform=? AND problem_id=?",
        (utc_now(), str(error)[:1000], platform, problem_id),
    )
    await db.commit()
