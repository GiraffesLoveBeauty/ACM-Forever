"""Persisted CF practice jobs; interrupted work is visible after service restart."""
import asyncio
import json
import time
import uuid
from pathlib import Path

import aiosqlite

from .cf_client import CFUnavailable, binding_key, cf_request
from .cf_practice import PracticeError, iso, metadata, normalize_problem, resolve_scope


async def open_db(path):
    db = await aiosqlite.connect(str(path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


class PracticeJobs:
    def __init__(self, db_path, sync_engine, query):
        self.db_path, self.engine, self.query = Path(db_path), sync_engine, query
        self.tasks = set()
        self._metadata_lock = asyncio.Lock()

    async def start(self):
        db = await open_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("UPDATE cf_practice_jobs SET status='interrupted',finished_at=?,error_code='service_restart',error_message='服务重启，未完成任务可重新发起' WHERE status IN ('queued','running')", (now,))
            await db.execute("UPDATE cf_practice_job_members SET status='interrupted',finished_at=?,error_code='service_restart',error_message='服务重启' WHERE status IN ('queued','running')", (now,))
            await db.execute("UPDATE user_platform_sync_state SET last_status='interrupted',last_error_code='service_restart',last_error_message='服务重启，请刷新历史' WHERE platform='codeforces' AND last_status='running'")
            await db.commit()
        finally:
            await db.close()

    async def close(self):
        active = list(self.tasks)
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    async def submit(self, kind, payload):
        db = await open_db(self.db_path)
        try:
            await db.execute("BEGIN IMMEDIATE")
            scope, members = await resolve_scope(db, payload, self.query.data_ttl)
            if not members:
                raise PracticeError("参与范围为空，无法创建任务", "empty_scope")
            payload = dict(payload, expected_scope_fingerprint=scope["fingerprint"])
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            async with db.execute("SELECT id FROM cf_practice_jobs WHERE kind=? AND payload=? AND status IN ('queued','running') LIMIT 1", (kind, serialized)) as cursor:
                existing = await cursor.fetchone()
            if existing:
                return existing["id"]
            async with db.execute("SELECT COUNT(*) FROM cf_practice_jobs WHERE status IN ('queued','running')") as cursor:
                if (await cursor.fetchone())[0] >= 8:
                    raise PracticeError("已有多个任务在排队，请稍后重试", "queue_full", 429)
            job_id = uuid.uuid4().hex
            await db.execute("INSERT INTO cf_practice_jobs(id,kind,status,payload,scope_fingerprint,created_at) VALUES(?,?,'queued',?,?,?)", (job_id, kind, serialized, scope["fingerprint"], int(time.time())))
            if kind == "sync":
                await db.executemany("INSERT INTO cf_practice_job_members(job_id,qq_id,handle,binding_key,status) VALUES(?,?,?,?,'queued')", [(job_id, member["qq_id"], member["cf_handle"], binding_key(member)) for member in members])
            await db.commit()
        finally:
            await db.close()
        task = asyncio.create_task(self._run(job_id, kind, payload), name="cf-practice-" + job_id)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job_id

    async def _update(self, job_id, status, *, result=None, error_code=None, error_message=None):
        db = await open_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("UPDATE cf_practice_jobs SET status=?,started_at=COALESCE(started_at,?),finished_at=?,result=?,error_code=?,error_message=? WHERE id=?", (status, now, None if status == "running" else now, json.dumps(result, ensure_ascii=False) if result is not None else None, error_code, error_message, job_id))
            await db.commit()
        finally:
            await db.close()

    async def _member_update(self, job_id, qq_id, status, code=None, message=None):
        db = await open_db(self.db_path)
        try:
            await db.execute("UPDATE cf_practice_job_members SET status=?,error_code=?,error_message=?,finished_at=? WHERE job_id=? AND qq_id=?", (status, code, message, None if status == "running" else int(time.time()), job_id, qq_id))
            await db.commit()
        finally:
            await db.close()

    async def _finish_members(self, job_id, status, code, message):
        db = await open_db(self.db_path)
        try:
            await db.execute("UPDATE cf_practice_job_members SET status=?,error_code=?,error_message=?,finished_at=? WHERE job_id=? AND status IN ('queued','running')", (status, code, message, int(time.time()), job_id))
            await db.commit()
        finally:
            await db.close()

    async def _snapshot(self, payload, operation):
        db = await open_db(self.db_path)
        try:
            await db.execute("BEGIN")
            return await operation(db, payload)
        finally:
            await db.rollback()
            await db.close()

    async def _run(self, job_id, kind, payload):
        try:
            await self._update(job_id, "running")
            if kind == "sync":
                await self._run_sync(job_id, payload)
            else:
                _, pending = await self._snapshot(payload, self.query.check)
                warnings = await self.refresh_metadata(pending) if pending else []
                result, _ = await self._snapshot(payload, self.query.check)
                if warnings:
                    result["metadata_warnings"] = warnings
                await self._update(job_id, "partial" if warnings else "completed", result=result)
        except asyncio.CancelledError:
            await self._update(job_id, "interrupted", error_code="interrupted", error_message="任务已中断，可重新发起")
            await self._finish_members(job_id, "interrupted", "interrupted", "任务已中断")
            raise
        except PracticeError as exc:
            await self._update(job_id, "failed", error_code=exc.code, error_message=str(exc))
            await self._finish_members(job_id, "failed", exc.code, str(exc))
        except Exception:
            await self._update(job_id, "failed", error_code="internal_error", error_message="后台任务失败，请重试")
            await self._finish_members(job_id, "failed", "internal_error", "后台任务失败，请重试")

    async def _run_sync(self, job_id, payload):
        async def scope_operation(db, data):
            return await resolve_scope(db, data, self.query.data_ttl)
        scope, members = await self._snapshot(payload, scope_operation)
        successes = 0
        for member in members:
            qq_id = member["qq_id"]
            if not (member["cf_handle"] or "").strip():
                await self._member_update(job_id, qq_id, "failed", "unbound", "未绑定 CF，请先处理账号绑定")
                continue
            await self._member_update(job_id, qq_id, "running")
            db = await open_db(self.db_path)
            try:
                async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
                    current = await cursor.fetchone()
            finally:
                await db.close()
            if not current or binding_key(current) != binding_key(member):
                await self._member_update(job_id, qq_id, "failed", "binding_changed", "CF 绑定已变化，请重新选择范围")
                continue
            task = {}
            await self.engine.sync_account(qq_id, ["codeforces"], task, days=0, incremental=True)
            if task.get("status") == "completed":
                successes += 1
                await self._member_update(job_id, qq_id, "completed")
            else:
                await self._member_update(job_id, qq_id, "failed", "sync_failed", "CF 历史同步未完成，数据不能判为可用")
        warnings = await self.refresh_metadata({"catalog": True, "contests": []})
        status = "completed" if successes == len(members) and not warnings else "partial" if successes else "failed"
        await self._update(job_id, status, result={"scope_fingerprint": scope["fingerprint"], "member_count": len(members), "success_count": successes, "failed_count": len(members) - successes, "metadata_warnings": warnings})

    async def refresh_metadata(self, pending):
        warnings = []
        async with self._metadata_lock:
            # The pending snapshot may predate another job's cache writes.
            requested = pending.get("problems", [])
            db = await open_db(self.db_path)
            try:
                async with db.execute("SELECT value FROM settings WHERE key='cf_problem_catalog_verified_at'") as cursor:
                    refreshed = await cursor.fetchone()
            finally:
                await db.close()
            refreshed_at = int(refreshed["value"]) if refreshed else 0
            catalog_fresh = 0 < refreshed_at <= int(time.time()) and int(time.time()) - refreshed_at <= self.query.problem_ttl
            if pending.get("catalog") and not catalog_fresh and not (requested and await self._problems_ready(requested)):
                try:
                    catalog = await cf_request(self.engine._http_session, "problemset.problems", config=self.engine._crawler_config())
                    if not isinstance(catalog, dict) or not isinstance(catalog.get("problems"), list) or not catalog["problems"]:
                        raise CFUnavailable("CF 题库格式异常")
                    await self._cache_problems(catalog["problems"], catalog=True)
                except CFUnavailable as exc:
                    warnings.append(str(exc))
            for contest_id in pending.get("contests", []):
                required = [pid for pid in requested if normalize_problem(pid)["contest_id"] == contest_id]
                if required and not pending.get("require_contest_list") and await self._problems_ready(required):
                    continue
                db = await open_db(self.db_path)
                try:
                    async with db.execute("SELECT verified_at FROM cf_contest_cache WHERE contest_id=?", (contest_id,)) as cursor:
                        existing = await cursor.fetchone()
                finally:
                    await db.close()
                if existing and int(time.time()) - existing["verified_at"] <= self.query.problem_ttl:
                    continue
                # A successful authoritative contest list can prove an index absent.
                # CF FAILED/404/429 responses only leave the input unknown.
                try:
                    contest = await cf_request(self.engine._http_session, "contest.standings", {"contestId": contest_id, "from": 1, "count": 1, "showUnofficial": "true"}, self.engine._crawler_config())
                    if not isinstance(contest, dict) or not isinstance(contest.get("contest"), dict) or not isinstance(contest.get("problems"), list) or not contest["problems"]:
                        raise CFUnavailable("CF 比赛题目列表格式异常")
                    if any(not isinstance(p, dict) or p.get("contestId") != contest_id for p in contest["problems"]):
                        raise CFUnavailable("CF 比赛题目列表格式异常")
                    complete = contest["contest"].get("phase") == "FINISHED"
                    await self._cache_problems(contest["problems"], contest_id if complete else None)
                    if not complete:
                        warnings.append(f"比赛 {contest_id} 尚未结束，无法核实完整题目列表")
                except (CFUnavailable, ValueError, TypeError) as exc:
                    warnings.append(str(exc))
        return warnings

    async def _problems_ready(self, ids):
        db = await open_db(self.db_path)
        try:
            cached = await metadata(db, ids)
            now = int(time.time())
            return all(pid in cached and 0 <= now - cached[pid]["verified_at"] <= self.query.problem_ttl for pid in ids)
        finally:
            await db.close()

    async def _cache_problems(self, problems, contest_id=None, *, catalog=False):
        now = int(time.time())
        values = []
        for problem in problems:
            if not isinstance(problem, dict):
                raise CFUnavailable("CF 题目资料格式异常")
            # Non-contest catalog entries cannot be addressed by a contest ID.
            if "contestId" not in problem:
                continue
            try:
                item = normalize_problem(f"{problem['contestId']}{problem['index']}")
            except (PracticeError, KeyError):
                raise CFUnavailable("CF 题目资料格式异常") from None
            tags = problem.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise CFUnavailable("CF 题目标签格式异常")
            rating = problem.get("rating")
            values.append((item["contest_id"], item["index"], str(problem.get("name") or "未命名题目"), rating if type(rating) is int and rating > 0 else None, json.dumps(tags), now))
        db = await open_db(self.db_path)
        try:
            await db.executemany("INSERT INTO cf_problem_cache(contest_id,problem_index,name,rating,tags,verified_at) VALUES(?,?,?,?,?,?) ON CONFLICT(contest_id,problem_index) DO UPDATE SET name=excluded.name,rating=excluded.rating,tags=excluded.tags,verified_at=excluded.verified_at", values)
            if contest_id:
                await db.execute("INSERT INTO cf_contest_cache(contest_id,problems,verified_at) VALUES(?,?,?) ON CONFLICT(contest_id) DO UPDATE SET problems=excluded.problems,verified_at=excluded.verified_at", (contest_id, json.dumps([value[1] for value in values]), now))
            if catalog:
                await db.execute("INSERT INTO settings(key,value) VALUES('cf_problem_catalog_verified_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(now),))
            await db.commit()
        finally:
            await db.close()

    async def get(self, job_id):
        db = await open_db(self.db_path)
        try:
            await db.execute("BEGIN")
            async with db.execute("SELECT * FROM cf_practice_jobs WHERE id=?", (job_id,)) as cursor:
                item = await cursor.fetchone()
            if not item:
                raise PracticeError("任务不存在", "job_not_found", 404)
            item = dict(item)
            payload = json.loads(item["payload"])
            await resolve_scope(db, payload, self.query.data_ttl)
            result = json.loads(item["result"]) if item["result"] else None
            if item["kind"] == "check" and item["status"] in {"completed", "partial"}:
                # Revalidate both scope and evidence at collection time, not only at job creation.
                result, _ = await self.query.check(db, payload)
                if item["result"]:
                    warnings = json.loads(item["result"]).get("metadata_warnings")
                    if warnings:
                        result["metadata_warnings"] = warnings
            async with db.execute("SELECT qq_id,handle,status,error_code,error_message,finished_at FROM cf_practice_job_members WHERE job_id=? ORDER BY qq_id", (job_id,)) as cursor:
                members = [dict(row) for row in await cursor.fetchall()]
            for member in members:
                member["finished_at"] = iso(member["finished_at"])
            return {"job_id": item["id"], "kind": item["kind"], "status": item["status"], "scope_fingerprint": item["scope_fingerprint"], "created_at": iso(item["created_at"]), "started_at": iso(item["started_at"]), "finished_at": iso(item["finished_at"]), "members": members, "completed_member_count": sum(row["status"] == "completed" for row in members), "failed_member_count": sum(row["status"] in {"failed", "interrupted"} for row in members), "result": result, "error_code": item["error_code"], "message": item["error_message"]}
        finally:
            await db.rollback()
            await db.close()
