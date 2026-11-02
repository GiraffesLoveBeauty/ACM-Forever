"""Disposable localhost fixture: never loads production data, secrets or sync jobs."""
import argparse
import asyncio
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


async def run(port):
    with tempfile.TemporaryDirectory(prefix="acm-browser-tests-") as temporary:
        # Ignore inherited production configuration, including custom upload directories.
        for name in list(os.environ):
            if name.startswith("ACM_"):
                del os.environ[name]
        database = Path(temporary) / "fixture.db"
        os.environ.update({
            "ACM_DATABASE_PATH": str(database),
            "ACM_WEBUI_SECRET_KEY": secrets.token_hex(32),
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "",
            "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
        })
        from feat.api.acm_api.auth_service import hash_password
        from feat.api.acm_api.database import connect_db
        from feat.api.acm_api.cf_practice_jobs import PracticeJobs
        from feat.api.service_runtime import SyncEngine
        from feat.api.app import create_app
        from hypercorn.asyncio import serve
        from hypercorn.config import Config

        db = await connect_db(database)
        try:
            now = int(time.time())
            encoded = hash_password("Browser-fixture-only!2026")
            for qq, role in [("10000001", "member"), ("10000002", "member"), ("10000003", "admin")]:
                await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, "浏览器测试" + role))
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) "
                    "VALUES(?,?,?,0,1,?,?)", (qq, encoded, role, now, now),
                )
            for number in range(1, 31):
                await db.execute(
                    "INSERT INTO forum_posts(id,category_id,author_qq_id,title,body,status,created_at,updated_at,reviewed_at) "
                    "VALUES(?,2,'10000001',?,?,'published',?,?,?)",
                    (number, f"合成算法讨论 {number:02}", "## 思路\n\n仅用于自动化测试的内容。", now - number, now, now),
                )
            await db.commit()
        finally:
            await db.close()
        SyncEngine.start = AsyncMock()
        SyncEngine.close = AsyncMock()
        PracticeJobs.start = AsyncMock()
        PracticeJobs.close = AsyncMock()
        config = Config()
        config.bind = [f"127.0.0.1:{port}"]
        config.accesslog = None
        await serve(create_app(), config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    asyncio.run(run(args.port))
