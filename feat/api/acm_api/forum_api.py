"""Public discussion forum API and authenticated member actions."""
import time
from datetime import datetime, timedelta, timezone

from quart import Blueprint, jsonify, request

from .backend_api import (
    _fetch_leaderboard,
    _leaderboard_options,
    _session_identity,
    admin_required,
    get_db,
    member_required,
)
from .mobile_profiles import prepare_public_profiles

forum_api = Blueprint("forum_api", __name__)


async def _viewer_id():
    identity = await _session_identity()
    return str(identity.get("qq_id") or "") if identity else ""


@forum_api.get("/community/leaderboard")
async def community_leaderboard():
    return await public_leaderboard()


async def public_leaderboard(include_public_id=False):
    days, page, page_size, sort_key, search, platforms = _leaderboard_options(request.args)
    period = str(request.args.get("period", "")).strip().lower()
    if period not in {"", "today"}:
        return jsonify({"message": "统计周期无效。"}), 400
    positive_only = request.args.get("positive_only", "0") == "1"
    start_time = end_time = None
    if period == "today":
        midnight = datetime.now(timezone(timedelta(hours=8))).replace(hour=0, minute=0, second=0, microsecond=0)
        start_time, end_time = int(midnight.timestamp()), int((midnight + timedelta(days=1)).timestamp())
    db = await get_db()
    try:
        rows, _ = await _fetch_leaderboard(db, days, 1, 0, sort_key, "", platforms, paginate=False, start_time=start_time, end_time=end_time)
        if positive_only:
            rows = [row for row in rows if row["total_count"] > 0]
        for row in rows:
            if not row.get("name") or str(row.get("name")) == str(row.get("qq_id")):
                row["name"] = "ACM 成员"
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in str(row.get("name") or "").casefold() or needle in str(row.get("status") or "").casefold()]
        total = len(rows)
        page = page if page <= max(1, (total + page_size - 1) // page_size) else 1
        start = (page - 1) * page_size
        public_rows = [
            {key: row.get(key) for key in (
                "name", "avatar_url", "status", "cf_count", "luogu_count", "nowcoder_count",
                "atcoder_count", "cjlu_count", "total_count",
            )}
            for row in rows[start:start + page_size]
        ]
        if include_public_id and public_rows:
            await prepare_public_profiles(db)
            selected = rows[start:start + page_size]
            placeholders = ",".join("?" for _ in selected)
            async with db.execute(
                f"SELECT qq_id,public_member_id FROM mobile_public_profiles WHERE qq_id IN ({placeholders})",
                tuple(row["qq_id"] for row in selected),
            ) as cursor:
                identities = {row["qq_id"]: row["public_member_id"] for row in await cursor.fetchall()}
            for public, source in zip(public_rows, selected):
                public["public_member_id"] = identities[source["qq_id"]]
        return jsonify({
            "rows": public_rows, "total": total, "page": page, "page_size": page_size,
            "days": days, "sort": sort_key, "search": search, "platforms": list(platforms),
            "period": period, "positive_only": positive_only,
            "timezone": "Asia/Shanghai" if period == "today" else None,
            "start_time": start_time, "end_time": end_time,
        })
    finally:
        await db.close()


@forum_api.get("/forum/categories")
async def categories():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT c.id,c.slug,c.name,c.description,"
            "(SELECT COUNT(*) FROM forum_posts p WHERE p.category_id=c.id AND p.status='published') AS post_count "
            "FROM forum_categories c ORDER BY c.sort_order,c.id"
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@forum_api.get("/forum/posts")
async def posts():
    return await public_posts()


async def public_posts(author_qq_id=None):
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(30, max(5, int(request.args.get("page_size", "12"))))
    except (TypeError, ValueError):
        return jsonify({"message": "分页参数无效。"}), 400
    sort = str(request.args.get("sort", "latest")).strip().lower()
    if sort not in {"latest", "hot", "unanswered"}:
        sort = "latest"
    query = str(request.args.get("q", "")).strip()[:100]
    category = str(request.args.get("category", "")).strip()[:48]
    where = ["p.status='published'"]
    params = []
    if query:
        where.append("(p.title LIKE ? OR p.body LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if category:
        where.append("c.slug=?")
        params.append(category)
    if author_qq_id is not None:
        where.append("p.author_qq_id=?")
        params.append(author_qq_id)
    where_sql = " AND ".join(where)
    order_sql = {
        "latest": "p.is_pinned DESC,p.created_at DESC,p.id DESC",
        "hot": "p.is_pinned DESC,(likes_count*3+comments_count*2+p.views_count)*1.0/MAX(2,(CAST(strftime('%s','now') AS INTEGER)-p.created_at)/3600+2) DESC,p.created_at DESC",
        "unanswered": "p.is_pinned DESC,comments_count ASC,p.created_at DESC",
    }[sort]
    viewer = await _viewer_id()
    db = await get_db()
    try:
        async with db.execute(
            "SELECT COUNT(*) FROM forum_posts p JOIN forum_categories c ON c.id=p.category_id WHERE " + where_sql,
            tuple(params),
        ) as cursor:
            total = int((await cursor.fetchone())[0])
        sql = (
            "SELECT p.id,p.title,substr(p.body,1,420) AS excerpt,p.created_at,p.updated_at,p.is_pinned,p.views_count,"
            "c.slug AS category_slug,c.name AS category_name,CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS author_name,u.avatar_url AS author_avatar_url,"
            "(SELECT COUNT(*) FROM forum_post_likes l WHERE l.post_id=p.id) AS likes_count,"
            "(SELECT COUNT(*) FROM forum_comments cm WHERE cm.post_id=p.id AND cm.status='published') AS comments_count,"
            "EXISTS(SELECT 1 FROM forum_post_likes vl WHERE vl.post_id=p.id AND vl.qq_id=?) AS viewer_liked,"
            "EXISTS(SELECT 1 FROM forum_bookmarks vb WHERE vb.post_id=p.id AND vb.qq_id=?) AS viewer_bookmarked "
            "FROM forum_posts p JOIN forum_categories c ON c.id=p.category_id "
            "JOIN users u ON u.qq_id=p.author_qq_id WHERE " + where_sql +
            " ORDER BY " + order_sql + " LIMIT ? OFFSET ?"
        )
        async with db.execute(sql, (viewer, viewer, *params, page_size, (page - 1) * page_size)) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        return jsonify({"rows": rows, "total": total, "page": page, "page_size": page_size})
    finally:
        await db.close()


@forum_api.get("/forum/posts/<int:post_id>")
async def post_detail(post_id):
    viewer = await _viewer_id()
    db = await get_db()
    try:
        async with db.execute(
            "SELECT p.id,p.title,p.body,p.created_at,p.updated_at,p.views_count,p.is_pinned,"
            "c.slug AS category_slug,c.name AS category_name,CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS author_name,u.avatar_url AS author_avatar_url,"
            "(SELECT COUNT(*) FROM forum_post_likes l WHERE l.post_id=p.id) AS likes_count,"
            "EXISTS(SELECT 1 FROM forum_post_likes vl WHERE vl.post_id=p.id AND vl.qq_id=?) AS viewer_liked,"
            "EXISTS(SELECT 1 FROM forum_bookmarks vb WHERE vb.post_id=p.id AND vb.qq_id=?) AS viewer_bookmarked "
            "FROM forum_posts p JOIN users u ON u.qq_id=p.author_qq_id "
            "JOIN forum_categories c ON c.id=p.category_id WHERE p.id=? AND p.status='published'",
            (viewer, viewer, post_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return jsonify({"message": "帖子不存在或尚未通过审核。"}), 404
        await db.execute("UPDATE forum_posts SET views_count=views_count+1 WHERE id=?", (post_id,))
        await db.commit()
        async with db.execute(
            "SELECT cm.id,cm.parent_id,cm.body,cm.created_at,"
            "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS author_name,u.avatar_url AS author_avatar_url "
            "FROM forum_comments cm JOIN users u ON u.qq_id=cm.author_qq_id "
            "WHERE cm.post_id=? AND cm.status='published' ORDER BY cm.created_at,cm.id LIMIT 500",
            (post_id,),
        ) as cursor:
            comments = [dict(item) for item in await cursor.fetchall()]
        result = dict(row)
        result["comments"] = comments
        result["views_count"] = int(result["views_count"] or 0) + 1
        return jsonify(result)
    finally:
        await db.close()


@forum_api.get("/forum/mine/posts")
@member_required
async def my_posts():
    qq_id = request.web_identity["qq_id"]
    db = await get_db()
    try:
        async with db.execute(
            "SELECT p.id,p.title,p.status,p.created_at,p.updated_at,c.name AS category_name "
            "FROM forum_posts p JOIN forum_categories c ON c.id=p.category_id "
            "WHERE p.author_qq_id=? AND p.status<>'removed' ORDER BY p.created_at DESC LIMIT 100",
            (qq_id,),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


def _draft_fields(data):
    if not isinstance(data, dict):
        return None, "请求格式无效。"
    title_value = data.get("title", "")
    body_value = data.get("body", "")
    if not isinstance(title_value, str) or not isinstance(body_value, str):
        return None, "标题和正文必须是文本。"
    title = title_value.strip()
    body = body_value
    if len(title) > 120:
        return None, "标题不能超过 120 个字符。"
    if len(body) > 20000:
        return None, "正文不能超过 20000 个字符。"
    category_value = data.get("category_id")
    if category_value in (None, "", 0, "0"):
        category_id = None
    else:
        try:
            category_id = int(category_value)
        except (TypeError, ValueError):
            return None, "请选择有效的帖子分类。"
        if category_id <= 0:
            return None, "请选择有效的帖子分类。"
    return {"title": title, "body": body, "category_id": category_id}, None


@forum_api.get("/forum/drafts")
@member_required
async def forum_drafts():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT d.id,d.title,d.category_id,c.name AS category_name,d.created_at,d.updated_at "
            "FROM forum_drafts d LEFT JOIN forum_categories c ON c.id=d.category_id "
            "WHERE d.author_qq_id=? ORDER BY d.updated_at DESC,d.id DESC LIMIT 100",
            (request.web_identity["qq_id"],),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@forum_api.post("/forum/drafts")
@member_required
async def create_forum_draft():
    data, error = _draft_fields(await request.get_json(silent=True) or {})
    if error:
        return jsonify({"message": error}), 400
    db = await get_db()
    try:
        if data["category_id"] is not None:
            async with db.execute("SELECT 1 FROM forum_categories WHERE id=?", (data["category_id"],)) as cursor:
                if not await cursor.fetchone():
                    return jsonify({"message": "请选择有效的帖子分类。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "INSERT INTO forum_drafts(author_qq_id,category_id,title,body,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (request.web_identity["qq_id"], data["category_id"], data["title"], data["body"], now, now),
        )
        await db.commit()
        return jsonify({"id": cursor.lastrowid, "updated_at": now, "message": "草稿已保存。"}), 201
    finally:
        await db.close()


@forum_api.get("/forum/drafts/<int:draft_id>")
@member_required
async def get_forum_draft(draft_id):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT d.id,d.category_id,d.title,d.body,d.created_at,d.updated_at "
            "FROM forum_drafts d WHERE d.id=? AND d.author_qq_id=?",
            (draft_id, request.web_identity["qq_id"]),
        ) as cursor:
            draft = await cursor.fetchone()
        if not draft:
            return jsonify({"message": "草稿不存在。"}), 404
        return jsonify(dict(draft))
    finally:
        await db.close()


@forum_api.put("/forum/drafts/<int:draft_id>")
@member_required
async def update_forum_draft(draft_id):
    data, error = _draft_fields(await request.get_json(silent=True) or {})
    if error:
        return jsonify({"message": error}), 400
    db = await get_db()
    try:
        if data["category_id"] is not None:
            async with db.execute("SELECT 1 FROM forum_categories WHERE id=?", (data["category_id"],)) as cursor:
                if not await cursor.fetchone():
                    return jsonify({"message": "请选择有效的帖子分类。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "UPDATE forum_drafts SET category_id=?,title=?,body=?,updated_at=? "
            "WHERE id=? AND author_qq_id=?",
            (data["category_id"], data["title"], data["body"], now, draft_id, request.web_identity["qq_id"]),
        )
        if cursor.rowcount == 0:
            return jsonify({"message": "草稿不存在。"}), 404
        await db.commit()
        return jsonify({"id": draft_id, "updated_at": now, "message": "草稿已保存。"})
    finally:
        await db.close()


@forum_api.delete("/forum/drafts/<int:draft_id>")
@member_required
async def delete_forum_draft(draft_id):
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM forum_drafts WHERE id=? AND author_qq_id=?",
            (draft_id, request.web_identity["qq_id"]),
        )
        if cursor.rowcount == 0:
            return jsonify({"message": "草稿不存在。"}), 404
        await db.commit()
        return jsonify({"message": "草稿已删除。"})
    finally:
        await db.close()


@forum_api.post("/forum/drafts/<int:draft_id>/submit")
@member_required
async def submit_forum_draft(draft_id):
    qq_id = request.web_identity["qq_id"]
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id,category_id,title,body FROM forum_drafts WHERE id=? AND author_qq_id=?",
            (draft_id, qq_id),
        ) as cursor:
            draft = await cursor.fetchone()
        if not draft:
            return jsonify({"message": "草稿不存在。"}), 404
        title, body, category_id = draft["title"].strip(), draft["body"].strip(), draft["category_id"]
        if not 4 <= len(title) <= 120:
            return jsonify({"message": "标题长度需要在 4 到 120 个字符之间。"}), 400
        if not 5 <= len(body) <= 20000:
            return jsonify({"message": "正文长度需要在 5 到 20000 个字符之间。"}), 400
        if not category_id:
            return jsonify({"message": "请选择帖子分类后再提交。"}), 400
        async with db.execute("SELECT 1 FROM forum_categories WHERE id=?", (category_id,)) as cursor:
            if not await cursor.fetchone():
                return jsonify({"message": "请选择有效的帖子分类。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "INSERT INTO forum_posts(author_qq_id,category_id,title,body,status,created_at,updated_at) "
            "VALUES(?,?,?,?,'pending',?,?)",
            (qq_id, category_id, title, body, now, now),
        )
        post_id = cursor.lastrowid
        await db.execute("DELETE FROM forum_drafts WHERE id=? AND author_qq_id=?", (draft_id, qq_id))
        await db.commit()
        return jsonify({"id": post_id, "status": "pending", "message": "帖子已提交，审核通过后会出现在论坛。"}), 201
    finally:
        await db.close()


@forum_api.post("/forum/posts")
@member_required
async def create_post():
    data = await request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"message": "请求格式无效。"}), 400
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    try:
        category_id = int(data.get("category_id", 0))
    except (TypeError, ValueError):
        category_id = 0
    if not 4 <= len(title) <= 120:
        return jsonify({"message": "标题长度需要在 4 到 120 个字符之间。"}), 400
    if not 5 <= len(body) <= 20000:
        return jsonify({"message": "正文长度需要在 5 到 20000 个字符之间。"}), 400
    db = await get_db()
    try:
        async with db.execute("SELECT 1 FROM forum_categories WHERE id=?", (category_id,)) as cursor:
            if not await cursor.fetchone():
                return jsonify({"message": "请选择有效的帖子分类。"}), 400
        now = int(time.time())
        cursor = await db.execute(
            "INSERT INTO forum_posts(author_qq_id,category_id,title,body,status,created_at,updated_at) "
            "VALUES(?,?,?,?,'pending',?,?)",
            (request.web_identity["qq_id"], category_id, title, body, now, now),
        )
        await db.commit()
        return jsonify({"id": cursor.lastrowid, "status": "pending", "message": "帖子已提交，审核通过后会出现在论坛。"}), 201
    finally:
        await db.close()


@forum_api.post("/forum/posts/<int:post_id>/comments")
@member_required
async def create_comment(post_id):
    data = await request.get_json(silent=True) or {}
    body = str(data.get("body", "")).strip() if isinstance(data, dict) else ""
    if not 2 <= len(body) <= 5000:
        return jsonify({"message": "评论长度需要在 2 到 5000 个字符之间。"}), 400
    try:
        parent_id = int(data.get("parent_id") or 0) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        parent_id = 0
    db = await get_db()
    try:
        async with db.execute("SELECT 1 FROM forum_posts WHERE id=? AND status='published'", (post_id,)) as cursor:
            if not await cursor.fetchone():
                return jsonify({"message": "帖子不存在。"}), 404
        if parent_id:
            async with db.execute(
                "SELECT 1 FROM forum_comments WHERE id=? AND post_id=? AND parent_id IS NULL AND status='published'",
                (parent_id, post_id),
            ) as cursor:
                if not await cursor.fetchone():
                    return jsonify({"message": "回复目标不存在。"}), 404
        cursor = await db.execute(
            "INSERT INTO forum_comments(post_id,parent_id,author_qq_id,body,created_at) VALUES(?,?,?,?,?)",
            (post_id, parent_id or None, request.web_identity["qq_id"], body, int(time.time())),
        )
        await db.commit()
        return jsonify({"id": cursor.lastrowid, "success": True}), 201
    finally:
        await db.close()


async def _toggle_post_relation(table, post_id, qq_id):
    if table not in {"forum_post_likes", "forum_bookmarks"}:
        raise ValueError("Unsupported forum relation")
    db = await get_db()
    try:
        async with db.execute("SELECT 1 FROM forum_posts WHERE id=? AND status='published'", (post_id,)) as cursor:
            if not await cursor.fetchone():
                return None
        async with db.execute(f"SELECT 1 FROM {table} WHERE post_id=? AND qq_id=?", (post_id, qq_id)) as cursor:
            exists = await cursor.fetchone()
        if exists:
            await db.execute(f"DELETE FROM {table} WHERE post_id=? AND qq_id=?", (post_id, qq_id))
            active = False
        else:
            await db.execute(f"INSERT INTO {table}(post_id,qq_id,created_at) VALUES(?,?,?)", (post_id, qq_id, int(time.time())))
            active = True
        await db.commit()
        return active
    finally:
        await db.close()


@forum_api.post("/forum/posts/<int:post_id>/like")
@member_required
async def toggle_like(post_id):
    result = await _toggle_post_relation("forum_post_likes", post_id, request.web_identity["qq_id"])
    if result is None:
        return jsonify({"message": "帖子不存在。"}), 404
    return jsonify({"active": result})


@forum_api.post("/forum/posts/<int:post_id>/bookmark")
@member_required
async def toggle_bookmark(post_id):
    result = await _toggle_post_relation("forum_bookmarks", post_id, request.web_identity["qq_id"])
    if result is None:
        return jsonify({"message": "帖子不存在。"}), 404
    return jsonify({"active": result})


@forum_api.get("/forum/mine/bookmarks")
@member_required
async def my_bookmarks():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT p.id,p.title,p.created_at,c.name AS category_name,"
            "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS author_name,u.avatar_url AS author_avatar_url "
            "FROM forum_bookmarks b JOIN forum_posts p ON p.id=b.post_id "
            "JOIN forum_categories c ON c.id=p.category_id JOIN users u ON u.qq_id=p.author_qq_id "
            "WHERE b.qq_id=? AND p.status='published' ORDER BY b.created_at DESC LIMIT 100",
            (request.web_identity["qq_id"],),
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@forum_api.post("/forum/posts/<int:post_id>/report")
@member_required
async def report_post(post_id):
    data = await request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()[:500] if isinstance(data, dict) else ""
    if len(reason) < 3:
        return jsonify({"message": "请简单说明举报原因。"}), 400
    db = await get_db()
    try:
        async with db.execute("SELECT 1 FROM forum_posts WHERE id=? AND status='published'", (post_id,)) as cursor:
            if not await cursor.fetchone():
                return jsonify({"message": "帖子不存在。"}), 404
        await db.execute(
            "INSERT INTO forum_reports(post_id,reporter_qq_id,reason,created_at) VALUES(?,?,?,?)",
            (post_id, request.web_identity["qq_id"], reason, int(time.time())),
        )
        await db.commit()
        return jsonify({"success": True}), 201
    finally:
        await db.close()


@forum_api.delete("/forum/posts/<int:post_id>")
@member_required
async def remove_post(post_id):
    identity = request.web_identity
    db = await get_db()
    try:
        async with db.execute("SELECT author_qq_id FROM forum_posts WHERE id=?", (post_id,)) as cursor:
            post = await cursor.fetchone()
        if not post:
            return jsonify({"message": "帖子不存在。"}), 404
        if post["author_qq_id"] != identity["qq_id"] and identity["role"] not in {"admin", "root"}:
            return jsonify({"message": "无权删除这篇帖子。"}), 403
        await db.execute("UPDATE forum_posts SET status='removed',updated_at=? WHERE id=?", (int(time.time()), post_id))
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@forum_api.get("/forum/moderation/posts")
@admin_required
async def moderation_posts():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT p.id,p.title,p.body,p.created_at,c.name AS category_name,"
            "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS author_name "
            "FROM forum_posts p JOIN forum_categories c ON c.id=p.category_id "
            "JOIN users u ON u.qq_id=p.author_qq_id WHERE p.status='pending' ORDER BY p.created_at LIMIT 200"
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@forum_api.post("/forum/moderation/posts/<int:post_id>")
@admin_required
async def moderate_post(post_id):
    data = await request.get_json(silent=True) or {}
    decision = str(data.get("decision", "")).strip() if isinstance(data, dict) else ""
    if decision not in {"publish", "reject"}:
        return jsonify({"message": "审核操作无效。"}), 400
    status = "published" if decision == "publish" else "rejected"
    identity = await _session_identity()
    now = int(time.time())
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE forum_posts SET status=?,updated_at=?,reviewed_at=?,reviewed_by=? "
            "WHERE id=? AND status='pending'",
            (status, now, now, identity.get("qq_id"), post_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "帖子不存在或已处理。"}), 404
        return jsonify({"success": True, "status": status})
    finally:
        await db.close()


@forum_api.get("/forum/moderation/reports")
@admin_required
async def moderation_reports():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT r.id,r.post_id,r.reason,r.created_at,p.title,"
            "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS reporter_name "
            "FROM forum_reports r JOIN forum_posts p ON p.id=r.post_id "
            "JOIN users u ON u.qq_id=r.reporter_qq_id WHERE r.status='pending' ORDER BY r.created_at LIMIT 200"
        ) as cursor:
            return jsonify([dict(row) for row in await cursor.fetchall()])
    finally:
        await db.close()


@forum_api.post("/forum/moderation/reports/<int:report_id>")
@admin_required
async def moderate_report(report_id):
    data = await request.get_json(silent=True) or {}
    decision = str(data.get("decision", "")).strip() if isinstance(data, dict) else ""
    if decision not in {"resolve", "dismiss"}:
        return jsonify({"message": "处理操作无效。"}), 400
    identity = await _session_identity()
    status = "resolved" if decision == "resolve" else "dismissed"
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE forum_reports SET status=?,resolved_at=?,resolved_by=? WHERE id=? AND status='pending'",
            (status, int(time.time()), identity.get("qq_id"), report_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "举报不存在或已处理。"}), 404
        return jsonify({"success": True, "status": status})
    finally:
        await db.close()
