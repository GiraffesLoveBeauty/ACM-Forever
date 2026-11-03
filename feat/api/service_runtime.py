"""Runtime adapters for the API-owned database and OJ synchronization."""
import asyncio
import time
import uuid
from pathlib import Path

import aiohttp
import aiosqlite

from .acm_api.constants import PLATFORM_SYNC_CONCURRENCY
from .acm_api.database import connect_db, isolated_connection
from .acm_api.binding_service import platform_spec
from .acm_api.problem_sync import ProblemSync
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

    async def sync_account(self, qq_id, platforms, task, days=0, *, incremental=False):
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        try:
            async with isolated_connection(self.db) as connection:
                async with connection.execute("SELECT * FROM users WHERE account_state='active' AND qq_id=?", (str(qq_id),)) as cursor:
                    user = await cursor.fetchone()
            task["bindings"] = {}
            if user:
                for platform in platforms:
                    _, field, version = platform_spec(platform)
                    task["bindings"][platform] = {"account": user[field] or "", "version": int(user[version]), "account_epoch": user["account_epoch"]}
            async with self._sync_cycle_lock:
                for platform in platforms:
                    try:
                        results[platform] = await self.sync_single_platform_for_days(
                            qq_id, platform, days, incremental=incremental,
                            expected_binding=task["bindings"].get(platform),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # A failure on one OJ should not discard results from
                        # the other platforms in this account sync task.
                        results[platform] = -3
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

    async def sync_all_accounts(self, task, days=0):
        """Run the configured platforms for all users as one serialized API task."""
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        try:
            async with self._sync_cycle_lock:
                async with self.db.execute(
                    "SELECT qq_id FROM users WHERE account_state='active' AND (cf_handle IS NOT NULL OR luogu_id IS NOT NULL "
                    "OR nowcoder_id IS NOT NULL OR atcoder_handle IS NOT NULL OR cjlu_username IS NOT NULL) "
                    "ORDER BY qq_id"
                ) as cursor:
                    qq_ids = [row["qq_id"] for row in await cursor.fetchall()]
                for qq_id in qq_ids:
                    results[str(qq_id)] = {}
                    for platform in ("codeforces", "luogu", "nowcoder", "atcoder", "cjlu"):
                        try:
                            count = await self.sync_single_platform_for_days(
                                qq_id, platform, days
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            count = -1
                        if count is not None and count != -2:
                            results[str(qq_id)][platform] = count
            task["result"] = results
            task["status"] = "completed"
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
        self.problem_sync = ProblemSync(sync_engine.db_path)

    def submit_problem_sync(self, options):
        for item in self.tasks.values():
            if item.get("kind") == "题目采集" and item["status"] in {"queued", "running"}:
                if item["options"] == options:
                    return {"id": item["id"], "merged": True}
                return None
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id, "kind": "题目采集", "platform": options["platform"], "options": dict(options),
            "status": "queued", "started_at": None, "finished_at": None, "result": None,
            "progress": {"done": 0, "total": 0},
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(self.problem_sync.run(options, item))
        return {"id": task_id, "merged": False}

    def submit_account_sync(self, qq_id, platforms, days=0):
        normalized = []
        for platform in platforms or ():
            value = "codeforces" if platform == "cf" else str(platform).strip()
            if value in {"codeforces", "luogu", "nowcoder", "atcoder", "cjlu"}:
                if value not in normalized:
                    normalized.append(value)
        if not normalized:
            return None

        try:
            days = max(0, min(3650, int(days)))
        except (TypeError, ValueError):
            days = 0

        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "账号全量同步",
            "qq_id": str(qq_id),
            "platform": ",".join(normalized),
            "days": days,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(
            self.sync_engine.sync_account(str(qq_id), normalized, item, days=days)
        )
        return {"id": task_id}

    def submit_all_accounts_sync(self, days=0):
        if any(
            item.get("status") in {"queued", "running"}
            for item in self.tasks.values()
        ):
            return None
        try:
            days = max(0, min(3650, int(days)))
        except (TypeError, ValueError):
            days = 0
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "全员平台同步",
            "qq_id": "*",
            "platform": "all",
            "days": days,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(
            self.sync_engine.sync_all_accounts(item, days=days)
        )
        return {"id": task_id}

    def snapshots(self):
        keys = (
            "id", "kind", "qq_id", "platform", "days", "status",
            "started_at", "finished_at", "result",
            "progress", "bindings",
        )
        return [{key: item.get(key) for key in keys} for item in self.tasks.values()]

    def cancel(self, task_id):
        item = self.tasks.get(str(task_id))
        task = item.get("_task") if item else None
        if not task or task.done():
            return False
        task.cancel()
        if item["kind"] == "题目采集":
            item.update(status="cancelled", finished_at=int(time.time()))
        return True

    async def close(self):
        pending = []
        for task_id, item in self.tasks.items():
            task = item.get("_task")
            if task and not task.done():
                self.cancel(task_id)
                pending.append(task)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


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
