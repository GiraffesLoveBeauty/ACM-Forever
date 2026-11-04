"""Sequential guarded execution, durable claims, response recovery and independent task identities."""
import json
import time
from copy import deepcopy
from pathlib import Path

from annotation_api import PROMPT_VERSION, RULE_VERSION
from annotation_api.adapter import adapt, digest
from annotation_api.client import APIClient, CallError, Response
from annotation_api.config import Config
from annotation_api.dispatch import dispatch, request_settings, wire_request
from annotation_api.storage import atomic_json, now
from label_pipeline import BASE, TAXONOMY, merge_one
from tag_management.storage import Journal
from .adapter import normalize
from .backup import check_sensitive, checked_path
from .execution_state import Ledger, Busy, read_record
from .planning import Planner, semantic_inputs, task_policies
from .repository import Repository, PROJECT_ROOT


def mock_config(model="mock-execution", **kwargs):
    values = dict(provider="compatible", base_url="https://offline.invalid/v1", model=model,
                  api_key="offline-mock-no-credential", max_retries=0, request_interval=0)
    return Config(**(values | kwargs))


def _redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        return {k.replace(secret, "[REDACTED]"): _redact(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secret) for v in value]
    return value


def task_identity(problem, task_type, config, *, mock=False):
    if task_type not in {"annotation", "translation"}:
        raise ValueError("未知任务类型")
    inputs = semantic_inputs(problem)[0 if task_type == "annotation" else 1]
    return {"version": 1, "problem_key": problem["problem_key"], "task_type": task_type,
            "input_semantic_hash": digest(inputs), "policy": task_policies()[task_type],
            "request_settings": request_settings(config), "mode": "mock" if mock else "live"}


def bind_plan(plan, task_type, settings):
    value = {k: deepcopy(v) for k, v in plan.items() if k != "plan_id"}
    value["execution_binding"] = {"task_type": task_type, "request_settings": deepcopy(settings)}
    check_sensitive(value)
    return {"plan_id": digest(value), **value}


class MockAnnotationClient:
    def __init__(self):
        self.calls = 0

    def call(self, messages, **kwargs):
        self.calls += 1
        p = json.loads(messages[1]["content"])
        result = {"problem_key": p["problem_key"], "content_hash": p["content_hash"], "specific_tag_ids": ["enumeration"],
                  "provisional_tag_ids": [], "resolved_cf_hints": [], "evidence_kind": "statement_only", "reason": "隔离 Mock：仅验证执行协议，不表示真实算法判断。"}
        return Response(json.dumps(result, ensure_ascii=False), "mock-annotation", {"total_tokens": 0}, "stop", elapsed_seconds=0)


class Executor:
    def __init__(self, root=None, *, config=None, mock=False, execute=False, client=None,
                 cache_roots=None, manifest_roots=None, checkpoint=None):
        if root is not None:
            checked_path(root)
        self.repo = Repository(root)
        self.ledger = Ledger(self.repo.root)
        self.config = config or (mock_config() if mock else None)
        self.mock, self.execute, self.client = mock, execute, client
        self.cache_roots, self.manifest_roots = cache_roots, manifest_roots
        self.checkpoint = checkpoint or (lambda stage, row: None)
        self.owned = False
        self.validated_plan = None
        if self.config:
            public = json.dumps(request_settings(self.config), ensure_ascii=False)
            if self.config.api_key in public:
                raise ValueError("公开请求参数中不得包含凭据")
            check_sensitive(request_settings(self.config))
        if mock and (root is None or self.repo.root.is_relative_to((PROJECT_ROOT / "data/labels").resolve())):
            raise ValueError("Mock 必须指定独立临时持久目录")
        if mock and isinstance(client, APIClient) and not client.offline_transport:
            raise ValueError("Mock 不允许使用真实网络客户端")
        if (execute or mock) and self.config is None:
            raise ValueError("执行需要显式配置")
        if execute and self.config.max_retries != 0:
            raise ValueError("安全执行要求应用重试为 0")
        # An entire root has one billing mode; Mock results must never become live evidence.
        if execute and any(r["identity"]["mode"] != "live" for r in self.ledger.records()):
            raise ValueError("真实执行不能使用 Mock 持久目录")
        if mock and any(r["identity"]["mode"] != "mock" for r in self.ledger.records()):
            raise ValueError("Mock 不能使用真实任务目录")

    def close(self):
        if self.owned:
            self.client.close()

    def planner(self, ignore=()):
        return Planner(self.repo.root, cache_roots=self.cache_roots, manifest_roots=self.manifest_roots,
                       ignore_execution_task_ids=ignore)

    def _fresh(self, p, ignore=()):
        return self.planner(ignore).one(p)

    @staticmethod
    def _stamp(entry, task_type):
        return digest({"problem_key": entry["problem_key"], "task": entry[task_type],
                       "manual": entry.get("manual_overrides") if task_type == "annotation" else None})

    def _prepare(self, p, task_type):
        if task_type == "annotation":
            from annotation_api.prompt import messages
            from annotation_api.schema import SCHEMA
            item = adapt(p)
            return messages(item), SCHEMA, "acm_tag_annotation", item
        from .translation import language_plan, prepare_request, SCHEMA
        prepared = prepare_request(p, language_plan(p))
        return prepared["messages"], SCHEMA, "acm_problem_translation", prepared

    def _source_current(self, p, task_type):
        from .planning import historical_problem
        catalog, _ = self.repo.snapshot()
        current = catalog.get(p["problem_key"])
        index = 0 if task_type == "annotation" else 1
        return current is not None and semantic_inputs(historical_problem(current))[index] == semantic_inputs(p)[index]

    def _view(self, p, task_type, status, **fields):
        return {"problem_key": p["problem_key"], "task_type": task_type, "status": status,
                "api_calls": 0, "real_api_calls": 0, **fields}

    def _finish(self, row):
        """Recovery consumes the saved response only. Never invokes a client."""
        task_id, task_type = row["task_id"], row["task_type"]
        p = normalize(row["input_problem"])
        response_file = self.ledger.path("responses", row["attempt_id"])
        envelope = self.ledger.artifact("responses", row["attempt_id"], row.get("response_sha256"))
        if envelope.get("task_id") != task_id or envelope.get("attempt_id") != row["attempt_id"]:
            raise ValueError("响应与任务身份不匹配")
        response = envelope["response"]
        if row["identity"]["policy"] != task_policies()[task_type]:
            raise ValueError("保存响应的任务策略已变化，需人工迁移")
        _, schema, _, prepared = self._prepare(p, task_type)
        result_file = self.ledger.path("results", task_id)
        if result_file.exists():
            artifact = self.ledger.artifact("results", task_id, row.get("result_sha256"))
            if artifact.get("task_id") != task_id or artifact.get("identity") != row["identity"]:
                raise ValueError("结果绑定损坏")
        else:
            if response.get("refused") or response.get("finish_reason") != "stop" or not response.get("content"):
                raise ValueError("模型响应拒绝、为空或被截断")
            if task_type == "annotation":
                from annotation_api.schema import validate
                prediction = validate(response["content"], prepared)
                prediction["model"] = response["model"]
                merged = merge_one(prepared["rule_base"], prediction)
                result = {**merged, "api_call_status": "success", "error": None,
                          "human_review_status": "not_reviewed", "taxonomy_version": TAXONOMY["version"],
                          "annotation_input_hash": prepared["annotation_input_hash"], "processing_policy": row["identity"]["policy"],
                          "annotation_rule_version": RULE_VERSION, "prompt_version": PROMPT_VERSION,
                          "requested_model": row["identity"]["request_settings"]["model"],
                          "provider": row["identity"]["request_settings"]["provider"]}
            else:
                from .translation import parse_translation, language_plan, TRANSLATION_VERSION, TRANSLATION_RESULT_MODE
                title, statement = parse_translation(response["content"], prepared)
                lang = language_plan(p)
                result = {"problem_key": p["problem_key"], "original_title": p["original_title"],
                          "original_statement": p["original_statement"], "source_links": p["source_links"],
                          "source_language": lang["source_language"], "target_language": "zh-CN", "title_zh": title,
                          "statement_zh": statement, "translation_status": "mock" if self.mock else "auto",
                          "translation_model": response["model"], "translation_version": TRANSLATION_VERSION,
                          "translation_validation_mode": TRANSLATION_RESULT_MODE,
                          "source_content_hash": p["content_hash"], "source_verified_hash": p["verified_content_hash"],
                          "processing_policy": row["identity"]["policy"], "fully_human_verified": False,
                          "output_mode": row["identity"]["request_settings"]["response_format"], "error": None}
                prediction = None
            result.update(model=response["model"], usage=response.get("usage"), elapsed_seconds=response.get("elapsed_seconds"),
                          request_id=response.get("request_id"), request_fingerprint=task_id, updated_at=now(),
                          execution_task_id=task_id, execution_request_settings=row["identity"]["request_settings"],
                          prediction_origin="mock" if self.mock else "ai")
            artifact = {"version": 1, "task_id": task_id, "identity": row["identity"], "prediction": prediction, "result": result}
            row["result_sha256"] = self.ledger.save_artifact("results", task_id, artifact)
            self.ledger.save(row)
        self.checkpoint("before_publish", row)
        self._publish(p, task_type, artifact["result"])
        self.ledger.transition(row, "completed", result_sha256=digest(artifact), response_sha256=digest(envelope))
        return self._view(p, task_type, "completed", task_id=task_id, result=artifact["result"])

    def _publish(self, p, task_type, result):
        folder = self.repo.current()
        problems, _ = self.repo.snapshot(folder)
        old = problems.get(p["problem_key"])
        if old:
            from .planning import historical_problem
            if semantic_inputs(historical_problem(old))[0 if task_type == "annotation" else 1] != semantic_inputs(p)[0 if task_type == "annotation" else 1]:
                raise ValueError("请求期间题面已改变，保留候选而不激活")
            # Never replace an already active valid result during recovery.
            fresh = self._fresh(p, [result["execution_task_id"]])
            if fresh[task_type]["status"] == "reuse_existing":
                return
        expected = folder.name if folder else ""
        if task_type == "annotation":
            self.repo.import_records([p], [result], expected_generation=expected)
        else:
            if old is None:
                self.repo.import_records([p], expected_generation=expected)
            with self.repo.lock.locked():
                current, _ = self.repo.snapshot()
                active = current[p["problem_key"]]
                if active["verified_content_hash"] != p["verified_content_hash"]:
                    raise ValueError("译文激活时原题已改变")
                with Journal(self.repo.root / "translations/writer.jsonl").locked():
                    fp = result["request_fingerprint"]
                    path = checked_path(self.repo.root / "translations/history" / (fp + ".json"))
                    if path.exists() and read_record(path) != result:
                        raise ValueError("不能覆盖翻译历史")
                    if not path.exists():
                        atomic_json(path, result)
                    if not self.mock:
                        path = checked_path(self.repo.root / "translations/current.json")
                        index = read_record(path) if path.exists() else {}
                        index[p["problem_key"]] = fp
                        atomic_json(path, index)

    def one(self, p, task_type, expected=None):
        if self.execute and (self.validated_plan is None or expected is None):
            raise ValueError("真实单题执行必须通过批量入口的绑定计划校验")
        if not (self.execute or self.mock):
            fresh = self._fresh(p)
            return self._view(p, task_type, "dry_run", planned_status=fresh[task_type]["status"],
                              needs_ai=fresh[task_type]["needs_ai"], needs_human_review=fresh["needs_human_review"])
        identity = task_identity(p, task_type, self.config, mock=self.mock)
        task_id = digest(identity)
        try:
            with self.ledger.locked(p["problem_key"], task_type):
                # A crashed owner can be recovered only while holding its released OS lock.
                # Record the pre-recovery view so this local state transition does not mask
                # unrelated durable changes since the batch plan was checked.
                before_recovery = self._fresh(p)
                recovered_claim = False
                for prior in self.ledger.records():
                    if prior["problem_key"] != p["problem_key"] or prior["task_type"] != task_type:
                        continue
                    if prior["state"] == "claimed":
                        # Acquiring the OS lock proves the previous owner no longer holds it, not that time expired.
                        self.ledger.transition(prior, "failed_before_dispatch", error="owner_exited_before_dispatch")
                        recovered_claim = True
                    elif prior["state"] in {"dispatched", "uncertain"}:
                        if self.ledger.path("responses", prior["attempt_id"]).exists():
                            if (prior["identity"]["input_semantic_hash"] != identity["input_semantic_hash"]
                                    or prior["identity"]["request_settings"] != identity["request_settings"]):
                                return self._view(p, task_type, "blocked", error="saved_response_input_or_settings_changed")
                            try:
                                recovered = self._finish(prior)
                                recovered["recovered_without_request"] = True
                                return recovered
                            except (ValueError, OSError, KeyError, TypeError):
                                self.ledger.transition(prior, "blocked", error="saved_response_requires_review")
                        elif prior["state"] == "dispatched":
                            self.ledger.transition(prior, "uncertain", error="no_durable_response")
                        return self._view(p, task_type, "uncertain", task_id=prior["task_id"], error="manual_delivery_check_required")
                    elif prior["state"] == "completed" and prior["task_id"] == task_id:
                        artifact = self.ledger.artifact("results", task_id, prior["result_sha256"])
                        latest = self._fresh(p, [task_id])
                        allowed = {"reuse_existing", "not_required"}
                        if self.mock and task_type == "translation":
                            allowed.add("needs_translation")  # Mock history is intentionally never a live index.
                        if latest[task_type]["status"] not in allowed:
                            return self._view(p, task_type, "blocked", task_id=task_id, error="completed_result_requires_review")
                        return self._view(p, task_type, "reuse_existing", task_id=task_id, result=artifact["result"],
                                          effective_tags=latest["effective_tags"])
                    elif prior["state"] == "completed" and prior["identity"]["input_semantic_hash"] == identity["input_semantic_hash"]:
                        if prior["identity"]["request_settings"] != identity["request_settings"]:
                            return self._view(p, task_type, "blocked", error="task_settings_changed_requires_review")
                    elif prior["state"] in {"uncertain", "blocked"}:
                        return self._view(p, task_type, "blocked", task_id=prior["task_id"], error="historical_task_blocked")
                fresh = self._fresh(p)
                if (recovered_claim and expected is not None
                        and self._stamp(before_recovery, task_type) == self._stamp(expected, task_type)):
                    expected = fresh
                status = fresh[task_type]["status"]
                if status in {"reuse_existing", "not_required"}:
                    if self.execute and status == "reuse_existing":
                        audit = self.planner()
                        source = fresh[task_type].get("existing_result") or {}
                        if task_type == "annotation":
                            saved = audit.automatic.get(p["problem_key"], {})
                            settings = saved.get("execution_request_settings")
                            if settings is None:
                                public = audit.profiles.get(saved.get("profile_id"), {}).get("config", {})
                                settings = {k: public.get(k) for k in request_settings(self.config)}
                        else:
                            fp = audit.translation_index.get(p["problem_key"])
                            saved = read_record(self.repo.root / "translations/history" / (fp + ".json")) if fp else {}
                            settings = saved.get("execution_request_settings")
                        authoritative = task_type == "annotation" and (not p["rule_base"].get("needs_ai", True)
                                                                 or fresh.get("label_review_status") == "verified")
                        if (source.get("kind") != "cf_rule_mapping" and not authoritative
                                and settings != request_settings(self.config)):
                            return self._view(p, task_type, "blocked", error="existing_request_settings_unverified_or_changed")
                    return self._view(p, task_type, "reuse_existing", existing_result=fresh[task_type].get("existing_result"),
                                      effective_tags=fresh["effective_tags"])
                if expected is not None and self._stamp(fresh, task_type) != self._stamp(expected, task_type):
                    return self._view(p, task_type, "blocked", error="stale_plan")
                if status != "needs_" + task_type:
                    return self._view(p, task_type, "blocked", error=fresh[task_type].get("reason", "not_ready"))
                # A corrected label set is authoritative; even an incomplete automatic baseline needs review first.
                manual = fresh.get("manual_overrides") or {}
                if task_type == "annotation" and (manual.get("added_tag_ids") or manual.get("removed_tag_ids") or manual.get("verified_fingerprint")):
                    return self._view(p, task_type, "blocked", error="human_labels_protected")
                # Stage only a new problem's immutable input/rule baseline, so even a first-request
                # crash has a complete catalog and can be included in the existing backup tool.
                folder = self.repo.current()
                problems, _ = self.repo.snapshot(folder)
                if p["problem_key"] not in problems:
                    self.repo.import_records([p], expected_generation=folder.name if folder else "")
                    fresh = self._fresh(p)
                    if fresh[task_type]["status"] != "needs_" + task_type:
                        return self._view(p, task_type, "blocked", error="state_changed_while_staging")
                row = self.ledger.claim(identity, p)
                calls = 0
                try:
                    self.checkpoint("claimed", row)
                    messages, schema, name, _ = self._prepare(p, task_type)
                    if self.client is None:
                        if self.mock:
                            from .translation import MockTranslationClient
                            self.client = MockAnnotationClient() if task_type == "annotation" else MockTranslationClient()
                        else:
                            self.client, self.owned = APIClient(self.config), True
                    current = self._fresh(p, [task_id])
                    if (not self._source_current(p, task_type) or self._stamp(current, task_type) != self._stamp(fresh, task_type)
                            or task_identity(p, task_type, self.config, mock=self.mock) != identity):
                        self.ledger.transition(row, "blocked", error="stale_plan")
                        return self._view(p, task_type, "blocked", error="stale_plan", task_id=task_id)
                    body = wire_request(self.config, messages, schema, name)
                    row["request_sha256"] = digest(body)
                    self.ledger.transition(row, "dispatched")
                    self.checkpoint("dispatched", row)
                    def validate():
                        saved = self.ledger.load(task_id)
                        if saved["state"] != "dispatched" or saved["attempt_id"] != row["attempt_id"]:
                            raise ValueError("任务许可失效")
                        if (not self._source_current(p, task_type)
                                or self._stamp(self._fresh(p, [task_id]), task_type) != self._stamp(fresh, task_type)
                                or task_identity(p, task_type, self.config, mock=self.mock) != identity):
                            raise ValueError("发送前持久状态或任务策略已变化")
                    with dispatch(self.config, body, validate):
                        validate()
                        calls = 1
                        response = self.client.call(messages, schema=schema, schema_name=name)
                    # Save full sanitized response before parsing or publication; recovery is free.
                    safe_response = _redact(response.as_dict(), self.config.api_key)
                    envelope = {"version": 1, "task_id": task_id, "attempt_id": row["attempt_id"], "response": safe_response}
                    row["response_sha256"] = self.ledger.save_artifact("responses", row["attempt_id"], envelope)
                    self.ledger.save(row)
                    self.checkpoint("response_saved", row)
                    outcome = self._finish(row)
                    outcome.update(api_calls=calls, real_api_calls=0 if self.mock or getattr(self.client, "offline_transport", False) else calls)
                    return outcome
                except BaseException as exc:
                    uncertain = row["state"] == "dispatched" and (not isinstance(exc, CallError) or exc.unknown)
                    if isinstance(exc, ValueError) and row.get("response_sha256"):
                        uncertain = False
                    if row["state"] == "claimed":
                        self.ledger.transition(row, "failed_before_dispatch", error="local_preparation_failed")
                    elif row["state"] == "dispatched":
                        codes = {"unknown_delivery", "rate_limit", "quota_exhausted", "api_configuration_error", "executor_required"}
                        self.ledger.transition(row, "uncertain" if uncertain else "blocked",
                            error=exc.code if isinstance(exc, CallError) and exc.code in codes else "response_or_local_failure",
                            http_status=exc.http_status if isinstance(exc, CallError) else None,
                            elapsed_seconds=exc.elapsed_seconds if isinstance(exc, CallError) else None)
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    return self._view(p, task_type, row["state"], task_id=task_id, error=row.get("error"), api_calls=calls,
                                      real_api_calls=0 if self.mock or getattr(self.client, "offline_transport", False) else calls)
        except Busy:
            return self._view(p, task_type, "blocked", task_id=task_id, error="task_already_running")


def execute_batch(rows, task_type, *, root=None, config=None, execute=False, mock=False, client=None, plan=None,
                  limit=None, cache_roots=None, manifest_roots=None, checkpoint=None):
    if task_type not in {"annotation", "translation"} or (execute and mock):
        raise ValueError("执行模式或任务类型错误")
    if limit is not None and limit < 1:
        raise ValueError("limit 必须大于零")
    executor = Executor(root, config=config, mock=mock, execute=execute, client=client, cache_roots=cache_roots,
                        manifest_roots=manifest_roots, checkpoint=checkpoint)
    try:
        source = rows[:limit] if limit else rows
        planner = executor.planner()
        live_plan = planner.plan(source)
        if execute and plan is None:
            raise ValueError("真实执行必须提供已核验且绑定模型参数的计划文件")
        if plan is not None:
            supplied = read_record(plan) if isinstance(plan, (str, Path)) else deepcopy(plan)
            if supplied.get("plan_id") != digest({k: v for k, v in supplied.items() if k != "plan_id"}):
                raise ValueError("计划摘要损坏")
            expected_binding = {"task_type": task_type, "request_settings": request_settings(executor.config)} if executor.config else None
            binding = supplied.get("execution_binding")
            if (execute and binding != expected_binding) or (binding and binding != expected_binding):
                raise ValueError("计划模型或请求参数不匹配")
            unbound = {k: v for k, v in supplied.items() if k not in {"plan_id", "execution_binding"}}
            if digest(unbound) != live_plan["plan_id"]:
                raise ValueError("处理计划已过期，请重新生成")
            executor.validated_plan = supplied["plan_id"]
        entries = {e["problem_key"]: e for e in live_plan["entries"] if e["problem_key"]}
        results, seen = [], set()
        for raw in source:
            try:
                p = normalize(raw)
                check_sensitive(p)
                if p["problem_key"] in seen:
                    continue
                seen.add(p["problem_key"])
                expected = entries[p["problem_key"]]
                if expected["status"] == "invalid":
                    raise ValueError("同批题目身份冲突")
                result = executor.one(p, task_type, expected)
            except (ValueError, OSError, KeyError, TypeError):
                result = {"problem_key": None, "task_type": task_type, "status": "blocked", "error": "input_or_storage_invalid",
                          "api_calls": 0, "real_api_calls": 0}
            results.append(result)
            if result.get("api_calls") and executor.config and executor.config.request_interval:
                time.sleep(executor.config.request_interval)
        return {"mode": "mock" if mock else "execute" if execute else "dry_run", "task_type": task_type,
                "selected_count": len(results), "planned_ai_tasks": sum(e[task_type]["needs_ai"] for e in entries.values()),
                "completed": sum(r["status"] == "completed" for r in results),
                "reused": sum(r["status"] == "reuse_existing" for r in results),
                "blocked": sum(r["status"] in {"blocked", "uncertain", "failed_before_dispatch"} for r in results),
                "api_calls": sum(r["api_calls"] for r in results), "real_api_calls": sum(r["real_api_calls"] for r in results),
                "results": results}
    finally:
        executor.close()
