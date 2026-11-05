"""Sequential execution, conservative delivery semantics, rule/manual protection."""
import hashlib
import json
import random
import re
import time
from pathlib import Path

from label_pipeline import BASE, TAXONOMY, TAG_BY_ID, merge_one
from . import ADAPTER_VERSION, SCHEMA_VERSION, PROMPT_VERSION, RULE_VERSION
from .adapter import digest, load_inputs, human_confirmed
from .prompt import messages, SYSTEM
from .schema import SCHEMA, validate
from .client import APIClient, CallError
from .storage import Store, atomic_json, read_jsonl, now


def load_reviews(path):
    if not path:
        return {}
    result = {}
    for row in read_jsonl(path):
        if "reviewed" in row and not isinstance(row["reviewed"], bool):
            raise ValueError("reviewed must be a JSON boolean")
        key = row.get("problem_key")
        if not key or key in result:
            raise ValueError("Invalid/duplicate human review identity")
        result[key] = row
    return result


def preview(input_path, platform="all", limit=None, reviews_path=None):
    rows, errors, duplicates = load_inputs(input_path, platform, limit, load_reviews(reviews_path))
    for item in rows:
        base = item["rule_base"]
        status = ("human_protected" if human_confirmed(base) else "rule_only" if not base["needs_ai"]
                  else "ready_for_ai" if item["has_statement"] else "missing_statement")
        print(json.dumps({"problem_key": base["problem_key"], "preprocessing_status": status,
                          "content_hash": base["content_hash"], "raw_tags": base["raw_tags"]}, ensure_ascii=False))
    summary = {"mode": "dry_run", "platform": platform, "selected_count": len(rows),
               "duplicate_count": duplicates, "input_error_count": len(errors),
               "ready_for_ai": sum(x["rule_base"]["needs_ai"] and x["has_statement"] and not human_confirmed(x["rule_base"]) for x in rows),
               "api_calls": 0, "files_written": 0}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def profile_for(config, input_path, platform="all"):
    source_files = [BASE / "tag_taxonomy_v0.3.json", BASE / "cf_mapping_v0.3.json", BASE / "label_pipeline.py"]
    source_files += sorted((BASE / "annotation_api").glob("*.py"))
    return {"config": config.public(), "platform_filter": platform, "dataset_sha256": hashlib.sha256(Path(input_path).read_bytes()).hexdigest(),
            "taxonomy_version": TAXONOMY["version"], "rule_version": RULE_VERSION,
            "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION, "prompt_hash": digest(SYSTEM), "schema_hash": digest(SCHEMA),
            "implementation_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}}


def request_fingerprint(profile_id, item):
    return digest({"profile": profile_id, "identity": item["rule_base"]["problem_key"],
                   "content_hash": item["rule_base"]["content_hash"],
                   "annotation_input_hash": item["annotation_input_hash"], "messages": messages(item)})


def metadata(config, item, fingerprint, profile_id):
    return {"problem_key": item["rule_base"]["problem_key"], "platform": item["rule_base"]["platform"],
            "content_hash": item["rule_base"]["content_hash"], "annotation_input_hash": item["annotation_input_hash"],
            "request_fingerprint": fingerprint, "profile_id": profile_id,
            "provider": config.provider, "requested_model": config.model,
            "taxonomy_version": TAXONOMY["version"], "annotation_rule_version": RULE_VERSION,
            "prompt_version": PROMPT_VERSION, "human_review_status": "pending_review", "updated_at": now()}


def run(input_path, config, *, platform="all", limit=None, output=None, cache_root=None,
        resume=False, reviews_path=None, retry_failed=False, client=None, sleep=time.sleep,
        execute=False, plan=None, data_root=None):
    # The old output-scoped runner remains an injected-offline-client test harness only.
    # Real APIClient.call and the HTTP hook independently reject missing executor capabilities.
    if client is None or not getattr(client, "offline_transport", True):
        from problem_processing.adapter import read_problems
        from problem_processing.executor import execute_batch
        if reviews_path or retry_failed:
            raise ValueError("真实执行不允许旧重试或独立审核路径")
        values = read_problems(input_path)
        values = [r for r in values if platform == "all" or r.get("platform", str(r.get("problem_key", "")).split(":")[0]) == platform]
        return execute_batch(values, "annotation", root=data_root, config=config, execute=execute, plan=plan,
                             client=client, limit=limit)
    rows, input_errors, duplicates = load_inputs(input_path, platform, limit, load_reviews(reviews_path))
    profile = profile_for(config, input_path, platform)
    profile_id = digest(profile)
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", config.model)[:48] or "model"
    output = Path(output) if output else BASE / "outputs" / safe_model / profile_id
    cache_root = Path(cache_root) if cache_root else BASE / "cache"
    # Refuse source directories as destinations; explicit output is a run directory.
    if output.resolve().is_relative_to(BASE.resolve()) and not output.resolve().is_relative_to((BASE / "outputs").resolve()):
        raise ValueError("Inside the test package, output must be under outputs/")
    counters = {"selected_count": len(rows), "api_calls": 0, "cache_hits": 0,
                "success_count": 0, "failed_count": 0, "human_protected_count": 0,
                "rule_only_count": 0, "input_error_count": len(input_errors), "duplicate_count": duplicates}
    owned_client = False
    stopped = None
    with Store(output, cache_root, profile, profile_id, resume) as store:
        store.set_selection(rows)
        for error in input_errors:
            error = {**error, "error_id": digest(error), "api_call_status": "not_called"}
            store.append_once("errors.jsonl", error)
        try:
            for item in rows:
                base = item["rule_base"]
                fingerprint = request_fingerprint(profile_id, item)
                meta = metadata(config, item, fingerprint, profile_id)
                protected = store.protected(base["problem_key"])
                if protected or human_confirmed(base):
                    counters["human_protected_count"] += 1
                    store.save_merged({**base, **meta, "review_status": "human_confirmed",
                                       "human_review_status": "approved", "api_call_status": "not_called_human_protected",
                                       "usage": None, "error": None})
                    continue
                if not base["needs_ai"]:
                    counters["rule_only_count"] += 1
                    result = {**base, **meta, "human_review_status": "not_reviewed",
                              "api_call_status": "not_required", "usage": None, "error": None,
                              "prediction_origin": "rule_only", "model_prediction": None}
                    store.append_once("predictions.jsonl", result)
                    store.save_merged(result)
                    continue
                cached = store.load(fingerprint)
                if cached and cached["state"] == "failed" and retry_failed:
                    cached["state"] = "retry_requested"
                error_code = None
                if not item["has_statement"]:
                    error_code = "missing_statement"
                    cached = {"state": "failed", "attempts": [], "error_code": error_code}
                elif cached and cached["state"] in {"sent", "retry_wait"}:
                    # No response was durably committed. Delivery is uncertain.
                    cached["state"], cached["error_code"] = "unknown_delivery", "unknown_delivery"
                if cached and cached["state"] in {"failed", "unknown_delivery"}:
                    error_code = cached["error_code"]
                    counters["cache_hits"] += 1
                    if cached.get("fatal"):
                        stopped = error_code
                elif cached and cached["state"] in {"received", "success"}:
                    counters["cache_hits"] += 1
                else:
                    cached = {"state": "prepared", "attempts": (cached or {}).get("attempts", [])}
                    if client is None:
                        client, owned_client = APIClient(config), True
                    for attempt in range(config.max_retries + 1):
                        if counters["api_calls"]:
                            sleep(config.request_interval)
                        cached["state"] = "sent"
                        store.save(fingerprint, cached)
                        counters["api_calls"] += 1
                        try:
                            response = client.call(messages(item)).as_dict()
                        except CallError as exc:
                            cached["attempts"].append({"status": exc.code, "usage": None, "time": now(),
                                                       "http_status": exc.http_status, "elapsed_seconds": exc.elapsed_seconds})
                            error_code = exc.code
                            cached.update(state="unknown_delivery" if exc.unknown else "failed", error_code=exc.code,
                                          fatal=exc.fatal, http_status=exc.http_status, elapsed_seconds=exc.elapsed_seconds)
                            store.save(fingerprint, cached)
                            if exc.retryable and attempt < config.max_retries:
                                delay = max(2 ** attempt + random.random(), exc.retry_after or 0)
                                if delay <= 60:
                                    cached["state"] = "retry_wait"
                                    store.save(fingerprint, cached)
                                    sleep(delay)
                                    error_code = None
                                    continue
                            if exc.fatal:
                                stopped = exc.code
                            break
                        cached["attempts"].append({"status": "received", "usage": response["usage"], "time": now(),
                                                   "elapsed_seconds": response.get("elapsed_seconds")})
                        cached.update(state="received", response=response)
                        store.save(fingerprint, cached)  # Commit response before parsing/merging.
                        break
                if not error_code:
                    response = cached["response"]
                    error_code = ("refusal" if response["refused"] else "incomplete_output" if response["finish_reason"] != "stop"
                                  else "empty_output" if not response["content"] else None)
                    if not error_code:
                        try:
                            pred = validate(response["content"], item)
                            pred["model"] = response["model"]
                            merged = merge_one(base, pred)
                        except (ValueError, TypeError, KeyError):
                            error_code = "invalid_annotation"
                    if not error_code:
                        common = {**meta, "model": response["model"], "usage": response["usage"],
                                  "api_call_status": "success", "error": None, "request_id": response["request_id"],
                                  "request_elapsed_seconds": response.get("elapsed_seconds")}
                        prediction = {**pred, **common, "raw_tags": base["raw_tags"], "cf_exact_tag_ids": base["cf_exact_tag_ids"],
                                      "rule_provisional_tag_ids": base["provisional_tag_ids"],
                                      "cf_unresolved_hints": base["cf_unresolved_hints"],
                                      "specific_tag_names_zh": [TAG_BY_ID[x]["name_zh"] for x in pred["specific_tag_ids"]],
                                      "provisional_tag_names_zh": [TAG_BY_ID[x]["name_zh"] for x in pred["provisional_tag_ids"]],
                                      "evaluation_specific_tag_names_zh": merged["specific_tag_names_zh"],
                                      "evaluation_provisional_tag_names_zh": merged["provisional_tag_names_zh"],
                                      "evaluation_specific_tag_ids": merged["specific_tag_ids"],
                                      "evaluation_provisional_tag_ids": merged["provisional_tag_ids"],
                                      "prediction_origin": "ai", "review_status": merged["review_status"]}
                        result = {**merged, **common}
                        # Cache commits first: interrupted output writes can be replayed for free.
                        cached.update(state="success", prediction=prediction, merged=result)
                        store.save(fingerprint, cached)
                        store.append_once("predictions.jsonl", prediction)
                        store.save_merged(result)
                        counters["success_count"] += 1
                if error_code:
                    counters["failed_count"] += 1
                    response = cached.get("response", {})
                    cached.update(error_code=error_code, state="unknown_delivery" if error_code == "unknown_delivery" else "failed")
                    store.save(fingerprint, cached)
                    error = {**meta, "error_code": error_code, "error": {"code": error_code},
                             "api_call_status": "unknown_delivery" if error_code == "unknown_delivery" else "failed",
                             "usage": response.get("usage"), "attempt_count": len(cached["attempts"]),
                             "http_status": cached.get("http_status"),
                             "request_elapsed_seconds": response.get("elapsed_seconds", cached.get("elapsed_seconds"))}
                    error["error_id"] = digest({"request": fingerprint, "code": error_code, "attempt_count": len(cached["attempts"])})
                    store.append_once("errors.jsonl", error)
                    store.save_merged({**base, **error})
                if stopped:
                    break
        except BaseException:
            stopped = "interrupted_or_local_failure"
            raise
        finally:
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            responses_without_usage = 0
            uncertain = 0
            for item in rows:
                entry = store.load(request_fingerprint(profile_id, item)) or {}
                uncertain += entry.get("state") in {"sent", "unknown_delivery"}
                for attempt in entry.get("attempts", []):
                    if attempt["status"] != "received":
                        continue
                    if attempt["usage"] is None:
                        responses_without_usage += 1
                    else:
                        for field in usage:
                            usage[field] += attempt["usage"].get(field, 0) or 0
            summary = {**counters, "mode": "execute", "output": str(output.resolve()), "profile_id": profile_id,
                       "failure_rate": counters["failed_count"] / len(rows) if rows else None,
                       "not_processed_count": len(rows) - sum(counters[x] for x in ("success_count", "failed_count", "human_protected_count", "rule_only_count")),
                       "token_usage_known": usage, "responses_without_usage": responses_without_usage,
                       "unknown_delivery_count": uncertain, "stopped_reason": stopped, "updated_at": now()}
            atomic_json(output / "summary.json", summary)
            if owned_client:
                client.close()
    return summary
