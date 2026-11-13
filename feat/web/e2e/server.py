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
            "ACM_ACCOUNT_CLOSURE_ENABLED": "true",
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
            for qq, role in [("10000001", "member"), ("10000002", "member"), ("10000003", "admin"),
                             ("10000004", "member"), ("10000005", "member"),
                             ("10000006", "member"), ("10000007", "member"),
                             ("10000008", "member"), ("10000009", "member")]:
                await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, "浏览器测试" + role))
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) "
                    "VALUES(?,?,?,0,1,?,?)", (qq, encoded, role, now, now),
                )
            for qq, name, active, has_account in [
                ("10000118", "训练任务成员A", 1, True), ("10000119", "训练任务成员B", 1, True),
                ("10000120", "训练任务停用成员", 0, True), ("10000121", "训练任务未开户成员", 1, False),
            ]:
                await db.execute("INSERT INTO users(qq_id,name,status) VALUES(?,?,'训练任务测试组')", (qq, name))
                if has_account:
                    await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) VALUES(?,?,'member',0,?,?,?)", (qq, encoded, active, now, now))
            await db.execute("UPDATE users SET cf_handle='TrainingFixture',real_name='训练测试姓名甲' WHERE qq_id='10000118'")
            await db.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,binding_key,full_history_at,coverage_through_at,last_status,last_success_at) VALUES('10000118','codeforces','trainingfixture:1',?,?,'success',?)", (now, now, now))
            await db.execute("INSERT INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,verdict,submitted_at,created_at) VALUES('10000118','codeforces','fixture:801','cf_1A','OK',?,?)", (now-3600, now))
            for pid, name in [('cf_1A', '合成训练题一'), ('cf_2A', '合成训练题二')]:
                await db.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) VALUES('codeforces',?,?, '1000',?,'implementation')", (pid, name, 'https://codeforces.com/contest/' + pid[3:-1] + '/problem/A'))
            for number in range(26):
                await db.execute(
                    "INSERT INTO users(qq_id,name,real_name,school,status,cf_handle,atcoder_handle,luogu_id,nowcoder_id,cjlu_username) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (str(21000000 + number), f"资料夹具{number:02}", None if number % 2 else f"合成姓名{number:02}",
                     "测试学校甲" if number % 2 else "测试学校乙", "测试现役" if number % 3 else "测试集训",
                     f"ProfileCF_{number}", f"ProfileAC_{number}", str(81000 + number), str(91000 + number), f"ProfileCampus_{number}"),
                )
            for number in range(1, 31):
                body = "## 思路\n\n仅用于自动化测试的内容。"
                if number == 30:
                    body = (
                        '## 多语言代码\n\n'
                        '```cpp\n#include <iostream>\nint main() { std::cout << "你好 <AC>"; return 0; }\n```\n\n'
                        '```python\ndef solve(n):\n    # 保留缩进\n    return "AC" * n\n```\n\n'
                        '```java\npublic class Main {\n    public static void main(String[] args) { System.out.println(42); }\n}\n```'
                    )
                await db.execute(
                    "INSERT INTO forum_posts(id,category_id,author_qq_id,title,body,status,created_at,updated_at,reviewed_at) "
                    "VALUES(?,2,'10000001',?,?,'published',?,?,?)",
                    (number, f"合成算法讨论 {number:02}", body, now - number, now, now),
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
