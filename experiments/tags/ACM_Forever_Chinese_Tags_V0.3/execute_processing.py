#!/usr/bin/env python3
"""安全任务入口：默认只读 dry-run，Mock 必须隔离，真实执行必须显式授权并提供绑定计划。"""
import argparse
import json

from annotation_api.config import Config
from problem_processing.adapter import read_problems
from problem_processing.executor import execute_batch, mock_config
from problem_processing.planning import Planner


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", choices=["annotation", "translation"], required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--platform", choices=["all", "codeforces", "atcoder", "nowcoder"], default="all")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--data-root")
    p.add_argument("--plan", help="真实执行必需：绑定端点、模型和输出参数的最新计划")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--mock", action="store_true")
    modes.add_argument("--execute", action="store_true")
    p.add_argument("--provider", choices=["openai", "compatible"], default="compatible")
    p.add_argument("--model")
    p.add_argument("--max-retries", type=int, default=0)
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--request-interval", type=float, default=1)
    p.add_argument("--max-output-tokens", type=int, default=4000)
    args = p.parse_args(argv)
    try:
        if args.limit < 1 or args.max_retries != 0:
            raise ValueError("单题/批量上限必须为正，自动重试必须为零")
        if args.execute and not args.plan:
            raise ValueError("真实执行前请先生成绑定计划")
        rows = read_problems(args.input)
        rows = [r for r in rows if args.platform == "all" or isinstance(r, dict) and
                r.get("platform", str(r.get("problem_key", "")).split(":")[0]) == args.platform][:args.limit]
        cfg = (Config.from_args(args) if args.execute else mock_config(model=args.model or "mock-execution",
               timeout=args.timeout, max_output_tokens=args.max_output_tokens) if args.mock else None)
        # Display task count/types before any claim or network action, even when a later check rejects execution.
        preview = Planner(args.data_root).plan(rows)
        print(json.dumps({"selected": len(rows), "task_type": args.task,
                          "planned_ai_tasks": sum(e[args.task]["needs_ai"] for e in preview["entries"]),
                          "mode": "execute" if args.execute else "mock" if args.mock else "dry_run"}, ensure_ascii=False))
        result = execute_batch(rows, args.task, root=args.data_root, config=cfg, execute=args.execute,
                               mock=args.mock, plan=args.plan)
        # Do not dump statements, raw responses, or authentication values to the console.
        for item in result["results"]:
            value = item.get("result") or {}
            item.pop("result", None)
            item.update({k: value[k] for k in ("usage", "model", "specific_tag_names_zh", "provisional_tag_names_zh",
                                              "translation_status", "elapsed_seconds") if k in value})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["blocked"] else 0
    except (ValueError, OSError, KeyError, TypeError):
        print("安全执行检查未通过：请核对隔离目录、输入和最新绑定计划；未自动重试或切换模型。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
