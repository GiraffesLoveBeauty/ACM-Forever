"""Persist public contest names and start times independently of problem bodies."""

import asyncio
import json
import re
import time

import aiohttp

from .cf_client import cf_request


ATCODER_CONTESTS_URL = "https://kenkoooo.com/atcoder/resources/contests.json"
CACHE_SECONDS = 24 * 60 * 60
_atcoder_lock = asyncio.Lock()
_atcoder_next_request = 0.0


def contest_metadata(platform, payload):
    if platform == "codeforces" and isinstance(payload, dict):
        if payload.get("status") != "OK":
            raise ValueError("CF 比赛目录未返回 OK 状态")
        payload = payload.get("result")
    if platform not in {"codeforces", "atcoder"} or not isinstance(payload, list) or not payload:
        raise ValueError("比赛元数据须为非空数组，平台须为 codeforces 或 atcoder")
    result = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        name = item.get("name") if platform == "codeforces" else item.get("title")
        start = item.get("startTimeSeconds") if platform == "codeforces" else item.get("start_epoch_second")
        if platform == "codeforces":
            if type(cid) is not int or not 1 <= cid <= 9999999:
                continue
            cid = str(cid)
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", cid):
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        start = start if type(start) is int and 0 < start <= 253402300799 else None
        result[cid] = {"platform": platform, "contest_id": cid,
                       "contest_name": name.strip()[:300], "start_time": start}
    if not result:
        raise ValueError("比赛目录不包含可识别的比赛信息")
    return list(result.values())


async def save_contests(db, items):
    now = int(time.time())
    try:
        await db.executemany(
            "INSERT INTO crawler_contests(platform,contest_id,contest_name,start_time,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(platform,contest_id) DO UPDATE SET contest_name=excluded.contest_name,"
            "start_time=COALESCE(excluded.start_time,crawler_contests.start_time),updated_at=excluded.updated_at",
            [(item["platform"], item["contest_id"], item["contest_name"], item["start_time"], now) for item in items],
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return len(items)


async def fetch_contests(session, platform, downloader=None):
    if platform == "codeforces":
        return await cf_request(session, "contest.list", {"gym": "false"})
    if platform != "atcoder":
        raise ValueError("不支持的比赛平台")
    if downloader is not None:
        return json.loads((await downloader(ATCODER_CONTESTS_URL)).decode("utf-8-sig"))
    global _atcoder_next_request
    async with _atcoder_lock:
        await asyncio.sleep(max(0, _atcoder_next_request - time.monotonic()))
        try:
            async with session.get(ATCODER_CONTESTS_URL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                return await response.json()
        finally:
            _atcoder_next_request = time.monotonic() + 1.5


async def refresh_contests(db, session, platform, required_ids, downloader=None):
    """Fetch one bulk catalog only when a requested contest has missing/stale metadata."""
    async with db.execute(
        "SELECT contest_id FROM crawler_contests WHERE platform=? AND start_time IS NOT NULL AND updated_at>=?",
        (platform, int(time.time()) - CACHE_SECONDS),
    ) as cursor:
        fresh = {row[0] for row in await cursor.fetchall()}
    if set(required_ids) <= fresh:
        return 0
    payload = await fetch_contests(session, platform, downloader)
    return await save_contests(db, contest_metadata(platform, payload))
