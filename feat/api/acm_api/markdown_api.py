"""Immutable, decoded Markdown images shared by Wiki and forum drafts."""

import asyncio
import io
import re
import secrets
import time
from pathlib import Path
from quart import Blueprint, Response, current_app, jsonify, request, send_file
from .backend_api import _session_identity, get_db, member_required
from .account_lifecycle_service import require_web_actor
from .markdown_content import ContentError, asset_public
from .wiki_api import attachment, endpoint
from .wiki_service import WikiError, integer, one

markdown_api = Blueprint("markdown_api", __name__)


def normalize_image(data):
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        fmt = image.format
        if (
            fmt not in {"PNG", "JPEG", "WEBP"}
            or max(image.size) > 4096
            or min(image.size) < 1
            or getattr(image, "n_frames", 1) > 1
        ):
            raise ContentError("仅支持静态 PNG、JPEG、WebP，最长边不超过 4096 像素。")
        image.verify()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        image.load()
        image = image.convert("RGB" if fmt == "JPEG" else "RGBA")
        output = io.BytesIO()
        image.save(output, format=fmt)
        if len(output.getvalue()) > 2 * 1024 * 1024:
            raise ContentError("图片处理后超过 2 MB，请压缩后重试。")
        return output.getvalue(), fmt.lower(), image.width, image.height
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        if isinstance(error, ContentError):
            raise
        raise ContentError("图片文件损坏或不支持。") from error


@markdown_api.post("/markdown/assets")
@member_required
async def upload():
    db = await get_db()
    destination = None
    try:
        data = await request.form
        files = await request.files
        kind = data.get("document_type")
        document_id = integer(data.get("document_id"))
        identity = request.web_identity
        if kind == "wiki":
            if identity["role"] not in {"admin", "root"}:
                return jsonify({"message": "仅限 Wiki 管理员上传。"}), 403
            if not await one(
                db, "SELECT id FROM wiki_pages WHERE id=?", (document_id,)
            ):
                raise WikiError("草稿不存在。", "not_found", 404)
        elif kind == "forum_draft":
            if not await one(
                db,
                "SELECT id FROM forum_drafts WHERE id=? AND author_qq_id=?",
                (document_id, identity["qq_id"]),
            ):
                raise WikiError("草稿不存在。", "not_found", 404)
        else:
            raise WikiError("不支持的资源归属类型。")
        file = files.get("file")
        if not file:
            raise ContentError("请选择图片。")
        raw = file.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise WikiError("单张图片不能超过 2 MB。", "file_too_large", 413)
        content, fmt, width, height = await asyncio.to_thread(normalize_image, raw)
        asset_id = secrets.token_hex(16)
        name = secrets.token_hex(24) + "." + fmt
        folder = Path(current_app.config["MARKDOWN_UPLOAD_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / name
        with destination.open("xb") as stream:
            stream.write(content)
        await db.execute("BEGIN IMMEDIATE")
        await require_web_actor(db, request.web_identity)
        await db.execute(
            "INSERT INTO markdown_assets VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                asset_id,
                name,
                "image/" + fmt,
                len(content),
                width,
                height,
                identity["qq_id"],
                kind,
                document_id,
                int(time.time()),
            ),
        )
        await db.commit()
        destination = None
        return (
            jsonify(
                {
                    "id": asset_id,
                    "url": "/api/markdown/assets/" + asset_id,
                    "size": len(content),
                    "width": width,
                    "height": height,
                }
            ),
            201,
        )
    except (ContentError, WikiError) as error:
        await db.rollback()
        return jsonify(
            {"message": str(error), "code": getattr(error, "code", "invalid_image")}
        ), getattr(error, "status", 400)
    finally:
        if destination:
            destination.unlink(missing_ok=True)
        await db.close()


@markdown_api.get("/markdown/assets/<asset_id>")
async def asset(asset_id):
    if not re.fullmatch(r"[a-f0-9]{32}", asset_id):
        return Response(status=404)
    db = await get_db()
    try:
        row = await one(db, "SELECT * FROM markdown_assets WHERE id=? AND NOT EXISTS(SELECT 1 FROM account_closure_resource_revocations v WHERE v.resource_kind='markdown' AND v.resource_id=markdown_assets.id)", (asset_id,))
        if not row:
            return Response(status=404)
        public = await asset_public(db, asset_id)
        identity = await _session_identity() if not public else None
        forum_reference_access = False
        if identity and not identity["must_change_password"]:
            forum_reference_access = bool(await one(db, """SELECT 1 FROM markdown_asset_references a
 LEFT JOIN forum_posts p ON a.document_type='forum_post' AND p.id=a.document_id
 LEFT JOIN forum_drafts d ON a.document_type='forum_draft' AND d.id=a.document_id
 WHERE a.asset_id=? AND (p.author_qq_id=? OR d.author_qq_id=? OR (? AND p.status IN ('pending','published','rejected'))) LIMIT 1""",
                (asset_id, identity["qq_id"], identity["qq_id"], identity["role"] in {"admin", "root"})))
        if not public and (
            not identity
            or identity["must_change_password"]
            or not (
                identity["qq_id"] == row["owner"]
                and row["document_type"] == "forum_draft"
                or row["document_type"] == "wiki"
                and identity["role"] in {"admin", "root"}
                or forum_reference_access
            )
        ):
            return Response(status=404)
        path = Path(current_app.config["MARKDOWN_UPLOAD_DIR"]) / row["storage_name"]
        if not path.is_file():
            return Response(status=404)
        response = await send_file(
            path, mimetype=row["content_type"], conditional=False
        )
        response.headers["Cache-Control"] = (
            "no-store"  # Visibility can change when a public revision is hidden.
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    finally:
        await db.close()


@markdown_api.get("/forum/posts/<int:post_id>/markdown")
@endpoint()
async def forum_download(db, data, actor, post_id):
    post = await one(
        db,
        "SELECT title,body FROM forum_posts WHERE id=? AND status='published'",
        (post_id,),
    )
    if not post:
        raise WikiError("话题不存在或尚未公开。", "not_found", 404)
    return attachment(post["title"], post["body"], f"forum-{post_id}")


@markdown_api.get("/forum/drafts/<int:draft_id>/markdown")
@member_required
@endpoint()
async def draft_download(db, data, actor, draft_id):
    draft = await one(
        db,
        "SELECT title,body FROM forum_drafts WHERE id=? AND author_qq_id=?",
        (draft_id, request.web_identity["qq_id"]),
    )
    if not draft:
        raise WikiError("草稿不存在。", "not_found", 404)
    return attachment(draft["title"], draft["body"], f"forum-draft-{draft_id}")
