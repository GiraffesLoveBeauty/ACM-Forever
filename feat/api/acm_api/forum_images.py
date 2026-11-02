"""Managed forum images, draft references and publication visibility."""
import asyncio
import io
import re
import secrets
import time
import warnings
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
import mistune
from quart import Blueprint, abort, current_app, jsonify, request, send_from_directory

from .backend_api import _session_identity, get_db, member_required

forum_image_api = Blueprint("forum_image_api", __name__)
IMAGE_ID = re.compile(r"[a-f0-9]{32}")
IMAGE_REFERENCE = re.compile(r"/api/forum/images/([a-f0-9]{32})")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_USER_BYTES = 200 * 1024 * 1024
_render_markdown = mistune.create_markdown(escape=False)


class _ImageReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attribute = {"img": "src", "a": "href"}.get(tag)
        if attribute:
            match = IMAGE_REFERENCE.fullmatch(dict(attrs).get(attribute) or "")
            if match:
                self.ids.add(match[1])


def referenced_images(body):
    # Parse Markdown so code samples and prose do not accidentally publish images.
    parser = _ImageReferences()
    parser.feed(_render_markdown(body))
    return parser.ids


def image_url(image_id):
    return f"/api/forum/images/{image_id}" if image_id else None


def normalize_image(contents):
    """Decode and re-encode images, stripping filenames, EXIF and other metadata."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contents)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("请选择 PNG、JPEG 或 WebP 图片。")
                if source.width * source.height > 20_000_000 or max(source.size) > 10_000:
                    raise ValueError("图片尺寸过大，请先缩小图片。")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("请使用静态图片。")
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
                image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
                output = io.BytesIO()
                image.save(output, "WEBP", quality=88, method=4)
                data = output.getvalue()
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("图片处理后仍超过 5 MB，请先缩小图片。")
                return data, image.width, image.height
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("无法读取图片，请上传有效的 PNG、JPEG 或 WebP 图片。") from error


async def sync_image_links(db, owner, body, cover_id, *, draft_id=None, post_id=None):
    """Validate references and update them in the caller's content transaction."""
    ids = referenced_images(body)
    if cover_id:
        ids.add(cover_id)
    if len(ids) > 30:
        raise ValueError("每篇帖子最多使用 30 张图片。")
    for image_id in ids:
        async with db.execute(
            "SELECT 1 FROM forum_images i WHERE i.id=? AND (i.owner_qq_id=? OR EXISTS("
            "SELECT 1 FROM forum_image_links l JOIN forum_posts p ON p.id=l.post_id "
            "WHERE l.image_id=i.id AND p.status='published') OR EXISTS("
            "SELECT 1 FROM forum_image_links l LEFT JOIN forum_drafts d ON d.id=l.draft_id "
            "LEFT JOIN forum_posts p ON p.id=l.post_id WHERE l.image_id=i.id "
            "AND (d.author_qq_id=? OR p.author_qq_id=?)))", (image_id, owner, owner, owner),
        ) as cursor:
            if not await cursor.fetchone():
                raise ValueError("正文或封面引用了不存在或无权使用的图片，请重新上传。")
    column, content_id = ("draft_id", draft_id) if draft_id is not None else ("post_id", post_id)
    await db.execute(f"DELETE FROM forum_image_links WHERE {column}=?", (content_id,))
    await db.executemany(
        f"INSERT INTO forum_image_links(image_id,{column}) VALUES(?,?)",
        [(image_id, content_id) for image_id in ids],
    )


@forum_image_api.post("/forum/images")
@member_required
async def upload_forum_image():
    files = await request.files
    upload = files.get("image")
    if upload is None:
        return jsonify({"message": "请选择图片文件。"}), 400
    contents = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(contents) > MAX_IMAGE_BYTES:
        return jsonify({"message": "上传图片不能超过 5 MB。"}), 413
    try:
        data, width, height = await asyncio.to_thread(normalize_image, contents)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    owner = request.web_identity["qq_id"]
    image_id = secrets.token_hex(16)
    upload_dir = Path(current_app.config["FORUM_UPLOAD_DIR"])
    path = upload_dir / f"{image_id}.webp"
    db = await get_db()
    written = False
    try:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT COALESCE(SUM(size_bytes),0) AS bytes,COUNT(*) AS count FROM forum_images WHERE owner_qq_id=?", (owner,),
        ) as cursor:
            usage = await cursor.fetchone()
        if usage["bytes"] + len(data) > MAX_USER_BYTES or usage["count"] >= 1000:
            return jsonify({"message": "图片存储已达账号上限，请联系管理员。"}), 400
        upload_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        written = True
        await db.execute(
            "INSERT INTO forum_images(id,owner_qq_id,width,height,size_bytes,created_at) VALUES(?,?,?,?,?,?)",
            (image_id, owner, width, height, len(data), int(time.time())),
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        if written:
            path.unlink(missing_ok=True)
        raise
    finally:
        await db.close()
    return jsonify({"id": image_id, "url": image_url(image_id), "width": width, "height": height, "size_bytes": len(data)}), 201


@forum_image_api.get("/forum/images/<image_id>")
async def read_forum_image(image_id):
    if not IMAGE_ID.fullmatch(image_id):
        abort(404)
    identity = await _session_identity()
    db = await get_db()
    try:
        async with db.execute(
            "SELECT i.owner_qq_id,EXISTS(SELECT 1 FROM forum_image_links l JOIN forum_posts p ON p.id=l.post_id "
            "WHERE l.image_id=i.id AND p.status='published') AS published,"
            "EXISTS(SELECT 1 FROM forum_image_links l JOIN forum_posts p ON p.id=l.post_id "
            "WHERE l.image_id=i.id AND p.status<>'removed') AS submitted,"
            "EXISTS(SELECT 1 FROM forum_image_links l LEFT JOIN forum_drafts d ON d.id=l.draft_id "
            "LEFT JOIN forum_posts p ON p.id=l.post_id WHERE l.image_id=i.id "
            "AND (d.author_qq_id=? OR p.author_qq_id=?)) AS referenced_by_viewer "
            "FROM forum_images i WHERE i.id=?",
            (identity["qq_id"] if identity else None, identity["qq_id"] if identity else None, image_id),
        ) as cursor:
            image = await cursor.fetchone()
        private_access = image and identity and not identity["must_change_password"] and (
            image["owner_qq_id"] is not None and identity["qq_id"] == image["owner_qq_id"]
            or image["referenced_by_viewer"]
            or identity["role"] in {"admin", "root"} and image["submitted"]
        )
        if not image or not (image["published"] or private_access):
            abort(404)
    finally:
        await db.close()
    response = await send_from_directory(current_app.config["FORUM_UPLOAD_DIR"], f"{image_id}.webp", conditional=False)
    # A moderation decision or deletion must take effect on subsequent requests.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Content-Type"] = "image/webp"
    return response
