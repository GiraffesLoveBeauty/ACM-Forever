"""Adapt crawler/flattened records, keeping prepare() as mapping authority."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from label_pipeline import prepare, problem_key, TAG_BY_ID, TAXONOMY, validate_id_list


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def text_field(value, name):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def canonical_identity(p):
    if not isinstance(p, dict):
        raise ValueError("Record must be an object")
    key = p.get("problem_key")
    platform = p.get("platform")
    contest, pid = p.get("contest_id"), p.get("problem_id")
    if key:
        if not isinstance(key, str) or len(parts := key.split(":")) != 3 or not all(parts):
            raise ValueError("Invalid problem_key")
        kp, kc, ki = parts
        if platform and platform != kp:
            raise ValueError("Conflicting platform")
        platform = kp
        if platform == "codeforces" and not re.fullmatch(r"(?:[A-Z]{1,3}\d{0,2}|\d{1,3})", ki):
            raise ValueError("Noncanonical CF index in problem_key")
        if contest is not None and str(contest) != kc:
            raise ValueError("Conflicting contest_id")
        if pid is not None:
            # An explicit key already separates a numeric CF index from its contest.
            allowed = {ki, kc + ki} if platform == "codeforces" else {ki}
            if str(pid) not in allowed:
                raise ValueError("Conflicting problem_id")
        contest, pid = kc, ki
    if platform not in {"atcoder", "codeforces"} or not contest or not pid:
        raise ValueError("Missing/unsupported source identity")
    canonical = (key if key and platform == "codeforces" else
                 problem_key({"platform": platform, "contest_id": str(contest), "problem_id": str(pid)}))
    if key and canonical != key:
        raise ValueError("problem_key must use canonical identity")
    url = p.get("url") or p.get("problem_url") or p.get("source_url")
    if url:
        if not isinstance(url, str):
            raise ValueError("url must be string")
        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        from_url = None
        if parsed.hostname in {"atcoder.jp", "www.atcoder.jp"} and len(parts) == 4 and parts[0] == "contests" and parts[2] == "tasks":
            from_url = f"atcoder:{parts[1]}:{parts[3]}"
        if parsed.hostname in {"codeforces.com", "www.codeforces.com"}:
            if len(parts) == 4 and parts[0] in {"contest", "gym"} and parts[2] == "problem":
                from_url = f"codeforces:{parts[1]}:{parts[3]}"
            elif len(parts) == 4 and parts[:2] == ["problemset", "problem"]:
                from_url = f"codeforces:{parts[2]}:{parts[3]}"
        if from_url and from_url != canonical:
            raise ValueError("Official URL identity conflicts with problem_key")
    return platform, str(contest), canonical.split(":", 2)[2], canonical, url


def human_confirmed(p):
    return (p.get("review_status") == "human_confirmed" or
            p.get("human_review_status") in {"approved", "human_confirmed"} or
            p.get("reviewed") is True)


def apply_review(base, review):
    if not human_confirmed(review):
        return base
    if review.get("problem_key") != base["problem_key"]:
        raise ValueError("Human review identity mismatch")
    if review.get("taxonomy_version") != TAXONOMY["version"]:
        raise ValueError("Human review taxonomy mismatch")
    if "accepted_specific_tag_ids" not in review and "specific_tag_ids" not in review:
        raise ValueError("Human-confirmed record must explicitly contain its accepted labels")
    specific = validate_id_list(review.get("accepted_specific_tag_ids", review.get("specific_tag_ids", [])), "specific", "human specific")
    provisional = validate_id_list(review.get("accepted_provisional_tag_ids", review.get("provisional_tag_ids", [])), "provisional", "human provisional")
    result = dict(base)
    result.update(specific_tag_ids=specific, provisional_tag_ids=provisional,
                  specific_tag_names_zh=[TAG_BY_ID[x]["name_zh"] for x in specific],
                  provisional_tag_names_zh=[TAG_BY_ID[x]["name_zh"] for x in provisional],
                  review_status="human_confirmed", human_review_status="approved", needs_ai=False,
                  human_review=dict(review),
                  human_review_stale=bool(review.get("content_hash") and review["content_hash"] != base["content_hash"]),
                  human_review_version_verified=bool(review.get("content_hash")))
    return result


def adapt(p, line=1, review=None):
    platform, contest, pid, key, url = canonical_identity(p)
    raw = p.get("raw_tags", p.get("tags", [])) or []
    if isinstance(raw, dict):
        raw = raw.get("values") or []
    statement_obj = p.get("statement") or {}
    if not isinstance(statement_obj, dict):
        raise ValueError("statement must be object")
    statement = text_field(p.get("statement_markdown", statement_obj.get("markdown")), "statement_markdown")
    editorial_obj = p.get("editorial") or {}
    if not isinstance(editorial_obj, dict):
        raise ValueError("editorial must be object")
    # Raw CF exports follow the same status=ok contract as make_samples.plain().
    raw_editorial = editorial_obj.get("markdown") if platform == "codeforces" and editorial_obj.get("status") == "ok" else None
    editorial = text_field(p.get("verified_editorial_markdown", raw_editorial), "verified_editorial_markdown")
    editorial_status = p.get("editorial_status", editorial_obj.get("status", "missing"))
    editorial_kind = p.get("editorial_evidence_kind", "official_editorial")
    # Only explicitly verified, matched evidence enters the prompt.
    if editorial_status != "ok" or editorial_kind not in {"official_editorial", "other_verified_solution"}:
        editorial = ""
    evidence = {"statement_markdown": statement, "statement_status": p.get("statement_status", statement_obj.get("status", "ok" if statement.strip() else "missing")),
                "verified_editorial_markdown": editorial, "editorial_status": editorial_status,
                "editorial_evidence_kind": editorial_kind}
    title = text_field(p.get("title", p.get("problem_name")), "title")
    content_hash = p.get("content_hash")
    if content_hash is not None and (not isinstance(content_hash, str) or not content_hash.strip()):
        raise ValueError("content_hash must be nonempty string or null")
    content_hash = content_hash or digest({"problem_key": key, "title": title, "statement_markdown": statement})
    # prepare() accepts combined CF IDs; protect the rare numeric index beginning
    # with the contest digits from its legacy combined-ID prefix stripping.
    prepared_pid = contest + pid if platform == "codeforces" and pid.startswith(contest) else pid
    base = prepare({"platform": platform, "contest_id": contest, "problem_id": prepared_pid,
                    "title": title, "url": url, "tags": raw, "content_hash": content_hash})
    base["problem_id"] = pid
    base["human_review_status"] = "pending_review" if base["needs_ai"] else "not_reviewed"
    if human_confirmed(p):
        base = apply_review(base, p)
    if review is not None:
        base = apply_review(base, review)
    return {"rule_base": base, "evidence": evidence, "source_line": line,
            "annotation_input_hash": digest({"key": key, "title": title, "raw_tags": raw, "evidence": evidence}),
            "has_statement": bool(statement.strip()) and evidence["statement_status"] == "ok"}


def load_inputs(path, platform="all", limit=None, reviews=None):
    """Stable distinct selection. Conflicting duplicate keys invalidate the whole key."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    rows, errors, seen, conflicts = [], [], {}, set()
    duplicates = 0
    for line, value in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not value.strip():
            continue
        key = None
        try:
            p = json.loads(value)
            source, _, _, key, _ = canonical_identity(p)
            if platform != "all" and source != platform:
                continue
            item = adapt(p, line, (reviews or {}).get(key))
            signature = digest({"input": item["annotation_input_hash"], "base": item["rule_base"]})
            if key in seen:
                duplicates += 1
                if seen[key] != signature:
                    conflicts.add(key)
                    errors.append({"source_line": line, "problem_key": key, "error_code": "conflicting_duplicate"})
                continue
            seen[key] = signature
            rows.append(item)
        except (ValueError, TypeError, KeyError) as exc:
            if key in seen:
                conflicts.add(key)
            # Fixed error category only: raw external values are not written to logs.
            errors.append({"source_line": line, "problem_key": key, "error_code": "invalid_input", "error_type": type(exc).__name__})
    rows = [x for x in rows if x["rule_base"]["problem_key"] not in conflicts]
    return (rows[:limit] if limit else rows), errors, duplicates
