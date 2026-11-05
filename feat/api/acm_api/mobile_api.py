"""Versioned mobile contracts; all database access remains on the server."""
import time

from quart import Blueprint, jsonify, request

from .backend_api import get_db, member_required
from .forum_api import public_leaderboard, public_posts, post_detail as web_post_detail
from .mobile_profiles import prepare_public_profiles
from .account_closure_service import closed_author_sql
from .account_lifecycle_service import require_web_actor

mobile_api = Blueprint("mobile_api", __name__)
PLATFORMS = (
    ("codeforces", "cf_count"), ("luogu", "luogu_count"),
    ("nowcoder", "nowcoder_count"), ("atcoder", "atcoder_count"), ("cjlu", "cjlu_count"),
)


@mobile_api.get("/capabilities")
async def capabilities():
    return jsonify({"api_version": 1, "features": {
        "public_member_ids": True, "member_profiles": True, "member_posts": True,
        "own_public_profile": True, "edit_motto": True,
    }})


@mobile_api.get("/leaderboard")
async def leaderboard():
    return await public_leaderboard(include_public_id=True)


async def with_public_authors(response, detail=False):
    if isinstance(response, tuple) or response.status_code != 200:
        return response
    result = await response.get_json()
    rows = [result] if detail else result["rows"]
    if not rows:
        return response
    db = await get_db()
    try:
        await prepare_public_profiles(db)
        placeholders = ",".join("?" for _ in rows)
        async with db.execute(
            "SELECT p.id,mp.public_member_id FROM forum_posts p "
            "JOIN mobile_public_profiles mp ON mp.qq_id=p.author_qq_id "
            "JOIN users u ON u.qq_id=p.author_qq_id "
            f"WHERE NOT {closed_author_sql('forum_post', 'p')} AND mp.account_epoch=u.account_epoch "
            f"AND p.id IN ({placeholders})", tuple(row["id"] for row in rows),
        ) as cursor:
            authors = {row["id"]: row["public_member_id"] for row in await cursor.fetchall()}
        for row in rows:
            row["author_public_member_id"] = authors.get(row["id"])
        if detail and result["comments"]:
            comments = result["comments"]
            placeholders = ",".join("?" for _ in comments)
            async with db.execute(
                "SELECT cm.id,mp.public_member_id FROM forum_comments cm "
                "JOIN mobile_public_profiles mp ON mp.qq_id=cm.author_qq_id "
                "JOIN users u ON u.qq_id=cm.author_qq_id "
                f"WHERE NOT {closed_author_sql('forum_comment', 'cm')} AND mp.account_epoch=u.account_epoch "
                f"AND cm.id IN ({placeholders})", tuple(row["id"] for row in comments),
            ) as cursor:
                authors = {row["id"]: row["public_member_id"] for row in await cursor.fetchall()}
            for comment in comments:
                comment["author_public_member_id"] = authors.get(comment["id"])
        return jsonify(result)
    finally:
        await db.close()


@mobile_api.get("/forum/posts")
async def posts():
    return await with_public_authors(await public_posts())


@mobile_api.get("/forum/posts/<int:post_id>")
async def post_detail(post_id):
    return await with_public_authors(await web_post_detail(post_id), detail=True)


async def public_profile(db, *, public_id=None, qq_id=None):
    field, value = ("mp.public_member_id", public_id) if public_id is not None else ("u.qq_id", qq_id)
    counts = ",".join(
        f"COUNT(DISTINCT CASE WHEN s.platform='{platform}' THEN s.problem_id END) AS {alias}"
        for platform, alias in PLATFORMS
    )
    async with db.execute(
        "SELECT mp.public_member_id,mp.motto,u.avatar_url,u.status,"
        "CASE WHEN NULLIF(u.name,'') IS NULL OR u.name=u.qq_id THEN 'ACM 成员' ELSE u.name END AS name,"
        + counts + " FROM users u JOIN mobile_public_profiles mp ON mp.qq_id=u.qq_id "
        "LEFT JOIN submissions s ON s.user_qq_id=u.qq_id "
        f"WHERE {field}=? AND u.account_state='active' AND mp.account_epoch=u.account_epoch GROUP BY u.qq_id", (value,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    result = dict(row)
    result["platform_counts"] = {platform: result[alias] for platform, alias in PLATFORMS}
    result["total_count"] = sum(result["platform_counts"].values())
    return result


@mobile_api.get("/members/<public_member_id>")
async def member_profile(public_member_id):
    db = await get_db()
    try:
        result = await public_profile(db, public_id=public_member_id)
        if result is None:
            return jsonify({"message": "公开成员不存在。"}), 404
        return jsonify(result)
    finally:
        await db.close()


@mobile_api.get("/members/<public_member_id>/posts")
async def member_posts(public_member_id):
    db = await get_db()
    try:
        async with db.execute("SELECT mp.qq_id FROM mobile_public_profiles mp JOIN users u ON u.qq_id=mp.qq_id "
                              "WHERE mp.public_member_id=? AND u.account_state='active' AND mp.account_epoch=u.account_epoch", (public_member_id,)) as cursor:
            member = await cursor.fetchone()
        if member is None:
            return jsonify({"message": "公开成员不存在。"}), 404
    finally:
        await db.close()
    return await with_public_authors(await public_posts(author_qq_id=member["qq_id"]))


@mobile_api.route("/me/public-profile", methods=["GET", "PUT"])
@member_required
async def own_public_profile():
    qq_id = request.web_identity["qq_id"]
    motto = None
    if request.method == "PUT":
        data = await request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {"motto"} or not isinstance(data["motto"], str):
            return jsonify({"message": "仅允许提交文本座右铭 motto。"}), 400
        motto = data["motto"].strip()
        if len(motto) > 100:
            return jsonify({"message": "座右铭不能超过 100 个字符。"}), 400
    db = await get_db()
    try:
        await prepare_public_profiles(db)
        if motto is not None:
            await db.execute("BEGIN IMMEDIATE")
            await require_web_actor(db, request.web_identity)
            await db.execute("UPDATE mobile_public_profiles SET motto=?,updated_at=? WHERE qq_id=?", (motto, int(time.time()), qq_id))
            await db.commit()
        result = await public_profile(db, qq_id=qq_id)
        if result is None:
            return jsonify({"message": "成员资料不存在。"}), 404
        return jsonify(result)
    finally:
        await db.close()
