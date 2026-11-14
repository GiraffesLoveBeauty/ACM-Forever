"""Bounded, paced Luogu HTTP requests shared by catalog and legacy callers."""

import asyncio
import json
import math
import time
import weakref
from urllib.parse import urlsplit

from .problem_content import TreeParser

ORIGIN = "https://www.luogu.com.cn"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
_GATES = weakref.WeakKeyDictionary()


class LuoguUnavailable(RuntimeError):
    def __init__(self, message, *, status=None, retry_after=0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _gate():
    loop = asyncio.get_running_loop()
    if loop not in _GATES:
        _GATES[loop] = {"lock": asyncio.Lock(), "next": 0.0, "cooldown": 0.0}
    return _GATES[loop]


async def luogu_get(session, url, *, interval=2.0, headers=None, timeout=30):
    """Never follow a login/challenge redirect or retry an access restriction."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "www.luogu.com.cn" or parsed.fragment:
        raise ValueError("洛谷采集仅支持固定 HTTPS 原站")
    interval = float(interval)
    if not math.isfinite(interval) or interval < 1.2:
        raise ValueError("洛谷请求间隔不得小于 1.2 秒")
    gate = _gate()
    async with gate["lock"]:
        now = time.monotonic()
        if now < gate["cooldown"]:
            raise LuoguUnavailable("洛谷请求处于冷却期，请稍后重试", retry_after=math.ceil(gate["cooldown"] - now))
        await asyncio.sleep(max(0, gate["next"] - now))
        try:
            async with session.get(url, headers=headers, timeout=timeout, allow_redirects=False) as response:
                if response.status in (403, 429):
                    delay = 300 if response.status == 403 else 60
                    retry = response.headers.get("Retry-After", "")
                    if retry.isdigit():
                        delay = max(delay, min(int(retry), 86400))
                    gate["cooldown"] = time.monotonic() + delay
                    raise LuoguUnavailable(f"洛谷返回 HTTP {response.status}，本次采集已停止", status=response.status, retry_after=delay)
                if response.status == 404:
                    raise LuoguUnavailable("洛谷题目或公开资源不存在（HTTP 404）", status=404)
                if 300 <= response.status < 400:
                    gate["cooldown"] = time.monotonic() + 300
                    raise LuoguUnavailable("洛谷返回跳转，可能要求登录或验证，本次采集已停止", status=response.status, retry_after=300)
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ValueError("洛谷响应超过大小限制")
                    chunks.append(chunk)
                return b"".join(chunks)
        finally:
            gate["next"] = time.monotonic() + interval


def page_context(raw, *, template=None):
    """Read the public page JSON; attribute order and whitespace are irrelevant."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("洛谷页面格式或大小异常")
    parser = TreeParser()
    parser.feed(raw)
    scripts = [node for node in parser.root.walk() if node.tag == "script" and node.attrs.get("id") == "lentille-context"
               and node.attrs.get("type", "").lower() == "application/json"]
    if len(scripts) != 1:
        raise ValueError("洛谷页面缺少唯一的公开数据，可能为登录或验证页面")
    try:
        context = json.loads("".join(child for child in scripts[0].children if isinstance(child, str)))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("洛谷页面公开数据不是有效 JSON") from error
    if not isinstance(context, dict) or not isinstance(context.get("data"), dict):
        raise ValueError("洛谷页面公开数据结构异常")
    if template and (context.get("template") != template or context.get("status") != 200):
        raise ValueError("洛谷页面类型或状态异常，保留已有数据")
    return context
