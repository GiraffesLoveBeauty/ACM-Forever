import asyncio
import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from quart import Quart, abort, jsonify, redirect, request, send_from_directory

from .acm_api.backend_api import api
from .acm_api.bot_api import bot_api
from .acm_api.auth_service import hash_password, validate_password
from .acm_api.database import connect_db
from .acm_api.forum_api import forum_api
from .acm_api.cf_practice import PracticeQuery
from .acm_api.cf_practice_api import cf_practice_api
from .acm_api.cf_practice_jobs import PracticeJobs
from .service_runtime import SyncEngine, WebTaskManager, create_web_challenge


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


def _write_admins(db_path, root_ids, admins):
    with sqlite3.connect(db_path, timeout=5) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            ("webui_admin_qq_ids", json.dumps(admins, ensure_ascii=False)),
        )
        connection.commit()
    return {"root": list(root_ids), "admins": list(admins)}


def create_app():
    app = Quart(__name__, static_folder=None)
    db_path = Path(os.getenv("ACM_DATABASE_PATH", "./data/acm_forever.db")).expanduser()
    secret_key = os.getenv("ACM_WEBUI_SECRET_KEY", "").strip()
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=_bool_env("ACM_WEBUI_COOKIE_SECURE", False),
    )
    app.config["DB_PATH"] = str(db_path)
    app.config["AVATAR_UPLOAD_DIR"] = db_path.parent / "uploads" / "avatars"
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
    app.config["BOT_API_TOKEN"] = os.getenv("ACM_BOT_API_TOKEN", "").strip()
    app.config["WEBUI_PUBLIC_DIR"] = Path(__file__).parent / "acm_api" / "public"
    root_ids = _csv_env("ACM_ROOT_QQ_IDS")
    initial_admin_ids = _csv_env("ACM_ADMIN_QQ_IDS")
    crawler_config = {
        "luogu_cookie": os.getenv("ACM_LUOGU_COOKIE", ""),
        "luogu_csrf_token": os.getenv("ACM_LUOGU_CSRF_TOKEN", ""),
        "cf_api_key": os.getenv("ACM_CF_API_KEY", ""),
        "cf_api_secret": os.getenv("ACM_CF_API_SECRET", ""),
        "cjlu_username": os.getenv("ACM_CJLU_USERNAME", ""),
        "cjlu_password": os.getenv("ACM_CJLU_PASSWORD", ""),
    }

    sync_engine = SyncEngine(db_path, crawler_config)
    task_manager = WebTaskManager(sync_engine)
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
        "_admin_config_updater": lambda admins: _write_admins(
            db_path, root_ids, admins
        ),
        "_task_provider": task_manager.snapshots,
        "_task_canceller": task_manager.cancel,
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
                if account_count == 0:
                    error = validate_password(bootstrap_password)
                    if error:
                        raise RuntimeError("ACM_BOOTSTRAP_ROOT_PASSWORD: " + error)
                    if not bootstrap_qq.isdigit() or not 4 <= len(bootstrap_qq) <= 12:
                        raise RuntimeError("ACM_BOOTSTRAP_ROOT_QQ_ID must be 4-12 digits.")
                    now = int(__import__("time").time())
                    await db.execute(
                        "INSERT OR IGNORE INTO users(qq_id,name) VALUES(?,?)",
                        (bootstrap_qq, bootstrap_qq),
                    )
                    await db.execute(
                        "INSERT OR IGNORE INTO web_accounts"
                        "(qq_id,password_hash,role,must_change_password,is_active,"
                        "credential_version,created_at,updated_at) "
                        "VALUES(?,?,'root',0,1,1,?,?)",
                        (bootstrap_qq, hash_password(bootstrap_password), now, now),
                    )
                    await db.commit()
        finally:
            await db.close()
        await sync_engine.start()
        await practice_jobs.start()

    @app.after_serving
    async def close_service():
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
            return redirect("/change-password.html?" + urlencode({"next": "/"}))
        return await send_from_directory(app.config["WEBUI_PUBLIC_DIR"], "index.html")

    @app.get("/<path:filename>")
    async def webui_static(filename):
        filename = filename.replace("\\", "/")
        extension = Path(filename).suffix.lower()
        if filename.startswith("assets/") and extension in {
            ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2", ".otf", ".ico",
        }:
            return await send_from_directory(app.config["WEBUI_PUBLIC_DIR"], filename)
        if filename not in _PUBLIC_PAGES:
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
            return await send_from_directory(app.config["WEBUI_PUBLIC_DIR"], filename)
        if identity and identity["must_change_password"] and filename != "change-password.html":
            return redirect("/change-password.html?" + urlencode({"next": target}))
        if filename in _ADMIN_PAGES:
            if not identity:
                return redirect("/login.html?" + urlencode({"next": target}))
            if identity["role"] not in {"admin", "root"}:
                abort(403)
        elif filename == "change-password.html":
            if not identity:
                return redirect("/login.html?" + urlencode({"next": target}))
        elif filename == "login.html":
            if identity:
                next_url = request.args.get("next", "/index.html")
                if not next_url.startswith("/") or next_url.startswith("//") or "\\" in next_url or any(ord(char) < 32 for char in next_url):
                    next_url = "/index.html"
                return redirect(next_url)
        elif filename not in _ANONYMOUS_PAGES and not identity:
            return redirect("/login.html?" + urlencode({"next": target}))
        if target != request.full_path.rstrip("?"):
            return redirect(target)
        return await send_from_directory(app.config["WEBUI_PUBLIC_DIR"], filename)

    @app.get("/uploads/avatars/<filename>")
    async def uploaded_avatar(filename):
        if not re.fullmatch(r"[a-f0-9]{32}\.(?:png|jpg|webp)", filename):
            abort(404)
        response = await send_from_directory(app.config["AVATAR_UPLOAD_DIR"], filename)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.after_request
    async def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; connect-src 'self'; img-src 'self' data:; "
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
    app.register_blueprint(bot_api, url_prefix="/internal/v1")
    app.register_blueprint(forum_api, url_prefix="/api")
    app.register_blueprint(cf_practice_api, url_prefix="/api")
    app.sync_engine = sync_engine
    app.task_manager = task_manager
    return app


_PUBLIC_PAGES = {
    "index.html", "login.html", "post.html", "forum-moderation.html",
    "change-password.html", "home.html", "admin.html",
    "leaderboard.html", "challenge.html", "reviews.html", "problem-bank.html",
    "submissions.html", "workspace.html", "contest-review.html", "member.html", "compose.html",
    "tasks.html", "settings.html", "cf-practice.html",
}
_ANONYMOUS_PAGES = {"index.html", "login.html", "post.html", "leaderboard.html"}
_ADMIN_PAGES = {"admin.html", "member.html", "tasks.html", "settings.html", "forum-moderation.html", "cf-practice.html"}
_RETIRED_PAGES = {"reviews.html", "submissions.html", "workspace.html"}
_LEGACY_ADMIN_PAGES = {"member.html": "members", "challenge.html": "training", "problem-bank.html": "problems", "contest-review.html": "contests", "tasks.html": "tasks", "settings.html": "settings", "forum-moderation.html": "moderation", "cf-practice.html": "cf-practice"}


app = create_app()
