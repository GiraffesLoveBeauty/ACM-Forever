import asyncio
import json
import logging
import os
import posixpath
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit

from quart import Quart, abort, jsonify, redirect, request, send_from_directory

from .acm_api.backend_api import api
from .acm_api.bot_api import bot_api
from .acm_api.account_closure_api import account_closure_api
from .acm_api.account_closure_cleanup import ClosureCleanup
from .acm_api.auth_service import hash_password, validate_password
from .acm_api.account_lifecycle_service import AccountLifecycleError, bootstrap_root, user_lifecycle
from .acm_api.database import connect_db
from .acm_api.forum_api import forum_api
from .acm_api.mobile_api import mobile_api
from .acm_api.forum_notifications import forum_notification_api
from .acm_api.wiki_api import wiki_api
from .acm_api.wiki_cache import WikiResponseCache
from .acm_api.markdown_api import markdown_api
from .acm_api.forum_images import forum_image_api
from .acm_api.cf_practice import PracticeQuery
from .acm_api.cf_practice_api import cf_practice_api
from .acm_api.cf_practice_jobs import PracticeJobs
from .service_runtime import SyncEngine, WebTaskManager, create_web_challenge
from .acm_api.event_log import install as install_event_logging


def _safe_web_next(value, fallback="/index.html"):
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//") or re.search(r"[\\\x00-\x1f\x7f]", value):
        return fallback
    try:
        raw_path = urlsplit(value).path
        path = unquote(raw_path, errors="strict")
        if re.search(r"%(?![0-9a-fA-F]{2})", raw_path):
            return fallback
        if path.startswith("//") or re.search(r"[\\\x00-\x1f\x7f]", path):
            return fallback
        if posixpath.normpath(path).lower() in {
            "/login.html", "/auth-unavailable.html", "/forbidden.html",
        }:
            return fallback
    except (ValueError, UnicodeError):
        return fallback
    return value


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


def _csv_env(name):
    return [item.strip() for item in os.getenv(name, "").replace("，", ",").split(",") if item.strip()]


def _read_admins(db_path, fallback):
    try:
        with sqlite3.connect(db_path, timeout=5) as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key='webui_admin_qq_ids'"
            ).fetchone()
        if row:
            value = json.loads(row[0])
            if isinstance(value, list):
                return [str(item) for item in value]
    except (sqlite3.Error, ValueError, TypeError):
        pass
    return list(fallback)


async def _write_admins(db_path, root_ids, admins, identity):
    from .acm_api.cf_practice_jobs import open_db
    from .acm_api.account_lifecycle_service import require_web_actor
    db = await open_db(db_path)
    try:
        await db.execute("BEGIN IMMEDIATE")
        await require_web_actor(db, identity, roles={"root"})
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", ("webui_admin_qq_ids", json.dumps(admins, ensure_ascii=False)))
        await db.commit()
        return {"root": list(root_ids), "admins": list(admins)}
    finally:
        await db.close()


def create_app(*, daily_problem_sync=False, member_sync=False):
    app = Quart(__name__, static_folder=None)

    @app.errorhandler(AccountLifecycleError)
    async def lifecycle_error_response(error):
        return jsonify({"success": False, "code": error.code, "message": str(error)}), error.status

    db_path = Path(os.getenv("ACM_DATABASE_PATH", "./data/acm_forever.db")).expanduser()
    secret_key = os.getenv("ACM_WEBUI_SECRET_KEY", "").strip()
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=_bool_env("ACM_WEBUI_COOKIE_SECURE", False),
    )
    app.config["DB_PATH"] = str(db_path)
    app.config["ACCOUNT_CLOSURE_ENABLED"] = _bool_env("ACM_ACCOUNT_CLOSURE_ENABLED", False)
    app.config["ACCOUNT_IMPORT_ENABLED"] = _bool_env("ACM_ACCOUNT_IMPORT_ENABLED", True)
    app.config["TRAINING_TASKS_ENABLED"] = _bool_env("ACM_TRAINING_TASKS_ENABLED", True)
    app.config["WIKI_CACHE_ENABLED"] = _bool_env("ACM_WIKI_CACHE_ENABLED", True)
    app.extensions["wiki_public_cache"] = WikiResponseCache()
    app.config["AVATAR_UPLOAD_DIR"] = db_path.parent / "uploads" / "avatars"
    app.config["MARKDOWN_UPLOAD_DIR"] = Path(os.getenv("ACM_MARKDOWN_UPLOAD_DIR", str(db_path.parent / "uploads" / "markdown"))).expanduser()
    app.config["PUBLIC_BASE_URL"] = os.getenv("ACM_PUBLIC_BASE_URL", "").strip()
    app.config["FORUM_UPLOAD_DIR"] = db_path.parent / "uploads" / "forum"
    app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
    app.config["BOT_API_TOKEN"] = os.getenv("ACM_BOT_API_TOKEN", "").strip()
    app.config["WEBUI_PUBLIC_DIR"] = Path(__file__).parent / "acm_api" / "public"
    app.config["WEBUI_DIST_DIR"] = Path(__file__).parent.parent / "web" / "dist"
    root_ids = _csv_env("ACM_ROOT_QQ_IDS")
    initial_admin_ids = _csv_env("ACM_ADMIN_QQ_IDS")
    luogu_interval = float(os.getenv("ACM_LUOGU_REQUEST_INTERVAL", "2.0"))
    luogu_daily_limit = int(os.getenv("ACM_LUOGU_DAILY_STATEMENT_LIMIT", "100"))
    luogu_max_pages = int(os.getenv("ACM_LUOGU_CATALOG_MAX_PAGES", "1000"))
    if not 1.2 <= luogu_interval <= 60 or not 1 <= luogu_daily_limit <= 1000 or not 1 <= luogu_max_pages <= 2000:
        raise ValueError("Luogu request interval must be 1.2–60, daily limit 1–1000, catalog pages 1–2000")
    crawler_config = {
        "luogu_request_interval": luogu_interval,
        "luogu_daily_statement_limit": luogu_daily_limit,
        "luogu_catalog_max_pages": luogu_max_pages,
        "luogu_daily_problem_sync_enabled": _bool_env("ACM_LUOGU_DAILY_PROBLEM_SYNC_ENABLED", False),
        "luogu_user_sync_enabled": _bool_env("ACM_LUOGU_USER_SYNC_ENABLED", False),
        "luogu_cookie": os.getenv("ACM_LUOGU_COOKIE", ""),
        "luogu_csrf_token": os.getenv("ACM_LUOGU_CSRF_TOKEN", ""),
        "cf_api_key": os.getenv("ACM_CF_API_KEY", ""),
        "cf_api_secret": os.getenv("ACM_CF_API_SECRET", ""),
        "cjlu_username": os.getenv("ACM_CJLU_USERNAME", ""),
        "cjlu_password": os.getenv("ACM_CJLU_PASSWORD", ""),
    }

    sync_engine = SyncEngine(db_path, crawler_config)
    task_manager = WebTaskManager(sync_engine)
    member_sync_minutes = int(os.getenv("ACM_MEMBER_SYNC_INTERVAL_MINUTES", "60"))
    if not 1 <= member_sync_minutes <= 1440:
        raise ValueError("ACM_MEMBER_SYNC_INTERVAL_MINUTES must be between 1 and 1440")
    data_ttl_hours = int(os.getenv("ACM_CF_DATA_TTL_HOURS", "24"))
    problem_ttl_hours = int(os.getenv("ACM_CF_PROBLEM_TTL_HOURS", "6"))
    if not 1 <= data_ttl_hours <= 720 or not 1 <= problem_ttl_hours <= 720:
        raise ValueError("CF data/problem TTL hours must be between 1 and 720")
    practice_query = PracticeQuery(data_ttl_hours * 3600, problem_ttl_hours * 3600)
    practice_jobs = PracticeJobs(db_path, sync_engine, practice_query)
    app.config["CF_PRACTICE_QUERY"] = practice_query
    app.config["CF_PRACTICE_JOBS"] = practice_jobs

    def admin_snapshot():
        return {
            "root": list(root_ids),
            "admins": _read_admins(db_path, initial_admin_ids),
        }

    plugin_config = {
        "webui_temporary_password_ttl_hours": int(
            os.getenv("ACM_TEMP_PASSWORD_TTL_HOURS", "72")
        ),
        "webui_legacy_admin_login": _bool_env(
            "ACM_WEBUI_LEGACY_ADMIN_LOGIN", False
        ),
        "webui_admin_username": os.getenv("ACM_WEBUI_ADMIN_USERNAME", ""),
        "webui_admin_password_hash": os.getenv(
            "ACM_WEBUI_ADMIN_PASSWORD_HASH", ""
        ),
        "webui_admin_password": os.getenv("ACM_WEBUI_ADMIN_PASSWORD", ""),
        "webui_trusted_proxies": _csv_env("ACM_WEBUI_TRUSTED_PROXIES"),
        "admins": initial_admin_ids,
        "_admin_config_provider": admin_snapshot,
        "_admin_config_updater": lambda admins, identity: _write_admins(
            db_path, root_ids, admins, identity
        ),
        "_task_provider": task_manager.public_snapshots,
        "_account_closure_notifier": task_manager.revoke_account_tasks,
        "_task_canceller": task_manager.cancel,
        "_problem_sync_submitter": task_manager.submit_problem_sync,
        "_account_sync_submitter": task_manager.submit_account_sync,
        "_all_account_sync_submitter": task_manager.submit_all_accounts_sync,
        "_registration_sync_submitter": lambda qq_id: task_manager.submit_account_sync(
            qq_id, ["codeforces", "luogu", "nowcoder", "atcoder", "cjlu"]
        ),
        "_challenge_provider": lambda platform="", tag="", difficulty=None, owner_qq_id=None: create_web_challenge(
            db_path, platform, tag, difficulty, owner_qq_id
        ),
        "web_allowed_origins": _csv_env("ACM_WEB_ALLOWED_ORIGINS"),
    }
    app.config["PLUGIN_CONFIG"] = plugin_config

    closure_cleanup = ClosureCleanup(db_path, {
        "avatar": app.config["AVATAR_UPLOAD_DIR"],
        "forum": app.config["FORUM_UPLOAD_DIR"],
        "forum_thumb": app.config["FORUM_UPLOAD_DIR"] / "thumbnails",
        "markdown": app.config["MARKDOWN_UPLOAD_DIR"],
    })
    app.extensions["account_closure_cleanup"] = closure_cleanup
    from .acm_api.account_import_api import account_import_api, maintenance_once, maintenance_loop
    app.register_blueprint(account_import_api)
    from .acm_api.training_task_api import training_task_api
    app.register_blueprint(training_task_api)

    @app.before_serving
    async def initialize_service():
        if not secret_key:
            raise RuntimeError("Set ACM_WEBUI_SECRET_KEY before starting the API service.")
        db = await connect_db(db_path)
        try:
            bootstrap_qq = os.getenv("ACM_BOOTSTRAP_ROOT_QQ_ID", "").strip()
            bootstrap_password = os.getenv("ACM_BOOTSTRAP_ROOT_PASSWORD", "")
            if bootstrap_qq and bootstrap_password:
                async with db.execute("SELECT COUNT(*) AS n FROM web_accounts") as cursor:
                    account_count = int((await cursor.fetchone())["n"])
                lifecycle = await user_lifecycle(db, bootstrap_qq)
                if account_count == 0 and (not lifecycle or lifecycle["account_state"] == "active"):
                    error = validate_password(bootstrap_password)
                    if error:
                        raise RuntimeError("ACM_BOOTSTRAP_ROOT_PASSWORD: " + error)
                    if not bootstrap_qq.isdigit() or not 4 <= len(bootstrap_qq) <= 12:
                        raise RuntimeError("ACM_BOOTSTRAP_ROOT_QQ_ID must be 4-12 digits.")
                    now = int(__import__("time").time())
                    bootstrap_hash = hash_password(bootstrap_password)
                    await bootstrap_root(db, bootstrap_qq, bootstrap_hash, now)
        finally:
            await db.close()
        await sync_engine.start()
        await practice_jobs.start()
        await closure_cleanup.start()
        await maintenance_once(app)
        app.extensions["account_import_maintenance"] = asyncio.create_task(maintenance_loop(app))
        if daily_problem_sync:
            task_manager.start_daily_problem_sync()
        if member_sync:
            task_manager.start_member_sync(member_sync_minutes * 60)

    @app.after_serving
    async def close_service():
        await closure_cleanup.close()
        import_task = app.extensions.pop("account_import_maintenance", None)
        if import_task:
            import_task.cancel()
            await asyncio.gather(import_task, return_exceptions=True)
        executor = app.extensions.pop("account_password_executor", None)
        if executor:
            executor.close()
        await task_manager.close()
        await practice_jobs.close()
        await sync_engine.close()

    @app.get("/health")
    async def health():
        db = await connect_db(db_path)
        try:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        finally:
            await db.close()
        return jsonify({"status": "ok"})

    @app.get("/")
    async def webui_index():
        from .acm_api.backend_api import _session_identity

        identity = await _session_identity()
        if identity and identity["must_change_password"]:
            return redirect("/change-password.html?" + urlencode({"next": request.full_path.rstrip("?")}))
        return await vue_entry()

    async def vue_entry(filename="index.html", status=200):
        dist = app.config["WEBUI_DIST_DIR"]
        if not (dist / "index.html").is_file():
            return (
                "Vue frontend has not been built. Run pnpm install and pnpm build in feat/web.",
                503,
            )
        response = await send_from_directory(dist, filename)
        response.status_code = status
        return response

    @app.get("/<path:filename>")
    async def webui_static(filename):
        filename = filename.replace("\\", "/")
        extension = Path(filename).suffix.lower()
        pdf_asset = filename.startswith("assets/pdfjs/") and extension in {".bcmap", ".pfb", ".ttf"}
        if filename.startswith("assets/") and (pdf_asset or extension in {
            ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2", ".otf", ".ico",
        }):
            dist_dir = Path(app.config["WEBUI_DIST_DIR"]).resolve()
            dist_asset = (dist_dir / filename).resolve()
            try:
                dist_asset.relative_to(dist_dir)
                in_dist = True
            except ValueError:
                in_dist = False
            if in_dist and dist_asset.is_file():
                response = await send_from_directory(dist_dir, filename)
                if extension == ".mjs":
                    response.headers["Content-Type"] = "text/javascript; charset=utf-8"
                elif extension == ".css":
                    response.headers["Content-Type"] = "text/css; charset=utf-8"
                return response
            response = await send_from_directory(app.config["WEBUI_PUBLIC_DIR"], filename)
            if extension == ".css":
                response.headers["Content-Type"] = "text/css; charset=utf-8"
            return response
        if filename not in _PUBLIC_PAGES:
            if filename.split("/", 1)[0] not in {"api", "internal", "assets", "uploads", "health"} and extension in {"", ".html"}:
                return await vue_entry(status=404)
            abort(404)

        from .acm_api.backend_api import _session_identity

        identity = await _session_identity()
        target = request.full_path.rstrip("?")
        legacy = _LEGACY_ADMIN_PAGES.get(filename)
        if legacy and (filename in _ADMIN_PAGES or identity and identity["role"] in {"admin", "root"}):
            params = request.args.to_dict()
            params["section"] = legacy
            target = "/admin.html?" + urlencode(params)
        if filename in _RETIRED_PAGES:
            return await vue_entry("retired.html")
        if identity and identity["must_change_password"] and filename != "change-password.html":
            if filename == "login.html":
                target = _safe_web_next(request.args.get("next"))
            return redirect("/change-password.html?" + urlencode({"next": target}))
        if filename in _ADMIN_PAGES:
            if not identity:
                return redirect("/login.html?" + urlencode({"next": target}))
            if identity["role"] not in {"admin", "root"}:
                return await vue_entry(status=403)
        elif filename == "change-password.html":
            if not identity:
                return redirect("/login.html?" + urlencode({"next": target}))
        elif filename == "login.html":
            if identity:
                return redirect(_safe_web_next(request.args.get("next")))
        elif filename not in _ANONYMOUS_PAGES and not identity:
            return redirect("/login.html?" + urlencode({"next": target}))
        if target != request.full_path.rstrip("?"):
            return redirect(target)
        return await vue_entry()

    @app.get("/uploads/avatars/<filename>")
    async def uploaded_avatar(filename):
        if not re.fullmatch(r"[a-f0-9]{32}\.(?:png|jpg|webp)", filename):
            abort(404)
        from .acm_api.backend_api import get_db
        db = await get_db()
        try:
            async with db.execute("SELECT 1 FROM users WHERE account_state='active' AND avatar_url=?", ("/uploads/avatars/" + filename,)) as cursor:
                if not await cursor.fetchone():
                    abort(404)
        finally:
            await db.close()
        response = await send_from_directory(app.config["AVATAR_UPLOAD_DIR"], filename)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.after_request
    async def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        problem_images = " https://*.codeforces.com https://codeforces.com https://img.atcoder.jp https://atcoder.jp https://www.luogu.com.cn https://cdn.luogu.com.cn" if request.path == "/problem.html" else ""
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            f"frame-ancestors 'none'; connect-src 'self'; img-src 'self' data: blob:{problem_images}; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
        )
        if response.content_type == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        elif response.content_type and response.content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        origin = request.headers.get("Origin", "")
        if origin and origin in plugin_config["web_allowed_origins"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-CSRF-Token, Authorization"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers.add("Vary", "Origin")
        return response

    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(account_closure_api, url_prefix="/api")
    app.register_blueprint(bot_api, url_prefix="/internal/v1")
    app.register_blueprint(forum_api, url_prefix="/api")
    app.register_blueprint(mobile_api, url_prefix="/api/mobile/v1")
    app.register_blueprint(forum_notification_api, url_prefix="/api")
    app.register_blueprint(wiki_api, url_prefix="/api")
    app.register_blueprint(markdown_api, url_prefix="/api")
    app.register_blueprint(forum_image_api, url_prefix="/api")
    app.register_blueprint(cf_practice_api, url_prefix="/api")
    app.sync_engine = sync_engine
    app.task_manager = task_manager
    install_event_logging(app, public_pages=_PUBLIC_PAGES)
    return app


_PUBLIC_PAGES = {
    "account-closure.html", "index.html", "login.html", "post.html", "wiki.html", "forum-moderation.html",
    "change-password.html", "home.html", "admin.html", "notifications.html", "my-post.html",
    "leaderboard.html", "training-tasks.html", "challenge.html", "reviews.html", "problem-bank.html", "my-problems.html", "problem.html",
    "submissions.html", "workspace.html", "contest-review.html", "member.html", "compose.html",
    "tasks.html", "settings.html", "cf-practice.html", "auth-unavailable.html", "forbidden.html",
}
_ANONYMOUS_PAGES = {"account-closure.html", "wiki.html", "index.html", "login.html", "post.html", "leaderboard.html", "auth-unavailable.html", "forbidden.html"}
_ADMIN_PAGES = {"admin.html", "member.html", "tasks.html", "settings.html", "forum-moderation.html", "cf-practice.html"}
_RETIRED_PAGES = {"reviews.html", "submissions.html", "workspace.html"}
_LEGACY_ADMIN_PAGES = {"member.html": "members", "problem-bank.html": "problems", "tasks.html": "tasks", "settings.html": "settings", "forum-moderation.html": "moderation", "cf-practice.html": "cf-practice"}


app = create_app(
    daily_problem_sync=_bool_env("ACM_DAILY_PROBLEM_SYNC_ENABLED", True),
    member_sync=_bool_env("ACM_MEMBER_SYNC_ENABLED", True),
)
