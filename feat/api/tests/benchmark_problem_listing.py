"""Reproducible synthetic SQL benchmark; never opens a configured/production DB.

Run from the repository root:
  python feat/api/tests/benchmark_problem_listing.py --problems 20000 --ac 100000
Cold means a fresh SQLite connection, not an OS/disk cache purge. Timings exclude
HTTP, authentication and rendering; the old/new SQL use the same source fixture.
The frozen legacy query is the reference from main 91a3ad6, not a runtime fallback.
"""
import argparse
import asyncio
import json
import platform
import re
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_listing import ListingConnection, indexed_query, listing_page, listing_tags
from feat.api.acm_api.problem_tags import has_problem_tag, problem_tags
from feat.api.acm_api.problem_tracker import problem_id_key
import aiosqlite

LEGACY_QUERY = """
    WITH sources AS (
        SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags,
               0 AS source,0 AS submit_time,NULL AS own_ac FROM crawler_problems
        UNION ALL
        SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags,
               1,0,NULL FROM recommendations
        UNION ALL
        SELECT platform,problem_id,problem_name,problem_rating,problem_url,
               CASE WHEN user_qq_id=owner THEN tags ELSE '' END,2,submit_time,
               CASE WHEN user_qq_id=owner THEN submit_time END
        FROM submissions CROSS JOIN (SELECT ? AS owner)
    ), keyed AS (
        SELECT *,problem_id_key(platform,problem_id) AS id_key FROM sources
    ), ranked AS (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY platform,id_key
                ORDER BY CASE source WHEN 1 THEN 0 WHEN 0 THEN 1 ELSE 2 END,
                         submit_time DESC,problem_id
            ) AS position,
            FIRST_VALUE(tags) OVER (
                PARTITION BY platform,id_key
                ORDER BY problem_has_tags(tags) DESC,source,submit_time DESC,problem_id
            ) AS effective_tags,
            MAX(own_ac) OVER (PARTITION BY platform,id_key) AS ac_at
        FROM keyed
    ), personal AS (
        SELECT platform,problem_id_key(platform,problem_id) AS id_key,
               MAX(is_favorite) AS is_favorite,
               MAX(COALESCE(state,'inbox')<>'inbox') AS outside_inbox
        FROM user_problem_state WHERE owner_qq_id=?
        GROUP BY platform,id_key
    )
    SELECT p.platform,CASE WHEN p.platform='luogu' THEN p.id_key ELSE p.problem_id END AS problem_id,
           p.problem_name,p.problem_rating,p.problem_url,p.id_key,p.ac_at,
           CASE WHEN problem_has_tags(p.effective_tags) THEN p.effective_tags ELSE '' END AS tags,
           COALESCE(s.is_favorite,0) AS is_favorite,COALESCE(s.outside_inbox,0) AS outside_inbox
    FROM ranked p LEFT JOIN personal s ON s.platform=p.platform AND s.id_key=p.id_key
    WHERE p.position=1
"""

LEGACY_TIME = """SELECT p.*,t.source_time,t.first_seen_at,COALESCE(t.source_time,t.first_seen_at) AS problem_time
FROM ({base}) p LEFT JOIN (
 SELECT c.platform,problem_id_key(c.platform,c.problem_id) AS id_key,
 MIN(CAST(strftime('%s',c.created_at) AS INTEGER)) AS first_seen_at,
 MAX(CASE WHEN c.platform<>'luogu' AND d.start_time>0 THEN d.start_time END) AS source_time
 FROM crawler_problems c LEFT JOIN crawler_contests d ON d.platform=c.platform AND d.contest_id=c.contest_id
 GROUP BY c.platform,problem_id_key(c.platform,c.problem_id)
) t ON t.platform=p.platform AND t.id_key=problem_id_key(p.platform,p.problem_id) WHERE p.platform='codeforces'"""


async def open_read(path):
    db = await aiosqlite.connect(path, factory=ListingConnection)
    db.row_factory = aiosqlite.Row
    await db.create_function("problem_id_key", 2, problem_id_key, deterministic=True)
    await db.create_function("problem_has_tags", 1, lambda value: bool(problem_tags(value)), deterministic=True)
    await db.create_function("problem_has_tag", 2, has_problem_tag, deterministic=True)
    return db


async def legacy(db, scenario):
    params = ["member", "member"]
    if scenario == "tags":
        async with db.execute("SELECT DISTINCT tags FROM (" + LEGACY_QUERY + ") WHERE platform='codeforces' AND tags<>''", params) as cursor:
            return sorted({tag.casefold() for row in await cursor.fetchall() for tag in problem_tags(row[0])})
    query = LEGACY_TIME.format(base=LEGACY_QUERY)
    if scenario == "filter":
        query += " AND problem_has_tag(p.tags,?)=1"
        params.append("math")
    if scenario == "solved":
        query += " AND ac_at IS NOT NULL"
    async with db.execute("SELECT COUNT(*) FROM (" + query + ")", params) as cursor:
        total = (await cursor.fetchone())[0]
    order = "ac_at DESC,p.platform,p.problem_id" if scenario == "solved" else "problem_time IS NULL,problem_time DESC,p.platform,problem_id_key(p.platform,p.problem_id),p.problem_id"
    async with db.execute(query + " ORDER BY " + order + " LIMIT 20 OFFSET ?", params + [10000 if scenario == "deep_page" else 0]) as cursor:
        rows = await cursor.fetchall()
    return {"total": total, "ids": [row["problem_id"] for row in rows]}


async def indexed(db, scenario):
    if scenario == "tags":
        return [tag.casefold() for tag in await listing_tags(db, "member", "codeforces")]
    args = {"platform": "codeforces", "page_size": "20"}
    if scenario == "filter":
        args["problem_tag"] = "math"
    if scenario == "solved":
        args["scope"] = "solved"
    if scenario == "deep_page":
        args["page"] = "501"
    result = await listing_page(db, "member", args)
    return {"total": result["total"], "ids": [row["problem_id"] for row in result["items"]]}


async def timed(db, callback, scenario):
    start = time.perf_counter()
    result = await callback(db, scenario)
    return round((time.perf_counter() - start) * 1000, 3), result


async def main(count, ac, repeats):
    with tempfile.TemporaryDirectory(prefix="acm-listing-benchmark-") as directory:
        path = Path(directory) / "synthetic.db"
        db = await connect_db(path)
        await db.close()
        source = sqlite3.connect(path)
        try:
            # Recreate a pre-index installation so migration includes table/index creation.
            for (name,) in source.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'listing_%'").fetchall():
                source.execute('DROP TRIGGER "' + name + '"')
            for table in ("problem_listing", "problem_listing_tags", "problem_listing_tag_options", "problem_listing_native_tags", "member_problem_index", "member_problem_tags", "problem_listing_dirty", "member_problem_dirty"):
                source.execute("DROP TABLE " + table)
            for index in ("idx_submissions_catalog_identity", "idx_submissions_member_identity", "idx_recommendations_identity", "idx_problem_state_identity"):
                source.execute("DROP INDEX " + index)
            source.execute("DELETE FROM settings WHERE key LIKE 'problem_listing_%'")
            source.executemany("INSERT INTO crawler_contests VALUES('codeforces',?,?,?,1)",
                               [(str(i), f"Contest {i}", 1700000000 + i * 60) for i in range(1, count + 1)])
            source.executemany("INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_name,problem_rating,problem_url,tags,metadata_json,created_at,updated_at,statement_html) VALUES('codeforces',?,?,?,?,?,?,'{}','2026-01-01','2026-01-01',?)",
                               [(f"cf_{i}A", str(i), f"Problem {i}", 800 + i % 2000, f"https://example.test/{i}", json.dumps(["math" if i % 2 else "dp", "implementation"]), "body " * 100) for i in range(1, count + 1)])
            source.executemany("INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) VALUES('codeforces',?,?,?,?,?)",
                               [(f"cf_{i}A", f"Problem {i}", 800 + i % 2000, f"https://example.test/{i}", "math,implementation" if i % 2 else "dp,implementation") for i in range(1, count + 1)])
            personal = min(1000, count)
            rows = [("member", f"cf_{i}A", 1700000000 + i) for i in range(1, personal + 1)]
            rows += [(f"other-{i // count}", f"cf_{i % count + 1}A", 1700000000 + i) for i in range(ac - personal)]
            source.executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces',?,?)", rows)
            source.commit()
        finally:
            source.close()
        source = sqlite3.connect(path)
        size_before = source.execute("PRAGMA page_count").fetchone()[0] * source.execute("PRAGMA page_size").fetchone()[0]
        source.close()
        start = time.perf_counter()
        db = await connect_db(path)
        migration_ms = round((time.perf_counter() - start) * 1000, 3)
        async with db.execute("PRAGMA page_count") as cursor:
            page_count = (await cursor.fetchone())[0]
        async with db.execute("PRAGMA page_size") as cursor:
            size_after = page_count * (await cursor.fetchone())[0]
        await db.close()
        results = {}
        for scenario in ("list", "tags", "filter", "solved", "deep_page"):
            row = {}
            reference = None
            for name, callback in (("legacy", legacy), ("indexed", indexed)):
                db = await open_read(path)
                try:
                    statements = []
                    await db.set_trace_callback(statements.append)
                    cold, result = await timed(db, callback, scenario)
                    await db.set_trace_callback(None)
                    query_count = len(statements)
                    warm = [(await timed(db, callback, scenario))[0] for _ in range(repeats)]
                    row[name] = {"sql_statements": query_count, "fresh_connection_ms": cold, "warm_median_ms": round(statistics.median(warm), 3), "warm_runs_ms": warm}
                    if reference is None:
                        reference = result
                    elif result != reference:
                        raise AssertionError((scenario, "result mismatch", reference, result))
                finally:
                    await db.close()
            row["warm_speedup"] = round(row["legacy"]["warm_median_ms"] / max(row["indexed"]["warm_median_ms"], .001), 2)
            results[scenario] = row
            print(json.dumps({"finished": scenario, **row}), file=sys.stderr, flush=True)
        db = await open_read(path)
        try:
            plans = {}
            for scope in ("all", "solved"):
                query, params = await indexed_query(db, "member", {"platform": "codeforces", "scope": scope})
                order = "m.ac_order,m.platform,m.id_key" if scope == "solved" else "p.sort_unknown,p.sort_order,p.platform,p.id_key"
                async with db.execute("EXPLAIN QUERY PLAN " + query + " ORDER BY " + order + " LIMIT 20", params) as cursor:
                    plans[scope] = [row[3] for row in await cursor.fetchall()]
                async with db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*) FROM (" + query + ")", params) as cursor:
                    plans[scope + "_count"] = [row[3] for row in await cursor.fetchall()]
            query, params = await indexed_query(db, "member", {"platform": "codeforces", "problem_tag": "math"})
            async with db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*) FROM (" + query + ")", params) as cursor:
                plans["filter_count"] = [row[3] for row in await cursor.fetchall()]
            before = {scenario: (await timed(db, indexed, scenario))[0] for scenario in ("list", "tags", "solved")}
            write_start = time.perf_counter()
            await db.executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces',?,?)",
                                 [(f"extra-{i // count}", f"cf_{i % count + 1}A", 1800000000 + i) for i in range(ac)])
            await db.commit()
            sync_ms = round((time.perf_counter() - write_start) * 1000, 3)
            after = {scenario: (await timed(db, indexed, scenario))[0] for scenario in ("list", "tags", "solved")}
        finally:
            await db.close()
        print(json.dumps({"environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "os": platform.platform()},
                          "fixture": {"problems": count, "ac": ac, "owner_ac": personal, "page_size": 20}, "migration_ms": migration_ms, "backfill_page_growth_bytes": size_after - size_before,
                          "results": results, "plans": plans, "other_members_scale": {"ac_before": ac, "ac_after": ac * 2, "extra_ac_insert_and_index_ms": sync_ms, "before_ms": before, "after_ms": after},
                          "notes": "Synthetic SQL/serialization helpers only; not production or complete HTTP latency. Fresh connection retains OS file cache. Different time semantics are excluded by using known source times for all fixture problems."}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problems", type=int, default=20000)
    parser.add_argument("--ac", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.problems < 10020 or args.ac < 1000 or args.repeats < 1:
        parser.error("Use at least 10020 problems, 1000 AC relations and one repeat")
    asyncio.run(main(args.problems, args.ac, args.repeats))
