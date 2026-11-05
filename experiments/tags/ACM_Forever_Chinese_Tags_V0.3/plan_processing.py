#!/usr/bin/env python3
"""只读生成独立标签/翻译任务计划；不加载 .env，不提供 execute 功能。"""
import argparse
import json
from pathlib import Path

from problem_processing.adapter import read_problems
from problem_processing.planning import Planner, task_policies, write_plan
from problem_processing.translation import TRANSLATION_VERSION
from annotation_api import PROMPT_VERSION


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="规范题目 JSON/JSONL；也兼容已有适配器可读的记录")
    source.add_argument("--from-persistent", action="store_true", help="只读当前持久目录中的题目")
    parser.add_argument("--data-root")
    parser.add_argument("--cache-root", action="append", help="可重复指定；默认只读模块 cache")
    parser.add_argument("--manifest-root", action="append", help="可重复指定；默认只读模块 outputs 的清单")
    parser.add_argument("--annotation-revision", default=PROMPT_VERSION)
    parser.add_argument("--translation-revision", default=TRANSLATION_VERSION)
    parser.add_argument("--preview", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--platform", choices=["all", "codeforces", "atcoder", "nowcoder"], default="all")
    parser.add_argument("--task-type", choices=["annotation", "translation"], help="绑定将来执行的任务类型")
    parser.add_argument("--provider", choices=["compatible", "openai"], default="compatible")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--response-format", choices=["json_schema", "json_object"], default="json_schema")
    parser.add_argument("--token-parameter", choices=["max_completion_tokens", "max_tokens"], default="max_completion_tokens")
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    parser.add_argument("--output", type=Path, help="--write 时必填：outputs/plans 下新 JSON 文件")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true", help="仅保存计划，绝不会执行任务")
    args = parser.parse_args(argv)
    try:
        if args.preview < 0 or (args.write and not args.output) or (args.limit is not None and args.limit < 1):
            raise ValueError("参数不完整")
        planner = Planner(args.data_root, cache_roots=args.cache_root, manifest_roots=args.manifest_root,
                          policies=task_policies(args.annotation_revision, args.translation_revision))
        rows = list(planner.problems.values()) if args.from_persistent else read_problems(args.input)
        rows = [r for r in rows if args.platform == "all" or isinstance(r, dict) and
                r.get("platform", str(r.get("problem_key", "")).split(":")[0]) == args.platform]
        if args.limit:
            rows = rows[:args.limit]
        plan = planner.plan(rows)
        if args.task_type or args.model or args.base_url:
            if not all((args.task_type, args.model, args.base_url)):
                raise ValueError("绑定计划必须明确指定任务、模型和端点")
            from annotation_api.config import Config
            from annotation_api.dispatch import request_settings
            from problem_processing.executor import bind_plan
            public = Config(provider=args.provider, model=args.model, base_url=args.base_url,
                            api_key="offline-plan-placeholder", max_retries=0, response_format=args.response_format,
                            token_parameter=args.token_parameter, max_output_tokens=args.max_output_tokens)
            plan = bind_plan(plan, args.task_type, request_settings(public))
        if args.write:
            write_plan(args.output, plan)
        print(json.dumps({"plan_id": plan["plan_id"], "summary": plan["summary"],
                          "preview": plan["entries"][:args.preview], "audit_warnings": plan["audit_warnings"],
                          "output_written": bool(args.write), "execution_supported": False}, ensure_ascii=False, indent=2))
        return 1 if plan["summary"]["invalid"] else 0
    except (OSError, ValueError, KeyError, TypeError):
        print("离线计划失败：请检查输入、历史证据及输出路径；未调用 API，未覆盖已有文件。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
