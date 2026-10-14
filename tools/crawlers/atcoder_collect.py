"""Collect AtCoder statements and samples into a local SQLite problem bank."""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from json_samples import positive_int, write_json
from problem_content import parse_atcoder
from problem_store import DEFAULT_DATABASE, ProblemStore, utc_now


DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "crawler-samples" / "atcoder"


def load_metadata(path):
    items = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(items, list) or not items:
        raise ValueError("元数据必须是非空题目对象数组，请先运行 atcoder_sample.py")
    seen = set()
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("platform") != "atcoder":
            raise ValueError("元数据必须全部为 AtCoder 题目")
        for key in ("problem_id", "contest_id"):
            if not isinstance(item.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", item[key]):
                raise ValueError(f"题目缺少有效的 {key}")
        if not isinstance(item.get("problem_name"), str) or not item["problem_name"]:
            raise ValueError(f"{item['problem_id']} 缺少题名")
        if item["problem_id"] in seen:
            continue
        item = dict(item)
        item["problem_url"] = (
            f"https://atcoder.jp/contests/{quote(item['contest_id'], safe='')}/tasks/{quote(item['problem_id'], safe='')}"
        )
        result.append(item)
        seen.add(item["problem_id"])
    return result


def collect(items, store, language, output_dir, html_dir=None):
    successes = []
    failures = []
    next_request = 0.0
    interrupted = False
    cache_dir = output_dir / "html"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for position, item in enumerate(items, 1):
        problem_id = item["problem_id"]
        source_url = item["problem_url"] + "?lang=" + language
        try:
            if html_dir:
                raw = (html_dir / (problem_id + ".html")).read_bytes()
            else:
                time.sleep(max(0, next_request - time.monotonic()))
                request = Request(source_url, headers={"User-Agent": "ACM-Forever-DataCollector/0.1"})
                try:
                    with urlopen(request, timeout=30) as response:
                        raw = response.read()
                finally:
                    next_request = time.monotonic() + 1.5
            content = parse_atcoder(raw, source_url, language)
            content.update(source_url=source_url, requested_language=language, sha256=hashlib.sha256(raw).hexdigest())
            (cache_dir / (problem_id + ".html")).write_bytes(raw)
            if store:
                store.save_content("atcoder", problem_id, content)
            successes.append({**item, **content})
            print(f"[{position}/{len(items)}] {problem_id}：完成，{len(content['samples'])} 组样例", flush=True)
        except KeyboardInterrupt:
            interrupted = True
            break
        except (HTTPError, URLError, OSError, ValueError, TimeoutError, sqlite3.Error) as error:
            if store:
                store.record_failure("atcoder", problem_id, error)
            failures.append({"problem_id": problem_id, "error": str(error)[:1000]})
            print(f"[{position}/{len(items)}] {problem_id}：失败，{error}", file=sys.stderr, flush=True)
    return successes, failures, interrupted


def main(argv=None):
    parser = argparse.ArgumentParser(description="采集 AtCoder 题面与样例，并写入 SQLite（样例存于题目记录中）")
    parser.add_argument("--metadata-json", type=Path, default=DEFAULT_OUTPUT / "atcoder_problems.json", help="atcoder_sample.py 导出的全量元数据")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite 文件，默认仓库 data/problem_bank.db")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--limit", type=positive_int, default=20, help="本次最多尝试的题目数，默认 20")
    group.add_argument("--all", action="store_true", help="尝试全部待采集题目")
    parser.add_argument("--problem-id", action="append", help="仅采指定题号，可重复传入")
    parser.add_argument("--contest", help="仅采指定比赛，如 abc370")
    parser.add_argument("--language", choices=["en", "ja"], default="en", help="优先题面语言，缺失时回退，默认 en")
    parser.add_argument("--refresh", action="store_true", help="重新采集已成功入库的题目")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="页面缓存、内容 JSON 和报告的输出目录")
    parser.add_argument("--html-dir", type=Path, help="从该目录读取 题号.html 进行离线采集")
    args = parser.parse_args(argv)
    store = None
    try:
        items = load_metadata(args.metadata_json)
        requested = set(args.problem_id or [])
        if requested - {item["problem_id"] for item in items}:
            raise ValueError("元数据中不存在题号：" + ", ".join(sorted(requested - {item["problem_id"] for item in items})))
        items = [item for item in items if (not requested or item["problem_id"] in requested)
                 and (not args.contest or item["contest_id"] == args.contest)]
        if not items:
            raise ValueError("没有符合筛选条件的题目")
        store = ProblemStore(args.database)
        store.import_metadata(items)
        completed = set() if args.refresh else store.completed_ids("atcoder", args.language)
        pending = [item for item in items if item["problem_id"] not in completed]
        selected = pending if args.all else pending[:args.limit]
        successes, failures, interrupted = collect(selected, store, args.language, args.output_dir, args.html_dir)
        report = {
            "generated_at": utc_now(), "database": str(args.database.resolve()),
            "metadata_source": str(args.metadata_json.resolve()), "scope_count": len(items),
            "skipped_count": len(items) - len(pending), "selected_count": len(selected),
            "success_count": len(successes), "failure_count": len(failures),
            "interrupted": interrupted, "failures": failures, "database_counts": store.counts("atcoder"),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.output_dir / "atcoder_content.json", successes)
        write_json(args.output_dir / "atcoder_content_report.json", report)
        print(f"入库成功：{len(successes)}；失败：{len(failures)}；已完成跳过：{report['skipped_count']}")
        print(f"数据库：{args.database.resolve()}")
        return 130 if interrupted else (1 if failures else 0)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"采集失败：{error}", file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
