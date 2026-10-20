#!/usr/bin/env python3
"""默认只预览；--mock 不读取密钥；真实调用只允许显式 --execute。"""
import argparse
import json
from annotation_api.config import Config
from problem_processing.adapter import read_problems, normalize
from problem_processing.translation import language_plan, translate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--platform", choices=["codeforces", "atcoder", "nowcoder"])
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--data-root")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--mock", action="store_true")
    modes.add_argument("--execute", action="store_true")
    p.add_argument("--provider", choices=["compatible", "openai"], default="compatible")
    p.add_argument("--model")
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--max-output-tokens", type=int, default=4000)
    args = p.parse_args(argv)
    args.max_retries, args.request_interval = 0, 1
    try:
        if args.limit < 1:
            raise ValueError("limit 必须大于零")
        rows = read_problems(args.input)
        rows = [r for r in rows if not args.platform or r.get("platform", str(r.get("problem_key", "")).split(":")[0]) == args.platform][:args.limit]
        cfg = Config.from_args(args) if args.execute else None
        calls = real_calls = 0
        for row in rows:
            problem = normalize(row)
            if not args.execute and not args.mock:
                plan = language_plan(problem)
                result = {"problem_key": problem["problem_key"], "action": plan["action"],
                          "source_language": plan["source_language"], "reason": plan["reason"], "api_calls": 0}
            else:
                result = translate(problem, root=args.data_root, config=cfg, mock=args.mock)
            print(json.dumps(result, ensure_ascii=False))
            calls += result.get("api_calls", 0)
            real_calls += result.get("real_api_calls", 0)
            if result.get("error"):
                print(json.dumps({"stopped": True, "api_calls": calls, "real_api_calls": real_calls}))
                return 1
        print(json.dumps({"selected_count": len(rows), "api_calls": calls, "real_api_calls": real_calls,
                          "mode": "execute" if args.execute else "mock" if args.mock else "dry_run"}))
        return 0
    except (ValueError, OSError, TypeError, KeyError):
        print("翻译配置/输入/存储检查失败；未自动切换模型或参数")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
