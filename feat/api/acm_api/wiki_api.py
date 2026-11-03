"""Wiki HTTP contract; public reads never use a role-dependent revision pointer."""

import hashlib
import sqlite3
from time import perf_counter
from functools import wraps
from urllib.parse import urlsplit

from quart import Blueprint, Response, current_app, jsonify, request
from .backend_api import _session_identity, admin_required, get_db
from .markdown_content import ContentError, export_markdown
from . import wiki_service as svc
from .wiki_cache import database_namespace

wiki_api = Blueprint("wiki_api", __name__)


def public_origin():
    origin = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not origin and request.host.split(":")[0] in {"127.0.0.1", "localhost"}:
        origin = request.host_url.rstrip("/")
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise svc.WikiError("公开站点地址配置无效。", "origin_not_configured", 503)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise svc.WikiError(
            "请配置 ACM_PUBLIC_BASE_URL 后再下载 Markdown。",
            "origin_not_configured",
            503,
        )
    return origin


def attachment(title, body, slug):
    source = export_markdown(title, body, public_origin())
    return Response(
        source,
        content_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.md"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def endpoint(write=False, public=False, cache=None):
    def decorate(func):
        @wraps(func)
        async def run(*args, **kwargs):
            started = perf_counter()
            db = await get_db()
            try:
                if write:
                    await db.execute("BEGIN IMMEDIATE")
                elif public:
                    await db.execute("BEGIN")
                data = await request.get_json(silent=True) if write else request.args
                if write and not isinstance(data, dict):
                    raise svc.WikiError("请求必须为 JSON 对象。")
                identity = await _session_identity() if write else None
                store = current_app.extensions["wiki_public_cache"]
                key = None
                version_ms = query_ms = json_ms = 0
                cache_status = "bypass"
                if cache:
                    if cache in {"pages", "search"}:
                        data = svc.public_list_query(data, search=cache == "search")
                    if cache == "category":
                        svc.integer(kwargs["category_id"])
                    state = await svc.settings(db)
                    versions = (state["public_content_version"],)
                    if cache in {"navigation", "category"}:
                        versions += (state["navigation_version"],)
                    key = (store.generation, database_namespace(current_app.config["DB_PATH"]),
                           cache, tuple(sorted(kwargs.items())), tuple(sorted(data.items()))
                           if cache in {"pages", "search"} else (), versions)
                    version_ms = (perf_counter() - started) * 1000
                enabled = cache and current_app.config["WIKI_CACHE_ENABLED"]
                entry = store.get(key) if enabled else None
                if entry is not None:
                    body, content_type, tag = entry.body, entry.content_type, entry.etag
                    cache_status = "hit"
                else:
                    query_started = perf_counter()
                    result = await func(
                        db, data, identity["qq_id"] if identity else "", *args, **kwargs
                    )
                    query_ms = (perf_counter() - query_started) * 1000
                    if write:
                        await db.commit()
                    if isinstance(result, Response):
                        return result
                    json_started = perf_counter()
                    response = jsonify(result)
                    if not public:
                        response.headers["Cache-Control"] = "private, no-store"
                        return response
                    body = await response.get_data()
                    content_type = response.content_type
                    tag = hashlib.sha256(body).hexdigest()
                    json_ms = (perf_counter() - json_started) * 1000
                    if enabled:
                        cache_status = "miss" if store.put(key, body, content_type, tag) else "skip"
                headers = {"ETag": '"' + tag + '"',
                           "Cache-Control": "public, max-age=0, must-revalidate"}
                if cache:
                    headers["Server-Timing"] = (
                        f'wiki-cache;desc="{cache_status}", wiki-version;dur={version_ms:.3f}, '
                        f'wiki-query;dur={query_ms:.3f}, wiki-json;dur={json_ms:.3f}'
                    )
                tags = request.if_none_match
                if tags.star_tag or tags.contains_weak(tag):
                    return Response(status=304, headers=headers)
                return Response(body, content_type=content_type, headers=headers)
            except (svc.WikiError, ContentError) as error:
                if write:
                    await db.rollback()
                return jsonify(
                    {
                        "message": str(error),
                        "code": getattr(error, "code", "invalid_content"),
                    }
                ), getattr(error, "status", 400)
            except sqlite3.IntegrityError:
                if write:
                    await db.rollback()
                return (
                    jsonify(
                        {
                            "message": "名称、slug 或层级存在冲突，请刷新并调整后重试。",
                            "code": "constraint_conflict",
                        }
                    ),
                    409,
                )
            finally:
                try:
                    if public and not write:
                        await db.rollback()
                finally:
                    await db.close()

        return run

    return decorate


@wiki_api.get("/wiki/navigation")
@endpoint(public=True, cache="navigation")
async def navigation(db, data, actor):
    return await svc.navigation(db)


@wiki_api.get("/wiki/categories/<int:category_id>")
@endpoint(public=True, cache="category")
async def category(db, data, actor, category_id):
    item = await svc.category(db, category_id)
    nav = await svc.navigation(db)
    clean = next(c for c in nav["categories"] if c["id"] == category_id)
    path = (
        [clean]
        if item["parent_id"] is None
        else [next(c for c in nav["categories"] if c["id"] == item["parent_id"]), clean]
    )
    return {
        "category": clean,
        "path": path,
        "children": [c for c in nav["categories"] if c["parent_id"] == category_id],
    }


@wiki_api.get("/wiki/pages")
@endpoint(public=True, cache="pages")
async def pages(db, data, actor):
    return await svc.page_list(db, data)


@wiki_api.get("/wiki/search")
@endpoint(public=True, cache="search")
async def search(db, data, actor):
    return await svc.page_list(db, data, search=True)


@wiki_api.get("/wiki/pages/<slug>")
@endpoint(public=True)
async def page(db, data, actor, slug):
    return await svc.public_page(db, slug)


@wiki_api.get("/wiki/pages/<slug>/revisions")
@endpoint(public=True)
async def history(db, data, actor, slug):
    current = await svc.public_page(db, slug)
    return await svc.rows(
        db,
        "SELECT id,title,created_at,published_at FROM wiki_revisions WHERE page_id=? AND published_at IS NOT NULL AND hidden=0 ORDER BY id DESC LIMIT 100",
        (current["page_id"],),
    )


@wiki_api.get("/wiki/pages/<slug>/revisions/<int:revision_id>")
@endpoint(public=True)
async def historical(db, data, actor, slug, revision_id):
    return await svc.public_page(db, slug, revision_id)


@wiki_api.get("/wiki/pages/<slug>/markdown")
@endpoint()
async def download(db, data, actor, slug):
    rid = svc.integer(data["revision_id"]) if data.get("revision_id") else None
    r = await svc.public_page(db, slug, rid)
    return attachment(r["title"], r["body"], slug)


@wiki_api.get("/admin/wiki/categories")
@admin_required
@endpoint()
async def admin_categories(db, data, actor):
    return await svc.navigation(db, True)


@wiki_api.post("/admin/wiki/categories")
@admin_required
@endpoint(write=True)
async def create_category(db, data, actor):
    return await svc.category_save(db, data, actor)


@wiki_api.patch("/admin/wiki/categories/<int:category_id>")
@admin_required
@endpoint(write=True)
async def edit_category(db, data, actor, category_id):
    return await svc.category_save(db, data, actor, category_id)


@wiki_api.put("/admin/wiki/categories/order")
@admin_required
@endpoint(write=True)
async def order(db, data, actor):
    return await svc.order_categories(db, data, actor)


@wiki_api.put("/admin/wiki/settings")
@admin_required
@endpoint(write=True)
async def defaults(db, data, actor):
    return await svc.default_category(db, data, actor)


@wiki_api.post("/admin/wiki/categories/<int:category_id>/delete-preview")
@admin_required
@endpoint(write=True)
async def preview_delete(db, data, actor, category_id):
    return await svc.delete_preview(db, category_id, actor)


@wiki_api.post("/admin/wiki/categories/<int:category_id>/delete")
@admin_required
@endpoint(write=True)
async def remove_category(db, data, actor, category_id):
    return await svc.idempotent(
        db,
        actor,
        f"delete:{category_id}",
        data,
        lambda: svc.delete_category(db, category_id, data, actor),
    )


@wiki_api.post("/admin/wiki/category-operations/<int:operation_id>/restore")
@admin_required
@endpoint(write=True)
async def restore_category(db, data, actor, operation_id):
    return await svc.restore_category(db, operation_id, actor)


@wiki_api.get("/admin/wiki/pages")
@admin_required
@endpoint()
async def admin_pages(db, data, actor):
    return await svc.page_list(db, data, True)


@wiki_api.post("/admin/wiki/pages")
@admin_required
@endpoint(write=True)
async def create_page(db, data, actor):
    return await svc.create_page(db, data, actor)


@wiki_api.get("/admin/wiki/pages/<int:page_id>")
@admin_required
@endpoint()
async def edit_page(db, data, actor, page_id):
    return await svc.edit_page(db, page_id)


@wiki_api.patch("/admin/wiki/pages/<int:page_id>")
@admin_required
@endpoint(write=True)
async def move_page(db, data, actor, page_id):
    return await svc.move_page(db, page_id, data, actor)


@wiki_api.get("/admin/wiki/pages/<int:page_id>/revisions")
@admin_required
@endpoint()
async def revisions(db, data, actor, page_id):
    await svc.page_record(db, page_id)
    return await svc.rows(
        db,
        "SELECT id,title,created_at,published_at,hidden FROM wiki_revisions WHERE page_id=? ORDER BY id DESC LIMIT 200",
        (page_id,),
    )


@wiki_api.get("/admin/wiki/revisions/<int:revision_id>")
@admin_required
@endpoint()
async def internal_revision(db, data, actor, revision_id):
    return await svc.revision(db, revision_id)


@wiki_api.post("/admin/wiki/pages/<int:page_id>/revisions")
@admin_required
@endpoint(write=True)
async def save_revision(db, data, actor, page_id):
    return await svc.save_revision(db, await svc.page_record(db, page_id), data, actor)


@wiki_api.post("/admin/wiki/revisions/<int:revision_id>/publish")
@admin_required
@endpoint(write=True)
async def publish(db, data, actor, revision_id):
    return await svc.idempotent(
        db,
        actor,
        f"publish:{revision_id}",
        data,
        lambda: svc.publish(db, revision_id, data, actor),
    )


@wiki_api.patch("/admin/wiki/revisions/<int:revision_id>")
@admin_required
@endpoint(write=True)
async def hide(db, data, actor, revision_id):
    return await svc.hide_revision(db, revision_id, data, actor)


@wiki_api.post("/admin/wiki/pages/<int:page_id>/restore")
@admin_required
@endpoint(write=True)
async def restore_page(db, data, actor, page_id):
    return await svc.restore_page(db, page_id, data, actor)


@wiki_api.get("/admin/wiki/revisions/<int:revision_id>/markdown")
@admin_required
@endpoint()
async def internal_download(db, data, actor, revision_id):
    r = await svc.revision(db, revision_id)
    p = await svc.page_record(db, r["page_id"])
    return attachment(r["title"], r["body"], p["slug"])
