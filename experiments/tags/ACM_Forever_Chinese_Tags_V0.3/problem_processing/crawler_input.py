"""Read-only crawler column decoding and independently checked source identities."""
import json
import re
from copy import deepcopy
from urllib.parse import urlsplit

VERSION = "crawler-input-1"
TOKEN = r"[A-Za-z0-9_-]{1,100}"
CF_INDEX = r"(?:[A-Z]{1,3}\d{0,2}|\d{1,3})"


def json_column(value, kind, name):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError(f"{name} 不是合法 JSON") from None
    if not isinstance(value, kind):
        raise ValueError(f"{name} 数据类型错误")
    return deepcopy(value)


def expanded(row, *, decode_payload=True):
    """SQL JSON columns and decoded HTTP JSON have the same semantics."""
    value = deepcopy(row)
    metadata = json_column(value.get("metadata_json") or {}, dict, "metadata_json")
    # Metadata is a fallback, not an authority that can silently change identity.
    for key in ("platform", "problem_id", "contest_id", "problem_index", "problem_url"):
        if metadata.get(key) is not None and value.get(key) is not None:
            if str(metadata[key]) != str(value[key]):
                raise ValueError("metadata_json 与题目身份字段冲突")
    for key in ("platform", "problem_id", "contest_id", "problem_index", "problem_url",
                "problem_name", "problem_rating", "difficulty_raw", "difficulty_source", "tags"):
        if value.get(key) is None and metadata.get(key) is not None:
            value[key] = metadata[key]
    if decode_payload and isinstance(value.get("tags"), str):
        value["tags"] = json_column(value["tags"], list, "tags")
    if decode_payload and value.get("samples") is not None:
        value["samples"] = json_column(value["samples"], list, "samples")
    return value


def source_urls(row):
    links = row.get("source_links") or []
    if not isinstance(links, list):
        raise ValueError("source_links 必须为 URL 数组")
    values = [row.get(k) for k in ("url", "problem_url", "source_url", "statement_source_url")]
    result = []
    for value in [*values, *links]:
        if value is None or value == "":
            continue
        if not isinstance(value, str) or re.search(r"[\x00-\x20]", value):
            raise ValueError("来源链接格式错误")
        try:
            url = urlsplit(value)
            valid = (url.scheme in {"http", "https"} and url.hostname and not url.username
                     and not url.password and url.port is None)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("来源链接必须为无认证信息的 HTTP(S) URL")
        if value not in result:
            result.append(value)
    return result


def resolve_identity(row):
    value = expanded(row, decode_payload=False)
    candidates = []
    key = value.get("problem_key")
    platform = value.get("platform")
    if key:
        if not isinstance(key, str) or len(parts := key.split(":")) != 3 or not all(parts):
            raise ValueError("非法 problem_key")
        candidates.append(tuple(parts))
        if platform and platform != parts[0]:
            raise ValueError("平台与 problem_key 冲突")
        platform = parts[0]
    links = source_urls(value)
    for link in links:
        url = urlsplit(link)
        found = None
        if url.hostname in {"codeforces.com", "www.codeforces.com"}:
            match = re.fullmatch(r"/(?:contest|gym)/(\d+)/problem/(" + CF_INDEX + r")/?", url.path)
            if not match:
                match = re.fullmatch(r"/problemset/problem/(\d+)/(" + CF_INDEX + r")/?", url.path)
            if match:
                found = ("codeforces", *match.groups())
        elif url.hostname in {"atcoder.jp", "www.atcoder.jp"}:
            match = re.fullmatch(r"/contests/(" + TOKEN + r")/tasks/(" + TOKEN + r")/?", url.path)
            if match:
                found = ("atcoder", *match.groups())
        if found:
            candidates.append(found)
            platform = platform or found[0]
    ids = [value[k] for k in ("problem_id", "source_problem_id") if value.get(k) is not None]
    if not ids and value.get("id") is not None:
        ids.append(value["id"])  # AtCoder Problems catalog's actual task ID.
    if not platform and any(isinstance(x, str) and x.startswith("cf_") for x in ids):
        platform = "codeforces"
    if platform not in {"codeforces", "atcoder"}:
        raise ValueError("缺少或不支持的平台")
    if any(p != platform for p, _, _ in candidates):
        raise ValueError("来源平台冲突")
    contest = value.get("contest_id")
    if contest is not None and (isinstance(contest, bool) or not isinstance(contest, (str, int))):
        raise ValueError("比赛 ID 类型错误")
    contest = str(contest) if contest is not None else candidates[0][1] if candidates else None
    # Alphanumeric combined IDs can be split unambiguously. Numeric-only IDs cannot.
    if platform == "codeforces" and contest is None:
        for pid in ids:
            match = re.fullmatch(r"(?:cf_)?([1-9]\d{0,6})([A-Z]{1,3}\d{0,2})", str(pid))
            if match:
                contest = match[1]
                break
    if not contest or not re.fullmatch(r"[1-9]\d{0,6}" if platform == "codeforces" else TOKEN, contest):
        raise ValueError("缺失或非法比赛 ID；纯数字 CF 题号必须提供比赛信息")
    if any(c != contest for _, c, _ in candidates):
        raise ValueError("比赛 ID 与链接或规范身份冲突")
    index = value.get("problem_index")
    if platform == "codeforces" and index not in (None, ""):
        if not isinstance(index, str) or not re.fullmatch(CF_INDEX, index):
            raise ValueError("非法 CF problem_index")
        candidates.append((platform, contest, index))
    resolved_ids = {p for _, _, p in candidates}
    for raw in ids:
        if not isinstance(raw, str) or not raw:
            raise ValueError("题目来源 ID 必须为非空字符串")
        if platform == "atcoder":
            pid = raw
        elif resolved_ids:
            # Validate combined IDs against independently known indices (numeric included).
            matches = [pid for pid in resolved_ids if raw in {pid, contest + pid, "cf_" + contest + pid}]
            if len(matches) != 1:
                raise ValueError("CF 来源题号与题序冲突")
            pid = matches[0]
        elif raw.startswith("cf_"):
            if not raw[3:].startswith(contest):
                raise ValueError("CF 来源题号与比赛冲突")
            pid = raw[3 + len(contest):]
        elif raw.startswith(contest) and re.fullmatch(CF_INDEX, raw[len(contest):]):
            pid = raw[len(contest):]
        else:
            pid = raw
        candidates.append((platform, contest, pid))
        resolved_ids.add(pid)
    if len(set(candidates)) != 1:
        raise ValueError("缺少题目唯一 ID 或存在冲突")
    _, _, pid = candidates[0]
    if not re.fullmatch(CF_INDEX if platform == "codeforces" else TOKEN, pid):
        raise ValueError("非法题目 ID")
    return platform, contest, pid, f"{platform}:{contest}:{pid}", links[0] if links else None


def is_crawler_record(row):
    return any(k in row for k in ("metadata_json", "statement_text", "statement_pdf", "last_fetch_status",
                                  "statement_sha256", "statement_source_url", "problem_index", "has_pdf")) or (
        isinstance(row.get("problem_id"), str) and row["problem_id"].startswith("cf_"))
