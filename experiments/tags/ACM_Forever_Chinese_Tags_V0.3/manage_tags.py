#!/usr/bin/env python3
"""独立人工标签工具；不调用 API，不修改自动预测。"""
import argparse
import json
import sys

from tag_management import TagManager
from tag_management.service import DEFAULT_OVERRIDES


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--auto-file", help="明确指定 merged_results.jsonl 或 predictions.jsonl；默认读取来源配置")
    p.add_argument("--overrides", help="独立人工 JSONL 历史文件，默认跟随所选存储")
    p.add_argument("--actor", default="local_admin", help="操作人；本地工具不承担管理员身份认证")
    p.add_argument("--reason", default="", help="修改原因，建议填写")
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("show", "history", "reset", "undo", "verify"):
        sub.add_parser(command).add_argument("problem_key")
    for command in ("add", "remove"):
        s = sub.add_parser(command)
        s.add_argument("problem_key"); s.add_argument("tags", nargs="+")
    s = sub.add_parser("replace")
    s.add_argument("problem_key"); s.add_argument("old_tag"); s.add_argument("new_tag")
    sub.add_parser("list")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        manager = TagManager(args.auto_file, args.overrides)
        if args.command == "show":
            result = {"message": "题目标签：自动结果、人工覆盖和最终有效标签", **manager.get_effective_tags(args.problem_key)}
        elif args.command == "history":
            result = {"message": "人工操作历史（包含撤销记录）", "history": manager.history(args.problem_key)}
        elif args.command == "list":
            result = {"message": "存在人工覆盖或完整确认的题目", "problems": manager.list_overrides()}
        else:
            tags = [args.old_tag, args.new_tag] if args.command == "replace" else getattr(args, "tags", [])
            result = manager.change(args.problem_key, args.command, tags, actor=args.actor, reason=args.reason)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        # Only local validation/storage exceptions; credentials/SDK are never loaded.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "文件读取或存储失败，请检查路径、权限和 JSONL 结构"
        print("操作失败：" + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
