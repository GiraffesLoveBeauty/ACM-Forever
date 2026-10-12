"""Shared Codeforces request pacing, timeout and retry policy."""
import asyncio
import hashlib
import random
import time
import weakref

import aiohttp


class CFUnavailable(RuntimeError):
    pass


_gates = weakref.WeakKeyDictionary()


async def cf_request(session, method, params=None, config=None):
    loop = asyncio.get_running_loop()
    gate = _gates.setdefault(loop, {"lock": asyncio.Lock(), "next": 0.0})
    config = config or {}
    for attempt in range(3):
        async with gate["lock"]:
            await asyncio.sleep(max(0, gate["next"] - time.monotonic()))
            values = dict(params or {})
            if config.get("cf_api_key") and config.get("cf_api_secret"):
                values.update(apiKey=config["cf_api_key"], time=str(int(time.time())))
                prefix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6))
                query = "&".join(f"{key}={value}" for key, value in sorted(values.items()))
                digest = hashlib.sha512(
                    f"{prefix}/{method}?{query}#{config['cf_api_secret']}".encode()
                ).hexdigest()
                values["apiSig"] = prefix + digest
            try:
                async with session.get(
                    "https://codeforces.com/api/" + method,
                    params=values, timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                if not isinstance(data, dict):
                    raise CFUnavailable("CF 响应格式异常")
                if data.get("status") != "OK":
                    raise CFUnavailable(str(data.get("comment", "CF 返回异常"))[:300])
                return data["result"]
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, CFUnavailable) as exc:
                detail = str(exc)[:300] if isinstance(exc, CFUnavailable) else f"网络或响应错误（{type(exc).__name__}）"
                error = CFUnavailable(f"Codeforces 暂不可用：{detail}")
            finally:
                gate["next"] = time.monotonic() + 2.1
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)
    raise error


def binding_key(user):
    return f"{str(user['cf_handle'] or '').strip().casefold()}:{int(user['cf_binding_version'] or 0)}"


def problem_url(contest_id, index):
    section = "gym" if int(contest_id) >= 100000 else "contest"
    return f"https://codeforces.com/{section}/{int(contest_id)}/problem/{index}"
