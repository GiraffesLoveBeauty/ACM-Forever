#!/usr/bin/env python3
"""Default is dry-run. --execute is an explicit network/billing opt-in."""
import argparse
import json
import sys
from annotation_api.config import Config
from annotation_api.runner import preview, run


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
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true", help="Explicitly retry cached known failures; never unknown delivery")
    p.add_argument("--reviews", help="Optional authoritative human review JSONL")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--request-interval", type=float, default=1)
    p.add_argument("--max-output-tokens", type=int)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not args.execute:
            result = preview(args.input, args.platform, args.limit, args.reviews)
            return 1 if result["input_error_count"] else 0
        config = Config.from_args(args)
        result = run(args.input, config, platform=args.platform, limit=args.limit,
                     output=args.output, resume=args.resume, reviews_path=args.reviews, retry_failed=args.retry_failed)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["failed_count"] or result["input_error_count"] or result["stopped_reason"] else 0
    except (ValueError, OSError) as exc:
        # Local error messages are controlled; never print SDK exception payloads.
        print(f"Local configuration/storage error ({type(exc).__name__}); check paths, manifest and configuration.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Use --resume; uncertain deliveries will not be resent.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
