"""Runtime adapters for the API-owned database and OJ synchronization."""
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import aiosqlite

from .acm_api.problem_listing import ListingConnection

from .acm_api.constants import PLATFORM_SYNC_CONCURRENCY
from .acm_api.database import connect_db, isolated_connection
from .acm_api.binding_service import platform_spec
from .acm_api.problem_sync import ProblemSync, sync_options
from .acm_api.sync_service import SyncMixin
from .acm_api.event_log import emit
from .acm_api.sync_policy import (
    SYNC_LUOGU_ACCESS_RESTRICTED,
    SYNC_PAUSED,
    SyncFailure,
    luogu_retry_delay,
    sync_result_is_non_failure,
)
from .acm_api import problem_schedule


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
        self.db = await aiosqlite.connect(str(self.db_path), factory=ListingConnection)
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

    @staticmethod
    def failure_detail(result):
        return {"code": result.code, "message": result.message,
                "http_status": result.http_status, "cause_http_status": result.cause_http_status,
                "deferred": result.deferred, "consecutive_failures": result.consecutive_failures,
                "attention_required": result.attention_required,
                "next_retry_at": int(time.time()) + result.retry_after if result.retry_after else 0}

    @staticmethod
    def sync_outcome(results, errors, *, many=False):
        def states(values, details):
            for key, value in values.items():
                detail = details.get(key, {})
                if isinstance(value, dict):
                    yield from states(value, detail)
                elif value is None or value < 0 and not sync_result_is_non_failure(value):
                    yield "waiting" if detail.get("deferred") else "failed"
        outcomes = set(states(results, errors))
        return ("partial" if many else "failed") if "failed" in outcomes else "waiting" if outcomes else "completed"

    async def sync_account(self, qq_id, platforms, task, days=0, *, incremental=False):
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        task["errors"] = {}
        try:
            async with isolated_connection(self.db) as connection:
                async with connection.execute("SELECT * FROM users WHERE account_state='active' AND qq_id=?", (str(qq_id),)) as cursor:
                    user = await cursor.fetchone()
            if not user or user["account_epoch"] != task.get("account_epoch", 1):
                task.update(status="cancelled", bindings={}, result=None, errors={})
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
                        result = await self.sync_single_platform_for_days(
                            qq_id, platform, days, incremental=incremental,
                            expected_binding=task["bindings"].get(platform),
                        )
                        if isinstance(result, SyncFailure):
                            task["errors"][platform] = self.failure_detail(result)
                            result = int(result)
                        results[platform] = result
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # A failure on one OJ should not discard results from
                        # the other platforms in this account sync task.
                        results[platform] = -3
            task["result"] = results
            task["status"] = self.sync_outcome(results, task["errors"])
        except asyncio.CancelledError:
            task["status"] = "cancelled"
            raise
        except Exception as exc:
            task["status"] = "failed"
            task["result"] = {"error": str(exc)[:500]}
        finally:
            task["finished_at"] = int(time.time())

    async def sync_all_accounts(self, task, days=0, *, incremental=False):
        """Run the configured platforms for all users as one serialized API task."""
        task["status"] = "running"
        task["started_at"] = int(time.time())
        results = {}
        task["errors"] = {}
        try:
            async with self._sync_cycle_lock:
                members = task.get("_account_snapshots", [])
                task["progress"] = {"done": 0, "total": len(members)}
                platforms = task.get("_platforms") or ("codeforces", "luogu", "nowcoder", "atcoder", "cjlu")
                for user in members:
                    qq_id = user["qq_id"]
                    results[str(qq_id)] = {}
                    for platform in platforms:
                        snapshot = self.binding_snapshot(user, [platform])[platform]
                        if not snapshot["account"].strip():
                            continue
                        try:
                            count = await self.sync_single_platform_for_days(
                                qq_id, platform, days, incremental=incremental,
                                expected_binding=snapshot,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            count = -3
                        if isinstance(count, SyncFailure):
                            task["errors"].setdefault(str(qq_id), {})[platform] = self.failure_detail(count)
                            count = int(count)
                        if count != -2:
                            results[str(qq_id)][platform] = -3 if count is None else count
                    task["progress"]["done"] += 1
            task["result"] = results
            task["status"] = self.sync_outcome(results, task["errors"], many=True)
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
        self.problem_sync = ProblemSync(sync_engine.db_path, getattr(sync_engine, "crawler_config", {}))
        self._daily_problem_sync_task = None
        self._problem_schedule_changed = asyncio.Event()
        self._claiming_daily_problem_sync = False
        self._member_sync_task = None
        self._training_sync_task = None
        self._claiming_all_accounts_sync = False

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
                return type(value) is int and value < 0 and not sync_result_is_non_failure(value) and value != -2

            if status == "waiting":
                level, message = "info", "同步正在等待重试，已有记录和训练进度保留"
            elif status == "failed":
                level, message = "error", "后台任务执行失败，请在任务队列查看结果"
            elif status in {"cancelled", "interrupted"}:
                level, message = "warning", "后台任务已取消或中断"
            elif status == "completed" and not failed(item.get("result")):
                level, message = "info", "后台任务已结束，请在任务队列查看各平台结果"
            else:
                level, message = "warning", "后台任务已结束，部分操作未完成，请查看任务结果"
            emit("task.finished", message, level, **fields)

    def _active_problem_sync(self):
        return next((item for item in self.tasks.values()
                     if item.get("kind") == "题目采集" and item["status"] in {"queued", "running"}), None)

    def submit_problem_sync(self, options):
        if self._claiming_daily_problem_sync or self._claiming_all_accounts_sync:
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

    def wake_problem_schedule(self):
        self._problem_schedule_changed.set()

    async def _claim_daily_problem_sync(self, platform, day):
        async with aiosqlite.connect(str(self.sync_engine.db_path), factory=ListingConnection) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            return await problem_schedule.claim(db, platform, day, getattr(self.sync_engine, "crawler_config", {}))

    async def _run_daily_problem_sync(self):
        day = datetime.now(PROBLEM_SYNC_TIMEZONE).date()
        platforms = problem_schedule.PLATFORMS
        for platform in platforms:
            if datetime.now(PROBLEM_SYNC_TIMEZONE).date() != day:
                break
            if self._claiming_daily_problem_sync or self._claiming_all_accounts_sync or self._active_problem_sync() is not None:
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
            request_options = {"platform": platform, "scope": "platform"}
            if platform == "luogu":
                request_options["limit"] = getattr(self.sync_engine, "crawler_config", {}).get("luogu_daily_statement_limit", 100)
            options = sync_options(request_options)
            options["scheduled"] = True
            task_id = self.submit_problem_sync(options)["id"]
            try:
                await asyncio.gather(self.tasks[task_id]["_task"], return_exceptions=True)
            finally:
                # Shutdown cancels the child before gather finishes; persist its
                # final status as well so a restart does not hide the interruption.
                try:
                    async with aiosqlite.connect(str(self.sync_engine.db_path), factory=ListingConnection) as db:
                        await problem_schedule.remember_result(db, self.tasks[task_id])
                except (OSError, aiosqlite.Error):
                    emit("problem_sync.result_save_failed", "每日题库更新结果暂未保存", "warning")
        return True

    async def _daily_problem_sync_loop(self):
        while True:
            now = datetime.now(PROBLEM_SYNC_TIMEZONE)
            due = now.replace(hour=PROBLEM_SYNC_HOUR, minute=0, second=0, microsecond=0)
            if now < due:
                try:
                    await asyncio.wait_for(self._problem_schedule_changed.wait(), timeout=(due - now).total_seconds())
                except asyncio.TimeoutError:
                    pass
                self._problem_schedule_changed.clear()
                continue
            try:
                complete = await self._run_daily_problem_sync()
            except (OSError, aiosqlite.Error):
                emit("problem_sync.schedule_failed", "每日题库更新暂无法安排，稍后重试", "warning")
                complete = False
            delay = PROBLEM_SYNC_RETRY_SECONDS
            if complete:
                delay = (due + timedelta(days=1) - datetime.now(PROBLEM_SYNC_TIMEZONE)).total_seconds()
            try:
                await asyncio.wait_for(self._problem_schedule_changed.wait(), timeout=max(0, delay))
            except asyncio.TimeoutError:
                pass
            self._problem_schedule_changed.clear()

    async def submit_account_sync(self, qq_id, platforms, days=0, *, expected_epoch=None):
        if self._claiming_all_accounts_sync:
            return None
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

        async with aiosqlite.connect(str(self.sync_engine.db_path), factory=ListingConnection) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE qq_id=? AND account_state='active'", (str(qq_id),)) as cursor:
                user = await cursor.fetchone()
        if not user or expected_epoch is not None and user["account_epoch"] != expected_epoch:
            return None
        if self._claiming_all_accounts_sync:
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

    async def submit_all_accounts_sync(self, days=0, *, incremental=False, scheduled=False, interval_seconds=3600, platforms=None):
        if self._claiming_all_accounts_sync or self._claiming_daily_problem_sync or any(
            item.get("status") in {"queued", "running"}
            for item in self.tasks.values()
        ):
            return None
        allowed = ("codeforces", "luogu", "nowcoder", "atcoder", "cjlu")
        if platforms is None:
            normalized_platforms = list(allowed)
        else:
            if isinstance(platforms, str):
                platforms = platforms.replace("，", ",").split(",")
            normalized_platforms = []
            for platform in platforms or ():
                value = "codeforces" if str(platform).strip().lower() in {"cf", "codeforces"} else str(platform).strip().lower()
                if value in allowed and value not in normalized_platforms:
                    normalized_platforms.append(value)
        if not normalized_platforms:
            return None
        try:
            days = max(0, min(3650, int(days)))
        except (TypeError, ValueError):
            days = 0
        self._claiming_all_accounts_sync = True
        try:
            async with aiosqlite.connect(str(self.sync_engine.db_path), factory=ListingConnection) as db:
                db.row_factory = aiosqlite.Row
                if scheduled:
                    now = int(time.time())
                    await db.execute("BEGIN IMMEDIATE")
                    async with db.execute(
                        "INSERT INTO settings(key,value) VALUES('member_sync_last_started_at',?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value "
                        "WHERE CAST(settings.value AS INTEGER)<=?",
                        (str(now), now - interval_seconds),
                    ) as cursor:
                        if cursor.rowcount != 1:
                            return None
                query = "SELECT * FROM users WHERE account_state='active'"
                if scheduled:
                    query += (
                        " AND (TRIM(COALESCE(cf_handle,''))<>'' OR TRIM(COALESCE(luogu_id,''))<>''"
                        " OR TRIM(COALESCE(nowcoder_id,''))<>'' OR TRIM(COALESCE(atcoder_handle,''))<>''"
                        " OR TRIM(COALESCE(cjlu_username,''))<>'')"
                    )
                async with db.execute(query + " ORDER BY qq_id") as cursor:
                    members = [dict(row) for row in await cursor.fetchall()]
                await db.commit()
        finally:
            self._claiming_all_accounts_sync = False
        if scheduled:
            for task_id, item in list(self.tasks.items()):
                if item.get("scheduled") and item["_task"].done():
                    del self.tasks[task_id]
        task_id = uuid.uuid4().hex[:12]
        item = {
            "id": task_id,
            "kind": "全员定时同步" if scheduled else "全员平台同步",
            "qq_id": "*",
            "_account_snapshots": members,
            "_account_epochs": {user["qq_id"]: user["account_epoch"] for user in members},
            "platform": ",".join(normalized_platforms),
            "_platforms": normalized_platforms,
            "days": days,
            "scheduled": scheduled,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }
        self.tasks[task_id] = item
        options = {"days": days}
        if incremental:
            options["incremental"] = True
        item["_task"] = asyncio.create_task(
            self._logged_task(self.sync_engine.sync_all_accounts, item, item, **options)
        )
        return {"id": task_id}

    def start_member_sync(self, interval_seconds=3600):
        if self._member_sync_task is None:
            self._member_sync_task = asyncio.create_task(
                self._member_sync_loop(interval_seconds), name="periodic-member-sync",
            )

    async def _member_sync_loop(self, interval_seconds):
        while True:
            try:
                submitted = await self.submit_all_accounts_sync(
                    incremental=True, scheduled=True, interval_seconds=interval_seconds,
                )
                if submitted:
                    await asyncio.gather(self.tasks[submitted["id"]]["_task"], return_exceptions=True)
            except (OSError, aiosqlite.Error):
                emit("member_sync.schedule_failed", "全员过题记录暂无法安排同步，稍后重试", "warning")
            await asyncio.sleep(60)

    def start_training_task_sync(self):
        if self._training_sync_task is None:
            self._training_sync_task = asyncio.create_task(
                self._training_task_sync_loop(), name="training-task-snapshots")

    async def schedule_training_snapshots(self, *, now=None):
        """Prioritize assigned Luogu snapshots through the existing account queue."""
        now = int(time.time()) if now is None else now
        if any(t.get("qq_id") == "*" and t.get("status") in {"queued", "running"} for t in self.tasks.values()):
            return 0
        from .acm_api.luogu_client import cooldown_error, load_request_state, recovery_pending
        async with isolated_connection(self.sync_engine.db) as db:
            await load_request_state(db)
            if cooldown_error():
                return 0
            recovery = recovery_pending()
            dispatch_limit = 1 if recovery else 20
            candidates = await db.execute("""
                SELECT r.qq_id,r.account_epoch,u.luogu_id,u.luogu_binding_version,
                  GROUP_CONCAT(DISTINCT r.id) AS recipient_ids,
                  s.last_status AS sync_status,COALESCE(s.last_attempt_at,0) AS last_attempt_at,
                  COALESCE(s.consecutive_failures,0) AS consecutive_failures,
                  MIN(COALESCE(json_extract(x.snapshot_json,'$.last_checked_at'),0)) AS priority,
                  MAX(COALESCE(json_extract(x.snapshot_json,'$.last_checked_at'),0) <= ? - 900
                      OR COALESCE(json_extract(x.snapshot_json,'$.last_checked_at'),0)=0) AS needed
                FROM training_task_recipients r JOIN training_tasks t ON t.id=r.task_id
                JOIN training_task_problems p ON p.task_id=t.id AND p.platform='luogu'
                JOIN training_task_progress x ON x.recipient_id=r.id AND x.problem_id=p.id
                JOIN users u ON u.qq_id=r.qq_id AND u.account_state='active' AND u.account_epoch=r.account_epoch
                JOIN web_accounts a ON a.qq_id=u.qq_id AND a.is_active=1
                LEFT JOIN user_platform_sync_state s ON s.user_qq_id=u.qq_id AND s.platform='luogu'
                LEFT JOIN binding_rate_limits b ON b.qq_id=u.qq_id AND b.platform='luogu' AND b.action='training_task_auto'
                WHERE t.state='published' AND r.closed=0
                  AND u.luogu_id IS NOT NULL AND TRIM(u.luogu_id)<>''
                  AND COALESCE(s.sync_enabled,1)=1
                  AND COALESCE(s.next_retry_at,0)<=? AND COALESCE(s.last_status,'')<>'paused'
                  AND COALESCE(b.last_at,0)<=?-60
                  AND x.on_time_json IS NULL AND x.late_json IS NULL AND x.uncertain_json IS NULL AND x.history_json IS NULL
                  AND (COALESCE(x.binding_key,CASE WHEN COALESCE(json_extract(r.bindings_json,'$.luogu.account'),'')<>''
                       THEN json_extract(r.bindings_json,'$.luogu.account')||':'||json_extract(r.bindings_json,'$.luogu.version') END)
                       =u.luogu_id||':'||u.luogu_binding_version
                    OR (x.binding_key IS NULL AND COALESCE(json_extract(r.bindings_json,'$.luogu.account'),'')=''
                        AND u.luogu_binding_version=COALESCE(json_extract(r.bindings_json,'$.luogu.version'),0)+1))
                GROUP BY r.qq_id,r.account_epoch HAVING needed=1 OR ?=1 ORDER BY priority,COALESCE(b.last_at,0),r.qq_id
                """, (now, now, now, int(recovery)))
            candidates = [dict(r) for r in await candidates.fetchall()]
        submitted = 0
        for candidate in candidates:
            # Limit dispatched work, so busy/cooling accounts cannot consume the batch.
            if submitted >= dispatch_limit:
                break
            if candidate["consecutive_failures"]:
                retry_delay = luogu_retry_delay(candidate["consecutive_failures"])
                if candidate["last_attempt_at"] + retry_delay > now:
                    continue
            qq = candidate["qq_id"]
            if any(t.get("qq_id") == qq and t.get("status") in {"queued", "running"} for t in self.tasks.values()):
                continue
            lock = self.sync_engine._sync_user_locks.get(qq)
            if lock is not None and lock.locked():
                continue
            async with isolated_connection(self.sync_engine.db) as db:
                claim = await db.execute("""INSERT INTO binding_rate_limits(qq_id,platform,action,window_start,attempts,last_at)
                    SELECT qq_id,'luogu','training_task_auto',?,1,? FROM users
                    WHERE qq_id=? AND account_state='active' AND account_epoch=? AND luogu_id=? AND luogu_binding_version=?
                    ON CONFLICT(qq_id,platform,action) DO UPDATE SET last_at=excluded.last_at,attempts=binding_rate_limits.attempts+1
                    WHERE binding_rate_limits.last_at<=?""",
                    (now, now, qq, candidate["account_epoch"], candidate["luogu_id"], candidate["luogu_binding_version"], now-60))
                await db.commit()
                claimed = claim.rowcount > 0
            if claimed:
                task = await self.submit_account_sync(qq, ["luogu"], expected_epoch=candidate["account_epoch"])
                submitted += bool(task)
                if task:
                    # 页面跟随最新的自动重试；限定本次候选、账号代际及绑定版本，避免旧任务串号。
                    recipient_ids = [int(value) for value in candidate["recipient_ids"].split(",")]
                    async with isolated_connection(self.sync_engine.db) as db:
                        for offset in range(0, len(recipient_ids), 400):
                            batch = recipient_ids[offset:offset + 400]
                            placeholders = ",".join("?" for _ in batch)
                            await db.execute("""UPDATE training_task_recipients SET refresh_task_id=?,refresh_at=?
                                WHERE id IN (""" + placeholders + """) AND qq_id=? AND account_epoch=? AND closed=0
                                  AND task_id IN (SELECT id FROM training_tasks WHERE state='published')
                                  AND EXISTS (SELECT 1 FROM users WHERE qq_id=? AND account_state='active'
                                      AND account_epoch=? AND luogu_id=? AND luogu_binding_version=?)""",
                                [task["id"], now, *batch, qq, candidate["account_epoch"], qq,
                                 candidate["account_epoch"], candidate["luogu_id"], candidate["luogu_binding_version"]])
                        await db.commit()
        return submitted

    async def _training_task_sync_loop(self):
        while True:
            try:
                await self.schedule_training_snapshots()
            except (OSError, aiosqlite.Error):
                emit("training_sync.schedule_failed", "训练任务快照暂无法安排，稍后重试", "warning")
            await asyncio.sleep(30)

    def snapshots(self):
        keys = (
            "id", "kind", "qq_id", "platform", "days", "status",
            "started_at", "finished_at", "result",
            "progress", "bindings", "account_epoch", "errors",
        )
        return [{key: item.get(key) for key in keys} for item in self.tasks.values()]

    async def public_snapshots(self):
        # Compare generations, including already re-registered QQs. A callback
        # can cancel only this process; other workers must consult durable state.
        # The member identity is included so the admin task page can filter
        # all-account results without exposing private task internals.
        async with aiosqlite.connect(str(self.sync_engine.db_path), factory=ListingConnection) as db:
            async with db.execute("SELECT qq_id,account_state,account_epoch,name,status FROM users") as cursor:
                active = {
                    row[0]: {"epoch": row[2], "name": row[3], "status": row[4] or ""}
                    for row in await cursor.fetchall()
                    if row[1] == "active"
                }
        snapshots = self.snapshots()
        for item in snapshots:
            qq_id = item.get("qq_id")
            original = self.tasks[item["id"]]
            if qq_id and qq_id != "*":
                member = active.get(qq_id)
                if not member or member["epoch"] != original.get("account_epoch", 1):
                    item.update(qq_id=None, bindings={}, result=None, errors={}, status="cancelled")
                else:
                    item["member"] = {"qq_id": qq_id, "name": member["name"], "status": member["status"]}
            elif qq_id == "*":
                epochs = original.get("_account_epochs", {})
                members = []
                for target_qq, target_epoch in epochs.items():
                    member = active.get(target_qq)
                    if member and member["epoch"] == target_epoch:
                        members.append({
                            "qq_id": target_qq,
                            "name": member["name"],
                            "status": member["status"],
                        })
                item["members"] = members
                item["member_statuses"] = {member["qq_id"]: member["status"] for member in members}
                visible = {member["qq_id"] for member in members}
                if isinstance(item.get("result"), dict):
                    filtered = {
                        key: value
                        for key, value in item["result"].items()
                        if key == "error" or key in visible
                    }
                    if "error" in item["result"]:
                        filtered["error"] = "后台同步失败，请重试"
                    item["result"] = filtered
                item["errors"] = {
                    key: value
                    for key, value in (item.get("errors") or {}).items()
                    if key == "error" or key in visible
                }
        return snapshots

    def revoke_account_tasks(self, qq_id):
        for item in self.tasks.values():
            if item.get("qq_id") == str(qq_id):
                self.cancel(item["id"])
                item.update(bindings={}, result=None, errors={}, status="cancelled")

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
        if self._training_sync_task is not None:
            self._training_sync_task.cancel()
            await asyncio.gather(self._training_sync_task, return_exceptions=True)
            self._training_sync_task = None
        if self._member_sync_task is not None:
            self._member_sync_task.cancel()
            await asyncio.gather(self._member_sync_task, return_exceptions=True)
            self._member_sync_task = None
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

    db = await aiosqlite.connect(str(db_path), factory=ListingConnection)
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
