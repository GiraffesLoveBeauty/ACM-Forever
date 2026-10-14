"""Export AtCoder problem metadata and estimated difficulties as JSON."""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from json_samples import field_report, positive_int, write_json


PROBLEMS_URL = "https://kenkoooo.com/atcoder/resources/problems.json"
MODELS_URL = "https://kenkoooo.com/atcoder/resources/problem-models.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "crawler-samples" / "atcoder"


def download(url):
    request = Request(url, headers={"User-Agent": "ACM-Forever-DataCollector/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def read_datasets(problem_raw, model_raw):
    problems = json.loads(problem_raw.decode("utf-8-sig"))
    models = json.loads(model_raw.decode("utf-8-sig"))
    if not isinstance(problems, list) or not problems or any(not isinstance(p, dict) for p in problems):
        raise ValueError("题目资源必须是非空的对象数组")
    if not isinstance(models, dict) or any(not isinstance(model, dict) for model in models.values()):
        raise ValueError("难度资源必须是以题目 ID 为键、模型对象为值的字典")
    return problems, models


def valid_difficulty(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def display_difficulty(raw):
    # Match the AtCoder Problems display scale used by the existing API crawler.
    # This form also avoids overflow when a model has a very negative difficulty.
    value = 400 * math.exp(raw / 400 - 1) if raw < 400 else raw
    return max(0, math.floor(value + 0.5))


def normalize_problems(problems, models):
    items = []
    seen = set()
    for problem in problems:
        problem_id, contest_id = problem.get("id"), problem.get("contest_id")
        if not isinstance(problem_id, str) or not problem_id or not isinstance(contest_id, str) or not contest_id:
            continue
        if problem_id in seen:
            continue
        name = problem.get("name") or problem.get("title")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{problem_id} 缺少有效题名")
        model = models.get(problem_id, {})
        raw_difficulty = valid_difficulty(model.get("difficulty"))
        experimental = model.get("is_experimental")
        items.append({
            "platform": "atcoder",
            "problem_id": problem_id,
            "contest_id": contest_id,
            "problem_index": problem.get("problem_index"),
            "problem_name": name,
            "problem_rating": display_difficulty(raw_difficulty) if raw_difficulty is not None else None,
            "difficulty_raw": raw_difficulty,
            "difficulty_source": "atcoder_problems" if raw_difficulty is not None else None,
            "difficulty_is_experimental": experimental if isinstance(experimental, bool) else None,
            "tags": [],
            "problem_url": f"https://atcoder.jp/contests/{quote(contest_id, safe='')}/tasks/{quote(problem_id, safe='')}",
            "statement_html": None,
        })
        seen.add(problem_id)
    if not items:
        raise ValueError("没有带有效 id/contest_id 的题目可供导出")
    return items


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出 AtCoder 全量题目元数据、难度和字段样本（不写入数据库）")
    parser.add_argument("--limit", type=positive_int, default=20, help="独立样本的数量上限，默认 20；全量文件不受影响")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="输出目录，默认仓库 data/crawler-samples/atcoder")
    parser.add_argument("--input-json", type=Path, help="离线题目原始 JSON，需同时提供 --input-models")
    parser.add_argument("--input-models", type=Path, help="离线难度模型 JSON，需同时提供 --input-json")
    args = parser.parse_args(argv)
    if (args.input_json is None) != (args.input_models is None):
        parser.error("离线导出需同时提供 --input-json 和 --input-models")

    try:
        if args.input_json:
            problem_raw = args.input_json.read_bytes()
            model_raw = args.input_models.read_bytes()
            sources = {"problems": str(args.input_json.resolve()), "models": str(args.input_models.resolve())}
        else:
            problem_raw = download(PROBLEMS_URL)
            # The dataset maintainer requests more than one second between accesses.
            time.sleep(1.1)
            model_raw = download(MODELS_URL)
            sources = {"problems": PROBLEMS_URL, "models": MODELS_URL}
        problems, models = read_datasets(problem_raw, model_raw)
        items = normalize_problems(problems, models)
        rated = [item for item in items if item["problem_rating"] is not None]
        unrated = [item for item in items if item["problem_rating"] is None]
        sample = (rated + unrated)[:args.limit]
        report = {
            "sources": sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "problem_count": len(problems),
            "model_count": len(models),
            "exported_count": len(items),
            "matched_model_count": sum(item["problem_id"] in models for item in items),
            "difficulty_available_count": len(rated),
            "difficulty_missing_count": len(unrated),
            "sample_count": len(sample),
            "problem_fields": field_report(problems),
            "model_fields": field_report(models.values()),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "atcoder_raw.json").write_bytes(problem_raw)
        (args.output_dir / "atcoder_models_raw.json").write_bytes(model_raw)
        write_json(args.output_dir / "atcoder_problems.json", items)
        write_json(args.output_dir / "atcoder_sample.json", sample)
        write_json(args.output_dir / "atcoder_fields.json", report)
    except (HTTPError, URLError, OSError, ValueError, TimeoutError, OverflowError) as error:
        print(f"采集失败：{error}", file=sys.stderr)
        return 1

    print(f"原始题目：{len(problems)}；导出题目：{len(items)}；有难度：{len(rated)}；样本：{len(sample)}")
    print("题目原始字段：" + ", ".join(report["problem_fields"]))
    print("模型原始字段：" + ", ".join(report["model_fields"]))
    print(f"输出目录：{args.output_dir.resolve()}")
    print(json.dumps(sample[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
