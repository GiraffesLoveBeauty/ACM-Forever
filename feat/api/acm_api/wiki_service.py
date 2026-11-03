"""Wiki transactions and immutable content revisions. Routes own commit/rollback."""

import hashlib
import json
import re
import secrets
import time
import unicodedata
from urllib.parse import urlsplit

from .markdown_content import record_assets, source_fields


class WikiError(ValueError):
    def __init__(self, message, code="invalid_request", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


async def rows(db, sql, args=()):
    return [dict(row) for row in await (await db.execute(sql, args)).fetchall()]


async def one(db, sql, args=()):
    row = await (await db.execute(sql, args)).fetchone()
    return dict(row) if row else None


async def settings(db):
    return await one(db, "SELECT * FROM wiki_settings WHERE id=1")


def integer(value, nullable=False):
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d{0,12}", str(value)):
        raise WikiError("请输入有效的编号或版本号。")
    return int(value)


def text(value, maximum, label, required=False):
    if (
        not isinstance(value, str)
        or len(value.strip()) > maximum
        or required
        and not value.strip()
    ):
        raise WikiError(
            f"{label}不能为空且长度不能超过 {maximum}。"
            if required
            else f"{label}格式或长度无效。"
        )
    return value.strip()


def version(data, current):
    if integer(data.get("version")) != current:
        raise WikiError(
            "内容已被其他管理员更新，请比较当前版本后重试；你的输入仍保留。",
            "version_conflict",
            409,
        )


async def category(db, category_id, child=False):
    row = await one(
        db,
        "SELECT * FROM wiki_categories WHERE id=? AND deleted_at IS NULL",
        (integer(category_id),),
    )
    if not row or child and row["parent_id"] is None:
        raise WikiError("分类不存在或层级不符合要求。", "category_unavailable", 404)
    return row


async def bump(db, public=False):
    await db.execute(
        "UPDATE wiki_settings SET navigation_version=navigation_version+1,public_content_version=public_content_version+? WHERE id=1",
        (int(public),),
    )


async def audit(db, actor, action, before, after):
    cur = await db.execute(
        "INSERT INTO wiki_category_operations(actor,action,before_json,after_json,created_at) VALUES(?,?,?,?,?)",
        (actor, action, encode(before), encode(after), int(time.time())),
    )
    return cur.lastrowid


async def navigation(db, admin=False):
    state = await settings(db)
    # Public reads never compute or materialize private draft statistics.
    draft_select = ", COALESCE(dc.draft_count,0) AS draft_count" if admin else ""
    draft_join = """
 LEFT JOIN (SELECT category_id,COUNT(*) draft_count FROM wiki_pages
 WHERE published_revision_id IS NULL OR draft_revision_id<>published_revision_id
 GROUP BY category_id) dc ON dc.category_id=c.id""" if admin else ""
    columns = "c.*" if admin else "c.id,c.parent_id,c.name,c.description,c.sort_order,c.version"
    categories = await rows(
        db,
        "SELECT " + columns + ", COALESCE(pc.published_count,0) AS published_count" + draft_select + """
 FROM wiki_categories c
 LEFT JOIN (SELECT p.category_id,COUNT(*) published_count
 FROM wiki_pages p JOIN wiki_revisions r ON r.id=p.published_revision_id
 WHERE r.hidden=0 GROUP BY p.category_id) pc ON pc.category_id=c.id""" + draft_join + """
 WHERE c.deleted_at IS NULL ORDER BY c.sort_order,c.id""",
    )
    totals = {}
    for child in categories:
        if child["parent_id"] is not None:
            total = totals.setdefault(child["parent_id"], [0, 0])
            total[0] += child["published_count"]
            if admin:
                total[1] += child["draft_count"]
    for top in categories:
        if top["parent_id"] is None:
            published, drafts = totals.get(top["id"], [0, 0])
            top["published_count"] = published
            if admin:
                top["draft_count"] = drafts
    result = {"categories": categories, **state}
    if admin:
        result["operations"] = await rows(
            db,
            "SELECT id,action,created_at,restored_at FROM wiki_category_operations WHERE action='delete' ORDER BY id DESC LIMIT 30",
        )
    return result


async def category_save(db, data, actor, category_id=None):
    state = await settings(db)
    version(data, state["navigation_version"])
    before = await category(db, category_id) if category_id else None
    parent = data.get("parent_id", before["parent_id"] if before else None)
    parent = integer(parent, nullable=True)
    if parent is not None:
        top = await category(db, parent)
        if top["parent_id"] is not None or category_id == parent:
            raise WikiError("小类只能归属有效的大类。")
    if before and (before["parent_id"] is None) != (parent is None):
        raise WikiError("不能将大类和小类互相转换；小类可以迁移到其他大类。")
    name = text(
        data.get("name", before["name"] if before else ""), 80, "分类名称", True
    )
    description = text(
        data.get("description", before["description"] if before else ""),
        2000,
        "分类简介",
    )
    key = unicodedata.normalize("NFKC", name).casefold()
    if before:
        await db.execute(
            "UPDATE wiki_categories SET parent_id=?,name=?,name_key=?,description=?,version=version+1 WHERE id=?",
            (parent, name, key, description, category_id),
        )
    else:
        cur = await db.execute(
            "INSERT INTO wiki_categories(parent_id,name,name_key,description,sort_order) VALUES(?,?,?,?,(SELECT COALESCE(MAX(sort_order),0)+1 FROM wiki_categories WHERE parent_id IS ? AND deleted_at IS NULL))",
            (parent, name, key, description, parent),
        )
        category_id = cur.lastrowid
        if parent is None and state["default_category_id"] is None:
            await db.execute(
                "UPDATE wiki_settings SET default_category_id=? WHERE id=1",
                (category_id,),
            )
    await bump(db, public=True)
    result = await category(db, category_id)
    await audit(db, actor, "edit" if before else "create", before, result)
    return result


async def order_categories(db, data, actor):
    version(data, (await settings(db))["navigation_version"])
    parent = integer(data.get("parent_id"), nullable=True)
    if parent is not None and (await category(db, parent))["parent_id"] is not None:
        raise WikiError("只能在同一父级内排序。")
    actual = await rows(
        db,
        "SELECT id FROM wiki_categories WHERE parent_id IS ? AND deleted_at IS NULL",
        (parent,),
    )
    ids = data.get("ids")
    if (
        not isinstance(ids, list)
        or any(type(i) is not int for i in ids)
        or len(ids) != len(set(ids))
        or set(ids) != {i["id"] for i in actual}
    ):
        raise WikiError("排序必须包含当前父级的完整分类集合。", "order_conflict", 409)
    for index, cid in enumerate(ids):
        await db.execute(
            "UPDATE wiki_categories SET sort_order=?,version=version+1 WHERE id=?",
            (index, cid),
        )
    await bump(db, True)
    await audit(db, actor, "order", actual, ids)
    return await navigation(db, True)


async def default_category(db, data, actor):
    state = await settings(db)
    version(data, state["navigation_version"])
    target = integer(data.get("default_category_id"), nullable=True)
    if target is not None and (await category(db, target))["parent_id"] is not None:
        raise WikiError("默认入口只能选择大类。")
    await db.execute(
        "UPDATE wiki_settings SET default_category_id=? WHERE id=1", (target,)
    )
    await bump(db, True)
    await audit(db, actor, "default", state["default_category_id"], target)
    return await settings(db)


async def delete_fingerprint(db):
    return fingerprint(
        {
            "settings": await settings(db),
            "categories": await rows(db, "SELECT * FROM wiki_categories ORDER BY id"),
            "pages": await rows(
                db, "SELECT id,category_id,version FROM wiki_pages ORDER BY id"
            ),
        }
    )


async def delete_preview(db, category_id, actor):
    item = await category(db, category_id)
    children = await rows(
        db,
        "SELECT id,name FROM wiki_categories WHERE parent_id=? AND deleted_at IS NULL",
        (category_id,),
    )
    ids = [category_id] + [c["id"] for c in children]
    pages = await rows(
        db,
        f"SELECT * FROM wiki_pages WHERE category_id IN ({','.join('?' for _ in ids)})",
        ids,
    )
    targets = await rows(
        db,
        "SELECT id,name FROM wiki_categories WHERE deleted_at IS NULL AND id<>? AND "
        + (
            "parent_id IS NULL"
            if item["parent_id"] is None
            else "parent_id IS NOT NULL"
        )
        + " ORDER BY sort_order,id",
        (category_id,),
    )
    token = secrets.token_urlsafe(24)
    await db.execute(
        "DELETE FROM wiki_delete_previews WHERE expires_at<?", (int(time.time()),)
    )
    await db.execute(
        "INSERT INTO wiki_delete_previews VALUES(?,?,?,?,?)",
        (
            token,
            actor,
            category_id,
            await delete_fingerprint(db),
            int(time.time()) + 300,
        ),
    )
    return {
        "token": token,
        "category": item,
        "children_count": len(children),
        "published_count": sum(p["published_revision_id"] is not None for p in pages),
        "draft_count": sum(
            p["published_revision_id"] is None
            or p["draft_revision_id"] != p["published_revision_id"]
            for p in pages
        ),
        "is_default": (await settings(db))["default_category_id"] == category_id,
        "targets": targets,
        "expires_in": 300,
    }


async def snapshot(db, category_ids, page_ids):
    cats = await rows(
        db,
        f"SELECT * FROM wiki_categories WHERE id IN ({','.join('?' for _ in category_ids)}) ORDER BY id",
        category_ids,
    )
    pages = await rows(
        db,
        f"SELECT id,category_id,version FROM wiki_pages WHERE category_id IN ({','.join('?' for _ in category_ids)})"
        + (f" OR id IN ({','.join('?' for _ in page_ids)})" if page_ids else "")
        + " ORDER BY id",
        [*category_ids, *page_ids],
    )
    return {"categories": cats, "pages": pages, "settings": await settings(db)}


async def delete_category(db, category_id, data, actor):
    preview = await one(
        db,
        "SELECT * FROM wiki_delete_previews WHERE token=? AND actor=? AND category_id=?",
        (text(data.get("token", ""), 100, "删除预览凭据", True), actor, category_id),
    )
    if (
        not preview
        or preview["expires_at"] < int(time.time())
        or preview["fingerprint"] != await delete_fingerprint(db)
    ):
        raise WikiError(
            "删除预览已过期或内容发生变化，请重新预览。", "preview_conflict", 409
        )
    item = await category(db, category_id)
    children = await rows(
        db,
        "SELECT * FROM wiki_categories WHERE parent_id=? AND deleted_at IS NULL",
        (category_id,),
    )
    direct = await rows(
        db, "SELECT id FROM wiki_pages WHERE category_id=?", (category_id,)
    )
    ids = [category_id] + [c["id"] for c in children]
    before = await snapshot(db, ids, [p["id"] for p in direct])
    target = data.get("target_id")
    if children or direct:
        target = await category(
            db, integer(target), child=item["parent_id"] is not None
        )
        if target["id"] in ids or (target["parent_id"] is None) != (
            item["parent_id"] is None
        ):
            raise WikiError("请选择同层级的有效接收分类。")
        if children:
            for child in children:
                await db.execute(
                    "UPDATE wiki_categories SET parent_id=?,version=version+1 WHERE id=?",
                    (target["id"], child["id"]),
                )
        else:
            await db.execute(
                "UPDATE wiki_pages SET category_id=?,version=version+1,updated_at=? WHERE category_id=?",
                (target["id"], int(time.time()), category_id),
            )
    state = await settings(db)
    if state["default_category_id"] == category_id:
        replacement = integer(data.get("default_category_id"), nullable=True)
        if (
            replacement == category_id
            or replacement is not None
            and (await category(db, replacement))["parent_id"] is not None
        ):
            raise WikiError("请选择有效的新默认大类，或明确选择无默认分类。")
        await db.execute(
            "UPDATE wiki_settings SET default_category_id=? WHERE id=1", (replacement,)
        )
    await db.execute(
        "UPDATE wiki_categories SET deleted_at=?,version=version+1 WHERE id=?",
        (int(time.time()), category_id),
    )
    await bump(db, True)
    after = await snapshot(db, ids, [p["id"] for p in before["pages"]])
    operation_id = await audit(db, actor, "delete", before, after)
    await db.execute("DELETE FROM wiki_delete_previews WHERE token=?", (data["token"],))
    return {"operation_id": operation_id, "message": "分类已删除，内容已按选择迁移。"}


async def restore_category(db, operation_id, actor):
    op = await one(
        db,
        "SELECT * FROM wiki_category_operations WHERE id=? AND action='delete'",
        (operation_id,),
    )
    if not op or op["restored_at"] is not None:
        raise WikiError("删除记录不存在或已恢复。", "restore_conflict", 409)
    before, after = json.loads(op["before_json"]), json.loads(op["after_json"])
    current = await snapshot(
        db, [c["id"] for c in after["categories"]], [p["id"] for p in after["pages"]]
    )
    if current != after:
        raise WikiError(
            "删除后分类或文章已变化，不能覆盖后续修改。", "restore_conflict", 409
        )
    for c in before["categories"]:
        await db.execute(
            "UPDATE wiki_categories SET parent_id=?,name=?,name_key=?,description=?,sort_order=?,deleted_at=?,version=version+1 WHERE id=?",
            (
                c["parent_id"],
                c["name"],
                c["name_key"],
                c["description"],
                c["sort_order"],
                c["deleted_at"],
                c["id"],
            ),
        )
    for p in before["pages"]:
        await db.execute(
            "UPDATE wiki_pages SET category_id=?,version=version+1,updated_at=? WHERE id=?",
            (p["category_id"], int(time.time()), p["id"]),
        )
    await db.execute(
        "UPDATE wiki_settings SET default_category_id=? WHERE id=1",
        (before["settings"]["default_category_id"],),
    )
    await bump(db, True)
    await db.execute(
        "UPDATE wiki_category_operations SET restored_at=? WHERE id=?",
        (int(time.time()), operation_id),
    )
    await audit(db, actor, "restore", after, before)
    return {"message": "分类与原内容归属已恢复。"}


def metadata(data):
    result = {
        key: text(data.get(key, ""), 2000, key)
        for key in ["summary", "source", "license"]
    }
    for key in ["tags", "aliases"]:
        value = data.get(key, [])
        if not isinstance(value, list) or len(value) > 30:
            raise WikiError("标签或别名最多 30 项。")
        result[key] = list(dict.fromkeys(text(v, 80, key, True) for v in value))
    exercises = data.get("exercises", [])
    if not isinstance(exercises, list) or len(exercises) > 30:
        raise WikiError("关联练习最多 30 项。")
    result["exercises"] = []
    for e in exercises:
        if not isinstance(e, dict):
            raise WikiError("练习格式无效。")
        url = text(e.get("url", ""), 1000, "练习地址", True)
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise WikiError("关联练习地址无效。")
        trusted = (
            parsed.scheme == "https"
            and not parsed.username
            and parsed.hostname
            and any(
                parsed.hostname == h or parsed.hostname.endswith("." + h)
                for h in [
                    "codeforces.com",
                    "atcoder.jp",
                    "luogu.com.cn",
                    "nowcoder.com",
                    "cjlu.edu.cn",
                ]
            )
        )
        if "\\" in url or not (
            trusted
            or parsed.path == "/problem.html"
            and not parsed.scheme
            and not parsed.netloc
        ):
            raise WikiError("关联练习仅支持站内题面或可信 OJ 的 HTTPS 地址。")
        result["exercises"].append(
            {"label": text(e.get("label", "练习"), 120, "练习名称", True), "url": url}
        )
    return result


async def page_record(db, page_id):
    result = await one(db, "SELECT * FROM wiki_pages WHERE id=?", (page_id,))
    if not result:
        raise WikiError("文章不存在。", "not_found", 404)
    return result


async def revision(db, revision_id, public=False):
    result = await one(
        db,
        "SELECT r.*,u.name maintainer FROM wiki_revisions r LEFT JOIN users u ON u.qq_id=r.author WHERE r.id=?",
        (revision_id,),
    )
    if not result or public and (result["published_at"] is None or result["hidden"]):
        raise WikiError("文章版本不存在或不可访问。", "not_found", 404)
    result.update(json.loads(result.pop("metadata")))
    if public:
        for internal in ["author", "parent_revision_id", "hidden"]:
            result.pop(internal, None)
        result["maintainer"] = (
            result["maintainer"]
            if result["maintainer"] and not str(result["maintainer"]).isdigit()
            else "Wiki 维护者"
        )
    return result


async def save_revision(db, page, data, actor):
    version(data, page["version"])
    if data.get("base_revision_id") != page["draft_revision_id"]:
        raise WikiError("基础修订已变化，请查看差异后再保存。", "version_conflict", 409)
    title, body = source_fields(data)
    meta = metadata(data)
    cur = await db.execute(
        "INSERT INTO wiki_revisions(page_id,parent_revision_id,title,body,metadata,author,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            page["id"],
            page["draft_revision_id"],
            title,
            body,
            encode(meta),
            actor,
            int(time.time()),
        ),
    )
    rid = cur.lastrowid
    await record_assets(db, body, "wiki", page["id"], rid, actor)
    await db.execute(
        "UPDATE wiki_pages SET draft_revision_id=?,version=version+1,updated_at=? WHERE id=?",
        (rid, int(time.time()), page["id"]),
    )
    return await edit_page(db, page["id"])


async def create_page(db, data, actor):
    cid = (await category(db, data.get("category_id"), True))["id"]
    slug = text(data.get("slug", ""), 100, "slug", True)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise WikiError("slug 仅支持小写字母、数字和单个连字符。")
    cur = await db.execute(
        "INSERT INTO wiki_pages(slug,category_id,created_at,updated_at) VALUES(?,?,?,?)",
        (slug, cid, int(time.time()), int(time.time())),
    )
    p = await page_record(db, cur.lastrowid)
    return await save_revision(
        db, p, {**data, "version": 1, "base_revision_id": None}, actor
    )


async def edit_page(db, page_id):
    p = await page_record(db, page_id)
    await category(db, p["category_id"], True)
    return {**p, "draft": await revision(db, p["draft_revision_id"])}


async def move_page(db, page_id, data, actor):
    p = await page_record(db, page_id)
    version(data, p["version"])
    cid = (await category(db, data.get("category_id"), True))["id"]
    await db.execute(
        "UPDATE wiki_pages SET category_id=?,version=version+1,updated_at=? WHERE id=?",
        (cid, int(time.time()), page_id),
    )
    await bump(db, True)
    await audit(db, actor, "page_move", p, await page_record(db, page_id))
    return await edit_page(db, page_id)


async def publish(db, revision_id, data, actor):
    r = await revision(db, revision_id)
    p = await page_record(db, r["page_id"])
    version(data, p["version"])
    await category(db, p["category_id"], True)
    if p["draft_revision_id"] != revision_id:
        raise WikiError("仅能发布当前草稿，请刷新版本。", "version_conflict", 409)
    if not r["title"].strip() or not r["body"].strip():
        raise WikiError("发布前请填写标题和正文。")
    if r["hidden"]:
        raise WikiError("该版本已隐藏，请基于它新建草稿后发布。")
    await db.execute(
        "UPDATE wiki_revisions SET published_at=COALESCE(published_at,?) WHERE id=?",
        (int(time.time()), revision_id),
    )
    await db.execute(
        "UPDATE wiki_pages SET published_revision_id=?,version=version+1,updated_at=? WHERE id=?",
        (revision_id, int(time.time()), p["id"]),
    )
    await db.execute(
        "INSERT OR REPLACE INTO wiki_search VALUES(?,?,?,?,?)",
        (
            p["id"],
            r["title"].casefold(),
            " ".join(r["aliases"]).casefold(),
            " ".join(r["tags"]).casefold(),
            r["body"].casefold(),
        ),
    )
    await bump(db, True)
    return await edit_page(db, p["id"])


async def restore_page(db, page_id, data, actor):
    p = await page_record(db, page_id)
    r = await revision(db, integer(data.get("revision_id")))
    if r["page_id"] != page_id:
        raise WikiError("修订不属于当前文章。", "not_found", 404)
    return await save_revision(
        db,
        p,
        {
            **r,
            "version": data.get("version"),
            "base_revision_id": data.get("base_revision_id"),
        },
        actor,
    )


async def hide_revision(db, revision_id, data, actor):
    r = await revision(db, revision_id)
    p = await page_record(db, r["page_id"])
    version(data, p["version"])
    if p["published_revision_id"] == revision_id:
        raise WikiError("当前公开版本不能隐藏，请先发布替代版本。")
    if type(data.get("hidden")) is not bool:
        raise WikiError("hidden 必须为布尔值。")
    await db.execute(
        "UPDATE wiki_revisions SET hidden=? WHERE id=?",
        (int(data["hidden"]), revision_id),
    )
    await db.execute("UPDATE wiki_pages SET version=version+1 WHERE id=?", (p["id"],))
    await bump(db, True)
    await audit(
        db, actor, "hide_revision", {"id": revision_id, "hidden": r["hidden"]}, data
    )
    return {"message": "历史版本可见性已更新。"}


async def public_page(db, slug, revision_id=None):
    p = await one(
        db,
        "SELECT p.* FROM wiki_pages p JOIN wiki_categories c ON c.id=p.category_id JOIN wiki_categories t ON t.id=c.parent_id WHERE p.slug=? AND p.published_revision_id IS NOT NULL AND c.deleted_at IS NULL AND t.deleted_at IS NULL",
        (slug,),
    )
    if not p:
        raise WikiError("文章不存在或尚未公开。", "not_found", 404)
    r = await revision(db, revision_id or p["published_revision_id"], True)
    if r["page_id"] != p["id"]:
        raise WikiError("版本不存在。", "not_found", 404)
    child = await category(db, p["category_id"], True)
    top = await category(db, child["parent_id"])
    return {
        **r,
        "slug": p["slug"],
        "category_id": child["id"],
        "path": [{"id": c["id"], "name": c["name"]} for c in [top, child]],
        "content_version": (await settings(db))["public_content_version"],
    }


def paging(query):
    try:
        page = int(query.get("page", 1))
        size = int(query.get("page_size", 20))
        if not 1 <= page <= 1000000 or not 1 <= size <= 50:
            raise ValueError()
    except (ValueError, TypeError):
        raise WikiError("分页参数无效，单页上限 50。")
    return page, size


def public_list_query(query, search=False):
    """Validate before cache lookup, preserving first-value/unknown-argument semantics."""
    page, size = paging(query)
    cid = integer(query["category_id"]) if query.get("category_id") else None
    q = text(query.get("q", ""), 100, "关键词")
    if search and not q:
        raise WikiError("请输入搜索关键词。")
    return {"page": page, "page_size": size, "category_id": cid, "q": q}


async def page_list(db, query, admin=False, search=False):
    parsed = public_list_query(query, search=search)
    page, size, cid, q = (parsed[k] for k in ("page", "page_size", "category_id", "q"))
    conditions = ["c.deleted_at IS NULL", "t.deleted_at IS NULL"]
    params = []
    if not admin:
        conditions += ["p.published_revision_id IS NOT NULL", "r.hidden=0"]
    if cid is not None:
        conditions.append("(c.id=? OR c.parent_id=?)")
        params.extend([cid, cid])
    if q:
        needle = (
            "%"
            + q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        columns = (
            ["r.title", "r.body", "r.metadata"]
            if admin
            else ["s.title", "s.aliases", "s.tags", "s.body"]
        )
        conditions.append(
            "(" + " OR ".join(col + " LIKE ? ESCAPE '\\'" for col in columns) + ")"
        )
        params.extend([needle] * len(columns))
    if admin and query.get("state"):
        if query["state"] == "draft":
            conditions.append(
                "(p.published_revision_id IS NULL OR p.draft_revision_id<>p.published_revision_id)"
            )
        elif query["state"] == "published":
            conditions.append("p.published_revision_id IS NOT NULL")
        else:
            raise WikiError("无效文章状态。")
    joins = (
        " FROM wiki_pages p JOIN wiki_categories c ON c.id=p.category_id JOIN wiki_categories t ON t.id=c.parent_id JOIN wiki_revisions r ON r.id=p."
        + ("draft_revision_id" if admin else "published_revision_id")
        + " LEFT JOIN wiki_search s ON s.page_id=p.id WHERE "
        + " AND ".join(conditions)
    )
    total = (await one(db, "SELECT COUNT(*) total" + joins, params))["total"]
    updated = "p.updated_at" if admin else "r.published_at"
    order = updated + " DESC,p.id DESC"
    order_args = []
    if q and not admin:
        order = (
            "CASE WHEN s.title LIKE ? ESCAPE '\\' THEN 0 WHEN s.aliases LIKE ? ESCAPE '\\' THEN 1 WHEN s.tags LIKE ? ESCAPE '\\' THEN 2 ELSE 3 END,"
            + order
        )
        order_args = [needle] * 3
    result = await rows(
        db,
        "SELECT p.id,p.slug,p.category_id,p.published_revision_id,p.draft_revision_id,p.version,"
        + updated
        + " updated_at,r.title,r.metadata,r.body,c.name category_name,t.name parent_name"
        + joins
        + " ORDER BY "
        + order
        + " LIMIT ? OFFSET ?",
        [*params, *order_args, size, (page - 1) * size],
    )
    for item in result:
        meta = json.loads(item.pop("metadata"))
        body = item.pop("body")
        pos = body.casefold().find(q.casefold()) if q else 0
        item.update(
            summary=meta["summary"],
            tags=meta["tags"],
            excerpt=body[max(0, pos - 40) : max(0, pos - 40) + 180],
        )
        if not admin:
            for key in ["id", "published_revision_id", "draft_revision_id", "version"]:
                item.pop(key, None)
    return {"items": result, "total": total, "page": page, "page_size": size}


async def idempotent(db, actor, operation, data, callback):
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 100:
        raise WikiError("请提供有效的幂等标识。")
    stamp = fingerprint(data)
    previous = await one(
        db,
        "SELECT * FROM wiki_requests WHERE actor=? AND operation=? AND key=?",
        (actor, operation, key),
    )
    if previous:
        if previous["fingerprint"] != stamp:
            raise WikiError("幂等标识已被用于其他内容。", "idempotency_conflict", 409)
        return json.loads(previous["response"])
    result = await callback()
    await db.execute(
        "INSERT INTO wiki_requests VALUES(?,?,?,?,?)",
        (actor, operation, key, stamp, encode(result)),
    )
    return result
