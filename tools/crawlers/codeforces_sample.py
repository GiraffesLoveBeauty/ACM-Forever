"""Download Codeforces problem metadata and export a small JSON sample."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from json_samples import field_report, positive_int, write_json


API_URL = "https://codeforces.com/api/problemset.problems"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "crawler-samples" / "codeforces"


def read_problems(raw):
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        detail = payload.get("comment", "响应缺少 OK 状态") if isinstance(payload, dict) else "响应不是对象"
        raise ValueError(f"Codeforces 返回失败：{detail}")
    result = payload.get("result")
    problems = result.get("problems") if isinstance(result, dict) else None
    if not isinstance(problems, list) or not problems or any(not isinstance(p, dict) for p in problems):
        raise ValueError("result.problems 必须是非空的题目对象数组")
    return problems


def make_sample(problems, limit):
    sample = []
    seen = set()
    for problem in problems:
        contest_id = problem.get("contestId")
        index = problem.get("index")
        if (problem.get("type") != "PROGRAMMING"
                or isinstance(contest_id, bool) or not isinstance(contest_id, int)
                or contest_id <= 0 or not isinstance(index, str) or not index):
            continue
        problem_id = f"{contest_id}{index}"
        if problem_id in seen:
            continue
        name, tags, rating = problem.get("name"), problem.get("tags", []), problem.get("rating")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{problem_id} 缺少有效题名")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"{problem_id} 的 tags 不是字符串数组")
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, int)):
            raise ValueError(f"{problem_id} 的 rating 不是整数或 null")
        section = "gym" if contest_id >= 100000 else "contest"
        sample.append({
            "platform": "codeforces",
            "problem_id": problem_id,
            "contest_id": contest_id,
            "problem_name": name,
            "problem_rating": rating,
            "tags": tags,
            "problem_url": f"https://codeforces.com/{section}/{contest_id}/problem/{index}",
            "statement_html": None,
        })
        seen.add(problem_id)
        if len(sample) == limit:
            break
    if not sample:
        raise ValueError("没有带有效 contestId/index 的编程题可供导出")
    return sample


def main(argv=None):
    parser = argparse.ArgumentParser(description="获取 CF 原始 JSON、字段统计和题目样本（不写入数据库）")
    parser.add_argument("--limit", type=positive_int, default=20, help="样本数量上限，默认 20")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="输出目录，默认仓库 data/crawler-samples/codeforces")
    parser.add_argument("--input-json", type=Path, help="使用已保存的原始 API JSON，跳过网络请求")
    args = parser.parse_args(argv)

    try:
        if args.input_json:
            raw = args.input_json.read_bytes()
            source = str(args.input_json.resolve())
        else:
            request = Request(API_URL, headers={"User-Agent": "ACM-Forever-DataCollector/0.1"})
            with urlopen(request, timeout=30) as response:
                raw = response.read()
            source = API_URL
        problems = read_problems(raw)
        sample = make_sample(problems, args.limit)
        report = {
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "problem_count": len(problems),
            "sample_count": len(sample),
            "fields": field_report(problems),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "cf_raw.json").write_bytes(raw)
        write_json(args.output_dir / "cf_sample.json", sample)
        write_json(args.output_dir / "cf_fields.json", report)
    except (HTTPError, URLError, OSError, ValueError, TimeoutError) as error:
        print(f"采集失败：{error}", file=sys.stderr)
        return 1

    print(f"原始题目：{len(problems)}；样本：{len(sample)}")
    print("原始字段：" + ", ".join(report["fields"]))
    print(f"输出目录：{args.output_dir.resolve()}")
    print(json.dumps(sample[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
