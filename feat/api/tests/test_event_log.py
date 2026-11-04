import io
import asyncio
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from quart import Quart

from feat.api.acm_api import event_log, log_viewer
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.backend_api import _LOGIN_ATTEMPTS
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app
from feat.api.service_runtime import WebTaskManager


def events(captured):
    return [record.acm_event for record in captured.records]


class ViewerTests(unittest.TestCase):
    def test_color_levels_filters_and_explanations(self):
        for item in log_viewer.demo_events():
            plain = log_viewer.render(item, explain=True)
            colored = log_viewer.render(item, color=True)
            self.assertNotIn("\033", plain)
            self.assertIn(log_viewer.COLORS[item["level"]], colored)
            self.assertIn("字段说明", plain)
            self.assertIn("耗时=", plain)
        noisy = {"event": "http.request", "level": "info", "route": "/assets/<path:filename>"}
        self.assertFalse(log_viewer.visible(noisy))
        self.assertTrue(log_viewer.visible(noisy, show_all=True))
        self.assertTrue(log_viewer.visible(dict(noisy, level="error")))
        self.assertFalse(log_viewer.visible(dict(noisy, level="warning"), minimum="error"))

    def test_old_diagnostics_and_terminal_injection(self):
        item = log_viewer.journal_event({"MESSAGE": 'ERROR password=secret-value Authorization: Bearer hidden-value\n\033[2J'})
        rendered = log_viewer.render(item)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("hidden-value", rendered)
        self.assertNotIn("\033", rendered)
        self.assertEqual(item["level"], "error")
        legacy = log_viewer.journal_event({"MESSAGE": '[INFO] "GET /health 1.1" 500 265 "-" "curl"'})
        self.assertEqual(legacy["level"], "error")
        for failure in ["修改 Web 账号密码失败", "创建 Web 账号失败", "批量创建 Web 成员账号失败",
                        "更新 Web 账号失败", "重发 Web 临时密码失败", "验证 Web 会话时读取账号失败"]:
            with self.subTest(failure=failure):
                legacy = log_viewer.journal_event({"MESSAGE": failure})
                self.assertEqual(legacy["level"], "error")
        self.assertEqual(log_viewer.journal_event({"MESSAGE": "任务完成，0 个失败"})["level"], "info")
        upstream = log_viewer.journal_event({"MESSAGE": "处理洛谷用户 123 第 1 页时出错: 401, message='Unauthorized', url='https://www.luogu.com.cn/record/list?user=private-query'"})
        self.assertEqual(upstream["level"], "warning")
        self.assertIn("洛谷同步请求未获授权", upstream["message"])
        self.assertNotIn("private-query", log_viewer.render(upstream))
        item = log_viewer.journal_event({"MESSAGE": 'GET /api/auth/login?token=hidden-query 1.1'})
        self.assertNotIn("hidden-query", log_viewer.render(item))
        self.assertIsNone(log_viewer.journal_event({"MESSAGE": [1, 2]}))
        malformed = log_viewer.journal_event({"MESSAGE": '{"acm_event":1,"level":[],"message":"x"}'})
        self.assertEqual(malformed["event"], "diagnostic")
        injected = dict(next(log_viewer.demo_events()), actor="名字\n[ERROR]\033[2J\u202etest")
        rendered = log_viewer.render(injected)
        self.assertNotIn("\033", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertEqual(len(rendered.splitlines()), 2)

    def test_json_formatter_allowlist_and_single_line(self):
        event_log.configure()
        with self.assertLogs("acm.events", level="INFO") as captured:
            event_log.emit("test", "测试\n消息", actor="成员", password="never-log-me", token="also-private")
        encoded = event_log.EventFormatter().format(captured.records[0])
        self.assertNotIn("never-log-me", encoded)
        self.assertNotIn("also-private", encoded)
        self.assertNotIn("\n", encoded)
        self.assertEqual(json.loads(encoded)["message"], "测试 消息")

    def test_demo_needs_no_journal_or_web_dependencies(self):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(log_viewer.main(["--demo", "--level", "error", "--color", "never"]), 0)
        self.assertIn("【演示】", output.getvalue())
        self.assertIn("[ERROR]", output.getvalue())
        self.assertNotIn("[WARNING] 登录", output.getvalue())


class RequestEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Quart(__name__)
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        @self.app.get("/example/<secret_part>")
        async def example(secret_part):
            return {"ok": True}

        @self.app.get("/broken")
        async def broken():
            raise sqlite3.OperationalError("database is locked")

        event_log.install(self.app)

    async def test_request_id_redaction_and_no_database_open(self):
        with self.assertLogs("acm.events", level="INFO") as captured:
            response = await self.app.test_client().get(
                "/example/private-path-token?password=secret-query",
                headers={"Authorization": "Bearer secret-bearer", "X-Request-ID": "untrusted-id"},
            )
        item = events(captured)[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(item["route"], "/example/<secret_part>")
        self.assertEqual(item["request_id"], response.headers["X-Request-ID"])
        self.assertNotEqual(item["request_id"], "untrusted-id")
        encoded = json.dumps(item)
        for value in ["secret-query", "private-path-token", "secret-bearer"]:
            self.assertNotIn(value, encoded)

    async def test_unmatched_path_is_not_copied_to_logs(self):
        with self.assertLogs("acm.events", level="INFO") as captured:
            response = await self.app.test_client().get("/one-time-private-token?token=private-query")
        item = events(captured)[0]
        self.assertEqual(response.status_code, 404)
        self.assertEqual(item["route"], "[未匹配路由]")
        self.assertNotIn("private", json.dumps(item))
        self.assertEqual(item["level"], "warning")

    async def test_frontend_catchall_classifies_resources_without_copying_filenames(self):
        app = Quart("catchall")

        @app.get("/<path:filename>")
        async def frontend(filename):
            return "frontend"

        event_log.install(app, public_pages={"index.html"})
        with self.assertLogs("acm.events", level="INFO") as captured:
            await app.test_client().get("/assets/private-file-name.js?token=hidden")
            await app.test_client().get("/index.html")
        items = events(captured)
        self.assertEqual(items[0]["route"], "/assets/<资源文件>")
        self.assertFalse(log_viewer.visible(items[0]))
        self.assertNotIn("private-file-name", json.dumps(items))
        self.assertEqual(items[1]["route"], "/index.html")
        self.assertIn("网站首页", items[1]["message"])

    async def test_database_lock_has_readable_error_and_request_context(self):
        with self.assertLogs("acm.events", level="INFO") as captured:
            response = await self.app.test_client().get("/broken")
        item = events(captured)[0]
        self.assertEqual(response.status_code, 500)
        self.assertEqual(item["level"], "error")
        self.assertEqual(item["error_type"], "OperationalError")
        self.assertIn("数据库", item["message"])
        self.assertIn("WAL", item["hint"])
        self.assertEqual(item["request_id"], response.headers["X-Request-ID"])


class AuthenticationEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "events.db"
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.path),
                                           "ACM_WEBUI_SECRET_KEY": "private-test-session-key",
                                           "ACM_WEBUI_LEGACY_ADMIN_LOGIN": "false"})
        self.env.start()
        _LOGIN_ATTEMPTS.clear()
        self.app = create_app()

    async def asyncTearDown(self):
        self.env.stop()
        _LOGIN_ATTEMPTS.clear()
        self.temp.cleanup()

    async def test_real_login_success_failure_and_no_credentials_in_event(self):
        async with self.app.test_app():
            db = await connect_db(self.path)
            try:
                now = int(time.time())
                await db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','日志测试员')")
                await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES('12345678',?,'member',0,1,1,?,?)",
                                 (hash_password("Correct-Password-123!"), now, now))
                await db.commit()
            finally:
                await db.close()
            client = self.app.test_client()
            with self.assertLogs("acm.events", level="INFO") as captured:
                failed = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "wrong-password-private"})
                success = await client.post("/api/auth/login?token=query-private", json={"qq_id": "12345678", "password": "Correct-Password-123!"})
                payload = await success.get_json()
                await client.get("/api/me/profile")
                logout = await client.post("/api/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]})
            self.assertEqual((failed.status_code, success.status_code, logout.status_code), (401, 200, 200))
            items = events(captured)
            self.assertEqual(items[0]["event"], "auth.login.failed")
            self.assertEqual(items[0]["actor"], "未验证身份的访问者")
            self.assertEqual(items[1]["event"], "auth.login.success")
            self.assertIn("日志测试员", items[1]["message"])
            self.assertEqual(items[1]["role"], "member")
            encoded = json.dumps(items, ensure_ascii=False)
            for value in ["wrong-password-private", "Correct-Password-123!", "query-private", payload["csrf_token"], "private-test-session-key"]:
                self.assertNotIn(value, encoded)
            self.assertEqual(len(items), 4)


class TaskEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_failure_is_warning_and_raw_result_is_not_logged(self):
        manager = WebTaskManager(type("Engine", (), {"db_path": Path("unused.db")})())
        item = {"id": "example", "kind": "全员平台同步", "status": "running"}

        async def operation():
            item.update(status="completed", result={"private-account": {"codeforces": 0, "luogu": -1}})

        with self.assertLogs("acm.events", level="INFO") as captured:
            await manager._logged_task(operation, item)
        items = events(captured)
        self.assertEqual([i["event"] for i in items], ["task.started", "task.finished"])
        self.assertEqual(items[1]["level"], "warning")
        self.assertNotIn("private-account", json.dumps(items))

    async def test_unexpected_task_error_is_logged_without_swallowing_it(self):
        manager = WebTaskManager(type("Engine", (), {"db_path": Path("unused.db")})())
        item = {"id": "example", "kind": "测试任务", "status": "queued"}

        async def operation():
            raise RuntimeError("private-upstream-error")

        with self.assertLogs("acm.events", level="INFO") as captured:
            with self.assertRaises(RuntimeError):
                await manager._logged_task(operation, item)
        self.assertEqual(events(captured)[-1]["level"], "error")
        self.assertNotIn("private-upstream-error", json.dumps(events(captured)))

    async def test_task_cancellation_is_preserved_and_logged(self):
        manager = WebTaskManager(type("Engine", (), {"db_path": Path("unused.db")})())
        item = {"id": "example", "kind": "测试任务", "status": "queued"}
        ready = asyncio.Event()

        async def operation():
            ready.set()
            await asyncio.Event().wait()

        with self.assertLogs("acm.events", level="INFO") as captured:
            task = asyncio.create_task(manager._logged_task(operation, item))
            await ready.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(events(captured)[-1]["level"], "warning")
