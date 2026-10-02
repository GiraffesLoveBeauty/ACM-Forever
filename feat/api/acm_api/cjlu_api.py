# -*- coding: utf-8 -*-
"""CJLU OJ（中国计量大学 Putong OJ）轻量 API 客户端。"""
import aiohttp

from .constants import LOG

BASE_URL = "https://acm.cjlu.edu.cn"
CJLU_PLATFORM = "cjlu"
CJLU_LABEL = "校OJ"


class CjluClient:
    """通过公开用户接口获取 CJLU 用户已解决题目，无需登录或浏览器。"""

    async def get_user_solved(self, session: aiohttp.ClientSession, username: str):
        url = f"{BASE_URL}/api/users/{username}"
        try:
            async with session.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "ACM-Helper/1.0"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if not isinstance(data, dict) or data.get("success") is not True:
                LOG.warning("CJLU 用户接口返回异常: %s", username)
                return None
            payload = data.get("data") or {}
            solved = payload.get("solved") or []
            heatmap = payload.get("submissionHeatmap") or {}
            return {
                "solved": [str(item) for item in solved],
                "heatmap": heatmap.get("data") or {},
            }
        except Exception as e:
            LOG.warning("请求 CJLU 用户 %s 失败: %s", username, e)
            return None


async def get_client(config: dict):
    """保留旧接口兼容性；客户端本身无状态，不启动浏览器。"""
    return CjluClient()


async def close_client():
    """兼容旧生命周期接口。"""
    return None


async def fetch_cjlu_submissions(session, user_row, start_timestamp: int, db, config: dict) -> int:
    """同步指定用户的 CJLU 已解决题目。公开接口没有逐题时间，记录时间为 0。"""
    username = (user_row["cjlu_username"] or "").strip()
    qq_id = user_row["qq_id"]
    if not username:
        return 0
    try:
        client = CjluClient()
        data = await client.get_user_solved(session, username)
        if data is None:
            return -1
        async with db.execute(
            "SELECT problem_id FROM submissions WHERE user_qq_id=? AND platform=?",
            (qq_id, CJLU_PLATFORM),
        ) as cursor:
            existing_ids = {row["problem_id"] for row in await cursor.fetchall()}
        insert_tasks = []
        seen = set()
        for pid in data["solved"]:
            if pid in existing_ids or pid in seen:
                continue
            seen.add(pid)
            insert_tasks.append(
                (
                    qq_id,
                    CJLU_PLATFORM,
                    pid,
                    pid,
                    "",
                    f"{BASE_URL}/problem/{pid}",
                    0,
                )
            )
        if insert_tasks:
            await db.executemany(
                "INSERT OR IGNORE INTO submissions (user_qq_id, platform, problem_id, problem_name, problem_rating, problem_url, submit_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                insert_tasks,
            )
            await db.commit()
        return len(insert_tasks)
    except Exception:
        LOG.exception("同步 CJLU 用户 %s 数据失败", username)
        return -1
