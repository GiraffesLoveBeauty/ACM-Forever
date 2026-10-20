"""Preserve crawler data and normalize a secondary-processing metadata contract."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from annotation_api.adapter import adapt, canonical_identity, digest
from label_pipeline import prepare

METADATA_VERSION = "secondary-1"


def source_identity(row):
    platform = row.get("platform") or str(row.get("problem_key", "")).split(":")[0]
    if platform != "nowcoder":
        value = dict(row)
        if not value.get("problem_key") and not value.get("contest_id"):
            url = value.get("url") or value.get("problem_url") or value.get("source_url") or ""
            match = re.search(r"/contests/([^/]+)/tasks/([^/?#]+)", url) if platform == "atcoder" else re.search(r"/(?:contest|gym)/(\d+)/problem/([^/?#]+)", url)
            if match:
                value["contest_id"] = match[1]
                value.setdefault("problem_id", match[2])
        return canonical_identity(value)
    key = row.get("problem_key")
    if key:
        parts = key.split(":")
        if len(parts) != 3 or parts[0] != "nowcoder" or not all(parts):
            raise ValueError("非法牛客题目身份")
        namespace, pid = parts[1:]
    else:
        pid = str(row.get("source_problem_id") or row.get("problem_id") or "")
        namespace = str(row.get("contest_id") or "problem")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", pid) or not re.fullmatch(r"[A-Za-z0-9_-]+", namespace):
        raise ValueError("牛客题目缺少可用来源 ID")
    if row.get("problem_id") is not None and str(row["problem_id"]) != pid:
        raise ValueError("牛客题目身份冲突")
    if row.get("contest_id") is not None and str(row["contest_id"]) != namespace:
        raise ValueError("牛客比赛身份冲突")
    url = row.get("url") or row.get("problem_url") or row.get("source_url")
    if url:
        parsed = urlsplit(url)
        if parsed.hostname not in {"ac.nowcoder.com", "www.nowcoder.com"}:
            raise ValueError("牛客来源域名不匹配")
        match = re.fullmatch(r"/acm/problem/(\d+)/?", parsed.path)
        if match and (namespace != "problem" or pid != match[1]):
            raise ValueError("牛客全局题目链接与身份冲突")
    return platform, namespace, pid, f"nowcoder:{namespace}:{pid}", url


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("题目必须是 JSON 对象")
    platform, contest, pid, key, url = source_identity(row)
    value = dict(row, platform=platform, contest_id=contest, problem_id=pid, problem_key=key)
    statement_obj = row.get("statement") or {}
    if not isinstance(statement_obj, dict):
        raise ValueError("statement 必须是对象")
    text = row.get("original_statement", row.get("statement_markdown", statement_obj.get("markdown", ""))) or ""
    html = row.get("statement_html", statement_obj.get("html", "")) or ""
    title = row.get("original_title", row.get("title", row.get("problem_name", ""))) or ""
    if not all(isinstance(x, str) for x in (text, html, title)):
        raise ValueError("题名和题面必须是字符串")
    raw = row.get("raw_tags", row.get("tags", [])) or []
    if isinstance(raw, dict):
        raw = raw.get("values") or []
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ValueError("当前已识别爬虫的 tags 应为数组或 values 数组")
    if platform in {"atcoder", "codeforces"}:
        item = adapt(dict(value, title=title, raw_tags=raw, statement_markdown=text))
        base = item["rule_base"]
        content_hash = base["content_hash"]
        status = item["evidence"]["statement_status"]
    else:
        content_hash = row.get("content_hash") or digest({"problem_key": key, "title": title, "statement_markdown": text})
        status = row.get("statement_status", statement_obj.get("status", "ok" if text else "missing"))
        base = {"problem_key": key, "platform": platform, "title": title, "source_url": url,
                "content_hash": content_hash, "raw_tags": raw, "specific_tag_ids": [],
                "provisional_tag_ids": [], "cf_exact_tag_ids": [], "needs_ai": True}
    if not isinstance(content_hash, str) or not content_hash:
        raise ValueError("content_hash 必须为非空字符串")
    links = list(row.get("source_links") or [])
    if not all(isinstance(link, str) and urlsplit(link).scheme in {"http", "https"} for link in links):
        raise ValueError("source_links 必须为 URL 数组")
    if url and url not in links:
        links.insert(0, url)
    return {"problem_key": key, "platform": platform, "source_problem_id": pid,
            "contest_id": None if platform == "nowcoder" and contest == "problem" else contest,
            "original_title": title, "original_statement": text, "original_statement_html": html,
            "statement_status": status if text else "html_only" if html else "missing",
            "source_links": links, "raw_tags": raw, "difficulty_raw": row.get("difficulty_raw", row.get("difficulty", row.get("problem_rating"))),
            "content_hash": content_hash, "verified_content_hash": digest({"title": title, "text": text, "html": html}),
            "metadata_version": METADATA_VERSION, "language_hint": statement_obj.get("primary_language", row.get("language")),
            "source_fetched_at": row.get("fetched_at"), "rights_status": row.get("rights_status", "unknown"),
            "translation_rights_status": "unknown", "rule_base": base}


def read_problems(path):
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("problems")
    if not isinstance(data, list):
        raise ValueError("输入需为数组、problems 对象或 JSONL")
    return data
