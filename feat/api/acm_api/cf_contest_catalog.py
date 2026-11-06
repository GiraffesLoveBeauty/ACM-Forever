"""Complete paired CF contest lists without guessing which problems they share."""

import asyncio
import json
import re
import time

import aiohttp
import aiosqlite

from .cf_client import CFUnavailable, cf_request
from .problem_bank import save_metadata_batch


CATALOG_CACHE_SECONDS = 7 * 86400
DIVISION = re.compile(r"^(.*?)\(Div\.\s*([12])((?:,[^)]*)?\).*)$", re.IGNORECASE)


async def save_cf_contest_catalog(db, contest_id, items):
    """Publish the complete list before marking it cached; keep saved bodies."""
    if not items or any(item["platform"] != "codeforces" or item["contest_id"] != contest_id for item in items):
        raise ValueError("CF 完整比赛目录包含无效题目")
    await save_metadata_batch(db, items)
    try:
        await db.execute(
            "INSERT INTO crawler_contest_catalogs(platform,contest_id,problem_ids,updated_at) "
            "VALUES('codeforces',?,?,?) ON CONFLICT(platform,contest_id) DO UPDATE SET "
            "problem_ids=excluded.problem_ids,updated_at=excluded.updated_at",
            (contest_id, json.dumps([item["problem_id"] for item in items]), int(time.time())),
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def _cached_catalog(db, contest_id):
    async with db.execute(
        "SELECT problem_ids,updated_at FROM crawler_contest_catalogs "
        "WHERE platform='codeforces' AND contest_id=?", (contest_id,),
    ) as cursor:
        cached = await cursor.fetchone()
    if not cached:
        return [], 0
    try:
        ids = json.loads(cached["problem_ids"])
    except (TypeError, ValueError):
        return [], 0
    if not isinstance(ids, list) or not ids or any(not isinstance(pid, str) for pid in ids):
        return [], 0
    async with db.execute(
        "SELECT metadata_json FROM crawler_problems WHERE platform='codeforces' AND contest_id=?",
        (contest_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    items = {}
    for row in rows:
        try:
            item = json.loads(row["metadata_json"])
        except (TypeError, ValueError):
            continue
        if (isinstance(item, dict) and item.get("platform") == "codeforces"
                and item.get("contest_id") == contest_id and isinstance(item.get("problem_id"), str)):
            items[item["problem_id"]] = item
    if any(pid not in items for pid in ids):
        return [], 0
    return [items[pid] for pid in ids], cached["updated_at"]


async def complete_cf_catalog(db, session, items, parse, *, progress=None, refresh=False):
    """Use official standings for paired divisions; tracker requests stay offline."""
    represented = {item["contest_id"] for item in items}
    pairs = {}
    async with db.execute(
        "SELECT contest_id,contest_name,start_time FROM crawler_contests "
        "WHERE platform='codeforces' AND start_time IS NOT NULL AND start_time>0",
    ) as cursor:
        for row in await cursor.fetchall():
            match = DIVISION.fullmatch(row["contest_name"])
            # A matching round name and start time identify candidates only.
            # Their actual problem membership always comes from the CF API.
            if match and match[1].strip():
                key = row["start_time"], match[1].strip().casefold(), match[3].strip().casefold()
                pairs.setdefault(key, {}).setdefault(match[2], []).append(row["contest_id"])
    contests = set()
    for divisions in pairs.values():
        if set(divisions) != {"1", "2"} or any(len(ids) != 1 for ids in divisions.values()):
            continue
        ids = {divisions["1"][0], divisions["2"][0]}
        if represented & ids:
            contests.update(ids)
    merged = {item["problem_id"]: item for item in items}
    bulk_ids = set(merged)
    errors = []
    if progress is not None and contests:
        progress.update(phase="contest_catalog", contests_done=0, contests_total=len(contests))
    for contest_id in sorted(contests, key=int):
        cached, updated = await _cached_catalog(db, contest_id)
        for item in cached:
            merged.setdefault(item["problem_id"], item)
        if refresh or not cached or updated < int(time.time()) - CATALOG_CACHE_SECONDS:
            try:
                data = await cf_request(session, "contest.standings", {"contestId": int(contest_id)})
                complete = parse(data.get("problems") if isinstance(data, dict) else None, contest_id)
                await save_cf_contest_catalog(db, contest_id, complete)
                for item in complete:
                    # Bulk metadata may have the more recent ratings/tags.
                    # Every contest retains its own problem ID and index.
                    if item["problem_id"] not in bulk_ids:
                        merged[item["problem_id"]] = item
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, OSError, ValueError, aiosqlite.Error, CFUnavailable) as error:
                errors.append({"contest_id": contest_id, "error": str(error)[:1000]})
        if progress is not None and contests:
            progress["contests_done"] += 1
    return list(merged.values()), errors
