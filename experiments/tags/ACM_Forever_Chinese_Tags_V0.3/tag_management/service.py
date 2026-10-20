"""Overlay corrections at query time; automatic files and old review states stay intact."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from annotation_api.adapter import canonical_identity, human_confirmed
from label_pipeline import BASE, TAG_BY_ID, TAXONOMY, prepare
from .model import (VERSION, effective_ids, empty_state, identity, ids, ordered,
                    resolve_tag, validate_state, verification_fingerprint)
from .storage import Journal, read_jsonl

DEFAULT_OVERRIDES = BASE / "manual_labels" / "overrides.jsonl"
DEFAULT_SETTINGS = BASE / "manual_labels" / "settings.json"


def automatic_path(path=None):
    if path is not None:
        return Path(path).resolve()
    settings = json.loads(DEFAULT_SETTINGS.read_text(encoding="utf-8"))
    if settings == {"schema_version": VERSION, "storage": "persistent"}:
        from problem_processing.repository import Repository
        folder = Repository().current()
        if folder is None:
            raise ValueError("持久标签目录为空，请先运行 import_tags.py")
        return folder / "auto_tags.jsonl"
    if set(settings) != {"schema_version", "auto_file"} or settings["schema_version"] != VERSION:
        raise ValueError("自动标签来源配置不兼容")
    value = settings["auto_file"]
    if not isinstance(value, str) or not value:
        raise ValueError("请配置明确的自动标签文件，不自动选择模型或运行目录")
    path = Path(value)
    return (BASE / path).resolve() if not path.is_absolute() else path.resolve()


def auto_record(row):
    from problem_processing.adapter import source_identity
    platform, contest, pid, key, url = source_identity(row)
    if row.get("taxonomy_version") != TAXONOMY["version"]:
        raise ValueError("自动结果标签版本不兼容")
    specific = ids(row.get("evaluation_specific_tag_ids", row.get("specific_tag_ids", [])))
    provisional = ids(row.get("evaluation_provisional_tag_ids", row.get("provisional_tag_ids", [])))
    if any(TAG_BY_ID[x]["tag_kind"] != "specific" for x in specific) or any(TAG_BY_ID[x]["tag_kind"] != "provisional" for x in provisional):
        raise ValueError("自动结果的具体/临时标签分类错误")
    legacy_verified = human_confirmed(row) or row.get("human_review_status") == "verified"
    baseline = (prepare({"platform": platform, "contest_id": contest, "problem_id": pid,
                         "tags": row.get("raw_tags", []), "content_hash": row.get("content_hash")})
                if platform != "nowcoder" else
                {"cf_exact_tag_ids": [], "provisional_tag_ids": [], "raw_tags": row.get("raw_tags", [])})
    cf_exact = baseline["cf_exact_tag_ids"]
    if platform == "codeforces" and not legacy_verified:
        specific = ordered(specific + cf_exact)
    tags = ordered(specific + provisional)
    origins = {}
    for tag in tags:
        origins[tag] = ("legacy_human" if legacy_verified else "cf_rule_mapping" if
                        platform == "codeforces" and (tag in cf_exact or tag in baseline["provisional_tag_ids"])
                        else "ai")
    issues = []
    status = row.get("api_call_status")
    if status in {"failed", "unknown_delivery", "sent", "retry_wait"} or row.get("error"):
        issues.append("automatic_call_failed_or_uncertain")
    if row.get("human_review_stale"):
        issues.append("legacy_human_content_changed")
    if row.get("review_status") == "needs_review" or row.get("human_review_status") == "needs_review":
        issues.append("explicit_review_required")
    if platform in {"atcoder", "nowcoder"} and status != "success" and not legacy_verified and not row.get("ai_annotation"):
        issues.append("missing_successful_auto_annotation")
    if "specific_tag_ids" not in row and "evaluation_specific_tag_ids" not in row:
        issues.append("missing_auto_tag_fields")
    content_hash = row.get("content_hash")
    if content_hash is not None and (not isinstance(content_hash, str) or not content_hash.strip()):
        raise ValueError("自动结果 content_hash 非法")
    return {"problem_key": key, "platform": platform, "title": row.get("title"), "source_url": url,
            "content_hash": content_hash, "tag_ids": tags, "origins": origins,
            "tags": [{"id": tag, "name_zh": TAG_BY_ID[tag]["name_zh"],
                      "tag_kind": TAG_BY_ID[tag]["tag_kind"], "source": origins[tag]} for tag in tags],
            "raw_tags": baseline["raw_tags"], "cf_exact_tag_ids": cf_exact,
            "model": row.get("model"), "taxonomy_version": TAXONOMY["version"],
            "legacy_review_status": row.get("review_status"),
            "legacy_human_review_status": row.get("human_review_status"),
            "legacy_verified": legacy_verified, "issues": issues}


class TagManager:
    def __init__(self, auto_file=None, override_file=None):
        self.auto_file = automatic_path(auto_file)
        if override_file is None:
            from problem_processing.repository import data_root
            root = data_root()
            override_file = root / "manual" / "overrides.jsonl" if self.auto_file.is_relative_to(root / "catalog") else DEFAULT_OVERRIDES
        self.journal = Journal(override_file)
        if self.auto_file == self.journal.path:
            raise ValueError("人工修正文件不能与自动结果文件相同")

    def catalog(self):
        if not self.auto_file.is_file():
            raise ValueError("自动标签文件不存在；请设置 --auto-file 或 manual_labels/settings.json")
        result = {}
        for row in read_jsonl(self.auto_file):
            auto = auto_record(row)
            if auto["problem_key"] in result:
                raise ValueError("自动文件包含重复题目；请明确选择单次模型运行结果")
            result[auto["problem_key"]] = auto
        return result

    def _auto(self, key):
        key = identity(key)
        catalog = self.catalog()
        if key not in catalog:
            raise ValueError("自动标签文件中找不到该题目")
        return catalog[key]

    def _view(self, auto, state, events):
        final = effective_ids(auto, state)
        issues = list(auto["issues"])
        active = bool(state["added_tag_ids"] or state["removed_tag_ids"] or state["verified_fingerprint"])
        if active:
            if not auto["content_hash"] or not state["anchor_content_hash"]:
                issues.append("manual_content_hash_unavailable")
            elif auto["content_hash"] != state["anchor_content_hash"]:
                issues.append("content_changed_since_manual_edit")
            if state["verified_fingerprint"] and state["verified_fingerprint"] != verification_fingerprint(auto, state):
                issues.append("automatic_labels_changed_since_verification")
        status = ("needs_review" if issues else "verified" if state["verified_fingerprint"] or
                  (auto["legacy_verified"] and not active) else "corrected" if active else "auto")
        sources = {tag: ([auto["origins"][tag]] if tag in auto["origins"] else []) +
                   (["manual_add"] if tag in state["added_tag_ids"] else []) for tag in final}
        own_events = [event for event in events if event["problem_key"] == auto["problem_key"]]
        return {"problem_key": auto["problem_key"], "platform": auto["platform"], "title": auto["title"],
                "source_url": auto["source_url"], "content_hash": auto["content_hash"],
                "taxonomy_version": TAXONOMY["version"], "auto_tags": deepcopy(auto),
                "manual_overrides": {**deepcopy(state), "history_count": len(own_events),
                                     "last_event_id": own_events[-1]["event_id"] if own_events else None},
                "effective_tags": [{"id": tag, "name_zh": TAG_BY_ID[tag]["name_zh"],
                                    "tag_kind": TAG_BY_ID[tag]["tag_kind"], "sources": sources[tag],
                                    "source": "manual_add" if "manual_add" in sources[tag] else sources[tag][0]}
                                   for tag in final],
                "specific_tag_ids": [tag for tag in final if TAG_BY_ID[tag]["tag_kind"] == "specific"],
                "provisional_tag_ids": [tag for tag in final if TAG_BY_ID[tag]["tag_kind"] == "provisional"],
                "specific_tag_names_zh": [TAG_BY_ID[tag]["name_zh"] for tag in final if TAG_BY_ID[tag]["tag_kind"] == "specific"],
                "provisional_tag_names_zh": [TAG_BY_ID[tag]["name_zh"] for tag in final if TAG_BY_ID[tag]["tag_kind"] == "provisional"],
                "review_status": status, "human_review_status": status,
                "needs_review_reasons": list(dict.fromkeys(issues)),
                "recommendation_eligible": status != "needs_review",
                "fully_human_verified": status == "verified"}

    def get_effective_tags(self, problem_key):
        return self.get_effective_tags_many([problem_key])[0]

    def get_effective_tags_many(self, problem_keys):
        keys = [identity(key) for key in problem_keys]
        catalog = self.catalog()
        events, states = self.journal.read()
        by_problem = {}
        for event in events:
            by_problem.setdefault(event["problem_key"], []).append(event)
        if any(key not in catalog for key in keys):
            raise ValueError("自动标签文件中找不到部分题目")
        return [self._view(catalog[key], states.get(key, empty_state()), by_problem.get(key, [])) for key in keys]

    def iter_effective_tags(self, platform=None, tag_ids=None, status=None):
        if platform is not None and platform not in {"codeforces", "atcoder", "nowcoder"}:
            raise ValueError("非法平台筛选")
        if status is not None and status not in {"auto", "corrected", "verified", "needs_review"}:
            raise ValueError("非法状态筛选")
        wanted = {resolve_tag(tag) for tag in (tag_ids or [])}
        catalog = self.catalog()
        events, states = self.journal.read()
        by_problem = {}
        for event in events:
            by_problem.setdefault(event["problem_key"], []).append(event)
        for key, auto in catalog.items():
            if platform is not None and auto["platform"] != platform:
                continue
            view = self._view(auto, states.get(key, empty_state()), by_problem.get(key, []))
            if status is not None and view["review_status"] != status:
                continue
            if wanted and not wanted.issubset({t["id"] for t in view["effective_tags"]}):
                continue
            yield view

    def history(self, problem_key):
        key = identity(problem_key)
        events, _ = self.journal.read()
        return [event for event in events if event["problem_key"] == key]

    def list_overrides(self):
        events, states = self.journal.read()
        catalog = self.catalog()
        results = []
        for key, state in states.items():
            if not (state["added_tag_ids"] or state["removed_tag_ids"] or state["verified_fingerprint"]):
                continue
            if key in catalog:
                results.append(self._view(catalog[key], state, events))
            else:
                # A change of model/dataset must not hide persistent corrections.
                results.append({"problem_key": key, "manual_overrides": state,
                                "review_status": "needs_review", "recommendation_eligible": False,
                                "needs_review_reasons": ["automatic_problem_missing"]})
        return results

    def change(self, problem_key, operation, tags=(), *, actor="local_admin", reason=""):
        key = identity(problem_key)
        if operation not in {"add", "remove", "replace", "reset", "verify", "undo"}:
            raise ValueError("未知人工操作")
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str):
            raise ValueError("请提供有效操作人及文字原因")
        resolved = list(dict.fromkeys(resolve_tag(tag) for tag in tags))
        if operation in {"add", "remove"} and not resolved:
            raise ValueError("请至少指定一个标签")
        if operation == "replace" and len(resolved) != 2:
            raise ValueError("replace 需要两个不同标签")
        if operation in {"reset", "verify", "undo"} and resolved:
            raise ValueError("此操作不接受标签参数")
        with self.journal.locked():
            events, states = self.journal.read()
            # Reload automatic results inside the transaction, never write them.
            auto = self._auto(key)
            before = deepcopy(states.get(key, empty_state()))
            after = deepcopy(before)
            details = {"tag_ids": resolved}
            if operation == "reset":
                after = empty_state()
            elif operation == "undo":
                own = [event for event in events if event["problem_key"] == key]
                if not own:
                    return {"changed": False, "message": "没有可撤销的人工操作", "result": self._view(auto, before, events)}
                after = deepcopy(own[-1]["before"])
                details["undo_event_id"] = own[-1]["event_id"]
            elif operation == "verify":
                if auto["issues"] or not auto["content_hash"]:
                    raise ValueError("自动结果异常或缺少题面哈希，不能完整确认")
                after["anchor_content_hash"] = auto["content_hash"]
                after["verified_fingerprint"] = verification_fingerprint(auto, after)
            else:
                added, removed = set(before["added_tag_ids"]), set(before["removed_tag_ids"])
                if operation == "replace":
                    old, new = resolved
                    if old not in effective_ids(auto, before) and not (old in removed and new in added):
                        raise ValueError("待替换标签不在当前有效标签中")
                    removed.add(old); added.discard(old)
                    added.add(new); removed.discard(new)
                for tag in resolved if operation != "replace" else []:
                    if operation == "add":
                        added.add(tag); removed.discard(tag)
                    else:
                        removed.add(tag); added.discard(tag)
                after["added_tag_ids"], after["removed_tag_ids"] = ordered(added), ordered(removed)
                if after["added_tag_ids"] != before["added_tag_ids"] or after["removed_tag_ids"] != before["removed_tag_ids"]:
                    after["verified_fingerprint"] = None
                    # Keep the first edit's anchor until an explicit reset or verification.
                    if not (before["added_tag_ids"] or before["removed_tag_ids"] or before["verified_fingerprint"]):
                        after["anchor_content_hash"] = auto["content_hash"]
            after = validate_state(after)
            if after == before:
                return {"changed": False, "message": "状态未变化，重复操作已跳过", "result": self._view(auto, before, events)}
            event = {"schema_version": VERSION, "event_id": uuid4().hex,
                     "previous_event_id": events[-1]["event_id"] if events else None,
                     "problem_key": key, "operation": operation,
                     "created_at": datetime.now(timezone.utc).isoformat(), "actor": actor.strip(), "reason": reason,
                     "taxonomy_version": TAXONOMY["version"], "before": before, "after": after,
                     "automatic_snapshot": deepcopy(auto), "details": details}
            self.journal.write(events + [event])
            return {"changed": True, "message": "人工操作已原子保存，原始预测保持不变", "event_id": event["event_id"],
                    "result": self._view(auto, after, events + [event])}


def get_effective_tags(problem_key, *, auto_file=None, override_file=None):
    """Default source is pinned in manual_labels/settings.json; never guess a latest model."""
    return TagManager(auto_file, override_file).get_effective_tags(problem_key)


def get_effective_tags_many(problem_keys, *, auto_file=None, override_file=None):
    return TagManager(auto_file, override_file).get_effective_tags_many(problem_keys)


def iter_effective_tags(platform=None, tag_ids=None, status=None, *, auto_file=None, override_file=None):
    yield from TagManager(auto_file, override_file).iter_effective_tags(platform, tag_ids, status)
