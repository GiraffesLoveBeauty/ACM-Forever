#!/usr/bin/env python3
"""Default is dry-run. --execute is an explicit network/billing opt-in."""
import argparse
import sys
from annotation_api.runner import preview


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", choices=["openai", "compatible"], default="openai")
    p.add_argument("--model")
    p.add_argument("--platform", choices=["all", "atcoder", "codeforces"], default="all")
    p.add_argument("--input", required=True)
    p.add_argument("--output", help="Separate output directory, not a JSONL filename")
    p.add_argument("--limit", type=int)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--mock", action="store_true")
    p.add_argument("--data-root")
    p.add_argument("--plan")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true", help="Explicitly retry cached known failures; never unknown delivery")
    p.add_argument("--reviews", help="Optional authoritative human review JSONL")
    p.add_argument("--max-retries", type=int, default=0)
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--request-interval", type=float, default=1)
    p.add_argument("--max-output-tokens", type=int)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.execute or args.mock:
            if args.retry_failed or args.reviews or args.output:
                raise ValueError("安全执行使用持久目录和人工覆盖，不接受旧输出路径、重试或独立审核文件")
            from execute_processing import main as guarded_main
            command = ["--task", "annotation", "--input", args.input, "--platform", args.platform,
                       "--limit", str(args.limit or 1), "--provider", args.provider, "--max-retries", str(args.max_retries),
                       "--timeout", str(args.timeout), "--request-interval", str(args.request_interval),
                       "--mock" if args.mock else "--execute"]
            for flag, value in (("--model", args.model), ("--data-root", args.data_root), ("--plan", args.plan),
                                ("--max-output-tokens", args.max_output_tokens)):
                if value is not None:
                    command.extend([flag, str(value)])
            return guarded_main(command)
        result = preview(args.input, args.platform, args.limit, args.reviews)
        return 1 if result["input_error_count"] else 0
    except (ValueError, OSError) as exc:
        # Local error messages are controlled; never print SDK exception payloads.
        print(f"Local configuration/storage error ({type(exc).__name__}); check paths, manifest and configuration.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Use --resume; uncertain deliveries will not be resent.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
