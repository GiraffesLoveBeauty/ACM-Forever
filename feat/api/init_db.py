"""Initialize the server SQLite schema without starting the HTTP service."""

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from .acm_api.database import connect_db


async def initialize(path):
    db = await connect_db(path)
    await db.close()
    print(f"数据库初始化完成：{path.resolve()}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="初始化服务端 SQLite 表结构，可重复执行，不清空已有数据")
    parser.add_argument("--database", type=Path, default=Path(os.getenv("ACM_DATABASE_PATH", "./data/acm_forever.db")),
                        help="数据库文件，默认读取 ACM_DATABASE_PATH")
    args = parser.parse_args(argv)
    try:
        asyncio.run(initialize(args.database.expanduser()))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"数据库初始化失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
