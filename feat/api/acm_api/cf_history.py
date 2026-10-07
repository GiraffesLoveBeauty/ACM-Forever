"""Paginated CF evidence storage with atomic binding-generation checks."""
import asyncio
import json
import time

from .cf_client import CFUnavailable, binding_key, cf_request, problem_url
from .cf_practice import PracticeError, normalize_problem
from .database import isolated_connection


async def fetch_history(session, user, start_timestamp, db, config):
    # Other users and Bot routes commit the engine connection independently.
    # Keep binding checks and page writes on a connection this sync alone owns.
    async with isolated_connection(db) as history_db:
        return await _fetch_history(session, user, start_timestamp, history_db, config)


async def _fetch_history(session, user, start_timestamp, db, config):
    from .crawler import _store_cf_attempts

    qq_id, handle = str(user["qq_id"]), user["cf_handle"]
    expected_binding = binding_key(user)
    coverage_at = int(time.time())
    async with db.execute(
        "SELECT binding_key,full_history_at FROM user_platform_sync_state "
        "WHERE user_qq_id=? AND platform='codeforces'", (qq_id,),
    ) as cursor:
        state = await cursor.fetchone()
    full = not start_timestamp or not state or state["binding_key"] != expected_binding or not state["full_history_at"]
    start_timestamp = 0 if full else max(0, int(start_timestamp) - 7 * 86400)
    if not full:
        async with db.execute(
            "SELECT MIN(submitted_at) FROM submission_attempts WHERE owner_qq_id=? "
            "AND platform='codeforces' AND verdict IN ('TESTING','UNKNOWN','RUNNING')", (qq_id,),
        ) as cursor:
            pending = (await cursor.fetchone())[0]
        if pending:
            start_timestamp = min(start_timestamp, pending)
    offset, added = 1, 0
    try:
        while True:
            page = await cf_request(session, "user.status", {"handle": handle, "from": offset, "count": 100}, config)
            if not isinstance(page, list):
                raise CFUnavailable("CF 提交分页格式异常")
            for submission in page:
                if not isinstance(submission, dict) or not isinstance(submission.get("problem"), dict):
                    raise CFUnavailable("CF 提交记录格式异常")
                if type(submission.get("id")) is not int or type(submission.get("creationTimeSeconds")) is not int or submission["creationTimeSeconds"] <= 0:
                    raise CFUnavailable("CF 提交时间或标识异常")
                problem = submission["problem"]
                try:
                    normalize_problem(f"{problem['contestId']}{problem['index']}")
                except (PracticeError, KeyError):
                    raise CFUnavailable("CF 提交题号格式异常") from None
                if not isinstance(problem.get("tags", []), list) or any(not isinstance(tag, str) for tag in problem.get("tags", [])):
                    raise CFUnavailable("CF 提交标签格式异常")
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
                    current = await cursor.fetchone()
                if not current or binding_key(current) != expected_binding:
                    raise CFUnavailable("同步期间 CF 绑定已变化，请重新同步")
                await _store_cf_attempts(db, qq_id, page, commit=False)
                for submission in page:
                    problem = submission.get("problem", {})
                    contest_id, index = problem.get("contestId"), problem.get("index")
                    submitted_at = int(submission.get("creationTimeSeconds") or 0)
                    if not contest_id or not index or not submitted_at:
                        continue
                    pid = f"cf_{contest_id}{index}"
                    canonical = normalize_problem(pid)["display_id"]
                    aliases = ("cf_" + canonical, canonical)
                    rating = problem.get("rating")
                    rating = rating if isinstance(rating, int) and rating > 0 else None
                    tags = problem.get("tags", [])
                    await db.execute(
                        "INSERT INTO cf_problem_cache(contest_id,problem_index,name,rating,tags,verified_at) "
                        "VALUES(?,?,?,?,?,?) ON CONFLICT(contest_id,problem_index) DO UPDATE SET "
                        "name=excluded.name,rating=excluded.rating,tags=excluded.tags,verified_at=excluded.verified_at",
                        (int(contest_id), str(index).upper(), problem.get("name", pid), rating, json.dumps(tags), coverage_at),
                    )
                    if submission.get("verdict") == "OK":
                        async with db.execute(
                            "SELECT problem_id,submit_time FROM submissions WHERE user_qq_id=? "
                            "AND platform='codeforces' AND problem_id IN (?,?) ORDER BY (problem_id=?) DESC",
                            (qq_id, *aliases, canonical),
                        ) as cursor:
                            existing = await cursor.fetchall()
                            if not existing:
                                added += 1
                        # Maintenance repair removes cf_. Reuse that key instead of creating a duplicate.
                        ac_pid = existing[0]["problem_id"] if existing else aliases[0]
                        ac_at = max([submitted_at] + [row["submit_time"] for row in existing])
                        await db.execute(
                            "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time) "
                            "VALUES(?,'codeforces',?,?,?,?,?,?) ON CONFLICT(user_qq_id,platform,problem_id) DO UPDATE SET "
                            "submit_time=MAX(submissions.submit_time,excluded.submit_time),problem_name=excluded.problem_name,"
                            "problem_rating=excluded.problem_rating,problem_url=excluded.problem_url,tags=excluded.tags",
                            (qq_id, ac_pid, problem.get("name", pid), str(rating) if rating else None,
                             problem_url(contest_id, index), ",".join(tags), ac_at),
                        )
                        await db.execute(
                            "DELETE FROM submissions WHERE user_qq_id=? AND platform='codeforces' "
                            "AND problem_id IN (?,?) AND problem_id<>?", (qq_id, *aliases, ac_pid),
                        )
                    else:
                        # A known AC rejudged to a non-AC must not remain a stale AC.
                        await db.execute(
                            "UPDATE submissions SET submit_time=(SELECT MAX(submitted_at) FROM submission_attempts "
                            "WHERE owner_qq_id=? AND platform='codeforces' AND problem_id IN (?,?) AND verdict='OK') "
                            "WHERE user_qq_id=? AND platform='codeforces' AND problem_id IN (?,?) AND submit_time=? "
                            "AND EXISTS (SELECT 1 FROM submission_attempts WHERE owner_qq_id=? "
                            "AND platform='codeforces' AND problem_id IN (?,?) AND verdict='OK')",
                            (qq_id, *aliases, qq_id, *aliases, submitted_at, qq_id, *aliases),
                        )
                        await db.execute(
                            "DELETE FROM submissions WHERE user_qq_id=? AND platform='codeforces' AND problem_id IN (?,?) "
                            "AND submit_time=? AND NOT EXISTS (SELECT 1 FROM submission_attempts WHERE owner_qq_id=? "
                            "AND platform='codeforces' AND problem_id IN (?,?) AND verdict='OK')",
                            (qq_id, *aliases, submitted_at, qq_id, *aliases),
                        )
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
            if len(page) < 100 or (start_timestamp and page and min(int(item.get("creationTimeSeconds") or 0) for item in page) < start_timestamp):
                break
            offset += 100
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute("SELECT * FROM users WHERE qq_id=?", (qq_id,)) as cursor:
            current = await cursor.fetchone()
        if not current or binding_key(current) != expected_binding:
            raise CFUnavailable("同步期间 CF 绑定已变化，请重新同步")
        await db.execute(
            "INSERT INTO user_platform_sync_state(user_qq_id,platform,binding_key,full_history_at,coverage_through_at) "
            "VALUES(?,'codeforces',?,?,?) ON CONFLICT(user_qq_id,platform) DO UPDATE SET "
            "binding_key=excluded.binding_key,full_history_at=CASE WHEN ? THEN excluded.full_history_at "
            "ELSE user_platform_sync_state.full_history_at END,coverage_through_at=excluded.coverage_through_at",
            (qq_id, expected_binding, int(time.time()) if full else 0, coverage_at, full),
        )
        await db.commit()
        return added
    except asyncio.CancelledError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        return -1
