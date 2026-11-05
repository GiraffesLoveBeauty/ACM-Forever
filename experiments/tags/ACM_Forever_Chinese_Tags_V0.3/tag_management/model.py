"""V0.3 validation and canonical manual state; no network dependencies."""
from annotation_api.adapter import canonical_identity, digest
from label_pipeline import TAG_BY_ID, TAXONOMY, validate_id_list

VERSION = 1
STATE_FIELDS = {"added_tag_ids", "removed_tag_ids", "anchor_content_hash", "verified_fingerprint"}


def identity(key):
    if isinstance(key, str) and key.startswith("nowcoder:"):
        from problem_processing.adapter import source_identity
        return source_identity({"problem_key": key})[3]
    return canonical_identity({"problem_key": key})[3]


def resolve_tag(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("标签不能为空")
    value = value.strip()
    if value in TAG_BY_ID:
        return value
    matches = [k for k, tag in TAG_BY_ID.items() if tag["name_zh"] == value]
    if len(matches) != 1:
        raise ValueError("未知或有歧义的标签，请使用 V0.3 标准 ID")
    return matches[0]


def ids(values):
    if not isinstance(values, list) or any(not isinstance(v, str) or v not in TAG_BY_ID for v in values):
        raise ValueError("标签列表含非法 V0.3 ID")
    if len(set(values)) != len(values):
        raise ValueError("标签列表含重复 ID")
    # Reuse the existing kind validator; do not maintain a second vocabulary.
    for kind in ("specific", "provisional"):
        validate_id_list([v for v in values if TAG_BY_ID[v]["tag_kind"] == kind], kind, "tags")
    return ordered(values)


def ordered(values):
    chosen = set(values)
    return [key for key in TAG_BY_ID if key in chosen]


def empty_state():
    return {"added_tag_ids": [], "removed_tag_ids": [], "anchor_content_hash": None,
            "verified_fingerprint": None}


def validate_state(value):
    if not isinstance(value, dict) or set(value) != STATE_FIELDS:
        raise ValueError("人工记录状态结构损坏")
    added, removed = ids(value["added_tag_ids"]), ids(value["removed_tag_ids"])
    if set(added) & set(removed):
        raise ValueError("同一标签不能同时新增和删除")
    for field in ("anchor_content_hash", "verified_fingerprint"):
        if value[field] is not None and (not isinstance(value[field], str) or not value[field].strip()):
            raise ValueError("人工记录哈希字段损坏")
    return {**value, "added_tag_ids": added, "removed_tag_ids": removed}


def effective_ids(auto, state):
    return ordered((set(auto["tag_ids"]) | set(state["added_tag_ids"])) - set(state["removed_tag_ids"]))


def verification_fingerprint(auto, state):
    return digest({"content_hash": auto["content_hash"], "taxonomy_version": TAXONOMY["version"],
                   "auto_tag_ids": auto["tag_ids"], "effective_tag_ids": effective_ids(auto, state)})
