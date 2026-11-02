"""Shared Markdown source contract; no HTML-to-source round trip or remote fetching."""

import re
from urllib.parse import urlsplit

TITLE_LIMIT = 120
BODY_LIMIT = 20000
FILE_LIMIT = 100 * 1024
ASSET_RE = re.compile(
    r"(?:!\[[^\]\n]*\]\(\s*<?|<img\b[^>]*\bsrc=[\"'])(?:https?://[^/\s<>\"']+)?(/api/markdown/assets/([a-f0-9]{32}))",
    re.I,
)


class ContentError(ValueError):
    pass


def source_fields(data):
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("title", ""), str)
        or not isinstance(data.get("body", ""), str)
    ):
        raise ContentError("标题和正文必须是文本。")
    title, body = data.get("title", "").strip(), data.get("body", "").replace(
        "\r\n", "\n"
    ).replace("\r", "\n").lstrip("\ufeff")
    if len(title) > TITLE_LIMIT:
        raise ContentError("标题不能超过 120 个字符。")
    if len(body) > BODY_LIMIT:
        raise ContentError("正文不能超过 20000 个字符。")
    return title, body


def export_markdown(title, body, origin):
    # Treat the title as text, keeping a single generated H1 and the source body intact.
    title = re.sub(r"([\\`*_{}\[\]()<>#+.!&|~-])", r"\\\1", title.replace("\n", " "))
    if not re.fullmatch(r"https?://[^/\s]+", origin):
        raise ContentError("请配置有效的公开站点地址。")
    body = re.sub(
        r"(?<![\w/])(/api/(?:markdown/assets|forum/images)/[a-f0-9]{32})", lambda m: origin + m[1], body
    )
    return "# " + title + "\n\n" + body + ("" if body.endswith("\n") else "\n")


async def asset_public(db, asset_id):
    query = """SELECT 1 FROM markdown_asset_references a
 LEFT JOIN wiki_revisions r ON a.document_type='wiki' AND r.id=a.revision_id AND r.page_id=a.document_id
 LEFT JOIN wiki_pages p ON p.id=r.page_id
 LEFT JOIN wiki_categories c ON c.id=p.category_id
 LEFT JOIN wiki_categories top ON top.id=c.parent_id
 LEFT JOIN forum_posts f ON a.document_type='forum_post' AND f.id=a.document_id
 WHERE a.asset_id=? AND (r.published_at IS NOT NULL AND r.hidden=0 AND c.deleted_at IS NULL AND top.id IS NOT NULL AND top.deleted_at IS NULL OR f.status='published') LIMIT 1"""
    return bool(await (await db.execute(query, (asset_id,))).fetchone())


async def record_assets(db, body, kind, document_id, revision_id, actor):
    assets = {m[2] for m in ASSET_RE.finditer(body)}
    for asset_id in assets:
        row = await (
            await db.execute("SELECT * FROM markdown_assets WHERE id=?", (asset_id,))
        ).fetchone()
        if not row or not (
            row["owner"] == actor
            and row["document_type"] == "forum_draft"
            or kind == "wiki"
            and row["document_type"] == "wiki"
            or await asset_public(db, asset_id)
        ):
            raise ContentError("图片资源不存在或无权引用，请重新上传。")
    await db.execute(
        "DELETE FROM markdown_asset_references WHERE document_type=? AND document_id=? AND revision_id=?",
        (kind, document_id, revision_id),
    )
    for asset_id in assets:
        await db.execute(
            "INSERT INTO markdown_asset_references VALUES(?,?,?,?)",
            (asset_id, kind, document_id, revision_id),
        )
