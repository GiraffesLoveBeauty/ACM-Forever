"""Runtime adapters for the API-owned database and OJ synchronization."""
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import aiosqlite

from .acm_api.constants import PLATFORM_SYNC_CONCURRENCY
from .acm_api.database import connect_db, isolated_connection
from .acm_api.binding_service import platform_spec
from .acm_api.problem_sync import ProblemSync, sync_options
from .acm_api.sync_service import SyncMixin
from .acm_api.event_log import emit


PROBLEM_SYNC_TIMEZONE = timezone(timedelta(hours=8))
PROBLEM_SYNC_HOUR = 4
PROBLEM_SYNC_RETRY_SECONDS = 60


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

    @staticmethod
    def binding_snapshot(user, platforms):
        result = {}
        for platform in platforms:
            _, field, version = platform_spec(platform)
            result[platform] = {"account": user[field] or "", "version": int(user[version]),
                                "account_epoch": user["account_epoch"]}
        return result

    async def sync_account(self, qq_id, platforms, task, days=0, *, incremental=False):
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        try:
            async with isolated_connection(self.db) as connection:
                async with connection.execute("SELECT * FROM users WHERE account_state='active' AND qq_id=?", (str(qq_id),)) as cursor:
                    user = await cursor.fetchone()
            if not user or user["account_epoch"] != task.get("account_epoch", 1):
                task.update(status="cancelled", bindings={}, result=None)
                return
            task["account_epoch"] = user["account_epoch"]
            if "bindings" not in task:
                task["bindings"] = {}
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
                members = task.get("_account_snapshots", [])
                for user in members:
                    qq_id = user["qq_id"]
                    results[str(qq_id)] = {}
                    for platform in ("codeforces", "luogu", "nowcoder", "atcoder", "cjlu"):
                        try:
                            count = await self.sync_single_platform_for_days(
                                qq_id, platform, days,
                                expected_binding=self.binding_snapshot(user, [platform])[platform],
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
        self._daily_problem_sync_task = None
        self._claiming_daily_problem_sync = False

    async def _logged_task(self, operation, item, *args, **kwargs):
        fields = {"task_id": item["id"], "task_kind": item.get("kind", "后台任务")}
        emit("task.started", "后台任务开始执行", **fields)
        final_status = None
        try:
            return await operation(*args, **kwargs)
        except asyncio.CancelledError:
            final_status = "cancelled"
            raise
        except Exception:
            final_status = "failed"
            raise
        finally:
            status = final_status or item.get("status")

            def failed(value):
                if isinstance(value, dict):
                    return ("error" in value or any(type(value.get(key)) is int and value[key] > 0
                                                   for key in ("failure_count", "failed_count"))
                            or any(failed(v) for v in value.values()))
                return type(value) is int and value < 0 and value != -2

            if status == "failed":
                level, message = "error", "后台任务执行失败，请在同步任务页面查看结果"
            elif status in {"cancelled", "interrupted"}:
                level, message = "warning", "后台任务已取消或中断"
            elif status == "completed" and not failed(item.get("result")):
                level, message = "info", "后台任务已结束，请在同步任务页面查看各平台结果"
            else:
                level, message = "warning", "后台任务已结束，部分操作未完成，请查看任务结果"
            emit("task.finished", message, level, **fields)

    def _active_problem_sync(self):
        return next((item for item in self.tasks.values()
                     if item.get("kind") == "题目采集" and item["status"] in {"queued", "running"}), None)

    def submit_problem_sync(self, options):
        if self._claiming_daily_problem_sync:
            return None
        active = self._active_problem_sync()
        if active is not None:
            return {"id": active["id"], "merged": True} if active["options"] == options else None
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id, "kind": "题目采集", "platform": options["platform"], "options": dict(options),
            "status": "queued", "started_at": None, "finished_at": None, "result": None,
            "progress": {"done": 0, "total": 0},
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(self._logged_task(self.problem_sync.run, item, options, item))
        return {"id": task_id, "merged": False}

    def start_daily_problem_sync(self):
        if self._daily_problem_sync_task is None:
            self._daily_problem_sync_task = asyncio.create_task(
                self._daily_problem_sync_loop(), name="daily-problem-sync",
            )

    async def _claim_daily_problem_sync(self, platform, day):
        async with aiosqlite.connect(str(self.sync_engine.db_path)) as db:
            async with db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE settings.value<excluded.value",
                (f"daily_problem_sync_{platform}", day),
            ) as cursor:
                claimed = cursor.rowcount == 1
            await db.commit()
        return claimed

    async def _run_daily_problem_sync(self):
        day = datetime.now(PROBLEM_SYNC_TIMEZONE).date()
        for platform in ("atcoder", "codeforces"):
            if datetime.now(PROBLEM_SYNC_TIMEZONE).date() != day:
                break
            if self._claiming_daily_problem_sync or self._active_problem_sync() is not None:
                return False
            # Hold admission across the SQLite claim so manual work cannot
            # take the slot after today's run has been recorded.
            self._claiming_daily_problem_sync = True
            try:
                claimed = await self._claim_daily_problem_sync(platform, day.isoformat())
            finally:
                self._claiming_daily_problem_sync = False
            if not claimed:
                continue
            for task_id, item in list(self.tasks.items()):
                if item.get("platform") == platform and item.get("options", {}).get("scheduled") and item["_task"].done():
                    del self.tasks[task_id]
            options = sync_options({"platform": platform, "scope": "platform"})
            options["scheduled"] = True
            task_id = self.submit_problem_sync(options)["id"]
            await asyncio.gather(self.tasks[task_id]["_task"], return_exceptions=True)
        return True

    async def _daily_problem_sync_loop(self):
        while True:
            now = datetime.now(PROBLEM_SYNC_TIMEZONE)
            due = now.replace(hour=PROBLEM_SYNC_HOUR, minute=0, second=0, microsecond=0)
            if now < due:
                await asyncio.sleep((due - now).total_seconds())
                continue
            try:
                complete = await self._run_daily_problem_sync()
            except (OSError, aiosqlite.Error):
                emit("problem_sync.schedule_failed", "每日题库更新暂无法安排，稍后重试", "warning")
                complete = False
            delay = PROBLEM_SYNC_RETRY_SECONDS
            if complete:
                delay = (due + timedelta(days=1) - datetime.now(PROBLEM_SYNC_TIMEZONE)).total_seconds()
            await asyncio.sleep(max(0, delay))

    async def submit_account_sync(self, qq_id, platforms, days=0, *, expected_epoch=None):
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

        async with aiosqlite.connect(str(self.sync_engine.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE qq_id=? AND account_state='active'", (str(qq_id),)) as cursor:
                user = await cursor.fetchone()
        if not user or expected_epoch is not None and user["account_epoch"] != expected_epoch:
            return None
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "账号全量同步",
            "qq_id": str(qq_id),
            "account_epoch": user["account_epoch"],
            "bindings": SyncEngine.binding_snapshot(user, normalized),
            "platform": ",".join(normalized),
            "days": days,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(
            self._logged_task(self.sync_engine.sync_account, item, str(qq_id), normalized, item, days=days)
        )
        return {"id": task_id}

    async def submit_all_accounts_sync(self, days=0):
        if any(
            item.get("status") in {"queued", "running"}
            for item in self.tasks.values()
        ):
            return None
        try:
            days = max(0, min(3650, int(days)))
        except (TypeError, ValueError):
            days = 0
        async with aiosqlite.connect(str(self.sync_engine.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE account_state='active' ORDER BY qq_id") as cursor:
                members = [dict(row) for row in await cursor.fetchall()]
        # Reading the durable snapshots yields control. Reserve only if another
        # request has not queued a task while that read was in progress.
        if any(item.get("status") in {"queued", "running"} for item in self.tasks.values()):
            return None
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "全员平台同步",
            "qq_id": "*",
            "_account_snapshots": members,
            "_account_epochs": {user["qq_id"]: user["account_epoch"] for user in members},
            "platform": "all",
            "days": days,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        item["_task"] = asyncio.create_task(
            self._logged_task(self.sync_engine.sync_all_accounts, item, item, days=days)
        )
        return {"id": task_id}

    def snapshots(self):
        keys = (
            "id", "kind", "qq_id", "platform", "days", "status",
            "started_at", "finished_at", "result",
            "progress", "bindings", "account_epoch",
        )
        return [{key: item.get(key) for key in keys} for item in self.tasks.values()]

    async def public_snapshots(self):
        # Compare generations, including already re-registered QQs. A callback
        # can cancel only this process; other workers must consult durable state.
        async with aiosqlite.connect(str(self.sync_engine.db_path)) as db:
            async with db.execute("SELECT qq_id,account_state,account_epoch FROM users") as cursor:
                active = {row[0]: row[2] for row in await cursor.fetchall() if row[1] == "active"}
        snapshots = self.snapshots()
        for item in snapshots:
            qq_id = item.get("qq_id")
            original = self.tasks[item["id"]]
            if qq_id and qq_id != "*" and active.get(qq_id) != original.get("account_epoch", 1):
                item.update(qq_id=None, bindings={}, result=None, status="cancelled")
            elif qq_id == "*" and isinstance(item.get("result"), dict):
                epochs = original.get("_account_epochs", {})
                filtered = {key: value for key, value in item["result"].items()
                            if key != "error" and active.get(key) == epochs.get(key, 1)}
                if "error" in item["result"]:
                    filtered["error"] = "后台同步失败，请重试"
                item["result"] = filtered
        return snapshots

    def revoke_account_tasks(self, qq_id):
        for item in self.tasks.values():
            if item.get("qq_id") == str(qq_id):
                self.cancel(item["id"])
                item.update(bindings={}, result=None, status="cancelled")

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
        if self._daily_problem_sync_task is not None:
            self._daily_problem_sync_task.cancel()
            await asyncio.gather(self._daily_problem_sync_task, return_exceptions=True)
            self._daily_problem_sync_task = None
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
