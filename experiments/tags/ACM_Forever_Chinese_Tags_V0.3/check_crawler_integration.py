#!/usr/bin/env python3
"""只读抽查本地爬虫 JSON/JSONL → 适配 → 增量规划，不采集、不执行 AI。"""
import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from label_pipeline import BASE
from problem_processing.adapter import normalize, read_problems, source_identity
from problem_processing.backup import checked_path, check_sensitive
from problem_processing.crawler_input import expanded
from problem_processing.planning import Planner, write_plan
from problem_processing.repository import data_root
from problem_processing.statement import newline


HASH_FIELDS = ("normalized_content_hash", "annotation_input_hash", "translation_input_hash")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persistent_hashes(root):
    """Only inspect this tool's explicit data root; never look for databases or .env."""
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): file_hash(checked_path(p))
            for p in sorted(root.rglob("*")) if p.is_file()}


def audit_files(paths, *, limit_per_file=3, root=None, cache_roots=None, manifest_roots=None,
                selection_manifest=None):
    if type(limit_per_file) is not int or limit_per_file < 1:
        raise ValueError("每个文件的抽查数量必须为正整数")
    root = data_root(root)
    protected_before = persistent_hashes(root)
    manifest = checked_path(selection_manifest or BASE / "data/selection_manifest.json")
    excluded = set()
    if manifest.exists():
        split = json.loads(manifest.read_text(encoding="utf-8"))
        keys = split.get("holdout_keys")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ValueError("分组清单缺少合法的 holdout_keys")
        excluded = set(keys)
    sources, entries, normalized = [], [], []
    for value in paths:
        path = checked_path(value)
        if path.suffix.lower() not in {".json", ".jsonl"}:
            raise ValueError("仅接受明确指定的本地 JSON/JSONL，不读取数据库或认证配置")
        if any(word in path.name.lower() for word in ("holdout", "gold_template")):
            raise ValueError("不读取正式留出集或人工答案文件")
        before_hash = file_hash(path)
        rows = read_problems(path)
        selected, skipped = [], 0
        for index, raw in enumerate(rows, 1):
            try:
                key = source_identity(raw)[3]
            except (ValueError, KeyError, TypeError, AttributeError):
                key = None
            if key in excluded:
                skipped += 1
                continue
            selected.append((index, raw))
            if len(selected) == limit_per_file:
                break
        sources.append({"path": str(path), "sha256": before_hash, "available": len(rows),
                        "selected": len(selected), "holdout_rows_skipped_before_normalization": skipped})
        for index, raw in selected:
            before = deepcopy(raw)
            try:
                check_sensitive(raw)
                item = normalize(raw)
                check_sensitive(item)
                repeated = normalize(raw)
                roundtrip = normalize(json.loads(json.dumps(item, ensure_ascii=False)))
                statement = raw.get("statement") or {}
                markdown = statement.get("markdown") if isinstance(statement, dict) else None
                fields = expanded(raw)
                raw_tags = fields.get("raw_tags", fields.get("tags", [])) or []
                if isinstance(raw_tags, dict):
                    raw_tags = raw_tags.get("values", []) or []
                if isinstance(raw_tags, str):
                    raw_tags = json.loads(raw_tags)
                checks = {"source_record_unchanged": raw == before,
                          "repeat_normalization_equal": item == repeated,
                          "json_roundtrip_equal": item == roundtrip,
                          "task_hashes_stable": all(item[k] == repeated[k] for k in HASH_FIELDS),
                          "source_markdown_preserved": (newline(markdown) in newline(item["original_statement"]))
                          if markdown else None,
                          "raw_tags_preserved": item["raw_tags"] == raw_tags}
                normalized.append(item)
                entries.append({"source": path.name, "source_row": index,
                                "problem_key": item["problem_key"], "source_problem_id": item["source_problem_id"],
                                "processing_status": item["processing_status"], "issues": item["processing_issues"],
                                "characters": len(item["original_statement"]),
                                "sample_count": len(item.get("samples", [])),
                                "omitted_outputs": sum(s["output"] is None for s in item.get("samples", [])),
                                "samples_embedded_in_markdown": bool(markdown and "```" in markdown),
                                "source_links": item["source_links"], "raw_tags": item["raw_tags"],
                                "source_statement_sha256": item["source_statement_sha256"],
                                **{k: item[k] for k in HASH_FIELDS}, "checks": checks})
            except (ValueError, KeyError, TypeError, RecursionError):
                entries.append({"source": path.name, "source_row": index,
                                "processing_status": "invalid", "error_code": "invalid_input"})
        sources[-1]["unchanged"] = path.exists() and file_hash(path) == before_hash

    def planner():
        return Planner(root, cache_roots=cache_roots, manifest_roots=manifest_roots)

    first = planner()
    plan = first.plan(normalized)
    second_plan = planner().plan(normalized)
    existing = first.plan(list(first.problems.values()))
    checks = {"sources_unchanged": all(s["unchanged"] for s in sources),
              "persistent_files_unchanged": persistent_hashes(root) == protected_before,
              "planning_idempotent": plan == second_plan,
              "records_consistent": all(all(v is not False for v in e.get("checks", {}).values())
                                        and e["processing_status"] != "invalid" for e in entries),
              "existing_annotations_reusable": all(e["annotation"]["status"] in {"reuse_existing", "not_required"}
                                                   for e in existing["entries"])}
    report = {"report_version": "crawler-integration-1", "mode": "offline_read_only",
              "execution_supported": False, "input_provenance": "caller_supplied_not_independently_verified",
              "sources": sources, "records": entries, "checks": checks,
              "selection_guard": {"manifest_found": manifest.exists(), "excluded_key_count": len(excluded)},
              "sample_plan": plan, "existing_results_plan": existing,
              "real_api_calls": 0, "success": bool(entries) and all(checks.values()) and plan["summary"]["invalid"] == 0,
              "limits": ["Only the selected records are checked; no recrawl or database access.",
                         "Preservation checks do not prove source completeness, mathematical correctness or reuse rights.",
                         "Legacy handoff files do not prove the latest crawler SQL/HTTP export works."]}
    check_sensitive(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--limit-per-file", type=int, default=3)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--report", type=Path, help="可选，仅写 outputs/plans/ 下的新 JSON 审计报告，不含题面")
    args = parser.parse_args(argv)
    try:
        report = audit_files(args.input, limit_per_file=args.limit_per_file, root=args.data_root)
        if args.report:
            write_plan(args.report, report)
        print(json.dumps({"success": report["success"], "checks": report["checks"],
                          "selected": len(report["records"]),
                          "sample_summary": report["sample_plan"]["summary"],
                          "existing_summary": report["existing_results_plan"]["summary"],
                          "records": report["records"], "real_api_calls": 0,
                          "report": str(args.report) if args.report else None}, ensure_ascii=False, indent=2))
        return 0 if report["success"] else 1
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("离线检查失败：请核对输入协议、持久数据及报告路径；未调用 API，未覆盖已有文件。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
