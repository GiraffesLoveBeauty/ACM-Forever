"""Local-only forum with administrator corrections and guarded single-question AI workers."""
import argparse
import asyncio
import ipaddress
import json
import os
import re
from pathlib import Path
import secrets
import sys
import time
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "experiments/tags/ACM_Forever_Chinese_Tags_V0.3"
sys.path[:0] = [str(ROOT), str(MODULE)]
sys.dont_write_bytecode = True
RUNTIME = ROOT / "local_demo/runtime"
LABELS = ROOT / "data/labels"
DEMO_QQ = "10000001"
DEMO_PASSWORD = "Local-Demo-Only!2026"
ADMIN_QQ = "1"
ADMIN_PASSWORD = "Local-Tag-Admin!2026"


def isolate_environment(database):
    for name in list(os.environ):
        if name.startswith(("ACM_", "OPENAI_", "TAG_", "ANTHROPIC_")):
            del os.environ[name]
    os.environ.update(ACM_DATABASE_PATH=str(database),
                      ACM_WEBUI_SECRET_KEY=secrets.token_hex(32),
                      TAG_DATA_ROOT=str(LABELS), PYTHONDONTWRITEBYTECODE="1")


def loopback_only(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
        if host not in (None, "localhost", "127.0.0.1", "::1"):
            raise PermissionError("本地演示禁止外部域名解析")
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple):
            raise PermissionError("本地演示仅允许回环网络")
        try:
            valid = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            valid = False
        if not valid:
            raise PermissionError("本地演示禁止外部网络请求")


class ReadOnlyLabels:
    def __init__(self, root=LABELS, override_file=None):
        from problem_processing.repository import Repository
        self.root = Path(root)
        self.repo = Repository(root)
        self.override_file = Path(override_file) if override_file else self.root.parent / 'local_tag_management/overrides.jsonl'

    def manager(self):
        from tag_management.service import TagManager
        if not self.override_file.exists():
            return self.repo.manager()
        return TagManager(self.repo.current() / 'auto_tags.jsonl', self.override_file)

    def views(self):
        from problem_processing.translation import current_translation
        # Reuse the real effective-tag and translation activation rules.
        problems, automatic = self.repo.snapshot()
        if not problems:
            return []
        effective = self.manager().get_effective_tags_many(list(problems))
        metadata = {p["problem_key"]: p for p in self.repo.metadata_many()}
        attempts = {}
        for path in sorted((self.root / "execution/tasks").glob("*.json")):
            task = json.loads(path.read_text(encoding="utf-8"))
            # Only allowlisted state fields; never expose a raw request/response.
            if task.get("task_type") == "translation":
                attempts.setdefault(task.get("problem_key"), []).append(task.get("state", "unknown"))
        result = []
        for view in effective:
            key = view["problem_key"]
            p, m, a = problems[key], metadata[key], automatic[key]
            parts = key.split(":")
            pid = "cf_" + parts[1] + parts[2] if parts[0] == "codeforces" else parts[-1]
            translation_status = m["translation_status"]
            states = attempts.get(key, [])
            if translation_status == "missing" and any(s in {"blocked", "uncertain", "dispatched"} for s in states):
                translation_status = "needs_review"
            active_translation = m["translation_status"] == "auto" and bool(m.get("translated_statement"))
            translation = current_translation(self.root, p) if active_translation else {}
            result.append({
                "problem_key": key, "platform": p["platform"], "problem_id": pid,
                "title": p["original_title"], "source_links": p["source_links"],
                "content_hash": p["content_hash"], "taxonomy_version": a["taxonomy_version"],
                "auto_tags": view["auto_tags"]["tags"], "effective_tags": view["effective_tags"],
                "review_status": view["review_status"], "fully_human_verified": view["fully_human_verified"],
                "manual_history_count": view["manual_overrides"]["history_count"],
                "manual_added_ids": view["manual_overrides"]["added_tag_ids"],
                "manual_removed_ids": view["manual_overrides"]["removed_tag_ids"],
                "needs_review_reasons": view["needs_review_reasons"],
                "model": view["auto_tags"]["model"],
                "annotation_status": a.get("api_call_status"),
                "translation_status": translation_status,
                "translation_task_states": states,
                "translation_active": active_translation,
                "translation_origin": translation.get("translation_origin", "ai") if active_translation else None,
                "translation_validation_mode": translation.get("translation_validation_mode", "legacy_strict") if active_translation else None,
                "translation_model": translation.get("translation_model") if active_translation else None,
                "translation_review_status": translation.get("translation_review_status") if active_translation else None,
                "translated_title": m.get("translated_title") if active_translation else None,
                "translated_statement": m.get("translated_statement") if active_translation else None,
                "read_only": True, "data_source": "existing_snapshot_with_local_manual_overlay",
            })
        return result

    def find(self, platform, problem_id):
        return next((v for v in self.views() if v["platform"] == platform and v["problem_id"] == problem_id), None)


async def initialize_database(database, labels, *, admin_password_hash=None):
    from feat.api.acm_api.database import connect_db
    from feat.api.acm_api.auth_service import hash_password
    from feat.api.acm_api.problem_bank import save_problem
    db = await connect_db(database)
    try:
        timestamp = int(time.time())
        await db.execute("INSERT OR IGNORE INTO users(qq_id,name) VALUES(?,?)", (DEMO_QQ, "本地验收账号"))
        await db.execute(
            "INSERT OR IGNORE INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) "
            "VALUES(?,?,'member',0,1,?,?)", (DEMO_QQ, hash_password(DEMO_PASSWORD), timestamp, timestamp))
        await db.commit()
        await db.execute("INSERT OR IGNORE INTO users(qq_id,name) VALUES(?,?)", (ADMIN_QQ, "本地标签管理员"))
        await db.execute(
            "INSERT OR IGNORE INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) "
            "VALUES(?,?,'admin',0,1,?,?)", (ADMIN_QQ, hash_password(ADMIN_PASSWORD), timestamp, timestamp))
        if admin_password_hash is not None:
            # Only this isolated SQLite account is updated. Never store the debug password in source.
            await db.execute("UPDATE web_accounts SET password_hash=?,role='admin',must_change_password=0,"
                             "is_active=1,credential_version=credential_version+1,updated_at=? "
                             "WHERE qq_id=? AND password_hash<>?",
                             (admin_password_hash, timestamp, ADMIN_QQ, admin_password_hash))
        await db.commit()
        problems, _ = labels.repo.snapshot()
        for view in labels.views():
            p = problems[view["problem_key"]]
            # Seed only missing rows. A later AI task registers crawler inputs in the
            # label catalog; restarting must not replay a sample-less seed over them.
            async with db.execute("SELECT 1 FROM crawler_problems WHERE platform=? AND problem_id=?",
                                  (p['platform'], view['problem_id'])) as cursor:
                if await cursor.fetchone():
                    continue
            await save_problem(db, {
                "platform": p["platform"], "problem_id": view["problem_id"], "contest_id": p["contest_id"],
                "problem_name": p["original_title"], "problem_url": p["source_links"][0],
                "problem_rating": p.get("difficulty_raw") if isinstance(p.get("difficulty_raw"), int) else None,
                "tags": p.get("raw_tags", []),
            }, {
                "statement_html": p.get("original_statement_html") or None,
                "statement_text": p["original_statement"], "statement_language": p.get("language_hint"),
                "requested_language": p.get("language_hint"), "samples": [],
                "source_url": p["source_links"][0], "sha256": p["verified_content_hash"],
            })
        # This is explicitly synthetic forum content, not copied team/private posts.
        body = "这是独立本地副本。请从「题库」查看有效标签；管理员从「管理后台 → 题库管理」进行二次处理。\n\n题面来自已有持久数据快照；没有新的采集或 AI 请求。"
        await db.execute("INSERT OR IGNORE INTO forum_posts(id,category_id,author_qq_id,title,body,status,created_at,updated_at,reviewed_at) "
                         "VALUES(1,2,?,?,?,'published',?,?,?)",
                         (DEMO_QQ, "本地演示：题目标签与翻译状态（模拟帖子）", body, timestamp, timestamp, timestamp))
        await db.commit()
    finally:
        await db.close()


def create_local_app(labels=None):
    from quart import jsonify, request
    from feat.api.acm_api.backend_api import member_required
    from feat.api.service_runtime import SyncEngine
    from feat.api.acm_api.cf_practice_jobs import PracticeJobs
    from feat.api.app import create_app
    from feat.api.app import _PUBLIC_PAGES
    # Disable background crawlers and periodic jobs before the real app starts.
    SyncEngine.start = AsyncMock()
    SyncEngine.close = AsyncMock()
    PracticeJobs.start = AsyncMock()
    PracticeJobs.close = AsyncMock()
    _PUBLIC_PAGES.add("processing-demo.html")
    _PUBLIC_PAGES.add("tag-management.html")
    app = create_app()
    labels = labels or ReadOnlyLabels()
    app.config["LOCAL_READ_ONLY_DEMO"] = True  # Existing forum/crawler writes remain blocked.
    app.config["LOCAL_TAG_MANAGEMENT"] = True
    from feat.api.acm_api import backend_api
    original_valid_qq = backend_api._valid_qq
    if not getattr(original_valid_qq, '_local_debug_account', False):
        def local_valid_qq(value):
            from quart import current_app
            return (current_app.config.get('LOCAL_TAG_MANAGEMENT') and value == ADMIN_QQ) or original_valid_qq(value)
        local_valid_qq._local_debug_account = True
        backend_api._valid_qq = local_valid_qq

    @app.before_request
    async def readonly_boundary():
        if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            return jsonify(message="仅允许本机访问"), 403
        edit_path = request.path.startswith('/api/secondary/tag-management/') and request.method == 'POST'
        ai_path = request.method == 'POST' and bool(re.fullmatch(
            r'/api/admin/problem-processing/(?:atcoder|codeforces)/[A-Za-z0-9_-]+/execute',request.path))
        if edit_path or ai_path:
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                return jsonify(message="不允许跨站修改"), 403
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                return jsonify(message="修改来源与本地站点不一致"), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.path not in {"/api/auth/login", "/api/auth/logout"} and not (edit_path or ai_path):
            return jsonify(message="本地隔离环境：此写入或采集入口未开放"), 403

    @app.after_request
    async def local_headers(response):
        response.headers["Cache-Control"] = "no-store"
        # Do not fetch remote avatars/images while viewing the original statement.
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["X-Local-Demo"] = "isolated-read-only"
        return response

    @app.get("/api/secondary/problems")
    @member_required
    async def catalog():
        rows = labels.views()
        return jsonify(items=rows, count=len(rows), real_api_calls=0,
                       active_translations=sum(v["translation_active"] for v in rows), read_only=True)

    @app.get("/api/secondary/problems/<platform>/<problem_id>")
    @member_required
    async def detail(platform, problem_id):
        row = labels.find(platform, problem_id)
        return (jsonify(row), 200) if row else (jsonify(message="该题暂无二次处理结果"), 404)

    from tag_editor import register_tag_management
    register_tag_management(app, labels)
    from problem_bank_labels import register_problem_bank_labels
    register_problem_bank_labels(app, labels)
    from admin_processing import register_admin_processing
    from ai_execution import register_ai_execution
    register_ai_execution(app,labels)
    register_admin_processing(app, labels)

    return app


async def run(port):
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    RUNTIME.mkdir(parents=True, exist_ok=True)
    database = RUNTIME / "forum-demo.sqlite3"
    isolate_environment(database)
    sys.addaudithook(loopback_only)
    labels = ReadOnlyLabels()
    credentials = RUNTIME / 'admin-login.json'
    configured = json.loads(credentials.read_text(encoding='utf-8')) if credentials.exists() else {}
    if configured and (configured.get('account') != ADMIN_QQ or not str(configured.get('password_hash', '')).startswith('pbkdf2_sha256$')):
        raise ValueError('本地调试账号配置无效')
    await initialize_database(database, labels, admin_password_hash=configured.get('password_hash'))
    app = create_local_app(labels)
    config = Config()
    config.bind = [f"127.0.0.1:{port}"]
    config.accesslog = None
    print(f"Isolated local forum: http://127.0.0.1:{port}/index.html", flush=True)
    await serve(app, config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18088)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口必须在 1024 到 65535 之间")
    asyncio.run(run(args.port))
