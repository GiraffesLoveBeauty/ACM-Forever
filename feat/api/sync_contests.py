"""Backfill contest dates from public catalogs without collecting problem statements."""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import aiohttp

from .acm_api.contest_metadata import contest_metadata, fetch_contests, save_contests
from .acm_api.cf_client import CFUnavailable
from .acm_api.database import connect_db


async def synchronize(database, platform, input_path=None):
    db = await connect_db(database)
    results = {}
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "ACM-Forever-DataCollector/0.1"},
                                         timeout=aiohttp.ClientTimeout(total=30)) as session:
            for selected in (("codeforces", "atcoder") if platform == "all" else (platform,)):
                payload = json.loads(input_path.read_text(encoding="utf-8-sig")) if input_path else await fetch_contests(session, selected)
                results[selected] = await save_contests(db, contest_metadata(selected, payload))
    finally:
        await db.close()
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="补全比赛名称与开始时间；只更新比赛元数据，不采集题面")
    parser.add_argument("--database", type=Path, default=Path(os.getenv("ACM_DATABASE_PATH", "./data/acm_forever.db")))
    parser.add_argument("--platform", choices=("codeforces", "atcoder", "all"), default="all")
    parser.add_argument("--input", type=Path, help="导入已下载的原始比赛 JSON，须指定单个平台")
    args = parser.parse_args(argv)
    if args.input and args.platform == "all":
        parser.error("--input 须同时指定 --platform codeforces 或 atcoder")
    try:
        result = asyncio.run(synchronize(args.database.expanduser(), args.platform, args.input))
    except (OSError, ValueError, sqlite3.Error, aiohttp.ClientError, CFUnavailable) as error:
        print(f"比赛元数据同步失败：{error}", file=sys.stderr)
        return 1
    print(json.dumps({"database": str(args.database.resolve()), "updated": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
