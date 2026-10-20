#!/usr/bin/env python3
"""Evaluate original predictions; never use AI labels as gold."""
import argparse
import json
from pathlib import Path
from annotation_api.evaluation import report
from annotation_api.storage import read_jsonl, atomic_json
from annotation_api.config import BASE


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--predictions", required=True)
    p.add_argument("--gold", required=True)
    p.add_argument("--manifest")
    p.add_argument("--errors")
    p.add_argument("--output")
    args = p.parse_args(argv)
    path = Path(args.predictions)
    manifest_path = Path(args.manifest) if args.manifest else path.parent / "manifest.json"
    error_path = Path(args.errors) if args.errors else path.parent / "errors.jsonl"
    try:
        if not path.is_file() or not Path(args.gold).is_file():
            raise ValueError("Required prediction/gold file missing")
        if (args.manifest and not manifest_path.is_file()) or (args.errors and not error_path.is_file()):
            raise ValueError("Explicit manifest/errors file missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        result = report(read_jsonl(path), read_jsonl(args.gold), manifest=manifest,
                        errors=read_jsonl(error_path))
        if args.output:
            dest = Path(args.output).resolve()
            sources = {Path(x).resolve() for x in (args.predictions, args.gold)} | {manifest_path.resolve(), error_path.resolve()}
            if dest in sources:
                raise ValueError("Cannot overwrite input data")
            if dest.is_relative_to(BASE.resolve()) and not dest.is_relative_to((BASE / "outputs").resolve()):
                raise ValueError("Inside the test package, reports must be under outputs/")
            atomic_json(dest, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        print("评估失败：检查重复 ID、人工审核布尔值、版本、题面哈希及输入文件类型。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
