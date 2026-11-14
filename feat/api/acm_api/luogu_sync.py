"""Incremental Luogu P catalog and statement tasks, using the shared problem bank."""

import asyncio
import json
import math
import time

import aiohttp
import aiosqlite

from .luogu_client import ORIGIN, LuoguUnavailable, luogu_get
from .luogu_problem import (catalog_page, load_taxonomy,
                            normalize_taxonomy, parse_problem, problem_id, save_taxonomy)
from .problem_bank import record_problem_failure, save_metadata_batch, save_problem


def sync_options(data):
    scope = data.get("scope", "problems" if data.get("problem_ids") else "platform")
    if not isinstance(scope, str) or scope not in {"problems", "catalog", "platform"} or "contest_id" in data:
        raise ValueError("洛谷 scope 支持 problems/catalog/platform，不接受 contest_id")
    ids = data.get("problem_ids", [])
    if not isinstance(ids, list) or len(ids) > 100:
        raise ValueError("problem_ids 必须为最多 100 道 P 题号的数组")
    ids = sorted({problem_id(value) for value in ids}, key=lambda value: int(value[1:]))
    if scope == "problems" and not ids:
        raise ValueError("指定题目采集必须提供 problem_ids")
    if scope != "problems" and "problem_ids" in data:
        raise ValueError("目录/全平台采集不接受 problem_ids")
    limit = data.get("limit", 100) if scope == "platform" else None
    if scope != "platform" and "limit" in data:
        raise ValueError("洛谷 limit 仅用于 platform 的题面数量上限")
    if scope == "platform" and (type(limit) is not int or not 1 <= limit <= 1000):
        raise ValueError("洛谷 limit 必须为 1–1000 的整数")
    batch = data.get("batch_size", 50)
    if type(batch) is not int or not 1 <= batch <= 100:
        raise ValueError("batch_size 必须为 1–100 的整数")
    language = data.get("language", "zh-CN")
    if language != "zh-CN":
        raise ValueError("洛谷本期仅支持 zh-CN 题面")
    refresh = data.get("refresh", False)
    if type(refresh) is not bool:
        raise ValueError("refresh 必须为布尔值")
    return {"platform": "luogu", "scope": scope, "contest_id": None, "problem_ids": ids,
            "limit": limit, "batch_size": batch, "language": language, "refresh": refresh}


class LuoguSync:
    def __init__(self, db_path, config=None):
        self.db_path = db_path
        self.config = config or {}

    async def download(self, http, path):
        return await luogu_get(http, ORIGIN + path, interval=self.config.get("luogu_request_interval", 2.0))

    async def taxonomy(self, db, http, result):
        cached = await load_taxonomy(db)
        if cached and not cached["stale"]:
            return cached
        try:
            config = json.loads(await self.download(http, "/_lfe/config"))
            tags = json.loads(await self.download(http, "/_lfe/tags"))
            normalized = normalize_taxonomy(config, tags)
            await save_taxonomy(db, normalized)
            return await load_taxonomy(db)
        except LuoguUnavailable:
            raise
        except (ValueError, aiohttp.ClientError, OSError, asyncio.TimeoutError) as error:
            if not cached:
                raise
            result["taxonomy_warning"] = "分类字典刷新失败，使用本地缓存：" + str(error)[:300]
            return cached

    async def catalog(self, db, http, taxonomy, task):
        result = task["result"]
        seen, items = set(), []
        total = per_page = None
        maximum = self.config.get("luogu_catalog_max_pages", 1000)
        for page in range(1, maximum + 1):
            batch, count, size = catalog_page(await self.download(http, f"/problem/list?type=P&page={page}"), taxonomy)
            if total is None:
                total, per_page = count, size
            elif (count, size) != (total, per_page):
                raise ValueError("洛谷目录在分页期间发生变化，请重新采集；已提交批次保留")
            expected = min(size, max(0, total - (page - 1) * size))
            if len(batch) != expected or any(item["problem_id"] in seen for item in batch) or len({item["problem_id"] for item in batch}) != len(batch):
                raise ValueError("洛谷目录出现重复题号或不完整分页，已停止以避免误报完成")
            result["discovered_count"] = len(items) + len(batch)
            for offset in range(0, len(batch), task["options"]["batch_size"]):
                chunk = batch[offset:offset + task["options"]["batch_size"]]
                await save_metadata_batch(db, chunk)
                result["metadata_count"] += len(chunk)
            items.extend(batch)
            seen.update(item["problem_id"] for item in batch)
            result.update(catalog_pages=page)
            task["progress"] = {"phase": "catalog", "done": len(items), "total": total}
            if len(items) >= total:
                result["catalog_complete"] = True
                return items
        raise ValueError("洛谷目录超出配置的页数上限，已停止；调整 ACM_LUOGU_CATALOG_MAX_PAGES 后重试")

    async def run(self, options, task):
        task.update(status="running", started_at=int(time.time()), options=dict(options))
        result = {"scope": options["scope"], "contest_id": None, "discovered_count": 0, "metadata_count": 0,
                  "scope_count": 0, "selected_count": 0, "skipped_count": 0, "remaining_count": 0,
                  "success_count": 0, "failure_count": 0, "sample_count": 0, "failures": [],
                  "batch_count": 0, "completed_batches": 0, "catalog_pages": 0, "catalog_complete": False,
                  "failure_details_truncated": False}
        task["result"] = result
        task["progress"] = {"phase": "taxonomy", "done": 0, "total": 0}
        db = None
        try:
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            # This collector never sends browser cookies or follows login redirects.
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                    cookie_jar=aiohttp.DummyCookieJar(), headers={"User-Agent": "ACM-Forever-DataCollector/0.1",
                    "Accept": "text/html,application/json"}) as http:
                taxonomy = await self.taxonomy(db, http, result)
                if options["scope"] == "problems":
                    items = []
                    for pid in options["problem_ids"]:
                        async with db.execute("SELECT metadata_json FROM crawler_problems WHERE platform='luogu' AND problem_id=?", (pid,)) as cursor:
                            old = await cursor.fetchone()
                        item = json.loads(old["metadata_json"]) if old else {"platform": "luogu", "problem_id": pid,
                            "contest_id": "", "problem_name": pid, "problem_rating": None,
                            "problem_url": ORIGIN + "/problem/" + pid, "tags": [], "luogu": {}}
                        items.append(item)
                        if not old:
                            await save_metadata_batch(db, [item])
                    result["discovered_count"] = len(items)
                else:
                    items = await self.catalog(db, http, taxonomy, task)
                if options["scope"] == "catalog":
                    task["status"] = "completed"
                    return
                async with db.execute("SELECT problem_id FROM crawler_problems WHERE platform='luogu' AND "
                        "(COALESCE(length(statement_html),0)>0 OR COALESCE(length(statement_text),0)>0)") as cursor:
                    saved = {row[0] for row in await cursor.fetchall()}
                result["scope_count"] = len(items)
                pending = [item for item in items if options["refresh"] or item["problem_id"] not in saved]
                # Reuse retry ordering so persistent failures cannot starve untouched rows.
                pending.sort(key=lambda item: int(item["problem_id"][1:]), reverse=True)
                if not options["refresh"] or options.get("scheduled"):
                    from .problem_sync import _scheduled_pending
                    pending = await _scheduled_pending(db, "luogu", pending)
                result["skipped_count"] = len(items) - len(pending)
                cap = options["limit"] if options["scope"] == "platform" else len(pending)
                if options.get("scheduled"):
                    cap = min(cap, self.config.get("luogu_daily_statement_limit", 100))
                selected = pending[:cap]
                result.update(selected_count=len(selected), remaining_count=len(pending),
                              batch_count=math.ceil(len(selected) / options["batch_size"]))
                failures_in_row = 0
                for index, item in enumerate(selected, 1):
                    pid = item["problem_id"]
                    task["progress"] = {"phase": "statements", "done": index - 1, "total": len(selected), "problem_id": pid}
                    try:
                        item, content = parse_problem(await self.download(http, "/problem/" + pid), pid, taxonomy)
                        await save_problem(db, item, content)
                        result["success_count"] += 1
                        result["sample_count"] += len(content["samples"])
                        result["remaining_count"] -= 1
                        failures_in_row = 0
                    except asyncio.CancelledError:
                        raise
                    except (ValueError, aiohttp.ClientError, aiosqlite.Error, OSError, asyncio.TimeoutError, LuoguUnavailable) as error:
                        await record_problem_failure(db, "luogu", pid, error)
                        result["failure_count"] += 1
                        if len(result["failures"]) < 100:
                            result["failures"].append({"problem_id": pid, "error": str(error)[:500]})
                        else:
                            result["failure_details_truncated"] = True
                        task["progress"]["done"] = index
                        if isinstance(error, LuoguUnavailable) and error.status != 404:
                            raise
                        failures_in_row += 1
                        if failures_in_row >= 3:
                            raise ValueError("连续三道题采集失败，已停止本次任务；已有题面与样例保留") from error
                    task["progress"]["done"] = index
                    result["completed_batches"] = index // options["batch_size"] + int(index == len(selected) and index % options["batch_size"] != 0)
                task["status"] = "partial" if result["failure_count"] else "completed"
        except asyncio.CancelledError:
            task["status"] = "cancelled"
            raise
        except Exception as error:
            result["error"] = str(error)[:1000]
            if isinstance(error, LuoguUnavailable):
                result.update(access_limited=error.status != 404, retry_after=error.retry_after)
            task["status"] = "partial" if result["metadata_count"] or result["success_count"] else "failed"
        finally:
            if db:
                await db.close()
            task["finished_at"] = int(time.time())
