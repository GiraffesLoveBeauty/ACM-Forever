"""Read-only, semantic task planning. This module never executes a plan or loads credentials."""
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

from annotation_api import PROMPT_VERSION, RULE_VERSION
from annotation_api.adapter import adapt, digest
from annotation_api.prompt import SYSTEM as ANNOTATION_PROMPT
from annotation_api.schema import SCHEMA as ANNOTATION_SCHEMA
from label_pipeline import BASE, MAPPING, TAXONOMY
from tag_management.service import auto_record
from .adapter import normalize
from .backup import check_sensitive, checked_path, safe_relative
from .repository import Repository
from .translation import SYSTEM as TRANSLATION_PROMPT, SCHEMA as TRANSLATION_SCHEMA
from .translation import TRANSLATION_VERSION, language_plan, translation_ready

VERSION = "offline-plan-1"
OUTPUT_ROOT = BASE / "outputs" / "plans"
HEX = re.compile(r"[0-9a-f]{64}")


def task_policies(annotation_revision=PROMPT_VERSION, translation_revision=TRANSLATION_VERSION):
    """Explicit semantic revisions; filesystem paths and implementation bytes are not task inputs."""
    from annotation_api import prompt, schema
    from . import translation
    return {
        "annotation": {"revision": annotation_revision, "prompt_hash": digest(prompt.SYSTEM),
                       "schema_hash": digest(schema.SCHEMA), "taxonomy_hash": digest(TAXONOMY),
                       "mapping_hash": digest(MAPPING), "rule_version": RULE_VERSION},
        "translation": {"revision": translation_revision, "prompt_hash": digest(translation.SYSTEM),
                        "schema_hash": digest(translation.SCHEMA), "target_language": "zh-CN"}}


def _text(value):
    return (value or "").replace("\r\n", "\n").replace("\r", "\n")


def semantic_inputs(problem):
    """Ignore unavailable editorial status spellings, retain all usable solution evidence."""
    editorial = problem.get("verified_editorial_markdown") or ""
    kind = problem.get("editorial_evidence_kind", "official_editorial")
    if problem.get("editorial_status") != "ok" or kind not in {"official_editorial", "other_verified_solution"}:
        editorial = ""
    common = {"problem_key": problem["problem_key"], "title": _text(problem["original_title"])}
    annotation = {**common, "statement": _text(problem["original_statement"]),
                  "raw_tags": sorted(set(problem["raw_tags"])), "editorial": _text(editorial),
                  "editorial_kind": kind if editorial else None}
    language = language_plan(problem)
    translation = {**common, "text": _text(language["source_text"]), "language": language["source_language"],
                   "action": language["action"]}
    return annotation, translation


def historical_problem(row):
    # secondary-1 predates the API aliases. Preserve HTML evidence while upgrading in memory only.
    source = deepcopy(row)
    if not source.get("input_adapter_version"):
        source["statement_html"] = source.get("original_statement_html", "")
    result = normalize(source)
    expected = digest({"title": row["original_title"], "text": row["original_statement"],
                       "html": row.get("original_statement_html", "")})
    if row.get("verified_content_hash") != expected:
        raise ValueError("历史正文校验失败")
    return result


def _read(path):
    return json.loads(checked_path(path).read_text(encoding="utf-8"))


class Planner:
    """Snapshot/indexes loaded once; no repository import, export, client or writer is invoked."""
    def __init__(self, root=None, *, cache_roots=None, manifest_roots=None, policies=None, ignore_execution_task_ids=()):
        self.repo = Repository(root)
        self.policies = deepcopy(policies or task_policies())
        if set(self.policies) != {"annotation", "translation"}:
            raise ValueError("必须分别提供标签与翻译策略")
        self.folder = self.repo.current()
        self.problems, self.automatic = self.repo.snapshot(self.folder)
        self.views = {v["problem_key"]: v for v in self.repo.manager(self.folder).get_effective_tags_many(
            sorted(self.automatic))} if self.folder else {}
        index = self.repo.root / "translations/current.json"
        self.translation_index = _read(index) if index.exists() else {}
        self.profiles, self.cache = {}, {}
        self.version_file_hashes = {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                                   for name in ("tag_taxonomy_v0.3.json", "cf_mapping_v0.3.json")}
        self.warnings = []
        self.blockers = {"annotation": set(), "translation": set()}
        self.executions = []
        try:
            from .execution_state import Ledger
            self.executions = [r for r in Ledger(self.repo.root).records() if r["task_id"] not in ignore_execution_task_ids]
        except (ValueError, OSError, KeyError, TypeError):
            for task in self.blockers:
                self.blockers[task].add("execution_ledger_requires_audit")
        for root_path in (manifest_roots if manifest_roots is not None else [BASE / "outputs"]):
            for path in self._files(root_path, "manifest.json", "annotation"):
                try:
                    value = _read(path)
                    profile = value["profile"]
                    if digest(profile) != value["profile_id"]:
                        raise ValueError("profile checksum")
                    self.profiles[value["profile_id"]] = profile
                except (OSError, ValueError, KeyError, TypeError):
                    self.warnings.append("unverified_annotation_manifest")
        for root_path in (cache_roots if cache_roots is not None else [BASE / "cache"]):
            for path in self._files(root_path, "*.json", "annotation"):
                try:
                    value = _read(path)
                    candidate = value.get("merged") or value.get("prediction") or {}
                    key = candidate.get("problem_key") or value.get("problem_key")
                    self._cache_entry("annotation", key, value, path, root_path)
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    self.blockers["annotation"].add("unreadable_request_record")
        requests = self.repo.root / "translations/requests"
        reverse = {fp: key for key, fp in self.translation_index.items()}
        for path in self._files(requests, "*.json", "translation"):
            try:
                value = _read(path)
                key = value.get("problem_key") or reverse.get(path.stem)
                if not key and HEX.fullmatch(path.stem):
                    history = self.repo.root / "translations/history" / path.name
                    if history.exists():
                        key = _read(history).get("problem_key")
                self._cache_entry("translation", key, value, path, requests)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                self.blockers["translation"].add("unreadable_request_record")

    def _files(self, root, pattern, task):
        try:
            root = checked_path(root)
            if not root.exists():
                return []
            return [checked_path(p) for p in sorted(root.rglob(pattern))]
        except (OSError, ValueError):
            self.blockers[task].add("unsafe_evidence_directory")
            return []

    def _cache_entry(self, task, key, value, path, root):
        state = value.get("state")
        if state not in {"prepared", "sent", "retry_wait", "received", "success", "failed", "unknown_delivery"}:
            raise ValueError("invalid request state")
        if key:
            from .adapter import source_identity
            if source_identity({"problem_key": key})[3] != key:
                raise ValueError("invalid cache identity")
            self.cache.setdefault((task, key), []).append({"state": state, "value": value,
                "source": task + "_requests/" + path.relative_to(checked_path(root)).as_posix()})
        elif state != "prepared":
            # Legacy sent/failed records may lack identity. Cannot safely issue any new task of this kind.
            self.blockers[task].add("unassigned_legacy_request")

    def _annotation_policy_matches(self, row):
        wanted = self.policies["annotation"]
        if row.get("processing_policy") is not None:
            return row["processing_policy"] == wanted
        profile = self.profiles.get(row.get("profile_id"))
        if not profile:
            return False
        hashes = profile.get("implementation_hashes", {})
        return (profile.get("prompt_version") == wanted["revision"]
                and profile.get("prompt_hash") == wanted["prompt_hash"]
                and profile.get("schema_hash") == wanted["schema_hash"]
                and profile.get("taxonomy_version") == TAXONOMY["version"]
                and profile.get("rule_version") == wanted["rule_version"]
                and all(hashes.get(name) == value for name, value in self.version_file_hashes.items())
                and wanted["taxonomy_hash"] == digest(TAXONOMY) and wanted["mapping_hash"] == digest(MAPPING))

    @staticmethod
    def _annotation_binding(row, old):
        item = adapt(old)
        expected = row.get("annotation_input_hash")
        if expected == item["annotation_input_hash"]:
            return True
        # secondary-1 omitted unavailable-editorial status. Reconstruct only known empty-evidence
        # spellings and require the original cryptographic hash, never infer equivalence from labels.
        if not item["evidence"]["verified_editorial_markdown"]:
            for status in ("missing", "not_found", "not_requested", "unavailable", "ambiguous"):
                evidence = {**item["evidence"], "editorial_status": status}
                if digest({"key": old["problem_key"], "title": old["original_title"],
                           "raw_tags": old["raw_tags"], "evidence": evidence}) == expected:
                    return True
        return False

    def _annotation(self, p, old, inputs, view):
        key = p["problem_key"]
        row = self.automatic.get(key)
        if (row and row.get("api_call_status") == "not_called" and not row.get("ai_annotation")
                and view and not view["fully_human_verified"]
                and not view["manual_overrides"]["added_tag_ids"] and not view["manual_overrides"]["removed_tag_ids"]):
            row = None  # An imported rule-base placeholder is not a completed annotation.
        if row:
            source = {"kind": "persistent_annotation", "generation": self.folder.name, "source_content_hash": row.get("content_hash"),
                      **{k: row.get(k) for k in ("request_fingerprint", "profile_id", "model", "provider",
                           "annotation_input_hash", "prompt_version", "annotation_rule_version", "taxonomy_version")}}
            auto = auto_record(row)
            if not old or row.get("content_hash") != old["content_hash"] or auto["issues"]:
                return "needs_review", "persistent_annotation_invalid_or_stale", source
            if semantic_inputs(old)[0] != inputs:
                return "needs_review", "annotation_semantic_input_changed", source
            # Old metadata sometimes omitted verified editorial fields entirely.
            ai = row.get("ai_annotation") or {}
            if ai.get("evidence_kind") in {"official_editorial", "other_verified_solution"} and not inputs["editorial"]:
                return "needs_review", "legacy_editorial_evidence_unavailable", source
            if view and view["needs_review_reasons"]:
                return "needs_review", "effective_labels_require_review", source
            if view and view["fully_human_verified"]:
                return "reuse_existing", "human_verified_labels_take_priority", source
            if not p["rule_base"]["needs_ai"]:
                return "reuse_existing", "cf_rule_mapping_available", source
            if not self._annotation_binding(row, old):
                return "needs_review", "legacy_annotation_input_binding_unverified", source
            if not self._annotation_policy_matches(row):
                return "needs_review", "annotation_policy_unverified_or_changed", source
            for cached in self.cache.get(("annotation", key), []):
                candidate = cached["value"].get("merged") or cached["value"].get("prediction") or {}
                if (cached["state"] == "success" and candidate.get("annotation_input_hash") == row.get("annotation_input_hash")
                        and candidate.get("content_hash") == row.get("content_hash") and self._annotation_policy_matches(candidate)
                        and auto_record(candidate)["tag_ids"] != auto["tag_ids"]):
                    return "needs_review", "persistent_and_cached_labels_conflict", source
            return "reuse_existing", "persisted_semantically_equivalent", source
        if p["platform"] == "codeforces" and not p["rule_base"]["needs_ai"]:
            return "not_required", "cf_exact_mapping_only", {"kind": "cf_rule_mapping"}
        if p["platform"] not in {"codeforces", "atcoder"}:
            return "needs_review", "annotation_platform_schema_unavailable", None
        cached = self.cache.get(("annotation", key), [])
        if cached:
            # Cache-only reuse needs an exact validated API input binding plus a known semantic policy.
            successes = [c for c in cached if c["state"] == "success"]
            candidates = []
            for c in successes:
                candidate = c["value"].get("merged") or c["value"].get("prediction") or {}
                auto = auto_record(candidate)
                if (not auto["issues"] and candidate.get("content_hash") == p["content_hash"]
                        and candidate.get("annotation_input_hash") == adapt(p)["annotation_input_hash"]
                        and self._annotation_policy_matches(candidate)):
                    candidates.append((c, candidate, auto))
            if candidates and len(candidates) == len(cached):
                if len({digest(c[2]["tag_ids"]) for c in candidates}) == 1:
                    c, candidate, auto = candidates[0]
                    return "reuse_existing", "cache_input_and_policy_verified", {
                        "kind": "annotation_cache", "source": c["source"], "model": candidate.get("model"),
                        "request_fingerprint": candidate.get("request_fingerprint"), "effective_tags": auto["tags"]}
            return "needs_review", "legacy_cache_unverified_or_conflicting", {"kind": "annotation_cache"}
        return "needs_annotation", "annotation_missing", None

    def _translation(self, p, old, inputs):
        key = p["problem_key"]
        fp = self.translation_index.get(key)
        if fp:
            if not isinstance(fp, str) or not HEX.fullmatch(fp):
                raise ValueError("非法翻译指针")
            row = _read(self.repo.root / "translations/history" / (fp + ".json"))
            source = {"kind": "persistent_translation", "request_fingerprint": fp,
                      "model": row.get("translation_model"), "version": row.get("translation_version")}
            if (row.get("problem_key") != key or row.get("request_fingerprint") != fp or not old
                    or row.get("source_content_hash") != old["content_hash"]
                    or row.get("source_verified_hash") != old["verified_content_hash"]):
                return "needs_review", "translation_source_binding_invalid", source
            if row.get("translation_status") != "auto" or str(row.get("translation_model", "")).startswith("mock"):
                return "needs_review", "mock_or_unsuccessful_translation_is_not_reusable", source
            if not row.get("title_zh") or not row.get("statement_zh"):
                return "needs_review", "translation_output_missing", source
            if semantic_inputs(old)[1] != inputs:
                return "needs_review", "translation_semantic_input_changed", source
            if row.get("processing_policy") != self.policies["translation"]:
                return "needs_review", "translation_policy_unverified_or_changed", source
            return "reuse_existing", "translation_semantically_equivalent", source
        if inputs["action"] == "skip":
            return "not_required", "already_simplified_chinese", None
        if inputs["action"] != "translate":
            return "pending", "language_or_source_incomplete", None
        if self.cache.get(("translation", key)):
            return "needs_review", "translation_request_exists_without_usable_result", {"kind": "translation_requests"}
        return "needs_translation", "translation_missing", None

    def one(self, raw):
        result = {"problem_key": None, "content_hash": None, "normalized_content_hash": None,
                  "annotation": {"status": "invalid"}, "translation": {"status": "invalid"},
                  "status": "invalid", "needs_ai": False, "needs_human_review": True,
                  "reasons": ["invalid_input"], "effective_tags": []}
        try:
            p = normalize(raw)
            key = p["problem_key"]
            result.update(problem_key=key, content_hash=p["content_hash"], normalized_content_hash=p["normalized_content_hash"])
            annotation_input, translation_input = semantic_inputs(p)
            for task, value in (("annotation", annotation_input), ("translation", translation_input)):
                result[task] = {"status": "pending", "input_semantic_hash": digest(value),
                                "task_key": digest({"task": task, "input": value, "policy": self.policies[task]}),
                                "policy": deepcopy(self.policies[task]), "existing_result": None, "needs_ai": False}
            view = self.views.get(key)
            if view:
                result.update(effective_tags=deepcopy(view["effective_tags"]), manual_overrides=deepcopy(view["manual_overrides"]),
                              label_review_status=view["review_status"])
            elif p["platform"] == "codeforces" and not p["rule_base"]["needs_ai"]:
                from label_pipeline import TAG_BY_ID
                result["effective_tags"] = [{"id": t, "name_zh": TAG_BY_ID[t]["name_zh"], "source": "cf_rule_mapping"}
                    for t in p["rule_base"]["specific_tag_ids"] + p["rule_base"]["provisional_tag_ids"]]
            if p["processing_status"] != "ready" or p["statement_status"] != "ok":
                for task in ("annotation", "translation"):
                    result[task].update(status="pending", reason="unreliable_statement")
                if translation_ready(p):
                    old = historical_problem(self.problems[key]) if key in self.problems else None
                    state, reason, source = self._translation(p, old, translation_input)
                    result['translation'].update(status=state, reason=reason, existing_result=source,
                        image_handling='preserve_local_images_translate_text_only')
            else:
                old = historical_problem(self.problems[key]) if key in self.problems else None
                for task, outcome in (("annotation", self._annotation(p, old, annotation_input, view)),
                                      ("translation", self._translation(p, old, translation_input))):
                    state, reason, source = outcome
                    result[task].update(status=state, reason=reason, existing_result=source)
                    if source and source.get("kind") == "annotation_cache":
                        result["effective_tags"] = source.get("effective_tags", [])
            for task in ("annotation", "translation"):
                records = self.cache.get((task, key), [])
                uncertain = [c for c in records if c["state"] in {"sent", "retry_wait", "received", "unknown_delivery", "failed"}]
                if self.blockers[task] or uncertain:
                    result[task].update(status="needs_review", reason="request_delivery_or_cache_audit_required",
                        request_states=sorted({c["state"] for c in uncertain}), global_blockers=sorted(self.blockers[task]))
                prior = [r for r in self.executions if r["problem_key"] == key and r["task_type"] == task
                         and (r["state"] in {"claimed", "dispatched", "uncertain", "blocked"}
                              or r["state"] == "completed" and result[task]["status"] not in {"reuse_existing", "not_required"})]
                if prior:
                    result[task].update(status="needs_review", reason="execution_recovery_or_review_required",
                                        execution_task_ids=sorted(r["task_id"] for r in prior))
                result[task]["needs_ai"] = result[task]["status"] == "needs_" + task
            states = [result[t]["status"] for t in ("annotation", "translation")]
            overall = ("needs_review" if "needs_review" in states else "pending" if "pending" in states else
                       "needs_both" if states == ["needs_annotation", "needs_translation"] else
                       "needs_annotation" if "needs_annotation" in states else
                       "needs_translation" if "needs_translation" in states else "reuse_existing")
            result.update(status=overall, needs_ai=any(result[t]["needs_ai"] for t in ("annotation", "translation")),
                          needs_human_review=overall in {"needs_review", "pending"},
                          effective_tags_are_current_input=result["annotation"]["status"] in {"reuse_existing", "not_required"},
                          reasons=[result[t]["reason"] for t in ("annotation", "translation")])
            check_sensitive(result)
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            # No raw exceptions/inputs in the output; no credentials or third-party statements are exported.
            key = result["problem_key"]
            try:
                check_sensitive({"problem_key": key})
            except ValueError:
                key = None
            return {"problem_key": key, "content_hash": None, "normalized_content_hash": None,
                    "status": "invalid", "needs_ai": False, "needs_human_review": True,
                    "annotation": {"status": "invalid", "needs_ai": False},
                    "translation": {"status": "invalid", "needs_ai": False},
                    "reasons": ["invalid_input_or_evidence"], "effective_tags": []}

    def plan(self, rows):
        selected, duplicates = {}, 0
        invalid = []
        for raw in rows:
            item = self.one(raw)
            key = item["problem_key"]
            if key is None:
                invalid.append(item)
            elif key in selected:
                duplicates += 1
                if selected[key] != item:
                    selected[key].update(status="invalid", needs_ai=False, needs_human_review=True,
                                         reasons=["conflicting_duplicate_identity"])
                    for task in ("annotation", "translation"):
                        selected[key][task] = {"status": "invalid", "needs_ai": False}
            else:
                selected[key] = item
        entries = [selected[k] for k in sorted(selected)] + invalid
        counts = Counter(x["status"] for x in entries)
        summary = {"total": len(entries), "duplicates": duplicates, "reuse_existing": counts["reuse_existing"],
                   "needs_annotation": sum(x["annotation"]["status"] == "needs_annotation" for x in entries),
                   "needs_translation": sum(x["translation"]["status"] == "needs_translation" for x in entries),
                   "needs_review": counts["needs_review"], "pending": counts["pending"], "invalid": counts["invalid"],
                   "annotation_reused": sum(x["annotation"]["status"] in {"reuse_existing", "not_required"} for x in entries),
                   "translation_reused": sum(x["translation"]["status"] in {"reuse_existing", "not_required"} for x in entries),
                   "estimated_api_tasks": sum(x[t].get("needs_ai", False) for x in entries for t in ("annotation", "translation")),
                   "real_api_calls": 0, "token_estimate": None, "cost_estimate": None}
        value = {"plan_version": VERSION, "mode": "offline_plan_only", "policies": self.policies,
                 "repository_generation": self.folder.name if self.folder else None,
                 "entries": entries, "summary": summary, "audit_warnings": sorted(set(self.warnings)),
                 "execution_supported": False}
        check_sensitive(value)
        return {"plan_id": digest(value), **value}


def write_plan(path, plan):
    """Publish a complete new file atomically, without an overwrite window (also on Windows)."""
    target = checked_path(path)
    if not target.is_relative_to(checked_path(OUTPUT_ROOT)) or target.suffix.lower() != ".json":
        raise ValueError("计划只能保存至 outputs/plans 下的新 JSON 文件")
    safe_relative(target.relative_to(checked_path(OUTPUT_ROOT)).as_posix())
    check_sensitive(plan)
    payload = (json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if target.exists():
        raise ValueError("拒绝覆盖已有计划")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".tmp-plan-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # link() fails if target exists; a partial JSON is never visible at the final name.
        os.link(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
