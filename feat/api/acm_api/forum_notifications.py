"""Private, durable forum feedback; event writes share the content transaction."""
import time

from quart import Blueprint, jsonify, request

from .backend_api import get_db, member_required

forum_notification_api = Blueprint("forum_notification_api", __name__)


async def add_notification(db, recipient, actor, kind, post_id, *, comment_id=None):
    await db.execute(
        "INSERT INTO forum_notifications(recipient_qq_id,actor_qq_id,kind,post_id,comment_id,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (recipient, actor, kind, post_id, comment_id, int(time.time())),
    )


@forum_notification_api.after_request
async def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.vary.add("Cookie")
    return response


@forum_notification_api.get("/me/notifications/count")
@member_required
async def unread_count():
    db = await get_db()
    try:
        async with db.execute(
            "SELECT COUNT(*) FROM forum_notifications WHERE recipient_qq_id=? AND read_at IS NULL",
            (request.web_identity["qq_id"],),
        ) as cursor:
            return jsonify({"unread_count": (await cursor.fetchone())[0]})
    finally:
        await db.close()


@forum_notification_api.get("/me/notifications")
@member_required
async def notifications():
    try:
        page = max(1, int(request.args.get("page", "1")))
        size = min(50, max(1, int(request.args.get("page_size", "20"))))
        if page > 1_000_000:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"message": "分页参数无效。"}), 400
    recipient = request.web_identity["qq_id"]
    where = "n.recipient_qq_id=?" + (" AND n.read_at IS NULL" if request.args.get("unread") == "1" else "")
    db = await get_db()
    try:
        await db.execute("BEGIN")
        async with db.execute(
            "SELECT COUNT(*) AS unread_count,COALESCE(MAX(id),0) AS latest_id FROM forum_notifications "
            "WHERE recipient_qq_id=? AND read_at IS NULL", (recipient,),
        ) as cursor:
            summary = dict(await cursor.fetchone())
        async with db.execute("SELECT COUNT(*) FROM forum_notifications n WHERE " + where, (recipient,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute(
            "SELECT n.id,n.kind,n.post_id,n.comment_id,n.created_at,n.read_at,p.status AS post_status,"
            "CASE WHEN p.status='published' OR p.author_qq_id=? THEN p.title ELSE '原话题已不可访问' END AS post_title,"
            "CASE WHEN p.author_qq_id=? AND n.kind='rejected' THEN p.review_reason ELSE '' END AS review_reason,"
            "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS actor_name,"
            "p.author_qq_id=? AS own_post,cm.status='published' AND (cm.parent_id IS NULL OR parent.status='published') AS comment_available "
            "FROM forum_notifications n JOIN forum_posts p ON p.id=n.post_id "
            "LEFT JOIN users u ON u.qq_id=n.actor_qq_id LEFT JOIN forum_comments cm ON cm.id=n.comment_id "
            "LEFT JOIN forum_comments parent ON parent.id=cm.parent_id WHERE " + where +
            " ORDER BY n.id DESC LIMIT ? OFFSET ?",
            (recipient, recipient, recipient, recipient, size, (page - 1) * size),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            row["target_url"] = None
            if row.pop("own_post") and row["kind"] in {"published", "rejected"}:
                row["target_url"] = f"/my-post.html?id={row['post_id']}"
            elif row["post_status"] == "published":
                row["target_url"] = (
                    f"/post.html?id={row['post_id']}&comment_id={row['comment_id']}#comment-{row['comment_id']}"
                    if row["comment_available"] else f"/post.html?id={row['post_id']}#comments"
                )
            row.pop("comment_available")
        return jsonify({"rows": rows, "total": total, "page": page, "page_size": size, **summary})
    finally:
        await db.close()


@forum_notification_api.post("/me/notifications/<int:notification_id>/read")
@member_required
async def read_notification(notification_id):
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE forum_notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND recipient_qq_id=?",
            (int(time.time()), notification_id, request.web_identity["qq_id"]),
        )
        if cursor.rowcount == 0:
            return jsonify({"message": "通知不存在。"}), 404
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()


@forum_notification_api.post("/me/notifications/read-all")
@member_required
async def read_all_notifications():
    data = await request.get_json(silent=True)
    through_id = data.get("through_id") if isinstance(data, dict) else None
    if type(through_id) is not int or not 0 <= through_id <= 9223372036854775807:
        return jsonify({"message": "请先刷新通知列表。"}), 400
    db = await get_db()
    try:
        await db.execute(
            "UPDATE forum_notifications SET read_at=? WHERE recipient_qq_id=? AND read_at IS NULL AND id<=?",
            (int(time.time()), request.web_identity["qq_id"], through_id),
        )
        await db.commit()
        return jsonify({"success": True})
    finally:
        await db.close()
