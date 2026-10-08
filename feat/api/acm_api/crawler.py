# -*- coding: utf-8 -*-
"""CF / 洛谷 / 牛客 / AtCoder 提交记录爬虫（移植自 astrbot_plugin_acm_helper，扩展牛客与 AtCoder）"""
import asyncio
import hashlib
import html as html_lib
import json
import math
import random
import re
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import aiosqlite

import logging
from .cf_client import CFUnavailable, cf_request

LOG = logging.getLogger("acm_api.crawler")

_NOWCODER_ROW_RE = re.compile(
    r'view-submission\?submissionId=(\d+).*?href="/acm/problem/(\d+)"[^>]*>([^<]+)</a>.*?<td>(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})</td>',
    re.S,
)

# AtCoder 题名与难度缓存（资源文件较大，每个进程只拉一次）
_ATCODER_TITLES = None
_ATCODER_TITLES_LOCK = asyncio.Lock()
_ATCODER_DIFFICULTIES = None
_ATCODER_DIFFICULTIES_LOCK = asyncio.Lock()

_LUOGU_GATE_LOCK = asyncio.Lock()
_LUOGU_NEXT_REQUEST_AT = 0.0
_LUOGU_COOLDOWN_UNTIL = 0.0
_LUOGU_FAILURES = 0
_LUOGU_MIN_INTERVAL = 1.2
_LUOGU_403_COOLDOWN = 300.0
_LUOGU_429_COOLDOWN = 60.0
async def _store_cf_attempts(db, qq_id, submissions, *, commit=True):
    """Persist submission evidence and record unsolved contest problems without learning queues."""
    now = int(time.time())
    contest_problems = set()
    values = []
    for sub in submissions or []:
        if not isinstance(sub, dict) or not isinstance(sub.get("problem"), dict):
            continue
        prob = sub["problem"]
        contest_id, index = prob.get("contestId"), prob.get("index")
        submitted_at = int(sub.get("creationTimeSeconds") or 0)
        if not contest_id or not index or not submitted_at:
            continue
        problem_id = f"cf_{contest_id}{index}"
        verdict = str(sub.get("verdict") or "UNKNOWN")
        external_id = f"{qq_id}:{sub.get('id')}" if sub.get("id") is not None else None
        values.append((str(qq_id), "codeforces", external_id, problem_id, str(contest_id), verdict,
                       str(sub.get("programmingLanguage") or ""), submitted_at, None, now))
        contest_problems.add((str(contest_id), problem_id))
    if values:
        await db.executemany("INSERT INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,contest_id,verdict,language,submitted_at,source_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,external_submission_id) DO UPDATE SET verdict=excluded.verdict,language=excluded.language,submitted_at=excluded.submitted_at", values)
    for contest_id, problem_id in contest_problems:
        async with db.execute("SELECT 1 FROM submission_attempts WHERE owner_qq_id=? AND platform='codeforces' AND contest_id=? AND problem_id=? AND verdict='OK' LIMIT 1", (str(qq_id), contest_id, problem_id)) as cursor:
            if await cursor.fetchone():
                continue
        async with db.execute("SELECT verdict FROM submission_attempts WHERE owner_qq_id=? AND platform='codeforces' AND contest_id=? AND problem_id=? ORDER BY submitted_at DESC LIMIT 1", (str(qq_id), contest_id, problem_id)) as cursor:
            latest = await cursor.fetchone()
        if not latest:
            continue
        await db.execute("INSERT OR IGNORE INTO contest_problem_reviews(owner_qq_id,contest_id,problem_id,verdict,status,updated_at) VALUES(?,?,?,?,?,?)", (str(qq_id), contest_id, problem_id, latest["verdict"], "unsolved", now))
    if values and commit:
        await db.commit()


_LUOGU_PROFILE_CONTEXT_RE = re.compile(
    r'<script\s+id="lentille-context"\s+type="application/json">(.*?)</script>',
    re.S,
)


async def _fetch_luogu_json(session, url, headers, timeout):
    """所有洛谷请求共享节流和短期熔断，避免并发用户形成失败风暴。"""
    global _LUOGU_NEXT_REQUEST_AT, _LUOGU_COOLDOWN_UNTIL, _LUOGU_FAILURES
    async with _LUOGU_GATE_LOCK:
        now = time.monotonic()
        if now < _LUOGU_COOLDOWN_UNTIL:
            raise RuntimeError("洛谷请求处于冷却期")
        wait = _LUOGU_NEXT_REQUEST_AT - now
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status == 403:
                    _LUOGU_FAILURES += 1
                    _LUOGU_COOLDOWN_UNTIL = time.monotonic() + _LUOGU_403_COOLDOWN
                    raise RuntimeError("洛谷返回 403，已进入冷却期")
                if response.status == 429:
                    _LUOGU_FAILURES += 1
                    _LUOGU_COOLDOWN_UNTIL = time.monotonic() + _LUOGU_429_COOLDOWN
                    raise RuntimeError("洛谷返回 429，已进入冷却期")
                response.raise_for_status()
                data = await response.json()
            _LUOGU_FAILURES = 0
            return data
        finally:
            _LUOGU_NEXT_REQUEST_AT = time.monotonic() + _LUOGU_MIN_INTERVAL

luogu_difficulty_map = {
    0: "未评定",
    1: "入门",
    2: "普及-",
    3: "普及/提高-",
    4: "普及+/提高",
    5: "提高+/省选-",
    6: "省选/NOI-",
    7: "NOI/NOI+/CTSC",
}


class Crawler:
    @staticmethod
    async def verify_account_ownership(session: aiohttp.ClientSession, platform: str, account: str, code: str, config: dict):
        """在账号公开资料中查找一次性验证码，确认绑定者拥有账号编辑权限。"""
        profile_urls = {
            "cf": [f"https://codeforces.com/profile/{urllib.parse.quote(account, safe='')}"],
            "luogu": [f"https://www.luogu.com.cn/user/{urllib.parse.quote(account, safe='')}"],
            "nowcoder": [f"https://ac.nowcoder.com/acm/contest/profile/{urllib.parse.quote(account, safe='')}/practice-coding"],
            "atcoder": [f"https://atcoder.jp/users/{urllib.parse.quote(account, safe='')}"],
            # CJLU 不同版本可能把公开资料放在用户页或用户 API，两个入口都检查。
            "cjlu": [
                f"https://acm.cjlu.edu.cn/user/{urllib.parse.quote(account, safe='')}",
                f"https://acm.cjlu.edu.cn/api/users/{urllib.parse.quote(account, safe='')}",
            ],
        }
        urls = profile_urls.get(platform)
        if not urls:
            return False, "不支持的平台"
        if session is None or not code:
            return False, "验证参数为空"
        try:
            bodies = []
            for url in urls:
                async with session.get(
                    url,
                    headers={"User-Agent": "ACM-Helper/1.0", "Accept": "text/html,application/json"},
                    timeout=15,
                ) as response:
                    if response.status == 404:
                        continue
                    response.raise_for_status()
                    bodies.append(await response.text())
            if not bodies:
                return False, "账号不存在"
            body = "\n".join(bodies)
        except aiohttp.ClientResponseError as exc:
            if exc.status == 404:
                return False, "账号不存在"
            return False, "平台资料页暂时不可用，请稍后重试"
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False, "平台资料页暂时不可用，请稍后重试"

        # 同时检查原始 HTML/JSON 与去标签文本，兼容资料页的转义和富文本格式。
        searchable = " ".join((body, html_lib.unescape(body), re.sub(r"<[^>]+>", " ", html_lib.unescape(body))))
        if code.casefold() in searchable.casefold():
            return True, "验证成功"
        return False, "未在账号公开资料中找到验证码，请确认已保存并稍后重试"

    @staticmethod
    async def validate_account(session: aiohttp.ClientSession, platform: str, account: str, config: dict):
        """验证平台账号是否存在，并返回平台规范化后的账号名。

        返回 ``(True, canonical_account)`` 表示验证成功，返回
        ``(False, reason)`` 表示绑定前无法确认账号。网络错误也会阻止绑定，
        避免把一个尚未验证的账号写入数据库。
        """
        validators = {
            "cf": Crawler._validate_cf_account,
            "luogu": Crawler._validate_luogu_account,
            "nowcoder": Crawler._validate_nowcoder_account,
            "atcoder": Crawler._validate_atcoder_account,
            "cjlu": Crawler._validate_cjlu_account,
        }
        validator = validators.get(platform)
        if validator is None:
            return False, "不支持的平台"
        if session is None or not account:
            return False, "验证参数为空"
        try:
            return await validator(session, account, config or {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("验证 %s 账号 %s 失败: %s", platform, account, exc)
            return False, "平台接口暂时不可用，请稍后重试"

    @staticmethod
    async def _validate_cf_account(session, handle: str, config: dict):
        try:
            users = await cf_request(session, "user.info", {"handles": handle}, config)
        except CFUnavailable as exc:
            comment = str(exc).lower()
            if "not found" in comment or "handle" in comment and "not" in comment:
                return False, "账号不存在"
            return False, "Codeforces 接口暂时不可用，请稍后重试"
        if isinstance(users, list) and users and isinstance(users[0], dict):
            canonical = users[0].get("handle") or handle
            return True, str(canonical)
        return False, "账号不存在或无法确认"

    @staticmethod
    async def _validate_luogu_account(session, uid: str, config: dict):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
        if config.get("luogu_cookie"):
            headers["Cookie"] = config["luogu_cookie"]
        if config.get("luogu_csrf_token"):
            headers["x-csrf-token"] = config["luogu_csrf_token"]
        # `/api/user/show` has been retired by Luogu and returns 404 even for
        # existing users. The public profile remains the supported source and
        # embeds its page data in the `lentille-context` JSON script.
        url = "https://www.luogu.com.cn/user/" + urllib.parse.quote(uid, safe="")
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 404:
                    return False, "账号不存在"
                response.raise_for_status()
                body = await response.text()
        except aiohttp.ClientResponseError as exc:
            if exc.status == 404:
                return False, "账号不存在"
            return False, "洛谷接口暂时不可用，请稍后重试"
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False, "洛谷接口暂时不可用，请稍后重试"

        match = _LUOGU_PROFILE_CONTEXT_RE.search(body)
        if not match:
            return False, "洛谷接口返回异常，暂时无法确认账号"
        try:
            context = json.loads(match.group(1))
        except json.JSONDecodeError:
            return False, "洛谷接口返回异常，暂时无法确认账号"

        payload = context.get("data") if isinstance(context, dict) else None
        user = payload.get("user") if isinstance(payload, dict) else None
        if isinstance(user, dict) and user.get("uid") is not None:
            return True, str(user["uid"])
        return False, "洛谷未返回用户资料，暂时无法确认账号"

    @staticmethod
    async def _validate_nowcoder_account(session, uid: str, config: dict):
        url = (
            f"https://ac.nowcoder.com/acm/contest/profile/{urllib.parse.quote(uid, safe='')}/practice-coding"
            "?pageSize=1&statusTypeFilter=5&languageCategoryFilter=-1&orderType=DESC&page=1"
        )
        try:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15) as response:
                if response.status == 404:
                    return False, "账号不存在"
                response.raise_for_status()
                html_str = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False, "牛客接口暂时不可用，请稍后重试"
        if any(marker in html_str for marker in ("用户不存在", "用户不存在或已注销", "页面不存在")):
            return False, "账号不存在"
        return True, uid

    @staticmethod
    async def _validate_atcoder_account(session, handle: str, config: dict):
        url = "https://atcoder.jp/users/" + urllib.parse.quote(handle, safe="")
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 404:
                    return False, "账号不存在"
                response.raise_for_status()
                await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False, "AtCoder 接口暂时不可用，请稍后重试"
        return True, handle

    @staticmethod
    async def _validate_cjlu_account(session, username: str, config: dict):
        from .cjlu_api import CjluClient

        data = await CjluClient().get_user_solved(session, username)
        if data is None:
            return False, "账号不存在或校 OJ 接口暂时不可用"
        return True, username

    @staticmethod
    async def _get_existing_problem_ids(db: aiosqlite.Connection, qq_id: str, platform: str) -> set:
        async with db.execute(
            "SELECT problem_id FROM submissions WHERE user_qq_id=? AND platform=?",
            (qq_id, platform),
        ) as cursor:
            return {row["problem_id"] for row in await cursor.fetchall()}

    @staticmethod
    def _generate_cf_api_sig(method_name: str, params: dict, api_key: str, api_secret: str) -> str:
        rand = "".join([chr(random.randint(ord("a"), ord("z"))) for _ in range(6)])
        param_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        text = f"{rand}/{method_name}?{param_str}#{api_secret}"
        sha512_hash = hashlib.sha512(text.encode("utf-8")).hexdigest()
        return f"{rand}{sha512_hash}"

    @staticmethod
    async def fetch_luogu_submissions(
        session: aiohttp.ClientSession,
        user_row,
        start_timestamp: int,
        db: aiosqlite.Connection,
        config: dict,
    ) -> int:
        luogu_uid, qq_id = user_row["luogu_id"], user_row["qq_id"]
        added_count = 0
        luogu_cookie = config.get("luogu_cookie")
        luogu_csrf_token = config.get("luogu_csrf_token")

        if not luogu_cookie or not luogu_csrf_token:
            LOG.warning("[同步模块] 洛谷 Cookie 或 CSRF-Token 未配置，跳过。")
            return -1

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": luogu_cookie,
            "x-csrf-token": luogu_csrf_token,
        }
        page, stop_fetching = 1, False
        sync_failed = False
        existing_ids = await Crawler._get_existing_problem_ids(db, qq_id, "luogu")

        while not stop_fetching:
            url = f"https://www.luogu.com.cn/record/list?user={luogu_uid}&page={page}&status=12&_contentOnly=1"
            try:
                data = await _fetch_luogu_json(session, url, headers, 15)
                records = data.get("currentData", {}).get("records", {}).get("result", [])
                if not records:
                    break

                insert_tasks = []
                for record in records:
                    if record["submitTime"] >= start_timestamp:
                        pid = record["problem"]["pid"]
                        if pid in existing_ids:
                            continue
                        difficulty = luogu_difficulty_map.get(
                            record["problem"].get("difficulty", 0), "未知"
                        )
                        insert_tasks.append(
                            (
                                qq_id,
                                "luogu",
                                pid,
                                record["problem"]["title"],
                                difficulty,
                                f"https://www.luogu.com.cn/problem/{pid}",
                                record["submitTime"],
                            )
                        )
                    else:
                        stop_fetching = True
                        break

                if insert_tasks:
                    await db.executemany(
                        "INSERT INTO submissions (user_qq_id, platform, problem_id, problem_name, problem_rating, problem_url, tags, submit_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        insert_tasks,
                    )
                    await db.commit()
                    added_count += len(insert_tasks)
                page += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                sync_failed = True
                LOG.error(f"处理洛谷用户 {luogu_uid} 第 {page} 页时出错: {e}")
                break
        return -1 if sync_failed else added_count

    @staticmethod
    async def fetch_cf_submissions(session, user_row, start_timestamp, db, config):
        return await Crawler.fetch_cf_submissions_paginated(session, user_row, start_timestamp, db, config)

    @staticmethod
    async def fetch_cf_submissions_paginated(session, user_row, start_timestamp, db, config):
        from .cf_history import fetch_history

        return await fetch_history(session, user_row, start_timestamp, db, config)

    @staticmethod
    async def fetch_luogu_submission(
        session: aiohttp.ClientSession,
        user_row,
        start_timestamp: int,
        db: aiosqlite.Connection,
        config: dict,
    ) -> int:
        """深度同步用的洛谷爬虫（分页聚合后一次性写入）。"""
        luogu_uid, qq_id = user_row["luogu_id"], user_row["qq_id"]
        luogu_cookie = config.get("luogu_cookie")
        luogu_csrf_token = config.get("luogu_csrf_token")

        if not luogu_cookie or not luogu_csrf_token:
            LOG.warning("[同步模块] 洛谷 Cookie 或 CSRF-Token 未配置，跳过。")
            return -1

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": luogu_cookie,
            "x-csrf-token": luogu_csrf_token,
        }
        page, stop_fetching = 1, False
        sync_failed = False
        all_insert_tasks = []
        processed_in_sync = set()
        existing_ids = await Crawler._get_existing_problem_ids(db, qq_id, "luogu")
        while not stop_fetching:
            url = f"https://www.luogu.com.cn/record/list?user={luogu_uid}&page={page}&status=12&_contentOnly=1"
            try:
                data = await _fetch_luogu_json(session, url, headers, 30)
                records = data.get("currentData", {}).get("records", {}).get("result", [])
                if not records:
                    break

                page_insert_tasks = []
                for record in records:
                    if record["submitTime"] >= start_timestamp:
                        pid = record["problem"]["pid"]
                        if pid in processed_in_sync:
                            continue
                        processed_in_sync.add(pid)
                        if pid in existing_ids:
                            continue
                        difficulty = luogu_difficulty_map.get(
                            record["problem"].get("difficulty", 0), "未知"
                        )
                        page_insert_tasks.append(
                            (
                                qq_id,
                                "luogu",
                                pid,
                                record["problem"]["title"],
                                difficulty,
                                f"https://www.luogu.com.cn/problem/{pid}",
                                record["submitTime"],
                            )
                        )
                    else:
                        stop_fetching = True
                        break

                if page_insert_tasks:
                    all_insert_tasks.extend(page_insert_tasks)
                page += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                sync_failed = True
                LOG.error(f"处理洛谷用户 {luogu_uid} 第 {page} 页时出错: {e}")
                break

        if sync_failed:
            return -1
        if all_insert_tasks:
            await db.executemany(
                "INSERT OR IGNORE INTO submissions (user_qq_id, platform, problem_id, problem_name, problem_rating, problem_url, submit_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                all_insert_tasks,
            )
            await db.commit()
            return len(all_insert_tasks)

        return 0

    # ================= 牛客 Nowcoder =================

    @staticmethod
    def _parse_nowcoder_html(html_str: str):
        """解析 practice-coding 页面，返回 [(submission_id, problem_id, title, submit_ts), ...]"""
        rows = []
        for m in _NOWCODER_ROW_RE.finditer(html_str):
            sid, pid, title, time_str = m.group(1), m.group(2), m.group(3), m.group(4)
            ts = Crawler._parse_nowcoder_time(time_str)
            rows.append((sid, pid, html_lib.unescape(title).strip(), ts))
        return rows

    @staticmethod
    def _parse_nowcoder_time(time_str: str):
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            return int(dt.timestamp())
        except Exception:
            return None

    @staticmethod
    async def fetch_nowcoder_submissions(
        session: aiohttp.ClientSession,
        user_row,
        start_timestamp: int,
        db: aiosqlite.Connection,
        config: dict,
        max_pages: int = 50,
    ) -> int:
        """抓取牛客 practice-coding 页面（无需登录），statusTypeFilter=5 为 AC 记录。"""
        uid = (user_row["nowcoder_id"] or "").strip()
        qq_id = user_row["qq_id"]
        if not uid:
            return 0

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        page = 1
        last_sid = None
        all_insert_tasks = []
        processed = set()
        sync_failed = False
        existing_ids = await Crawler._get_existing_problem_ids(db, qq_id, "nowcoder")

        while page <= max_pages:
            url = (
                f"https://ac.nowcoder.com/acm/contest/profile/{uid}/practice-coding"
                f"?pageSize=200&statusTypeFilter=5&languageCategoryFilter=-1&orderType=DESC&page={page}"
            )
            try:
                async with session.get(url, headers=headers, timeout=20) as response:
                    if response.status == 404:
                        break
                    response.raise_for_status()
                    html_str = await response.text()
            except Exception as e:
                sync_failed = True
                LOG.error(f"处理牛客用户 {uid} 第 {page} 页时出错: {e}")
                break

            if "用户不存在" in html_str:
                break

            rows = Crawler._parse_nowcoder_html(html_str)
            if not rows:
                break

            first_sid = rows[0][0]
            if first_sid == last_sid:
                break  # 页面已循环，停止
            last_sid = first_sid

            for sid, pid, title, ts in rows:
                if ts is None:
                    continue
                if ts < start_timestamp:
                    # 时间倒序，遇到旧记录即可停止整个同步
                    page = max_pages
                    break
                if pid in processed:
                    continue
                processed.add(pid)
                if pid in existing_ids:
                    continue
                all_insert_tasks.append(
                    (
                        qq_id,
                        "nowcoder",
                        pid,
                        title or f"P{pid}",
                        "",
                        f"https://ac.nowcoder.com/acm/problem/{pid}",
                        ts,
                    )
                )

            if page > max_pages or (rows and rows[-1][3] is not None and rows[-1][3] < start_timestamp):
                break
            page += 1
            await asyncio.sleep(0.5)

        if all_insert_tasks:
            await db.executemany(
                "INSERT OR IGNORE INTO submissions (user_qq_id, platform, problem_id, problem_name, problem_rating, problem_url, submit_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                all_insert_tasks,
            )
            await db.commit()
        return -1 if sync_failed else len(all_insert_tasks)

    # ================= AtCoder =================

    @staticmethod
    async def _get_atcoder_titles(session: aiohttp.ClientSession) -> dict:
        global _ATCODER_TITLES
        if _ATCODER_TITLES is not None:
            return _ATCODER_TITLES
        async with _ATCODER_TITLES_LOCK:
            if _ATCODER_TITLES is not None:
                return _ATCODER_TITLES
            try:
                async with session.get(
                    "https://kenkoooo.com/atcoder/resources/problems.json", timeout=60
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                _ATCODER_TITLES = {
                    p["id"]: (p.get("title") or p.get("name") or p["id"]) for p in data
                }
            except Exception as e:
                LOG.warning(f"获取 AtCoder 题名列表失败: {e}")
                _ATCODER_TITLES = {}
        return _ATCODER_TITLES

    @staticmethod
    def _atcoder_display_difficulty(raw_difficulty):
        """转换为 AtCoder Problems 前端使用的显示难度。"""
        if isinstance(raw_difficulty, bool) or not isinstance(raw_difficulty, (int, float)):
            return ""
        value = float(raw_difficulty)
        if not math.isfinite(value):
            return ""
        if value < 400:
            value = 400 / math.exp(1.0 - value / 400.0)
        return str(max(0, math.floor(value + 0.5)))

    @staticmethod
    async def _get_atcoder_difficulties(session: aiohttp.ClientSession) -> dict:
        global _ATCODER_DIFFICULTIES
        if _ATCODER_DIFFICULTIES is not None:
            return _ATCODER_DIFFICULTIES
        async with _ATCODER_DIFFICULTIES_LOCK:
            if _ATCODER_DIFFICULTIES is not None:
                return _ATCODER_DIFFICULTIES
            try:
                async with session.get(
                    "https://kenkoooo.com/atcoder/resources/problem-models.json", timeout=60
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                if not isinstance(data, dict) or not data:
                    raise ValueError("AtCoder 难度资源为空或格式错误")
                _ATCODER_DIFFICULTIES = {
                    str(problem_id): Crawler._atcoder_display_difficulty(model.get("difficulty"))
                    for problem_id, model in data.items()
                    if isinstance(model, dict) and model.get("difficulty") is not None
                }
            except Exception as e:
                LOG.warning(f"获取 AtCoder 难度列表失败: {e}")
                # 保持 None，下一轮同步可重试，不把一次故障永久缓存为空。
                _ATCODER_DIFFICULTIES = None
        return _ATCODER_DIFFICULTIES

    @staticmethod
    async def fetch_atcoder_submissions(
        session: aiohttp.ClientSession,
        user_row,
        start_timestamp: int,
        db: aiosqlite.Connection,
        config: dict,
    ) -> int:
        """通过 kenkoooo (AtCoderProblems) API 获取 AC 记录，无需认证。"""
        handle = (user_row["atcoder_handle"] or "").strip()
        qq_id = user_row["qq_id"]
        if not handle:
            return 0

        url = (
            "https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions"
            f"?user={urllib.parse.quote(handle)}&from_second={start_timestamp}"
        )
        try:
            async with session.get(url, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
            if not isinstance(data, list):
                LOG.error(f"AtCoder API 返回异常 (用户: {handle})")
                return -1

            titles, difficulties = await asyncio.gather(
                Crawler._get_atcoder_titles(session),
                Crawler._get_atcoder_difficulties(session),
            )
            difficulties = difficulties or {}
            if difficulties:
                await db.executemany(
                    "UPDATE submissions SET problem_rating=? WHERE platform='atcoder' AND problem_id=? AND (problem_rating IS NULL OR problem_rating='')",
                    [(rating, pid) for pid, rating in difficulties.items() if rating],
                )
            insert_tasks = []
            rating_updates = []
            processed = set()
            existing_ids = await Crawler._get_existing_problem_ids(db, qq_id, "atcoder")
            for sub in data:
                if not isinstance(sub, dict) or sub.get("result") != "AC":
                    continue
                pid = sub.get("problem_id")
                contest_id = sub.get("contest_id")
                if not pid:
                    continue
                if pid in processed:
                    continue
                processed.add(pid)
                rating = difficulties.get(pid, "")
                if rating:
                    rating_updates.append((rating, qq_id, pid))
                if pid in existing_ids:
                    continue
                problem_url = (
                    f"https://atcoder.jp/contests/{contest_id}/tasks/{pid}" if contest_id else "https://atcoder.jp"
                )
                insert_tasks.append(
                    (
                        qq_id,
                        "atcoder",
                        pid,
                        titles.get(pid, pid),
                        rating,
                        problem_url,
                        sub.get("epoch_second", 0),
                    )
                )

            if insert_tasks:
                await db.executemany(
                    "INSERT OR IGNORE INTO submissions (user_qq_id, platform, problem_id, problem_name, problem_rating, problem_url, submit_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    insert_tasks,
                )
            if rating_updates:
                await db.executemany(
                    "UPDATE submissions SET problem_rating=? WHERE user_qq_id=? AND platform='atcoder' AND problem_id=? AND (problem_rating IS NULL OR problem_rating='')",
                    rating_updates,
                )
            if insert_tasks or rating_updates:
                await db.commit()
            return len(insert_tasks)
        except Exception as e:
            LOG.error(f"处理 AtCoder 用户 {handle} 时出错: {e}")
            return -1

    @staticmethod
    async def fetch_recent_ac_submissions(session, user_row, platform: str, since_timestamp: int, limit: int, config: dict):
        """获取指定平台最近的不同 AC 题目，不写入数据库；失败返回 None。"""
        fetchers = {
            "codeforces": Crawler._fetch_recent_cf_ac,
            "luogu": Crawler._fetch_recent_luogu_ac,
            "nowcoder": Crawler._fetch_recent_nowcoder_ac,
            "atcoder": Crawler._fetch_recent_atcoder_ac,
        }
        fetcher = fetchers.get(platform)
        if fetcher is None:
            return []
        return await fetcher(session, user_row, since_timestamp, limit, config)

    @staticmethod
    async def _fetch_recent_cf_ac(session, user_row, since_timestamp, limit, config):
        handle = (user_row["cf_handle"] or "").strip()
        if not handle:
            return []
        try:
            submissions = await cf_request(session, "user.status", {"handle": handle, "from": 1, "count": 100}, config)
            result, seen = [], set()
            for sub in submissions:
                if sub.get("verdict") != "OK" or not isinstance(sub.get("problem"), dict):
                    continue
                prob = sub["problem"]
                submitted_at = int(sub.get("creationTimeSeconds", 0) or 0)
                if submitted_at < since_timestamp:
                    break
                contest_id, problem_index = prob.get("contestId"), prob.get("index")
                if not contest_id or not problem_index:
                    continue
                problem_id = f"cf_{contest_id}{problem_index}"
                if problem_id in seen:
                    continue
                seen.add(problem_id)
                result.append({
                    "platform": "codeforces",
                    "problem_id": problem_id,
                    "problem_name": prob.get("name") or problem_id,
                    "problem_rating": str(prob.get("rating", -1)),
                    "problem_url": f"https://codeforces.com/{'gym' if contest_id >= 100000 else 'problemset/problem'}/{contest_id}/problem/{problem_index}" if contest_id >= 100000 else f"https://codeforces.com/problemset/problem/{contest_id}/{problem_index}",
                    "submit_time": submitted_at,
                })
                if len(result) >= limit:
                    break
            return result
        except Exception:
            LOG.exception("challenge_done 查询 CF 最近 AC 失败: %s", handle)
            return None

    @staticmethod
    async def _fetch_recent_luogu_ac(session, user_row, since_timestamp, limit, config):
        uid = (user_row["luogu_id"] or "").strip()
        cookie, csrf = config.get("luogu_cookie"), config.get("luogu_csrf_token")
        if not uid:
            return []
        if not cookie or not csrf:
            LOG.warning("challenge_done 查询洛谷失败：Cookie 或 CSRF-Token 未配置")
            return None
        headers = {"User-Agent": "Mozilla/5.0", "Cookie": cookie, "x-csrf-token": csrf}
        result, seen = [], set()
        try:
            for page in range(1, 4):
                url = f"https://www.luogu.com.cn/record/list?user={urllib.parse.quote(uid)}&page={page}&status=12&_contentOnly=1"
                data = await _fetch_luogu_json(session, url, headers, 15)
                records = data.get("currentData", {}).get("records", {}).get("result", [])
                if not records:
                    break
                stop = False
                for record in records:
                    submitted_at = int(record.get("submitTime", 0) or 0)
                    if submitted_at < since_timestamp:
                        stop = True
                        break
                    problem = record.get("problem") or {}
                    problem_id = str(problem.get("pid") or "")
                    if not problem_id or problem_id in seen:
                        continue
                    seen.add(problem_id)
                    result.append({
                        "platform": "luogu",
                        "problem_id": problem_id,
                        "problem_name": problem.get("title") or problem_id,
                        "problem_rating": luogu_difficulty_map.get(problem.get("difficulty", 0), "未知"),
                        "problem_url": f"https://www.luogu.com.cn/problem/{problem_id}",
                        "submit_time": submitted_at,
                    })
                    if len(result) >= limit:
                        return result
                if stop:
                    break
                await asyncio.sleep(0.2)
            return result
        except Exception:
            LOG.exception("challenge_done 查询洛谷最近 AC 失败: %s", uid)
            return None

    @staticmethod
    async def _fetch_recent_nowcoder_ac(session, user_row, since_timestamp, limit, config):
        uid = (user_row["nowcoder_id"] or "").strip()
        if not uid:
            return []
        result, seen = [], set()
        try:
            for page in range(1, 3):
                url = f"https://ac.nowcoder.com/acm/contest/profile/{urllib.parse.quote(uid)}/practice-coding?pageSize=200&statusTypeFilter=5&languageCategoryFilter=-1&orderType=DESC&page={page}"
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15) as response:
                    if response.status == 404:
                        break
                    response.raise_for_status()
                    rows = Crawler._parse_nowcoder_html(await response.text())
                if not rows:
                    break
                stop = False
                for _, problem_id, title, submitted_at in rows:
                    if submitted_at is None:
                        continue
                    if submitted_at < since_timestamp:
                        stop = True
                        break
                    if problem_id in seen:
                        continue
                    seen.add(problem_id)
                    result.append({
                        "platform": "nowcoder",
                        "problem_id": problem_id,
                        "problem_name": title or f"P{problem_id}",
                        "problem_rating": "",
                        "problem_url": f"https://ac.nowcoder.com/acm/problem/{problem_id}",
                        "submit_time": submitted_at,
                    })
                    if len(result) >= limit:
                        return result
                if stop:
                    break
                await asyncio.sleep(0.2)
            return result
        except Exception:
            LOG.exception("challenge_done 查询牛客最近 AC 失败: %s", uid)
            return None

    @staticmethod
    async def _fetch_recent_atcoder_ac(session, user_row, since_timestamp, limit, config):
        handle = (user_row["atcoder_handle"] or "").strip()
        if not handle:
            return []
        url = "https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?" + urllib.parse.urlencode({"user": handle, "from_second": since_timestamp})
        try:
            async with session.get(url, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
            if not isinstance(data, list):
                return None
            difficulties = await Crawler._get_atcoder_difficulties(session)
            result, seen = [], set()
            for sub in sorted((item for item in data if isinstance(item, dict)), key=lambda item: item.get("epoch_second", 0), reverse=True):
                if sub.get("result") != "AC":
                    continue
                submitted_at = int(sub.get("epoch_second", 0) or 0)
                if submitted_at < since_timestamp:
                    continue
                problem_id = str(sub.get("problem_id") or "")
                if not problem_id or problem_id in seen:
                    continue
                seen.add(problem_id)
                contest_id = sub.get("contest_id")
                result.append({
                    "platform": "atcoder",
                    "problem_id": problem_id,
                    "problem_name": problem_id,
                    "problem_rating": difficulties.get(problem_id, ""),
                    "problem_url": f"https://atcoder.jp/contests/{contest_id}/tasks/{problem_id}" if contest_id else "https://atcoder.jp",
                    "submit_time": submitted_at,
                })
                if len(result) >= limit:
                    break
            return result
        except Exception:
            LOG.exception("challenge_done 查询 AtCoder 最近 AC 失败: %s", handle)
            return None
