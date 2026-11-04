"""Small, structured operational events; never read request bodies or credentials."""
import json
import logging
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone

from quart import g, got_request_exception, request

from .auth_service import resolve_client_ip
from .log_text import clean

LOGGER = logging.getLogger("acm.events")
FIELDS = {"request_id", "method", "route", "status", "duration_ms", "client_ip",
          "actor", "role", "error_type", "hint", "task_id", "task_kind"}


class EventFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(record.acm_event, ensure_ascii=False, separators=(",", ":"))


def configure():
    if not any(isinstance(h.formatter, EventFormatter) for h in LOGGER.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(EventFormatter())
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def emit(event, message, level="info", **fields):
    payload = {"acm_event": 1, "time": datetime.now(timezone.utc).isoformat(),
               "level": level, "event": clean(event), "message": clean(message)}
    for key, value in fields.items():
        if key in FIELDS and value is not None:
            payload[key] = value if type(value) in {int, float} else clean(value)
    LOGGER.log({"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}[level],
               message, extra={"acm_event": payload})


def remember_identity(identity, name=None):
    """Called only after existing authentication checks; no extra DB connection."""
    if identity:
        g.log_identity = dict(identity)
        if name:
            g.log_actor_name = clean(name, 80)
    return identity


def actor_fields():
    identity = getattr(g, "log_identity", None)
    if not identity:
        return {"actor": "未验证身份的访问者"}
    if identity.get("role") == "service":
        return {"actor": "已认证的 Bot 服务", "role": "service"}
    if identity.get("legacy"):
        actor = "旧版管理员"
    else:
        actor = "QQ " + clean(identity.get("qq_id", "未知账号"), 16)
        name = getattr(g, "log_actor_name", "")
        if name:
            actor = name + "（" + actor + "）"
    return {"actor": actor, "role": identity.get("role")}


def action_name(route, method):
    exact = {
        "/health": "检查网站健康状态", "/internal/v1/health": "检查 Bot API 状态",
        "/api/auth/me": "检查登录状态", "/api/auth/change-password": "修改密码",
        "/api/forum/posts": "读取帖子列表" if method in {"GET", "HEAD"} else "提交帖子审核",
        "/api/forum/categories": "读取帖子分类", "/api/wiki/navigation": "读取 Wiki 目录",
        "/api/me/notifications/count": "检查未读通知数量",
        "/internal/v1/sync/accounts": "提交全员同步任务",
        "/api/auth/logout": "退出登录",
        "/index.html": "打开网站首页", "/login.html": "打开登录页面",
        "/admin.html": "打开管理中心", "/compose.html": "打开写帖页面",
        "/notifications.html": "打开消息中心",
    }
    if route in exact:
        return exact[route]
    if route.startswith("/assets/"):
        return "加载页面资源"
    if route.startswith("/uploads/") or "/forum/images/" in route:
        return "读取图片"
    if "/comments" in route:
        return "读取评论" if method in {"GET", "HEAD"} else "提交评论"
    if "/forum/moderation/" in route and method == "POST":
        return "处理帖子审核"
    if "/forum/drafts" in route:
        return "提交帖子审核" if route.endswith("/submit") else "处理帖子草稿"
    if "/forum/posts/" in route and method == "DELETE":
        return "删除帖子"
    if "/wiki/" in route:
        return "读取 Wiki 内容" if method in {"GET", "HEAD"} else "修改 Wiki 内容"
    if route.startswith("/internal/"):
        return "调用 Bot 接口"
    if route.startswith("/api/"):
        return "读取网站数据" if method in {"GET", "HEAD"} else "提交网站操作"
    return "访问页面"


def error_summary(error):
    if isinstance(error, sqlite3.OperationalError) and any(s in str(error).lower() for s in ["locked", "busy"]):
        return "数据库正被其他写入任务占用", "检查同步任务和数据库事务，不要删除数据库或 WAL 文件"
    if isinstance(error, sqlite3.Error):
        return "数据库操作失败", "查看原始错误堆栈，检查数据库状态"
    return "程序处理请求时出现异常", "按请求编号和时间查找原始错误堆栈"


def install(app, public_pages=()):
    configure()

    @app.before_request
    async def begin_request_log():
        g.log_started = time.monotonic()
        g.log_request_id = uuid.uuid4().hex[:16]

    async def on_exception(sender, exception, **extra):
        g.log_failure = error_summary(exception)
        g.log_error_type = type(exception).__name__

    app.extensions["acm_event_exception_receiver"] = on_exception
    got_request_exception.connect(on_exception, sender=app)

    @app.after_request
    async def finish_request_log(response):
        status = response.status_code
        level = "error" if status >= 500 else "warning" if status >= 400 else "info"
        # A matched route template avoids leaking IDs/one-time tokens in URLs.
        # Never record query strings or arbitrary unmatched paths.
        route = request.url_rule.rule if request.url_rule else "[未匹配路由]"
        if route == "/<path:filename>":
            if request.path.startswith("/assets/"):
                route = "/assets/<资源文件>"
            elif request.path.removeprefix("/") in public_pages:
                route = request.path
            else:
                route = "[未匹配页面路径]"
        event = "http.request"
        action = action_name(route, request.method)
        actor = actor_fields()
        if request.path == "/api/auth/login" and request.method == "POST":
            if status == 200:
                event, message = "auth.login.success", actor["actor"] + "成功登录"
            elif status == 429:
                event, message = "auth.login.limited", "登录尝试过于频繁，已暂时限制"
            elif status == 401:
                event, message = "auth.login.failed", "登录失败：账号、密码或账号状态未通过验证"
            elif status >= 500:
                event, message = "auth.login.failed", "登录请求未能完成：" + getattr(g, "log_failure", ("服务器暂时无法完成请求", ""))[0]
            else:
                event, message = "auth.login.failed", "登录请求未能完成"
        elif status >= 500:
            message = action + "失败：" + getattr(g, "log_failure", ("服务器暂时无法完成请求", ""))[0]
        elif status == 401:
            message = action + "被拒绝：需要有效的登录状态或服务凭据"
        elif status == 403:
            message = action + "被拒绝：权限或安全校验未通过"
        elif status == 404:
            message = action + "失败：目标不存在或当前不可见"
        elif status == 429:
            message = action + "被限流：请降低请求频率"
        elif status >= 400:
            message = action + "未完成：请检查参数、数据状态或操作条件"
        elif status == 304:
            message = action + "成功：内容未变化，继续使用浏览器缓存"
        elif 300 <= status < 400:
            message = action + "：已跳转到其他页面"
        elif status == 202:
            message = action + "已受理，后台任务尚未完成"
        else:
            message = action + "成功"
        trusted = app.config.get("PLUGIN_CONFIG", {}).get("webui_trusted_proxies", [])
        if isinstance(trusted, str):
            trusted = trusted.replace("，", ",").split(",")
        fields = {"request_id": getattr(g, "log_request_id", uuid.uuid4().hex[:16]),
                  "method": request.method, "route": route, "status": status,
                  "duration_ms": round((time.monotonic() - getattr(g, "log_started", time.monotonic())) * 1000, 2),
                  "client_ip": resolve_client_ip(request.remote_addr, request.headers.get("X-Forwarded-For", ""), trusted),
                  **actor}
        if status >= 500:
            fields.update(error_type=getattr(g, "log_error_type", None),
                          hint=getattr(g, "log_failure", ("", "查看原始错误堆栈"))[1])
        emit(event, message, level, **fields)
        response.headers["X-Request-ID"] = fields["request_id"]
        return response

    @app.before_serving
    async def started():
        emit("service.ready", "网站服务初始化完成，开始接收请求")

    @app.after_serving
    async def stopped():
        emit("service.stopped", "网站服务已结束本次运行")
