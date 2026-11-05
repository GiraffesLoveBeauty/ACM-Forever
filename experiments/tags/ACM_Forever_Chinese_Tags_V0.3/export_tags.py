#!/usr/bin/env python3
"""导出有效题目元数据；不调用论坛接口。"""
import argparse
import json
from problem_processing.repository import Repository


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root")
    args = p.parse_args(argv)
    try:
        print(json.dumps(Repository(args.data_root).export(), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("导出失败：" + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
