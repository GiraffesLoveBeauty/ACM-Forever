"""Administrator-triggered collection of public AtCoder and Codeforces problems."""

import asyncio
import hashlib
import json
import re
import time

import aiohttp
import aiosqlite

from .problem_bank import record_problem_failure, save_problem, save_metadata_batch
from .problem_content import parse_atcoder, parse_atcoder_tasks, parse_codeforces
from .cf_client import CFUnavailable, cf_page, cf_request, problem_url
from .cf_practice import normalize_problem
from .contest_metadata import contest_metadata, refresh_contests, save_contests

ATCODER_CATALOG_URL = "https://kenkoooo.com/atcoder/resources/problems.json"


def sync_options(data):
    if not isinstance(data, dict):
        raise ValueError("请求须为 JSON 对象")
    if set(data) - {"platform", "scope", "contest_id", "problem_ids", "limit", "batch_size", "language", "refresh"}:
        raise ValueError("存在不支持的参数，仅支持 platform/scope/contest_id/problem_ids/limit/batch_size/language/refresh")
    platform = data.get("platform", "atcoder")
    if platform not in ("atcoder", "codeforces"):
        raise ValueError("题面采集支持 atcoder 和 codeforces")
    scope = data.get("scope", "contest")
    if scope not in ("contest", "platform"):
        raise ValueError("scope 必须为 contest（单场比赛）或 platform（整个平台）")
    contest = data.get("contest_id")
    if scope == "platform":
        if "contest_id" in data or "problem_ids" in data or "limit" in data:
            raise ValueError("全平台采集不接受 contest_id/problem_ids/limit；可使用 batch_size 设置批次大小")
    elif platform == "atcoder":
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
    if scope == "contest" and platform == "codeforces":
        normalized = []
        for value in ids:
            try:
                item = normalize_problem(value)
            except ValueError:
                # A few historical contests (e.g. 921) use numeric indices.
                if not re.fullmatch(r"(?:cf_)?" + re.escape(contest) + r"\d{1,3}", value, re.I):
                    raise
                normalized.append("cf_" + re.sub(r"^cf_", "", value, flags=re.I))
                continue
            if str(item["contest_id"]) != contest:
                raise ValueError("CF 题号必须属于指定比赛")
            normalized.append("cf_" + item["display_id"])
        ids = normalized
    limit = data.get("limit", 20) if scope == "contest" else None
    if scope == "contest" and (type(limit) is not int or not 1 <= limit <= 100):
        raise ValueError("limit 必须为 1–100 的整数")
    batch_size = data.get("batch_size", 100) if scope == "platform" else None
    if scope == "contest" and "batch_size" in data:
        raise ValueError("batch_size 仅用于全平台采集")
    if scope == "platform" and (type(batch_size) is not int or not 1 <= batch_size <= 100):
        raise ValueError("batch_size 必须为 1–100 的整数")
    language = data.get("language", "en")
    if language not in ("en", "ja"):
        raise ValueError("language 必须为 en 或 ja")
    if platform == "codeforces" and language != "en":
        raise ValueError("CF 题面目前仅支持 en")
    refresh = data.get("refresh", False)
    if type(refresh) is not bool:
        raise ValueError("refresh 必须为布尔值")
    return {"platform": platform, "scope": scope, "contest_id": contest, "problem_ids": sorted(set(ids)),
            "limit": limit, "batch_size": batch_size, "language": language, "refresh": refresh}


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
        if not isinstance(index, str) or not re.fullmatch(r"(?:[A-Z]{1,3}\d{0,2}|\d{1,3})", index) or not isinstance(name, str) or not name:
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


def atcoder_catalog_metadata(problems):
    if not isinstance(problems, list) or not problems:
        raise ValueError("AtCoder 题目目录必须为非空数组")
    items, seen = [], set()
    for problem in problems:
        if not isinstance(problem, dict):
            raise ValueError("AtCoder 题目元数据格式异常")
        pid, contest = problem.get("id"), problem.get("contest_id")
        name = problem.get("name") or problem.get("title")
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value) for value in (pid, contest)):
            raise ValueError("AtCoder 目录包含无效题号或比赛 ID")
        if not isinstance(name, str) or not name:
            raise ValueError("AtCoder 目录包含无效题名")
        if pid in seen:
            continue
        items.append({"platform": "atcoder", "problem_id": pid, "contest_id": contest,
                      "problem_index": str(problem.get("problem_index") or ""), "problem_name": name,
                      "problem_rating": None, "tags": [],
                      "problem_url": f"https://atcoder.jp/contests/{contest}/tasks/{pid}"})
        seen.add(pid)
    return items


def cf_catalog_metadata(problems):
    if not isinstance(problems, list) or not problems:
        raise ValueError("CF 题目目录必须为非空数组")
    groups = {}
    for problem in problems:
        if not isinstance(problem, dict):
            raise ValueError("CF 题目元数据格式异常")
        contest = problem.get("contestId")
        if type(contest) is int and 1 <= contest <= 99999 and problem.get("type", "PROGRAMMING") == "PROGRAMMING":
            groups.setdefault(str(contest), []).append(problem)
    items = [item for contest in sorted(groups, key=int) for item in cf_metadata(groups[contest], contest)]
    if not items:
        raise ValueError("CF 目录没有可采集的普通公开比赛题目")
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
                    if response.status == 404 and url.startswith("https://atcoder.jp/"):
                        raise ValueError(f"AtCoder 原站返回 HTTP 404，题目可能未公开或已移除：{url}")
                    response.raise_for_status()
                    return await response.read()
            finally:
                self._next_request_at = time.monotonic() + 1.5

    async def run(self, options, task):
        task.update(status="running", started_at=int(time.time()))
        full = options["scope"] == "platform"
        result = {
            "contest_id": options["contest_id"], "discovered_count": 0, "scope_count": 0,
            "selected_count": 0, "skipped_count": 0, "remaining_count": 0,
            "scope": options["scope"], "success_count": 0, "failure_count": 0, "sample_count": 0, "failures": [],
            "metadata_count": 0, "batch_count": 0, "completed_batches": 0, "failure_details_truncated": False,
        }
        task["result"] = result
        task["progress"] = {"done": 0, "total": 0, "phase": "catalog"}
        db = None
        try:
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "ACM-Forever-DataCollector/0.1"},
            ) as http:
                if full and options["platform"] == "atcoder":
                    items = atcoder_catalog_metadata(json.loads((await self.download(http, ATCODER_CATALOG_URL)).decode("utf-8-sig")))
                elif full:
                    data = await cf_request(http, "problemset.problems")
                    items = cf_catalog_metadata(data.get("problems") if isinstance(data, dict) else None)
                elif options["platform"] == "atcoder":
                    listing = f"https://atcoder.jp/contests/{options['contest_id']}/tasks?lang={options['language']}"
                    items = parse_atcoder_tasks(await self.download(http, listing), options["contest_id"])
                else:
                    data = await cf_request(http, "contest.standings", {"contestId": int(options["contest_id"])})
                    items = cf_metadata(data.get("problems") if isinstance(data, dict) else None, options["contest_id"])
                try:
                    if options["platform"] == "codeforces" and not full:
                        contest = data.get("contest")
                        if isinstance(contest, dict) and str(contest.get("id")) == options["contest_id"]:
                            await save_contests(db, contest_metadata("codeforces", [contest]))
                    else:
                        await refresh_contests(db, http, options["platform"],
                                               {item["contest_id"] for item in items},
                                               lambda url: self.download(http, url))
                except (aiohttp.ClientError, OSError, ValueError, aiosqlite.Error, CFUnavailable) as error:
                    result["contest_metadata_error"] = str(error)[:1000]
                result["discovered_count"] = len(items)
                if full:
                    task["progress"].update(phase="metadata", metadata_done=0, metadata_total=len(items))
                    for start in range(0, len(items), options["batch_size"]):
                        batch = items[start:start + options["batch_size"]]
                        await save_metadata_batch(db, batch)
                        result["metadata_count"] += len(batch)
                        task["progress"]["metadata_done"] = result["metadata_count"]
                requested = set(options["problem_ids"])
                unknown = requested - {item["problem_id"] for item in items}
                if unknown:
                    raise ValueError("比赛题目列表中不存在题号：" + ", ".join(sorted(unknown)))
                items = [item for item in items if not requested or item["problem_id"] in requested]
                result["scope_count"] = len(items)
                async with db.execute(
                    "SELECT problem_id FROM crawler_problems WHERE platform=? "
                    "AND last_fetch_status='ok' AND (statement_html IS NOT NULL OR statement_pdf IS NOT NULL) AND requested_language=?",
                    (options["platform"], options["language"]),
                ) as cursor:
                    completed = {row[0] for row in await cursor.fetchall()} if not options["refresh"] else set()
                pending = [item for item in items if item["problem_id"] not in completed]
                selected = pending if full else pending[:options["limit"]]
                result.update(skipped_count=len(items) - len(pending), selected_count=len(selected),
                              remaining_count=len(pending) if full else len(pending) - len(selected))
                batch_size = options["batch_size"] if full else max(1, len(selected))
                result["batch_count"] = (len(selected) + batch_size - 1) // batch_size
                task["progress"]["total"] = len(selected)
                task["progress"]["phase"] = "statements"
                for position, item in enumerate(selected):
                    task["progress"]["batch"] = position // batch_size + 1
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
                        if len(result["failures"]) < 100:
                            result["failures"].append({"problem_id": problem_id, "error": str(error)[:1000]})
                        else:
                            result["failure_details_truncated"] = True
                    task["progress"]["done"] += 1
                    if full:
                        result["remaining_count"] = len(selected) - task["progress"]["done"]
                    if task["progress"]["done"] % batch_size == 0 or task["progress"]["done"] == len(selected):
                        result["completed_batches"] += 1
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
