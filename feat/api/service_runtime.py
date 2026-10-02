"""Runtime adapters for the API-owned database and OJ synchronization."""
import asyncio
import time
import uuid
from pathlib import Path

import aiohttp
import aiosqlite

from .acm_api.constants import PLATFORM_SYNC_CONCURRENCY
from .acm_api.database import connect_db
from .acm_api.sync_service import SyncMixin


class SyncEngine(SyncMixin):
    def __init__(self, db_path: Path, crawler_config: dict):
        self.db_path = Path(db_path)
        self.crawler_config = dict(crawler_config)
        self.db = None
        self._http_session = None
        self._sync_cycle_lock = asyncio.Lock()
        self._sync_user_locks = {}
        self._sync_user_semaphore = asyncio.Semaphore(4)
        self._platform_sync_semaphores = {
            platform: asyncio.Semaphore(limit)
            for platform, limit in PLATFORM_SYNC_CONCURRENCY.items()
        }

    async def start(self):
        self.db = await aiosqlite.connect(str(self.db_path))
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
        await self.db.execute("PRAGMA busy_timeout=5000")
        await self.db.execute("PRAGMA foreign_keys=ON")
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45)
        )

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self.db:
            await self.db.close()

    def _crawler_config(self):
        return self.crawler_config

    async def sync_account(self, qq_id, platforms, task):
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        try:
            async with self._sync_cycle_lock:
                for platform in platforms:
                    results[platform] = await self.sync_single_platform_for_days(
                        qq_id, platform, 0
                    )
            task["result"] = results
            task["status"] = (
                "completed"
                if all(value is not None and value >= 0 for value in results.values())
                else "failed"
            )
        except asyncio.CancelledError:
            task["status"] = "cancelled"
            raise
        except Exception as exc:
            task["status"] = "failed"
            task["result"] = {"error": str(exc)[:500]}
        finally:
            task["finished_at"] = int(time.time())


class WebTaskManager:
    def __init__(self, sync_engine: SyncEngine):
        self.sync_engine = sync_engine
        self.tasks = {}

    def submit_account_sync(self, qq_id, platforms):
        normalized = []
        for platform in platforms or ():
            value = "codeforces" if platform == "cf" else str(platform).strip()
            if value in {"codeforces", "luogu", "nowcoder", "atcoder", "cjlu"}:
                if value not in normalized:
                    normalized.append(value)
        if not normalized:
            return None

        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "账号全量同步",
            "qq_id": str(qq_id),
            "platform": ",".join(normalized),
            "days": 0,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(
            self.sync_engine.sync_account(str(qq_id), normalized, item)
        )
        return {"id": task_id}

    def snapshots(self):
        keys = (
            "id", "kind", "qq_id", "platform", "days", "status",
            "started_at", "finished_at", "result",
        )
        return [{key: item.get(key) for key in keys} for item in self.tasks.values()]

    def cancel(self, task_id):
        item = self.tasks.get(str(task_id))
        task = item.get("_task") if item else None
        if not task or task.done():
            return False
        task.cancel()
        return True


async def create_web_challenge(db_path, platform="", tag="", difficulty=None, owner_qq_id=None):
    from .acm_api.difficulty import (
        challenge_filter,
        challenge_time_limit,
        normalize_platform,
    )
    from .acm_api.training_logic import score_candidate

    platform = normalize_platform(platform)
    if platform and (difficulty is None or str(difficulty).strip() == ""):
        return {
            "success": False,
            "message": "已选择平台，请先选择该平台的难度后再生成挑战。",
        }
    try:
        difficulty_sql, difficulty_params, difficulty_label = challenge_filter(
            platform, difficulty, "r.problem_rating"
        )
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    sql = """
        SELECT r.platform, r.problem_id, r.problem_name, r.problem_rating,
               r.problem_url, r.tags
        FROM (
            SELECT platform, problem_id, problem_name, problem_rating, problem_url, tags
            FROM recommendations
            UNION
            SELECT platform, problem_id, problem_name, problem_rating, problem_url, tags
            FROM submissions
        ) r
        WHERE r.platform <> 'cjlu'
          AND r.problem_url IS NOT NULL AND r.problem_url <> ''
    """
    params = []
    if owner_qq_id:
        sql += (
            " AND NOT EXISTS (SELECT 1 FROM submissions mine "
            "WHERE mine.user_qq_id=? AND mine.platform=r.platform "
            "AND mine.problem_id=r.problem_id)"
        )
        params.append(str(owner_qq_id))
    if platform:
        sql += " AND r.platform=?"
        params.append(platform)
    if difficulty_sql:
        sql += " AND " + difficulty_sql
        params.extend(difficulty_params)
    if tag:
        sql += (
            " AND (r.problem_name LIKE ? OR r.problem_id LIKE ? "
            "OR COALESCE(r.tags, '') LIKE ?)"
        )
        params.extend([f"%{tag}%"] * 3)
    sql += " ORDER BY RANDOM() LIMIT 20"

    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        async with db.execute(sql, tuple(params)) as cursor:
            candidates = await cursor.fetchall()
    finally:
        await db.close()

    if not candidates:
        scope = platform or "全部平台"
        return {
            "success": False,
            "message": (
                f"{scope} 暂无匹配难度（{difficulty_label}）的题目，"
                "请先同步或补全题目难度。"
            ),
            "difficulty": difficulty_label,
        }

    target_rating = difficulty if difficulty is not None else 1000
    ranked = [
        (score_candidate(dict(row), target_rating, [tag] if tag else ()), row)
        for row in candidates
    ]
    ranked.sort(key=lambda item: item[0]["score"], reverse=True)
    score_info, problem = ranked[0]
    return {
        "success": True,
        "platform": problem["platform"],
        "problem_id": problem["problem_id"],
        "problem_name": problem["problem_name"],
        "problem_rating": problem["problem_rating"],
        "problem_url": problem["problem_url"],
        "tags": problem["tags"] or "",
        "recommendation_score": score_info["score"],
        "recommendation_reason": score_info["reason"],
        "difficulty": difficulty_label,
        "challenge_rating": difficulty_label,
        "time_limit_minutes": challenge_time_limit(platform, difficulty_label),
    }
