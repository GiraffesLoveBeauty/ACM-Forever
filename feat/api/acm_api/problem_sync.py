"""Administrator-triggered collection of public AtCoder and Codeforces problems."""

import asyncio
import hashlib
import re
import time

import aiohttp
import aiosqlite

from .problem_bank import record_problem_failure, save_problem
from .problem_content import parse_atcoder, parse_atcoder_tasks, parse_codeforces
from .cf_client import CFUnavailable, cf_page, cf_request, problem_url
from .cf_practice import normalize_problem


def sync_options(data):
    if not isinstance(data, dict):
        raise ValueError("请求须为 JSON 对象")
    if set(data) - {"platform", "contest_id", "problem_ids", "limit", "language", "refresh"}:
        raise ValueError("存在不支持的参数，仅支持 platform/contest_id/problem_ids/limit/language/refresh")
    platform = data.get("platform", "atcoder")
    if platform not in ("atcoder", "codeforces"):
        raise ValueError("题面采集支持 atcoder 和 codeforces")
    contest = data.get("contest_id")
    if platform == "atcoder":
        if not isinstance(contest, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", contest):
            raise ValueError("contest_id 必须为有效的 AtCoder 比赛 ID，如 abc370")
    else:
        if type(contest) not in (str, int) or not re.fullmatch(r"[1-9]\d{0,4}", str(contest)):
            raise ValueError("CF contest_id 必须为 1–99999 的普通公开比赛 ID")
        contest = str(contest)
    ids = data.get("problem_ids", [])
    if not isinstance(ids, list) or len(ids) > 100 or any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value) for value in ids
    ):
        raise ValueError("problem_ids 必须为最多 100 个题号组成的数组")
    if platform == "codeforces":
        normalized = [normalize_problem(value) for value in ids]
        if any(str(item["contest_id"]) != contest for item in normalized):
            raise ValueError("CF 题号必须属于指定比赛")
        ids = ["cf_" + item["display_id"] for item in normalized]
    limit = data.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit 必须为 1–100 的整数")
    language = data.get("language", "en")
    if language not in ("en", "ja"):
        raise ValueError("language 必须为 en 或 ja")
    if platform == "codeforces" and language != "en":
        raise ValueError("CF 题面目前仅支持 en")
    refresh = data.get("refresh", False)
    if type(refresh) is not bool:
        raise ValueError("refresh 必须为布尔值")
    return {"platform": platform, "contest_id": contest, "problem_ids": sorted(set(ids)),
            "limit": limit, "language": language, "refresh": refresh}


def cf_metadata(problems, contest):
    if not isinstance(problems, list) or not problems:
        raise ValueError("CF 比赛没有公开题目列表")
    items = []
    seen = set()
    for problem in problems:
        if not isinstance(problem, dict):
            raise ValueError("CF 题目元数据格式异常")
        if problem.get("type", "PROGRAMMING") != "PROGRAMMING":
            continue
        index, name = problem.get("index"), problem.get("name")
        if not isinstance(index, str) or not re.fullmatch(r"[A-Z]{1,3}\d{0,2}", index) or not isinstance(name, str) or not name:
            raise ValueError("CF 题目缺少有效题序或题名")
        if problem.get("contestId", int(contest)) != int(contest):
            raise ValueError("CF 题目比赛 ID 不匹配")
        tags, rating = problem.get("tags", []), problem.get("rating")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("CF 标签格式异常")
        if rating is not None and type(rating) is not int:
            raise ValueError("CF Rating 格式异常")
        problem_id = f"cf_{contest}{index}"
        if problem_id in seen:
            continue
        items.append({"platform": "codeforces", "problem_id": problem_id, "contest_id": contest,
                      "problem_index": index, "problem_name": name, "problem_rating": rating,
                      "tags": tags, "problem_url": problem_url(contest, index)})
        seen.add(problem_id)
    if not items:
        raise ValueError("CF 比赛没有可采集的编程题")
    return items


class ProblemSync:
    def __init__(self, db_path):
        self.db_path = db_path
        self._request_lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def download(self, session, url):
        if url.startswith("https://codeforces.com/"):
            return await cf_page(session, url)
        async with self._request_lock:
            await asyncio.sleep(max(0, self._next_request_at - time.monotonic()))
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.read()
            finally:
                self._next_request_at = time.monotonic() + 1.5

    async def run(self, options, task):
        task.update(status="running", started_at=int(time.time()))
        result = {
            "contest_id": options["contest_id"], "discovered_count": 0, "scope_count": 0,
            "selected_count": 0, "skipped_count": 0, "remaining_count": 0,
            "success_count": 0, "failure_count": 0, "sample_count": 0, "failures": [],
        }
        task["result"] = result
        task["progress"] = {"done": 0, "total": 0}
        db = None
        try:
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "ACM-Forever-DataCollector/0.1"},
            ) as http:
                if options["platform"] == "atcoder":
                    listing = f"https://atcoder.jp/contests/{options['contest_id']}/tasks?lang={options['language']}"
                    items = parse_atcoder_tasks(await self.download(http, listing), options["contest_id"])
                else:
                    data = await cf_request(http, "contest.standings", {"contestId": int(options["contest_id"])})
                    items = cf_metadata(data.get("problems") if isinstance(data, dict) else None, options["contest_id"])
                result["discovered_count"] = len(items)
                requested = set(options["problem_ids"])
                unknown = requested - {item["problem_id"] for item in items}
                if unknown:
                    raise ValueError("比赛题目列表中不存在题号：" + ", ".join(sorted(unknown)))
                items = [item for item in items if not requested or item["problem_id"] in requested]
                result["scope_count"] = len(items)
                async with db.execute(
                    "SELECT problem_id FROM crawler_problems WHERE platform=? "
                    "AND last_fetch_status='ok' AND statement_html IS NOT NULL AND requested_language=?",
                    (options["platform"], options["language"]),
                ) as cursor:
                    completed = {row[0] for row in await cursor.fetchall()} if not options["refresh"] else set()
                pending = [item for item in items if item["problem_id"] not in completed]
                selected = pending[:options["limit"]]
                result.update(skipped_count=len(items) - len(pending), selected_count=len(selected),
                              remaining_count=len(pending) - len(selected))
                task["progress"]["total"] = len(selected)
                for item in selected:
                    problem_id = item["problem_id"]
                    task["progress"]["problem_id"] = problem_id
                    try:
                        source = item["problem_url"] + ("?lang=" + options["language"] if options["platform"] == "atcoder" else "?locale=en")
                        raw = await self.download(http, source)
                        content = parse_atcoder(raw, source, options["language"]) if options["platform"] == "atcoder" else parse_codeforces(raw, source)
                        content.update(source_url=source, requested_language=options["language"],
                                       sha256=hashlib.sha256(raw).hexdigest())
                        await save_problem(db, item, content)
                        result["success_count"] += 1
                        result["sample_count"] += len(content["samples"])
                    except (aiohttp.ClientError, OSError, ValueError, aiosqlite.Error, CFUnavailable) as error:
                        await record_problem_failure(db, options["platform"], problem_id, error)
                        result["failure_count"] += 1
                        result["failures"].append({"problem_id": problem_id, "error": str(error)[:1000]})
                    task["progress"]["done"] += 1
                task["status"] = (
                    "completed" if not result["failure_count"] else
                    "partial" if result["success_count"] else "failed"
                )
        except asyncio.CancelledError:
            task["status"] = "cancelled"
            raise
        except Exception as error:
            task["status"] = "failed"
            result["error"] = str(error)[:1000]
        finally:
            if db:
                await db.close()
            task["finished_at"] = int(time.time())
