"""Chinese, colored journal viewer. Standard library only; --demo works offline."""
import argparse
from datetime import datetime
import json
import os
import re
import shutil
import subprocess
import sys

from .log_text import clean

COLORS = {"info": "\033[32m", "warning": "\033[33m", "error": "\033[31m"}
RANK = {"info": 0, "warning": 1, "error": 2}
ROLES = {"member": "普通成员", "admin": "管理员", "root": "最高管理员", "service": "服务调用"}
LEGEND = """颜色：[INFO] 绿色=正常记录；[WARNING] 黄色=请求受限/操作未完成；[ERROR] 红色=服务器错误。
字段：时间=本机时区；用户=已验证的账号（否则标明未验证）；身份=账号权限；来源=按可信代理规则解析的 IP；
      请求=方法和路由模板；结果=HTTP 状态码；耗时=服务器处理至生成响应的时间，不含完整网络传输；编号=本次请求 ID。
路由中的 <...> 是参数占位符；来源为 127.0.0.1 时只能确认代理连接，不能据此判断真实访客。
一个请求不等于一个人；202=任务已受理，304=使用缓存，3xx=跳转，4xx=请求/权限问题，5xx=服务器问题。
默认收起成功的静态资源、健康检查和通知轮询；--all 显示全部。Ctrl+C 只退出查看，不停止网站。"""


def safe_diagnostic(value):
    text = clean(value, 1200)
    # Best-effort handling for older, unstructured diagnostics.
    text = re.sub(r'(?i)(authorization|cookie|password|csrf[_-]?token|api[_-]?key|secret|token)([\s"\x27:=]+)(?:bearer\s+)?[^\s,;]+',
                  r'\1\2[已隐藏]', text)
    text = re.sub(r'((?:GET|POST|PUT|PATCH|DELETE|HEAD)\s+[^ ?"]+)\?[^\s"]*', r'\1?[查询参数已隐藏]', text)
    text = re.sub(r'(https?://[^\s?"\x27]+)\?[^\s"\x27]*', r'\1?[查询参数已隐藏]', text)
    return text


def journal_event(item):
    message = item.get("MESSAGE", "")
    if not isinstance(message, str):
        return None
    try:
        event = json.loads(message)
    except (ValueError, TypeError):
        event = None
    if (isinstance(event, dict) and event.get("acm_event") == 1
            and isinstance(event.get("level"), str) and event["level"] in RANK
            and isinstance(event.get("message"), str)):
        return event
    priority = str(item.get("PRIORITY", "6"))
    level = "error" if priority in {"0", "1", "2", "3"} else "warning" if priority == "4" else "info"
    access = re.search(r'"(?:GET|POST|HEAD|PUT|PATCH|DELETE|OPTIONS) [^ ]+ [^"]+" (\d{3})\b', message)
    if access:
        status = int(access.group(1))
        level = "error" if status >= 500 else "warning" if status >= 400 else "info"
    elif re.search(r'\b(?:ERROR|CRITICAL|Traceback)\b|\b\w*(?:Error|Exception):', message):
        level = "error"
    elif re.search(r'\bWARNING\b|时出错|请求失败|抓取失败|同步失败|验证失败|未授权|Unauthorized|Forbidden|超时', message):
        level = "warning"
    item_event = {"event": "diagnostic", "level": level,
                  "message": "程序诊断：" + safe_diagnostic(message), "journal_time": item.get("__REALTIME_TIMESTAMP")}
    if not access and "401" in message and "Unauthorized" in message:
        platform = next((p for p in ["洛谷", "Codeforces", "AtCoder", "牛客", "校 OJ"] if p in message), "外部平台")
        item_event.update(message=platform + "同步请求未获授权（HTTP 401）：平台凭据可能失效或访问受限",
                          detail=safe_diagnostic(message))
    return item_event


def visible(event, minimum="info", show_all=False):
    level = event.get("level", "info")
    if RANK.get(level, 0) < RANK[minimum]:
        return False
    if show_all or level != "info" or event.get("event") != "http.request":
        return True
    route = str(event.get("route", ""))
    return not (route.startswith("/assets/") or route in {
        "/health", "/internal/v1/health", "/api/me/notifications/count", "/api/auth/me"})


def time_label(event):
    try:
        if event.get("time"):
            value = datetime.fromisoformat(event["time"])
        else:
            value = datetime.fromtimestamp(int(event["journal_time"]) / 1_000_000).astimezone()
        return value.astimezone().strftime("%m-%d %H:%M:%S %z")
    except (TypeError, ValueError, KeyError, OSError, OverflowError):
        return "时间未知"


def render(event, color=False, explain=False):
    level = event.get("level", "info")
    if level not in RANK:
        level = "info"
    label = "[" + level.upper() + "]"
    if color:
        label = COLORS[level] + label + "\033[0m"
    line = time_label(event) + " " + label + " " + clean(event.get("message", "无事件说明"), 1200)
    details = []
    for field, title in [("actor", "用户"), ("role", "身份"), ("client_ip", "来源")]:
        if event.get(field) is not None:
            value = ROLES.get(str(event[field]), event[field]) if field == "role" else event[field]
            details.append(title + "=" + clean(value))
    if "route" in event:
        details.append("请求=" + clean(event.get("method", "")) + " " + clean(event["route"]))
    for field, title, suffix in [("status", "结果", ""), ("duration_ms", "耗时", "ms"),
                                  ("request_id", "编号", ""), ("task_kind", "任务", ""),
                                  ("task_id", "任务编号", ""), ("error_type", "错误类型", "")]:
        if event.get(field) is not None:
            details.append(title + "=" + clean(event[field]) + suffix)
    if details:
        line += "\n  " + " ｜ ".join(details)
    if event.get("detail"):
        line += "\n  原始信息：" + safe_diagnostic(event["detail"])
    if event.get("hint"):
        line += "\n  排查建议：" + clean(event["hint"])
    if explain and "request_id" in event:
        line += "\n  字段说明：用户/身份说明操作者；来源说明连接地址；请求说明所访问接口；结果说明 HTTP 状态；耗时用于判断慢请求；编号用于关联同一次请求。"
    return line


def demo_events():
    common = {"acm_event": 1, "time": datetime.now().astimezone().isoformat(),
              "actor": "演示成员（QQ 12345678）", "role": "member", "client_ip": "192.0.2.10",
              "method": "POST", "route": "/api/auth/login", "duration_ms": 38.2,
              "request_id": "demo-only-0001"}
    for level, status, event, message in [
        ("info", 200, "auth.login.success", "【演示】演示成员成功登录"),
        ("warning", 401, "auth.login.failed", "【演示】登录失败：账号、密码或账号状态未通过验证"),
        ("warning", 403, "http.request", "【演示】操作被拒绝：权限或安全校验未通过"),
        ("info", 202, "http.request", "【演示】同步任务已受理，后台任务尚未完成"),
        ("error", 500, "http.request", "【演示】健康检查失败：数据库正被其他写入任务占用"),
    ]:
        item = dict(common, level=level, status=status, event=event, message=message)
        if status in {401, 403}:
            item.update(actor="未验证身份的访问者")
            item.pop("role", None)
        if status == 403:
            item.update(method="GET", route="/api/admin/members")
        elif status == 202:
            item.update(route="/internal/v1/sync/accounts", actor="已认证的 Bot 服务", role="service")
        elif status == 500:
            item.update(method="GET", route="/health", actor="健康检查程序", error_type="OperationalError",
                        hint="检查同步任务和数据库事务，不要删除数据库或 WAL 文件")
            item.pop("role", None)
        yield item


def main(argv=None):
    parser = argparse.ArgumentParser(description="用中文和彩色级别查看 ACM-Forever 实时日志（不修改服务或数据库）")
    parser.add_argument("-f", "--follow", action="store_true", help="持续跟踪新日志")
    parser.add_argument("-n", "--lines", type=int, default=50, help="读取最近多少条原始记录，默认 50")
    parser.add_argument("--since", help="只读取此时间之后的记录，例如 '30 minutes ago'")
    parser.add_argument("--level", choices=RANK, default="info", help="最低显示级别")
    parser.add_argument("--all", action="store_true", help="同时显示正常静态资源和轮询请求")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--explain", action="store_true", help="在每条请求后补充字段说明")
    parser.add_argument("--demo", action="store_true", help="显示标明为演示的样例，不连接 journal 或网站")
    args = parser.parse_args(argv)
    if not 0 <= args.lines <= 100000:
        parser.error("--lines 必须在 0 到 100000 之间")
    color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    if color and os.name == "nt":
        os.system("")  # Enable ANSI handling on supported Windows terminals.
    print(LEGEND, flush=True)
    if args.demo:
        for item in demo_events():
            if visible(item, args.level, args.all):
                print(render(item, color, args.explain), flush=True)
        return 0
    if not shutil.which("journalctl"):
        parser.error("此命令需要在 systemd 服务器执行；本地可使用 --demo 查看效果")
    command = ["journalctl", "--unit=acm-forever-webui.service", "--output=json", "--no-pager", "--quiet", "--lines=" + str(args.lines)]
    if args.follow:
        command.append("--follow")
    if args.since:
        command.extend(["--since", args.since])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    try:
        for line in process.stdout:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            event = journal_event(item)
            if event and visible(event, args.level, args.all):
                print(render(event, color, args.explain), flush=True)
        return process.wait()
    except (KeyboardInterrupt, BrokenPipeError):
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
        process.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
