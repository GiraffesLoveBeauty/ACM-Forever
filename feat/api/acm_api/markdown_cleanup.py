"""Dry-run first maintenance for unreferenced Markdown images.

Run with the API stopped; all Wiki revisions (including hidden history) are retained.
Only registered assets inside the supplied persistent folder are considered.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from .database import connect_db


async def cleanup_assets(database, uploads, grace_days=7, apply=False, now=None):
    if not 7 <= grace_days <= 3650:
        raise ValueError("宽限期必须为 7–3650 天。")
    folder = Path(uploads).resolve()
    db = await connect_db(Path(database))
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            """SELECT a.* FROM markdown_assets a
 WHERE a.created_at < ? AND NOT EXISTS (
 SELECT 1 FROM markdown_asset_references x
 LEFT JOIN wiki_revisions r ON x.document_type='wiki' AND r.id=x.revision_id AND r.page_id=x.document_id
 LEFT JOIN forum_posts p ON x.document_type='forum_post' AND p.id=x.document_id
 LEFT JOIN forum_drafts d ON x.document_type='forum_draft' AND d.id=x.document_id
 WHERE x.asset_id=a.id AND (r.id IS NOT NULL OR p.id IS NOT NULL OR d.id IS NOT NULL))
 ORDER BY a.created_at,a.id""",
            (int(now if now is not None else time.time()) - grace_days * 86400,),
        )
        assets = [dict(row) for row in await cursor.fetchall()]
        for asset in assets:
            path = (folder / asset["storage_name"]).resolve()
            if path.parent != folder or path.name != asset["storage_name"]:
                raise ValueError("资源路径超出持久化目录，已停止清理。")
        if apply:
            # A second reference check is protected by this write transaction.
            # Keep metadata on file errors so maintenance can be retried.
            for asset in assets:
                (folder / asset["storage_name"]).unlink(missing_ok=True)
                await db.execute(
                    "DELETE FROM markdown_asset_references WHERE asset_id=?",
                    (asset["id"],),
                )
                await db.execute(
                    "DELETE FROM markdown_assets WHERE id=?", (asset["id"],)
                )
            await db.commit()
        else:
            await db.rollback()
        return {
            "applied": apply,
            "grace_days": grace_days,
            "assets": [
                {"id": a["id"], "storage_name": a["storage_name"], "size": a["size"]}
                for a in assets
            ],
        }
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--uploads", required=True, type=Path)
    parser.add_argument("--grace-days", type=int, default=7)
    parser.add_argument(
        "--apply", action="store_true", help="执行清理；省略时仅列出候选。"
    )
    args = parser.parse_args()
    if not args.database.is_file() or not args.uploads.is_dir():
        parser.error("数据库与持久化图片目录必须已存在。")
    result = asyncio.run(
        cleanup_assets(args.database, args.uploads, args.grace_days, args.apply)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
