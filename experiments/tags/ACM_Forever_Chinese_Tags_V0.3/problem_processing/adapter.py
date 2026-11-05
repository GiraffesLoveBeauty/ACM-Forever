"""Preserve crawler data and normalize a secondary-processing metadata contract."""
import json
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from annotation_api.adapter import adapt, digest
from .crawler_input import VERSION, expanded, is_crawler_record, resolve_identity, source_urls
from .statement import html_statement, newline

METADATA_VERSION = "secondary-1"


def normalized_attachments(attachments):
    """Accept the crawler's public ZIP references; never fetch or expand a file."""
    if not isinstance(attachments, list):
        raise ValueError("样例 attachments 必须为数组")
    result = {}
    for item in attachments:
        if not isinstance(item, dict) or set(item) - {"url", "name"}:
            raise ValueError("样例附件仅接受 url 和 name 字段")
        url, name = item.get("url"), item.get("name", "官方样例 ZIP")
        if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\()]", url):
            raise ValueError("样例附件 URL 格式错误")
        try:
            parts = urlsplit(url)
            valid = (parts.scheme == "https" and parts.hostname == "img.atcoder.jp"
                     and not parts.username and not parts.password and parts.port in (None, 443)
                     and parts.path.lower().endswith(".zip"))
            private_query = any(re.sub(r"[^a-z0-9]", "", key.lower()) in {
                "key", "apikey", "token", "accesstoken", "authtoken", "authorization",
                "password", "secret", "signature", "credential", "credentials",
            } for key, _ in parse_qsl(parts.query, keep_blank_values=True))
        except ValueError:
            valid, private_query = False, False
        if not valid or private_query:
            raise ValueError("样例附件必须是无认证信息的 AtCoder 官方 HTTPS ZIP 引用")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("样例附件 name 必须为非空字符串")
        value = {"url": url, "name": newline(name)}
        if url in result and result[url] != value:
            raise ValueError("相同样例附件 URL 的名称冲突")
        result[url] = value
    return [result[url] for url in sorted(result)]


def normalized_samples(samples, sample_count=None):
    """Preserve judge data: null plus a note is unavailable text, never empty I/O."""
    if samples is None:
        samples = []
    if not isinstance(samples, list):
        raise ValueError("samples 必须为数组")
    result = []
    for sample in samples:
        if (not isinstance(sample, dict) or type(sample.get("index")) is not int
                or sample["index"] < 1 or "input" not in sample or "output" not in sample):
            raise ValueError("样例必须包含正整数 index、input 和 output 字段")
        value = deepcopy(sample)
        for kind in ("input", "output"):
            code, note = sample[kind], sample.get(kind + "_note")
            if not isinstance(code, str) and code is not None:
                raise ValueError(f"样例 {kind} 必须为字符串或带说明的 null")
            if kind + "_note" in sample and (not isinstance(note, str) or not note.strip()):
                raise ValueError(f"{kind}_note 必须为非空字符串")
            if code is None and not note:
                raise ValueError(f"样例未提供 {kind} 文本时必须提供 {kind}_note")
            value[kind] = newline(code) if code is not None else None
            if note is not None:
                value[kind + "_note"] = newline(note)
        if "source_index" in sample and (type(sample["source_index"]) is not int or sample["source_index"] < 0):
            raise ValueError("原始样例 source_index 必须为非负整数")
        if "attachments" in sample:
            value["attachments"] = normalized_attachments(sample["attachments"])
        result.append(value)
    if len({s["index"] for s in result}) != len(result):
        raise ValueError("样例序号重复")
    source_indices = [s["source_index"] for s in result if "source_index" in s]
    if len(set(source_indices)) != len(source_indices):
        raise ValueError("原始样例 source_index 重复")
    if sample_count is not None and (type(sample_count) is not int or sample_count != len(result)):
        raise ValueError("sample_count 与样例数量冲突")
    return sorted(result, key=lambda s: s["index"])


def sample_note_block(sample, kind="output"):
    # English protocol markers must not make a short English problem look Chinese.
    suffix = f" ({kind} omitted by source)" if sample[kind] is None else " (source explanation)"
    note = "\n".join("> " + line for line in sample[kind + "_note"].split("\n"))
    role = "expected output" if kind == "output" else "actual input"
    return (f"### Sample {kind.title()} {sample['index']}{suffix}\n\n"
            f"> Original-source note; this is not {role}.\n" + note)


def sample_attachment_block(sample):
    def label(name):
        return re.sub(r"([\\`\[\]<>])", r"\\\1", name).replace("\n", " ")
    links = "\n".join(f"- [{label(a['name'])}]({a['url']})" for a in sample["attachments"])
    return (f"### Sample Files {sample['index']} (external ZIP references)\n\n"
            "> References only; files have not been downloaded or expanded.\n\n" + links)


def sample_pending_issues(samples):
    issues = set()
    for sample in samples:
        if sample["input"] is None:
            issues.add("sample_input_unavailable")
        if sample.get("attachments") and any(sample[k] is None for k in ("input", "output")):
            issues.add("sample_attachment_unexpanded")
    return sorted(issues)


def source_identity(row):
    platform = row.get("platform") or str(row.get("problem_key", "")).split(":")[0]
    if platform != "nowcoder":
        return resolve_identity(row)
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


def _normalize_legacy(row):
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


def _crawler_fields(row):
    value = expanded(row)
    platform, contest, pid, key, url = source_identity(value)
    original_id = value.get("source_problem_id", value.get("problem_id", value.get("id", pid)))
    links = source_urls(value)
    statement = value.get("statement") or {}
    if not isinstance(statement, dict):
        raise ValueError("statement 必须为对象")
    text = value.get("original_statement", value.get("statement_markdown", value.get("statement_text", statement.get("markdown")))) or ""
    raw_text = value.get("statement_text") or ""
    html = value.get("statement_html") or value.get("original_statement_html") or statement.get("html") or ""
    if not all(isinstance(x, str) for x in (text, raw_text, html)):
        raise ValueError("题面必须为文本，PDF 二进制不能作为正文")
    samples = normalized_samples(value.get("samples"), value.get("sample_count"))
    issues = []
    language = value.get("statement_language") or value.get("language") or "en"
    format_ = "text" if text.strip() else "missing"
    if html.strip():
        try:
            converted = html_statement(html, value.get("statement_source_url") or url or "", language)
        except (ValueError, OSError, ImportError, RecursionError):
            converted = {"text": "", "language": language, "issues": ["html_conversion_failed"]}
        # HTML contains more structure than the crawler's lossy plain-text column.
        text = converted["text"] or text
        language = converted["language"]
        issues.extend(converted["issues"])
        format_ = "html"
    text = newline(text)
    pdf = value.get("statement_pdf")
    pdf_present = bool(pdf) or bool(value.get("has_pdf")) or value.get("statement_format") == "pdf"
    pdf_metadata = {"present": pdf_present}
    if pdf:
        if isinstance(pdf, (bytes, bytearray)):
            import hashlib
            pdf_metadata.update(bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest())
        elif isinstance(pdf, str):
            # JSON exporters may supply a filename, URL or encoded representation;
            # none is treated as text, decoded, downloaded, or copied into API input.
            pdf_metadata["representation"] = "external_or_encoded_reference"
        elif isinstance(pdf, dict):
            pdf_metadata["representation"] = "metadata_object"
        else:
            raise ValueError("不支持的 PDF 元数据类型")
    if pdf_present and not html and "\n" not in text and re.fullmatch(r"\S+\.pdf(?:[?#]\S*)?", text.strip(), re.I):
        text = ""
    if not text.strip():
        status = "pdf_pending" if pdf_present else "html_pending" if html else "missing_statement"
        issues.append(status)
        if pdf_present:
            format_ = "pdf"
    else:
        status = "html_pending" if issues else "ready"
    fetch = value.get("last_fetch_status")
    if fetch is not None and fetch not in {"ok", "never", "failed"}:
        raise ValueError("非法采集状态")
    if fetch in {"failed", "never"}:
        issues.append("source_fetch_" + fetch)
        if status == "ready":
            status = "source_pending"
    if value.get("statement_status", statement.get("status")) not in (None, "ok"):
        issues.append("source_statement_not_ok")
        if status == "ready":
            status = "source_pending"
    sample_issues = sample_pending_issues(samples)
    issues.extend(sample_issues)
    if sample_issues and status == "ready":
        status = "sample_pending"
    # Samples are carried independently. Append any missing fenced sample,
    # including exports whose HTML fragment omits the separately stored samples.
    if text.strip() and samples:
        for sample in samples:
            for kind, heading in (("input", "Sample Input"), ("output", "Sample Output")):
                code = sample[kind]
                if code is None:
                    # Keep missing-text explanations outside all input/output fences.
                    block = sample_note_block(sample, kind)
                    if block not in text:
                        text += "\n\n" + block
                    continue
                fence = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", code)), default=0))
                block = f"{fence}\n{code}" + ("" if code.endswith("\n") else "\n") + fence
                if not html or block not in text:
                    text += f"\n\n### {heading} {sample['index']}\n\n" + block
                if sample.get(kind + "_note"):
                    note_block = sample_note_block(sample, kind)
                    if note_block not in text:
                        text += "\n\n" + note_block
            if sample.get("attachments"):
                block = sample_attachment_block(sample)
                if block not in text:
                    text += "\n\n" + block
    # atcoder_collect.py exports sha256; SQL rows expose statement_sha256.
    source_hashes = [value[k] for k in ("source_statement_sha256", "statement_sha256", "sha256")
                     if value.get(k) is not None]
    if any(not isinstance(h, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", h) for h in source_hashes):
        raise ValueError("爬虫 statement_sha256 必须为 SHA-256 十六进制字符串")
    if len({h.lower() for h in source_hashes}) > 1:
        raise ValueError("爬虫原始题面哈希字段冲突")
    source_sha = source_hashes[0] if source_hashes else None
    input_row = {**value, "problem_key": key, "platform": platform, "contest_id": contest,
                 "problem_id": pid, "original_statement": text, "statement_markdown": text,
                 "statement_html": html, "statement_status": "ok" if status == "ready" else status,
                 "source_links": links}
    # Never reuse a differently defined source hash as the normalized content hash.
    input_row.pop("content_hash", None)
    input_row.pop("source_problem_id", None)
    input_row.pop("metadata_json", None)
    extras = {"source_problem_id": original_id, "source_statement_sha256": source_sha,
              "source_content_hash": value.get("content_hash"), "source_statement_text": raw_text,
              "statement_format": format_, "processing_status": status, "processing_issues": sorted(set(issues)),
              "samples": samples, "pdf_metadata": pdf_metadata, "language_hint": language,
              "source_fetched_at": value.get("statement_fetched_at", value.get("fetched_at")),
              "source_fetch_status": fetch, "source_updated_at": value.get("updated_at"),
              "difficulty_source": value.get("difficulty_source"), "source_problem_index": value.get("problem_index")}
    return input_row, extras


def _derived_hashes(result):
    from .translation import language_plan
    plan = language_plan(result)
    return {"normalized_content_hash": digest({"problem_key": result["problem_key"], "title": result["original_title"],
                                               "statement_markdown": result["original_statement"]}),
            "translation_input_hash": digest({"key": result["problem_key"], "title": result["original_title"],
                                              "action": plan["action"], "language": plan["source_language"], "text": plan["source_text"]})}


def normalize(row):
    """Normalize new crawler records while keeping legacy identities/hashes intact."""
    if not isinstance(row, dict):
        raise ValueError("题目必须是 JSON 对象")
    if row.get("input_adapter_version") not in (None, VERSION):
        raise ValueError("不支持的输入适配版本")
    if row.get("input_adapter_version") == VERSION:
        # Re-importing our own output is idempotent; do not append samples twice.
        if "samples" in row and normalized_samples(row["samples"], row.get("sample_count")) != row["samples"]:
            raise ValueError("规范题目样例元数据损坏")
        samples = row.get("samples", [])
        if row["original_statement"].strip() and any(
                s.get(kind + "_note") and sample_note_block(s, kind) not in row["original_statement"]
                for s in samples for kind in ("input", "output")):
            raise ValueError("规范题目样例说明与正文不一致")
        if row["original_statement"].strip() and any(s.get("attachments") and
                sample_attachment_block(s) not in row["original_statement"] for s in samples):
            raise ValueError("规范题目样例附件与正文不一致")
        if sample_pending_issues(samples) and (row.get("processing_status") == "ready" or row.get("statement_status") == "ok"):
            raise ValueError("样例文本尚未展开，规范题目不能标记 ready")
        if source_identity(row)[3] != row["problem_key"] or digest({"title": row["original_title"],
                "text": row["original_statement"], "html": row["original_statement_html"]}) != row["verified_content_hash"]:
            raise ValueError("规范题目身份或正文哈希损坏")
        if row["rule_base"]["content_hash"] != row["content_hash"] or row["rule_base"]["problem_key"] != row["problem_key"]:
            raise ValueError("规范题目与规则标签不匹配")
        if row["title"] != row["original_title"] or row["statement_markdown"] != row["original_statement"]:
            raise ValueError("规范题目的 API 字段别名不一致")
        if any(row[k] != v for k, v in _derived_hashes(row).items()):
            raise ValueError("规范题目输入哈希损坏")
        if row["platform"] in {"atcoder", "codeforces"} and adapt(row)["annotation_input_hash"] != row["annotation_input_hash"]:
            raise ValueError("规范题目标签输入哈希损坏")
        return deepcopy(row)
    source = row
    extras = {}
    if is_crawler_record(row):
        source, extras = _crawler_fields(row)
    result = _normalize_legacy(source)
    result.update(extras)
    result.setdefault("source_statement_sha256", row.get("source_statement_sha256"))
    result.setdefault("statement_format", "text" if result["original_statement"].strip() else "html" if result["original_statement_html"] else "missing")
    result.setdefault("processing_status", "ready" if result["statement_status"] == "ok" else "html_pending" if result["statement_status"] == "html_only" else "missing_statement")
    result.setdefault("processing_issues", [] if result["processing_status"] == "ready" else [result["statement_status"]])
    result.update(problem_id=source_identity(source)[2], title=result["original_title"],
                  statement_markdown=result["original_statement"],
                  source_url=result["source_links"][0] if result["source_links"] else None,
                  input_adapter_version=VERSION)
    # Keep prepare()/adapt() as the only label/evidence authority.
    if result["platform"] in {"codeforces", "atcoder"}:
        item = adapt({**source, **{k: result[k] for k in ("problem_key", "platform", "contest_id", "problem_id", "title",
                      "statement_markdown", "statement_status", "content_hash", "raw_tags", "source_url")}})
        result.update({k: item["evidence"][k] for k in ("verified_editorial_markdown", "editorial_status", "editorial_evidence_kind")})
        result["annotation_input_hash"] = item["annotation_input_hash"]
    else:
        result["annotation_input_hash"] = None  # No Nowcoder annotation schema invented here.
    result.update(_derived_hashes(result))
    return result


def read_problems(path):
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("problems", data.get("items", [data] if "platform" in data or "problem_key" in data else None))
    if not isinstance(data, list):
        raise ValueError("输入需为数组、problems 对象或 JSONL")
    return data
