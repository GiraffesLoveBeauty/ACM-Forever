"""洛谷公开页面请求：共享限速、访问限制冷却，以及可追踪的失败原因。"""

import asyncio
import json
import math
import time
import weakref
from http import HTTPStatus
from urllib.parse import urljoin, urlsplit

import aiohttp

from .problem_content import TreeParser

ORIGIN = "https://www.luogu.com.cn"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
_GATES = weakref.WeakKeyDictionary()


class LuoguUnavailable(RuntimeError):
    def __init__(self, message, *, status=None, retry_after=0, code=None, cause_http_status=None):
        super().__init__(message)
        # status 只代表本次实际收到的 HTTP 响应；冷却跳过不能冒充又收到了 403。
        self.status = status
        self.retry_after = retry_after
        self.code = code or (f"luogu_http_{status}" if status else "luogu_cooldown")
        self.cause_http_status = cause_http_status
        self.deferred = self.code == "luogu_cooldown"
        self.attention_required = False


class LuoguRequestError(aiohttp.ClientError):
    """保留网络错误类型，让题库采集沿用原来的缓存回退和逐题失败处理。"""

    def __init__(self, message, *, status=None, code="luogu_network_error"):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = 0
        self.cause_http_status = None
        self.deferred = False
        self.attention_required = False


class LuoguResponseError(ValueError):
    """已收到响应，但公开页面内容不完整或无法解析。"""

    def __init__(self, message, *, status=200):
        super().__init__(message)
        self.status = status
        self.message = str(message)[:500]
        self.code = "luogu_invalid_snapshot"
        self.retry_after = 0
        self.cause_http_status = None
        self.deferred = False
        self.attention_required = False


def request_failure(error, *, status=None, timeout=None):
    """统一错误分类，不把 Cookie、完整响应正文或带查询参数的 URL 写入日志。"""
    if isinstance(error, (LuoguUnavailable, LuoguRequestError, LuoguResponseError)):
        return error
    status = status if status is not None else getattr(error, "status", None) or None
    if isinstance(error, asyncio.TimeoutError):
        code, reason = "luogu_timeout", "请求或响应读取超时"
        if timeout is not None:
            reason += f"（单次请求上限 {timeout} 秒）"
    elif isinstance(error, aiohttp.ClientSSLError):
        code, reason = "luogu_network_error", "HTTPS 连接或证书校验失败"
    elif isinstance(error, aiohttp.ClientConnectorError):
        cause = error.os_error
        detail = getattr(cause, "strerror", None) or type(cause).__name__
        code, reason = "luogu_network_error", f"无法建立网络连接：{detail}（errno={cause.errno}）"
    elif isinstance(error, aiohttp.ClientPayloadError):
        code, reason = "luogu_network_error", "响应内容传输中断或不完整"
    elif isinstance(error, aiohttp.ClientResponseError):
        code = f"luogu_http_{status}" if status else "luogu_network_error"
        reason = "HTTP 响应处理失败"
    elif isinstance(error, aiohttp.ServerDisconnectedError):
        code, reason = "luogu_network_error", "服务器在响应完成前断开连接"
    elif isinstance(error, aiohttp.ClientError):
        code, reason = "luogu_network_error", f"网络请求失败（{type(error).__name__}）"
    elif isinstance(error, ValueError):
        code, reason = "luogu_invalid_snapshot", str(error)
    else:
        raise TypeError("不支持的洛谷请求异常") from error
    received = f"HTTP {status}" if status is not None else "未收到 HTTP 响应"
    return LuoguRequestError(f"洛谷同步失败：{reason}（{received}）", status=status, code=code)


def _gate():
    loop = asyncio.get_running_loop()
    if loop not in _GATES:
        _GATES[loop] = {"lock": asyncio.Lock(), "next": 0.0, "cooldown": 0.0,
                        "cause_http_status": None, "failures": 0, "updated_at": 0}
    return _GATES[loop]


def cooldown_error():
    """只观察门禁，不发请求、不改变失败次数。"""
    gate = _gate()
    remaining = math.ceil(gate["cooldown"] - time.monotonic())
    if remaining <= 0:
        return None
    cause = gate.get("cause_http_status")
    previous = f"，上次收到 HTTP {cause}" if cause is not None else ""
    error = LuoguUnavailable(f"洛谷请求处于冷却期，本次未发送请求{previous}",
                             retry_after=remaining, code="luogu_cooldown", cause_http_status=cause)
    error.attention_required = gate.get("failures", 0) >= 3
    return error


def recovery_pending():
    # 同一事件循环共享门禁；调度器恢复时只派发一个成员，实际请求仍逐个串行。
    return bool(_gate().get("failures", 0))


def _open_gate(error, base_delay):
    gate = _gate()
    gate["failures"] = gate.get("failures", 0) + 1
    delay = max(error.retry_after, min(3600, base_delay * 2 ** min(6, gate["failures"] - 1)))
    gate.update(cooldown=time.monotonic() + delay, cause_http_status=error.status, updated_at=time.time_ns())
    error.retry_after = delay
    error.attention_required = gate["failures"] >= 3
    if gate["failures"] > 1:
        error.args = (f"{error}；已连续 {gate['failures']} 轮实际请求失败，至少等待 {delay} 秒",)
    return error


def response_recovered():
    gate = _gate()
    gate.update(cooldown=0.0, cause_http_status=None, failures=0, updated_at=time.time_ns())


def response_failed(error):
    """HTTP 200 的访问验证页或坏快照仍应等待，不能放行后续成员。"""
    return _open_gate(error, 300)


async def load_request_state(db):
    """复用 settings 保存全站门禁；重启或另一个任务不能绕过已有等待时间。"""
    async with db.execute("SELECT value FROM settings WHERE key='luogu_request_gate'") as cursor:
        row = await cursor.fetchone()
    if not row:
        return
    try:
        data = json.loads(row[0])
        updated = int(data["updated_at"])
        until = float(data["blocked_until"])
        failures = int(data["failures"])
        cause = data.get("cause_http_status")
        if not math.isfinite(until) or not 0 <= failures <= 1000000 or (cause is not None and type(cause) is not int):
            return
    except (TypeError, ValueError, KeyError):
        return
    gate = _gate()
    async with gate["lock"]:
        if updated > gate.get("updated_at", 0):
            gate.update(cooldown=time.monotonic() + max(0, until - time.time()),
                        failures=failures, cause_http_status=cause, updated_at=updated)


async def save_request_state(db):
    gate = _gate()
    if not gate.get("updated_at"):
        return
    data = {"blocked_until": time.time() + max(0, gate["cooldown"] - time.monotonic()),
            "failures": gate.get("failures", 0), "cause_http_status": gate.get("cause_http_status"),
            "updated_at": gate["updated_at"]}
    # 后完成的旧请求不能覆盖更新的恢复/冷却状态。这里只存门禁信息，不存 Cookie。
    await db.execute("""INSERT INTO settings(key,value) VALUES('luogu_request_gate',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        WHERE CASE WHEN json_valid(settings.value)
          THEN COALESCE(json_extract(settings.value,'$.updated_at'),0) ELSE 0 END < ?""",
        (json.dumps(data, separators=(",", ":")), data["updated_at"]))
    await db.commit()


async def luogu_get(session, url, *, interval=2.0, headers=None, timeout=30, recover_on_response=False):
    """匿名访问固定原站；不跟随登录/验证跳转，不重试 403/429。

    HTTP 200 只证明收到了响应，不能证明它是可用的洛谷公开数据。
    调用方完成页面或 JSON 结构校验后，才可以显式传入
    ``recover_on_response=True`` 清除共享冷却；默认保持门禁状态，避免
    验证码页、错误页或残缺响应提前放行后续账号。
    """
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "www.luogu.com.cn" or parsed.fragment:
        raise ValueError("洛谷采集仅支持固定 HTTPS 原站")
    interval = float(interval)
    if not math.isfinite(interval) or interval < 1.2:
        raise ValueError("洛谷请求间隔不得小于 1.2 秒")
    gate = _gate()
    async with gate["lock"]:
        # 公开页面不需要登录。首次匿名访问可能设置会话 Cookie 并跳回同一地址，
        # 只允许这种初始化重试一次；它仍与普通请求一样遵守共享请求间隔。
        for attempt in range(2):
            now = time.monotonic()
            waiting = cooldown_error()
            if waiting:
                raise waiting
            await asyncio.sleep(max(0, gate["next"] - now))
            status = None
            try:
                async with session.get(url, headers=headers, timeout=timeout, allow_redirects=False) as response:
                    status = response.status
                    if status in (403, 429):
                        delay = 300 if status == 403 else 60
                        retry = response.headers.get("Retry-After", "")
                        if retry.isdigit():
                            delay = max(delay, min(int(retry), 86400))
                        reason = "服务器拒绝本次访问" if status == 403 else "请求频率受限"
                        error = LuoguUnavailable(f"洛谷返回 HTTP {status}：{reason}，停止采集并冷却至少 {delay} 秒",
                                                 status=status, retry_after=delay)
                        raise _open_gate(error, 300 if status == 403 else 60)
                    if status == 404:
                        raise LuoguUnavailable("洛谷返回 HTTP 404：题目或公开资源不存在", status=status)
                    if 300 <= status < 400:
                        location = response.headers.get("Location", "")
                        target = urljoin(url, location)
                        if (attempt == 0 and status in (302, 303, 307)
                                and location and target == url and getattr(response, "cookies", None)):
                            continue
                        if not location:
                            reason = "跳转响应缺少 Location 地址"
                        elif target == url:
                            reason = ("匿名会话初始化后仍重复跳转到同一公开页面" if attempt
                                      else "跳转到同一公开页面，但未收到用于初始化的匿名会话 Cookie")
                        else:
                            redirect = urlsplit(target)
                            if redirect.scheme != "https" or redirect.netloc != parsed.netloc:
                                reason = "收到非原站 HTTPS 地址的跳转，未继续访问"
                            else:
                                # 只展示路径，去掉可能带凭据的查询参数；不凭 302 推断必须登录。
                                reason = f"跳转到其他路径 {redirect.path[:120]}，未获取到预期公开页面"
                        error = LuoguUnavailable(f"洛谷返回 HTTP {status}：{reason}，停止本次采集",
                                                 status=status, retry_after=300)
                        raise _open_gate(error, 300)
                    if status != 200:
                        try:
                            reason = HTTPStatus(status).phrase
                        except ValueError:
                            reason = "非预期的 HTTP 状态"
                        raise LuoguRequestError(f"洛谷返回 HTTP {status}：{reason}，未获取到正常公开页面",
                                                status=status, code=f"luogu_http_{status}")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise LuoguResponseError("洛谷响应超过 12 MiB 大小限制", status=status)
                        chunks.append(chunk)
                    if recover_on_response:
                        response_recovered()
                    return b"".join(chunks)
            except LuoguResponseError as error:
                raise response_failed(error) from None
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                # 读取途中失败时保留已收到的状态；网络/5xx 故障也需要等待，避免逐成员重试。
                failure = request_failure(error, status=status, timeout=timeout)
                if status is None or status >= 500 or failure.code in {"luogu_timeout", "luogu_network_error"}:
                    _open_gate(failure, 60)
                if failure is error:
                    raise
                raise failure from error
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
        raise ValueError("响应缺少唯一的 lentille-context 公开数据，可能为错误页、访问验证页或页面结构变化")
    try:
        context = json.loads("".join(child for child in scripts[0].children if isinstance(child, str)))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("洛谷页面公开数据不是有效 JSON") from error
    if not isinstance(context, dict) or not isinstance(context.get("data"), dict):
        raise ValueError("洛谷页面公开数据结构异常")
    if template and (context.get("template") != template or context.get("status") != 200):
        raise ValueError("洛谷页面类型或状态异常，保留已有数据")
    return context
