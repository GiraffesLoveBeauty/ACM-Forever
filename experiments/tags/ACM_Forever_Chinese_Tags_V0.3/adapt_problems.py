#!/usr/bin/env python3
"""离线验证题库 JSON/JSONL；默认 dry-run，不连接数据库、不调用 API。"""
import argparse
import json
from collections import Counter
from pathlib import Path

from label_pipeline import BASE
from problem_processing.adapter import normalize, read_problems
from problem_processing.backup import checked_path, check_sensitive
from problem_processing.crawler_input import resolve_identity

OUTPUT_ROOT = BASE / "outputs" / "adapted"


def adapt_file(path):
    path = Path(path)
    if path.suffix.lower() not in {".json", ".jsonl"}:
        raise ValueError("仅支持本地 JSON / JSONL，不访问数据库")
    if path.suffix.lower() == ".jsonl":
        entries = []
        for line, text in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not text.strip():
                continue
            try:
                entries.append((line, json.loads(text)))
            except ValueError:
                entries.append((line, None))
    else:
        entries = list(enumerate(read_problems(path), 1))
    rows, errors, seen, conflicts = [], [], {}, set()
    duplicates = 0
    for line, raw in entries:
        key = None
        try:
            if isinstance(raw, dict) and raw.get("platform") != "nowcoder":
                key = resolve_identity(raw)[3]
            result = normalize(raw)
            key = result["problem_key"]
            check_sensitive(result)
            signature = (result["normalized_content_hash"], result["annotation_input_hash"],
                         result["translation_input_hash"], result["processing_status"])
            if key in seen:
                duplicates += 1
                old_signature, old_result = seen[key]
                if old_signature != signature:
                    conflicts.add(key)
                    errors.append({"source_line": line, "problem_key": key, "error_code": "conflicting_duplicate"})
                else:
                    old_result["source_links"] = list(dict.fromkeys(old_result["source_links"] + result["source_links"]))
                    old_result["source_problem_ids"] = list(dict.fromkeys(old_result["source_problem_ids"] + [result["source_problem_id"]]))
                continue
            result["source_problem_ids"] = [result["source_problem_id"]]
            seen[key] = (signature, result)
            rows.append(result)
        except (ValueError, KeyError, TypeError, RecursionError) as exc:
            if key:
                conflicts.add(key)
            errors.append({"source_line": line, "problem_key": key, "error_code": "invalid_input", "error_type": type(exc).__name__})
    rows = [r for r in rows if r["problem_key"] not in conflicts]
    statuses = Counter(r["processing_status"] for r in rows)
    summary = {"input_count": len(entries), "normalized_count": len(rows), "ready": statuses["ready"],
               "pending": len(rows) - statuses["ready"], "invalid": len(errors), "duplicates": duplicates,
               "status_counts": dict(sorted(statuses.items())), "api_calls": 0, "real_api_calls": 0}
    return rows, errors, summary


def preview(row):
    return {k: row[k] for k in ("problem_key", "source_problem_id", "original_title", "statement_format",
            "statement_status", "processing_status", "processing_issues", "source_statement_sha256",
            "normalized_content_hash", "annotation_input_hash", "translation_input_hash")} | {
                "statement_characters": len(row["original_statement"]), "source_links": row["source_links"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--preview", type=int, default=3)
    parser.add_argument("--output", type=Path, help="仅 --write 时写入 outputs/adapted/ 下的新 JSONL")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.preview < 0:
            raise ValueError("preview 不能为负")
        target = None
        if args.write:
            if not args.output:
                raise ValueError("--write 必须指定 --output")
            target = checked_path(args.output)
            if (not target.is_relative_to(checked_path(OUTPUT_ROOT)) or target.suffix.lower() != ".jsonl"
                    or target.exists() or target == checked_path(args.input)):
                raise ValueError("输出必须是 outputs/adapted/ 下尚不存在的 JSONL")
        rows, errors, summary = adapt_file(args.input)
        # Isolated failures never partially publish an apparently complete batch.
        if target and not errors:
            payload = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
        print(json.dumps({"mode": "write" if args.write else "dry_run", "summary": summary,
                          "preview": [preview(r) for r in rows[:args.preview]], "errors": errors,
                          "output_written": bool(target and not errors)}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (OSError, ValueError, KeyError, TypeError):
        print("输入/输出检查失败；请检查文件格式、身份和输出路径。未调用 API，未覆盖已有文件。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
