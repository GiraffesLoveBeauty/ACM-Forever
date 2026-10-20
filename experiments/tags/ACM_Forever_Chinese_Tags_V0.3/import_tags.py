#!/usr/bin/env python3
"""离线导入题目及既有自动标签，不生成 AI 请求。"""
import argparse
import json
from pathlib import Path

from annotation_api.storage import read_jsonl
from problem_processing.adapter import read_problems
from problem_processing.repository import Repository, jsonl_write
from tag_management.storage import Journal


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--annotations")
    p.add_argument("--platform", choices=["codeforces", "atcoder", "nowcoder"])
    p.add_argument("--limit", type=int)
    p.add_argument("--data-root")
    p.add_argument("--migrate-manual", help="可选：复制已有人工历史，绝不覆盖不同记录")
    args = p.parse_args(argv)
    try:
        rows = read_problems(args.input)
        if args.platform:
            rows = [r for r in rows if r.get("platform", str(r.get("problem_key", "")).split(":")[0]) == args.platform]
        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("limit 必须大于零")
            rows = rows[:args.limit]
        repo = Repository(args.data_root)
        history = None
        if args.migrate_manual:
            history, _ = Journal(args.migrate_manual).read()
            dest = repo.root / "manual" / "overrides.jsonl"
            if dest.exists() and read_jsonl(dest) != history:
                raise ValueError("目标人工历史不同，拒绝覆盖")
        result = repo.import_records(rows, read_jsonl(args.annotations) if args.annotations else [])
        if history is not None:
            dest = repo.root / "manual" / "overrides.jsonl"
            journal = Journal(dest)
            with journal.locked():
                if dest.exists() and read_jsonl(dest) != history:
                    raise ValueError("人工历史已被其他进程更新，拒绝覆盖")
                if not dest.exists():
                    jsonl_write(dest, history)
            result["manual_events_copied"] = len(history)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("导入失败：" + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
