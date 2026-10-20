#!/usr/bin/env python3
"""标签/翻译离线备份、校验和隔离恢复；不会调用 AI。"""
import argparse
import json

from label_pipeline import BASE
from problem_processing.backup import create_backup, list_backups, restore_backup, verify_backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="创建并校验备份")
    create.add_argument("--data-root")
    create.add_argument("--backup-root", help="仓库外备份根目录，或设置 TAG_BACKUP_ROOT")
    create.add_argument("--request-root", default=str(BASE / "cache"), help="仅读取标注缓存的状态字段")
    create.add_argument("--no-annotation-requests", action="store_true", help="仅备份持久数据，明确跳过实验请求状态")
    listing = commands.add_parser("list", help="列出备份与完整性")
    listing.add_argument("--backup-root")
    for name in ("verify", "summary", "restore"):
        command = commands.add_parser(name)
        command.add_argument("backup")
        if name == "restore":
            command.add_argument("--destination", required=True, help="必须为不存在的隔离目录")
            command.add_argument("--generation", help="可选的历史目录版本；人工历史仍完整保留")
            command.add_argument("--active-root", help="额外保护的数据根目录")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_backup(args.data_root, args.backup_root,
                                   request_root=None if args.no_annotation_requests else args.request_root)
        elif args.command == "list":
            result = list_backups(args.backup_root)
        elif args.command == "restore":
            result = restore_backup(args.backup, args.destination, generation=args.generation, active_root=args.active_root)
        else:
            result = verify_backup(args.backup)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError):
        # Raw exception text may include untrusted fields or OS paths containing credentials.
        print("操作失败：数据、路径、版本或完整性检查未通过；未覆盖原数据。请检查清单和本地目录。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
